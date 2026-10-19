"""Notifications request reconciliation; periodic scans cover events missed while closed."""

import logging
import threading

from watchfiles import watch

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
        with self.lock:
            if library['id'] in self.threads:
                return
            thread = threading.Thread(target=self._watch, args=(library,), daemon=True, name='gallery-watch')
            self.threads[library['id']] = thread
            thread.start()

    def _watch(self, library):
        from pathlib import Path
        root = Path(library['path'])
        while not self.stop_event.is_set():
            try:
                if not root.is_dir():
                    self.stop_event.wait(5)
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
                for changes in watch(root, stop_event=self.stop_event, debounce=500, step=100,
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
                        self._submit(library['id'])
                    else:
                        for directory_id in directories:
                            self._submit(library['id'], directory_id)
            except OSError:
                logging.getLogger(__name__).exception('Directory watcher interrupted')
                self._submit(library['id'])
                self.stop_event.wait(5)

    def _submit(self, library_id, directory_id=None):
        payload = {'library_id': library_id, 'force': True}
        if directory_id:
            payload['directory_id'] = directory_id
        try:
            self.tasks.submit('scan', payload)
        except Busy:
            pass  # Periodic reconciliation also covers notification overflow.

    def stop(self):
        self.stop_event.set()
        for thread in self.threads.values():
            thread.join(timeout=3)
