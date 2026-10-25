"""Notifications request reconciliation; periodic scans cover events missed while closed."""

import logging
import threading

from watchfiles import watch

from gallery.catalog import path_key
from gallery.jobs import Busy


class Watcher:
    def __init__(self, catalog, tasks, enabled=True, excluded=()):
        self.catalog, self.tasks, self.enabled = catalog, tasks, enabled
        self.stop_event = threading.Event()
        self.threads = {}
        self.lock = threading.Lock()
        self.excluded = excluded

    def add(self, library):
        if not self.enabled:
            return
        with self.tasks.lock, self.lock:
            current = self.catalog.entity('libraries', library['id'])
            if (self.stop_event.is_set() or not current or not current['managed']
                    or current['path_key'] != path_key(library['path']) or library['id'] in self.threads):
                return
            stopped = threading.Event()
            thread = threading.Thread(target=self._watch, args=(current, stopped), daemon=True, name='gallery-watch')
            self.threads[library['id']] = (thread, stopped)
            thread.start()

    def remove(self, library_id):
        # Do not join while the lifecycle caller holds the task lock: an old notification
        # might be waiting for that lock. The signal also wakes an offline root's wait.
        with self.lock:
            watched = self.threads.pop(library_id, None)
            if watched:
                watched[1].set()

    def _watch(self, library, stopped):
        from pathlib import Path
        root = Path(library['path'])
        while not stopped.is_set():
            try:
                if not root.is_dir():
                    stopped.wait(5)
                    continue
                def include(_change, value):
                    path = Path(value)
                    try:
                        parts = path.relative_to(root).parts
                        if parts and parts[0].startswith('.') and (root / parts[0]).is_dir():
                            return False
                    except ValueError:
                        return False
                    return not any(path == excluded or excluded in path.parents for excluded in self.excluded)
                for changes in watch(root, stop_event=stopped, debounce=500, step=100,
                                     raise_interrupt=False, watch_filter=include):
                    directories = set()
                    for _change, path in changes:
                        try:
                            rel = Path(path).parent.relative_to(root).as_posix()
                        except ValueError:
                            continue
                        if rel == '.':
                            rel = ''
                        while True:
                            row = self.catalog.one('SELECT id FROM directories WHERE library_id=? AND path_key=?',
                                                   (library['id'], rel.lower()))
                            if row:
                                directories.add(row['id'])
                                break
                            if not rel:
                                break
                            rel = rel.rpartition('/')[0]
                    if len(directories) > 32:
                        self._submit(library)
                    else:
                        for directory_id in directories:
                            self._submit(library, directory_id)
            except OSError:
                logging.getLogger(__name__).exception('Directory watcher interrupted')
                self._submit(library)
                stopped.wait(5)

    def _submit(self, library, directory_id=None):
        payload = {'library_id': library['id'], 'force': True}
        if directory_id:
            payload['directory_id'] = directory_id
        try:
            with self.tasks.lock:
                current = self.catalog.entity('libraries', library['id'])
                if not current or not current['managed'] or current['path_key'] != library['path_key']:
                    return
                self.tasks.submit('scan', payload, trigger='watcher')
        except Busy:
            pass  # Periodic reconciliation also covers notification overflow.

    def stop(self):
        self.stop_event.set()
        with self.lock:
            watched = list(self.threads.values())
            for _thread, stopped in watched:
                stopped.set()
        for thread, _stopped in watched:
            thread.join(timeout=3)
