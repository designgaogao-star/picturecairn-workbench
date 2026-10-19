"""The catalog owns persistence. File-system work never happens inside its transactions."""

import contextlib
import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path


def new_id():
    return uuid.uuid4().hex


def path_key(value):
    return str(value).replace('\\', '/').lower()


def category(name):
    for prefix in ('R16', 'R18', '非R18'):
        if name.startswith(f'[{prefix}]'):
            return prefix
    return '其他'


def image_sort_key(relative_in_group):
    relative = str(relative_in_group).replace('\\', '/')
    album = relative.split('/', 1)[0] if '/' in relative else ''
    return album.lower() + '\x1f' + relative.lower()


class Catalog:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        with self.write() as db:
            db.execute('PRAGMA journal_mode=WAL')
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version > 1:
                raise RuntimeError('Catalog was created by a newer application')
            if version == 0:
                sql = (Path(__file__).parent / 'sql' / '001_catalog.sql').read_text(encoding='utf-8')
                db.executescript('BEGIN IMMEDIATE;\n' + sql + '\nPRAGMA user_version=1;\nCOMMIT;')

    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA synchronous=NORMAL')
        return db

    @contextlib.contextmanager
    def write(self):
        with self.lock, contextlib.closing(self.connect()) as db, db:
            yield db

    def rows(self, sql, args=()):
        with contextlib.closing(self.connect()) as db:
            return [dict(row) for row in db.execute(sql, args)]

    def one(self, sql, args=()):
        rows = self.rows(sql, args)
        return rows[0] if rows else None

    def execute(self, sql, args=()):
        with self.write() as db:
            db.execute(sql, args)

    def revision(self, library_id):
        row = self.one('SELECT revision FROM libraries WHERE id=?', (library_id,))
        return row['revision'] if row else 0

    def bump(self, library_id):
        self.execute('UPDATE libraries SET revision=revision+1 WHERE id=?', (library_id,))

    def entity(self, table, entity_id):
        if table not in {'libraries', 'directories', 'packages', 'files'}:
            raise ValueError(table)
        return self.one(f'SELECT * FROM {table} WHERE id=?', (entity_id,))

    def libraries(self):
        return self.rows('SELECT * FROM libraries ORDER BY name COLLATE NOCASE,id')

    def add_library(self, path, name=None):
        path = Path(path).resolve(strict=True)
        if not path.is_dir() or not path.drive and str(path).startswith('//'):
            raise ValueError('Select a local directory')
        if str(path).startswith('\\\\'):
            raise ValueError('Network libraries are not supported')
        key = path_key(path)
        existing = self.one('SELECT * FROM libraries WHERE path_key=?', (key,))
        if existing:
            return existing
        for lib in self.libraries():
            other = Path(lib['path'])
            if path.is_relative_to(other) or other.is_relative_to(path):
                raise ValueError('Library roots must not overlap')
        library_id = new_id()
        self.execute('INSERT INTO libraries(id,name,path,path_key) VALUES(?,?,?,?)',
                     (library_id, name or path.name or str(path), str(path), key))
        return self.entity('libraries', library_id)

    def page(self, select, where, args, order, offset, limit, library_id):
        total = self.one(f'SELECT COUNT(*) n FROM ({select} {where})', args)['n']
        rows = self.rows(f'{select} {where} ORDER BY {order} LIMIT ? OFFSET ?', (*args, limit, offset))
        return {'items': rows, 'total': total, 'offset': offset, 'limit': limit,
                'revision': self.revision(library_id)}

    def groups(self, library_id, offset, limit, state=None, category_filter=None):
        where = ('WHERE d.library_id=? AND d.present=1 AND (d.id=d.group_id) '
                 'AND (d.rel<>\'\' OR EXISTS(SELECT 1 FROM files f WHERE f.group_id=d.id AND f.present=1 AND f.is_image=1))')
        args = [library_id]
        if state is not None:
            where += " AND COALESCE(r.state,'none')=?"
            args.append(state)
        if category_filter == '其他':
            where += " AND d.name NOT LIKE '[R16]%' AND d.name NOT LIKE '[R18]%' AND d.name NOT LIKE '[非R18]%'"
        elif category_filter:
            where += ' AND d.name LIKE ?'
            args.append(f'[{category_filter}]%')
        select = """SELECT d.*,COALESCE(r.state,'none') state,r.image_id resume_image_id,
          (SELECT COUNT(*) FROM files f WHERE f.group_id=d.id AND f.present=1 AND f.is_image=1) image_count,
          (SELECT COALESCE(SUM(size),0) FROM files f WHERE f.group_id=d.id AND f.present=1) bytes
          FROM directories d LEFT JOIN review r ON r.group_id=d.id"""
        result = self.page(select, where, args, 'bytes DESC,d.sort_key,d.id', offset, limit, library_id)
        for row in result['items']:
            row['category'] = category(row['name'])
        return result

    def packages(self, group_id, offset, limit):
        group = self.entity('directories', group_id)
        select = """SELECT p.*,d.rel,d.present,
          (SELECT COUNT(*) FROM files f WHERE f.package_id=p.id AND f.present=1 AND f.is_image=1) image_count,
          (SELECT id FROM files f WHERE f.package_id=p.id AND f.present=1 AND f.is_image=1
           ORDER BY f.sort_key,f.id LIMIT 1) cover_id
          FROM packages p JOIN directories d ON p.directory_id=d.id"""
        return self.page(select, 'WHERE p.group_id=? AND d.present=1 AND EXISTS('
                         'SELECT 1 FROM files f WHERE f.package_id=p.id AND f.present=1 AND f.is_image=1)', [group_id],
                         'p.sort_key,p.id', offset, limit, group['library_id'])

    def images(self, package_id, offset, limit):
        pkg = self.entity('packages', package_id)
        return self.page('SELECT id,library_id,group_id,package_id,rel,name,size,mtime_ns,width,height,animated,error '
                         'FROM files', 'WHERE package_id=? AND is_image=1 AND present=1', [package_id],
                         'sort_key,id', offset, limit, pkg['library_id'])

    def save_review(self, group_id, state=None, image_id=None):
        with self.write() as db:
            db.execute('INSERT OR IGNORE INTO review(group_id,updated) VALUES(?,?)', (group_id, time.time()))
            if state is not None:
                db.execute('UPDATE review SET state=?,updated=? WHERE group_id=?', (state, time.time(), group_id))
            if image_id is not None:
                db.execute('UPDATE review SET image_id=?,updated=? WHERE group_id=?',
                           (image_id, time.time(), group_id))
        return self.one('SELECT * FROM review WHERE group_id=?', (group_id,))

    def image_context(self, image_id):
        image = self.entity('files', image_id)
        if not image or not image['is_image'] or not image['present']:
            return None
        args = (image['package_id'], image['sort_key'], image['sort_key'], image_id)
        before = self.one('SELECT id FROM files WHERE package_id=? AND present=1 AND is_image=1 '
                          'AND (sort_key<? OR (sort_key=? AND id<?)) ORDER BY sort_key DESC,id DESC LIMIT 1', args)
        after = self.one('SELECT id FROM files WHERE package_id=? AND present=1 AND is_image=1 '
                         'AND (sort_key>? OR (sort_key=? AND id>?)) ORDER BY sort_key,id LIMIT 1', args)
        index = self.one('SELECT COUNT(*) n FROM files WHERE package_id=? AND present=1 AND is_image=1 '
                         'AND (sort_key<? OR (sort_key=? AND id<?))', args)['n']
        return {'image': image, 'previous_id': before['id'] if before else None,
                'next_id': after['id'] if after else None, 'index': index,
                'revision': self.revision(image['library_id'])}

    def task(self, task_id):
        row = self.one('SELECT * FROM tasks WHERE id=?', (task_id,))
        if row:
            row['payload'] = json.loads(row['payload'])
            row['result'] = json.loads(row['result']) if row['result'] else None
        return row
