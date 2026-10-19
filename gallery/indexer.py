"""Incremental directory enumeration. A failed enumeration never implies deletion."""

import contextlib
import os
import stat as stat_module
import threading
import time
from pathlib import Path

from gallery.access import Access
from gallery.catalog import image_sort_key, new_id, path_key
from gallery.config import IMG_EXT
from gallery.jobs import Cancelled


def identity(stat):
    return f'{stat.st_dev}:{stat.st_ino}' if stat.st_ino else None


class Indexer:
    def __init__(self, catalog, events, excluded=()):
        self.catalog, self.events = catalog, events
        self.access = Access(catalog)
        self.excluded = {Path(p).resolve() for p in excluded}
        self.locks = {}
        self.lock = threading.Lock()

    def _upsert_directory(self, db, library_id, rel, parent, group_id, stat):
        key, file_identity = path_key(rel), identity(stat)
        row = db.execute('SELECT * FROM directories WHERE library_id=? AND path_key=?',
                         (library_id, key)).fetchone()
        if not row and file_identity:
            row = db.execute('SELECT * FROM directories WHERE library_id=? AND identity=? LIMIT 1',
                             (library_id, file_identity)).fetchone()
        directory_id = row['id'] if row else new_id()
        group_id = group_id or directory_id
        name = Path(rel).name if rel else self.catalog.entity('libraries', library_id)['name']
        db.execute('INSERT INTO directories(id,library_id,parent_id,group_id,rel,path_key,name,sort_key,identity) '
                   'VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET parent_id=excluded.parent_id,'
                   'group_id=excluded.group_id,rel=excluded.rel,path_key=excluded.path_key,name=excluded.name,'
                   'sort_key=excluded.sort_key,identity=excluded.identity,present=1,error=NULL',
                   (directory_id, library_id, parent, group_id, rel, key, name, key, file_identity))
        return directory_id, group_id

    def _package(self, db, library_id, group_id, directory_id, name, loose=False):
        row = db.execute('SELECT id FROM packages WHERE group_id=? AND directory_id=?',
                         (group_id, directory_id)).fetchone()
        package_id = row['id'] if row else new_id()
        db.execute('INSERT INTO packages(id,library_id,group_id,directory_id,name,sort_key,loose) '
                   'VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,sort_key=excluded.sort_key',
                   (package_id, library_id, group_id, directory_id, name, name.lower(), int(loose)))
        return package_id

    def scan(self, context, payload):
        library_id = payload['library_id']
        with self.exclusive(context, library_id):
            try:
                return self._scan(context, payload)
            except Cancelled:
                self.catalog.execute("UPDATE libraries SET scan_status='interrupted' WHERE id=?", (library_id,))
                raise

    @contextlib.contextmanager
    def exclusive(self, context, library_id):
        with self.lock:
            lock = self.locks.setdefault(library_id, threading.Lock())
        while not lock.acquire(timeout=.1):
            context.check()
        try:
            yield
        finally:
            lock.release()

    def _scan(self, context, payload):
        library_id = payload['library_id']
        library = self.catalog.entity('libraries', library_id)
        root = Path(library['path'])
        subtree = payload.get('directory_id')
        directory = self.catalog.entity('directories', subtree) if subtree else None
        if directory and directory['library_id'] != library_id:
            raise ValueError('Directory belongs to another library')
        self.catalog.execute("UPDATE libraries SET scan_status='scanning',error=NULL WHERE id=?", (library_id,))
        try:
            with context.io(root):
                root_stat = root.stat()
            if not root.is_dir():
                raise OSError('Library root is not a directory')
        except OSError as exc:
            self.catalog.execute("UPDATE libraries SET online=0,scan_status='offline',error=? WHERE id=?",
                                 (str(exc), library_id))
            self.events.publish('catalog', {'library_id': library_id})
            return {'online': False}
        self.catalog.execute('UPDATE libraries SET online=1 WHERE id=?', (library_id,))
        with self.catalog.write() as db:
            root_id, _ = self._upsert_directory(db, library_id, '', None, None, root_stat)
            root_pkg = self._package(db, library_id, root_id, root_id, '', True)
        if directory and directory['rel']:
            package = self.catalog.one('SELECT package_id FROM files WHERE directory_id=? LIMIT 1', (subtree,))
            pkg = self.catalog.one('SELECT id FROM packages WHERE directory_id=? AND loose=0', (subtree,))
            start_pkg = pkg['id'] if pkg else package['package_id'] if package else None
            if start_pkg is None:
                directory = None
        if directory and directory['rel']:
            stack = [(directory['rel'], directory['id'], directory['group_id'], start_pkg)]
        else:
            stack = [('', root_id, root_id, root_pkg)]
        visited = failed = files_seen = 0
        while stack:
            context.check()
            rel, directory_id, group_id, package_id = stack.pop()
            base = root / rel
            try:
                with context.io(base):
                    base = self.access.path({'library_id': library_id, 'rel': rel}, allow_root=True)
                    directory_stat = base.stat()
                old_directory = self.catalog.entity('directories', directory_id)
                if not payload.get('force', False) and old_directory['mtime_ns'] == directory_stat.st_mtime_ns:
                    for child in self.catalog.rows('SELECT * FROM directories WHERE parent_id=? AND present=1', (directory_id,)):
                        if not rel:
                            child_pkg = self.catalog.one('SELECT id FROM packages WHERE directory_id=? AND loose=1', (child['id'],))['id']
                        elif directory_id == group_id:
                            child_pkg = self.catalog.one('SELECT id FROM packages WHERE directory_id=? AND loose=0', (child['id'],))['id']
                        else:
                            child_pkg = package_id
                        stack.append((child['rel'], child['id'], child['group_id'], child_pkg))
                    visited += 1
                    context.update(current=rel)
                    continue
                with context.io(base):
                    entries = os.scandir(base)
                with entries:
                    items = []
                    while True:
                        with context.io(base):
                            entry = next(entries, None)
                            if entry is None:
                                break
                            if (not rel and entry.name.startswith('.') and entry.is_dir(follow_symlinks=False)
                                    or Path(entry.path).resolve() in self.excluded):
                                continue
                            if entry.is_symlink() or (hasattr(os.path, 'isjunction') and os.path.isjunction(entry.path)):
                                items.append((entry.name, False, os.lstat(entry.path)))
                                continue
                            # DirEntry.stat on Windows reports st_ino=0; os.stat exposes the NTFS file ID.
                            stat = os.stat(entry.path, follow_symlinks=False)
                            items.append((entry.name, entry.is_dir(follow_symlinks=False), stat))
            except (OSError, ValueError) as exc:
                failed += 1
                self.catalog.execute('UPDATE directories SET error=? WHERE id=?', (str(exc), directory_id))
                continue
            seen_dirs, seen_files = set(), set()
            group_rel = self.catalog.entity('directories', group_id)['rel']
            known_paths = {row['path_key'] for row in self.catalog.rows(
                'SELECT path_key FROM files WHERE directory_id=?', (directory_id,))}
            hard_links = set()
            for name, is_dir, stat in items:
                child_rel = f'{rel}/{name}' if rel else name
                if is_dir or path_key(child_rel) in known_paths or not identity(stat):
                    continue
                candidates = self.catalog.rows('SELECT rel FROM files WHERE library_id=? AND identity=? LIMIT 2',
                                               (library_id, identity(stat)))
                if len(candidates) == 1:
                    with context.io(root):
                        if (root / candidates[0]['rel']).exists():
                            hard_links.add(name)
            with self.catalog.write() as db:
                for name, is_dir, stat in items:
                    child_rel = f'{rel}/{name}' if rel else name
                    if is_dir:
                        child_group = None if not rel else group_id
                        child_id, child_group = self._upsert_directory(
                            db, library_id, child_rel, directory_id, child_group, stat)
                        if not rel:
                            child_pkg = self._package(db, library_id, child_id, child_id, '', True)
                        elif directory_id == group_id:
                            child_pkg = self._package(db, library_id, group_id, child_id, name)
                        else:
                            child_pkg = package_id
                        seen_dirs.add(child_id)
                        stack.append((child_rel, child_id, child_group, child_pkg))
                    else:
                        file_id = self._file(db, library_id, directory_id, group_id, package_id,
                                             child_rel, stat, group_rel, name not in hard_links)
                        seen_files.add(file_id)
                        files_seen += 1
                for row in db.execute('SELECT id FROM files WHERE directory_id=? AND present=1', (directory_id,)):
                    if row['id'] not in seen_files:
                        db.execute('UPDATE files SET present=0 WHERE id=?', (row['id'],))
                missing = [row['id'] for row in db.execute(
                    'SELECT id FROM directories WHERE parent_id=? AND present=1', (directory_id,))
                    if row['id'] not in seen_dirs]
                for removed in missing:
                    self.mark_missing(db, removed)
                db.execute('UPDATE directories SET error=NULL,present=1,mtime_ns=? WHERE id=?',
                           (directory_stat.st_mtime_ns, directory_id))
                db.execute('UPDATE libraries SET revision=revision+1 WHERE id=?', (library_id,))
                if not stack or stack[-1][2] != group_id:
                    self.catalog.refresh_group(db, group_id)
            visited += 1
            context.update(progress=files_seen, current=rel)
            if visited % 20 == 0:
                self.events.publish('catalog', {'library_id': library_id})
        self.catalog.execute('UPDATE libraries SET scan_status=?,last_scan=? WHERE id=?',
                             ('partial' if failed else 'ready', time.time(), library_id))
        self.events.publish('catalog', {'library_id': library_id})
        context.update(progress=files_seen, current='', force=True)
        return {'directories': visited, 'files': files_seen, 'failed_directories': failed, 'online': True}

    @staticmethod
    def mark_missing(db, directory_id):
        ids = [r[0] for r in db.execute('WITH RECURSIVE sub(id) AS (SELECT ? UNION ALL '
                                       'SELECT d.id FROM directories d JOIN sub ON d.parent_id=sub.id) '
                                       'SELECT id FROM sub', (directory_id,))]
        db.executemany('UPDATE directories SET present=0 WHERE id=?', [(i,) for i in ids])
        db.executemany('UPDATE files SET present=0 WHERE directory_id=?', [(i,) for i in ids])

    @staticmethod
    def _file(db, library_id, directory_id, group_id, package_id, rel, stat, group_rel='', allow_identity_move=True):
        key, file_identity = path_key(rel), identity(stat)
        row = db.execute('SELECT * FROM files WHERE library_id=? AND path_key=?', (library_id, key)).fetchone()
        if not row and file_identity and allow_identity_move:
            matches = db.execute('SELECT * FROM files WHERE library_id=? AND identity=?',
                                 (library_id, file_identity)).fetchall()
            if len(matches) == 1:
                row = matches[0]
        file_id = row['id'] if row else new_id()
        migrated_unchanged = (row and row['mtime_ns'] == 0 and row['size'] == stat.st_size
                              and row['hash_mtime_ns'] is not None
                              and row['hash_mtime_ns'] // 10**9 == stat.st_mtime_ns // 10**9)
        changed = row and not migrated_unchanged and (row['size'] != stat.st_size or row['mtime_ns'] != stat.st_mtime_ns)
        if changed:
            db.execute('UPDATE files SET width=NULL,height=NULL,animated=NULL,error=NULL,phash=NULL,'
                       'hash_version=NULL,hash_mtime_ns=NULL WHERE id=?', (file_id,))
        db.execute('INSERT INTO files(id,library_id,directory_id,group_id,package_id,rel,path_key,name,sort_key,'
                   'identity,size,mtime_ns,is_image) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET '
                   'directory_id=excluded.directory_id,group_id=excluded.group_id,package_id=excluded.package_id,'
                   'rel=excluded.rel,path_key=excluded.path_key,name=excluded.name,sort_key=excluded.sort_key,'
                   'identity=excluded.identity,size=excluded.size,mtime_ns=excluded.mtime_ns,'
                   'is_image=excluded.is_image,present=1',
                   (file_id, library_id, directory_id, group_id, package_id, rel, key, Path(rel).name,
                    image_sort_key(rel[len(group_rel) + 1:] if group_rel else rel), file_identity,
                    stat.st_size, stat.st_mtime_ns, int(Path(rel).suffix.lower() in IMG_EXT
                                                       and not stat_module.S_ISLNK(stat.st_mode))))
        return file_id
