"""Library registration changes preserve catalog identity and never move source files."""

from pathlib import Path

from gallery.catalog import path_key


class LibraryBusy(ValueError):
    """A library cannot change its root while its existing jobs can still use it."""


class Libraries:
    def __init__(self, catalog, tasks, watcher, events):
        self.catalog, self.tasks, self.watcher, self.events = catalog, tasks, watcher, events

    def get(self, library_id):
        library = self.catalog.entity('libraries', library_id)
        if not library or not library['managed']:
            raise FileNotFoundError('Library is not managed')
        return library

    def _idle(self, library):
        active = self.catalog.tasks(0, 1, library_id=library['id'], active=True)['total']
        # Legacy import starts with a root path, before it has a library ID.
        imports = self.catalog.tasks(0, 500, kind='migrate', active=True)['items']
        if active or any(path_key(Path(task['payload']['root']).resolve()) == library['path_key'] for task in imports):
            raise LibraryBusy('此图库还有未结束的任务，请等待完成或在后台任务中取消后重试')

    def add(self, path, name=None):
        with self.tasks.lock:
            self.tasks.ensure_capacity()
            library = self.catalog.add_library(path, name)
            if not library['managed']:
                root = self.catalog.local_root(library['path'])
                self.catalog.check_library_root(root, library['id'])
                self.catalog.execute("UPDATE libraries SET managed=1,revision=revision+1,scan_status='pending' "
                                     'WHERE id=?', (library['id'],))
                library = self.get(library['id'])
            self.tasks.submit('scan', {'library_id': library['id'], 'force': True})
        self.watcher.add(library)
        self.events.publish('catalog', {'library_id': library['id']})
        return library

    def rename(self, library_id, name):
        with self.tasks.lock:
            self.get(library_id)
            with self.catalog.write() as db:
                db.execute('UPDATE libraries SET name=?,revision=revision+1 WHERE id=?', (name, library_id))
                db.execute("UPDATE directories SET name=? WHERE library_id=? AND rel=''", (name, library_id))
            library = self.get(library_id)
        self.events.publish('catalog', {'library_id': library_id})
        return library

    def reconnect(self, library_id, path):
        with self.tasks.lock:
            self._idle(self.get(library_id))
            self.tasks.ensure_capacity()
            root = self.catalog.local_root(path)
            self.catalog.check_library_root(root, library_id)
            self.catalog.execute("UPDATE libraries SET path=?,path_key=?,online=1,revision=revision+1,"
                                 "scan_status='pending',last_scan=NULL,error=NULL WHERE id=?",
                                 (str(root), path_key(root), library_id))
            self.watcher.remove(library_id)
            task = self.tasks.submit('scan', {'library_id': library_id, 'force': True})
            library = self.get(library_id)
        self.watcher.add(library)
        self.events.publish('catalog', {'library_id': library_id})
        return task

    def remove(self, library_id):
        with self.tasks.lock:
            self._idle(self.get(library_id))
            self.catalog.execute('UPDATE libraries SET managed=0,revision=revision+1 WHERE id=?', (library_id,))
            self.watcher.remove(library_id)
        self.events.publish('catalog', {'library_id': library_id})
