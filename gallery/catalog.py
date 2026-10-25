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


def content_version(size, mtime_ns):
    return f'v2-{size:x}-{mtime_ns:x}'


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
            if version > 8:
                raise RuntimeError('Catalog was created by a newer application')
            if version == 0:
                sql = (Path(__file__).parent / 'sql' / '001_catalog.sql').read_text(encoding='utf-8')
                db.executescript('BEGIN IMMEDIATE;\n' + sql + '\nPRAGMA user_version=1;\nCOMMIT;')
                version = 1
            if version == 1:
                sql = (Path(__file__).parent / 'sql' / '002_group_stats.sql').read_text(encoding='utf-8')
                db.executescript('BEGIN IMMEDIATE;\n' + sql + '\nPRAGMA user_version=2;\nCOMMIT;')
                version = 2
            if version == 2:
                sql = (Path(__file__).parent / 'sql' / '003_directory_mtime.sql').read_text(encoding='utf-8')
                db.executescript('BEGIN IMMEDIATE;\n' + sql + '\nPRAGMA user_version=3;\nCOMMIT;')
                version = 3
            if version == 3:
                sql = (Path(__file__).parent / 'sql' / '004_findings.sql').read_text(encoding='utf-8')
                db.executescript('BEGIN IMMEDIATE;\n' + sql + '\nPRAGMA user_version=4;\nCOMMIT;')
                version = 4
            if version == 4:
                sql = (Path(__file__).parent / 'sql' / '005_pending_positions.sql').read_text(encoding='utf-8')
                db.executescript('BEGIN IMMEDIATE;\n' + sql + '\nPRAGMA user_version=5;\nCOMMIT;')
                version = 5
            if version == 5:
                sql = (Path(__file__).parent / 'sql' / '006_operation_tasks.sql').read_text(encoding='utf-8')
                db.executescript('BEGIN IMMEDIATE;\n' + sql + '\nPRAGMA user_version=6;\nCOMMIT;')
                version = 6
            if version == 6:
                sql = (Path(__file__).parent / 'sql' / '007_task_sources.sql').read_text(encoding='utf-8')
                db.executescript('BEGIN IMMEDIATE;\n' + sql + '\nPRAGMA user_version=7;\nCOMMIT;')
                version = 7
            if version == 7:
                sql = (Path(__file__).parent / 'sql' / '008_library_management.sql').read_text(encoding='utf-8')
                db.executescript('BEGIN IMMEDIATE;\n' + sql + '\nPRAGMA user_version=8;\nCOMMIT;')

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

    @staticmethod
    def refresh_group(db, group_id):
        db.execute('UPDATE directories SET image_count=(SELECT COUNT(*) FROM files WHERE group_id=? '
                   'AND present=1 AND is_image=1), bytes=(SELECT COALESCE(SUM(size),0) FROM files '
                   'WHERE group_id=? AND present=1) WHERE id=?', (group_id, group_id, group_id))
        pending = db.execute('SELECT legacy_index FROM review WHERE group_id=? AND image_id IS NULL '
                             'AND legacy_index IS NOT NULL', (group_id,)).fetchone()
        if pending:
            image = db.execute('SELECT id FROM files WHERE group_id=? AND present=1 AND is_image=1 '
                               'ORDER BY sort_key,id LIMIT 1 OFFSET ?', (group_id, pending['legacy_index'])).fetchone()
            if not image:
                image = db.execute('SELECT id FROM files WHERE group_id=? AND present=1 AND is_image=1 '
                                   'ORDER BY sort_key DESC,id DESC LIMIT 1', (group_id,)).fetchone()
            if image:
                db.execute('UPDATE review SET image_id=?,legacy_index=NULL WHERE group_id=?', (image['id'], group_id))

    def entity(self, table, entity_id):
        if table not in {'libraries', 'directories', 'packages', 'files'}:
            raise ValueError(table)
        return self.one(f'SELECT * FROM {table} WHERE id=?', (entity_id,))

    def libraries(self):
        return self.rows('SELECT * FROM libraries WHERE managed=1 ORDER BY name COLLATE NOCASE,id')

    @staticmethod
    def local_root(value):
        if str(value).startswith(('\\\\', '//')):
            raise ValueError('Network libraries are not supported')
        path = Path(value).resolve(strict=True)
        if str(path).startswith('\\\\') or not path.is_dir():
            raise ValueError('Select a local directory')
        return path

    def check_library_root(self, path, library_id=None):
        occupied = self.one('SELECT id FROM libraries WHERE path_key=?', (path_key(path),))
        if occupied and occupied['id'] != library_id:
            raise ValueError('该目录已有图库记录，请重新添加原目录以恢复原记录')
        for lib in self.libraries():
            if lib['id'] == library_id:
                continue
            other = Path(lib['path'])
            if path.is_relative_to(other) or other.is_relative_to(path):
                raise ValueError('Library roots must not overlap')

    def add_library(self, path, name=None):
        existing = self.one('SELECT * FROM libraries WHERE path_key=?', (path_key(Path(path).absolute()),))
        if existing:
            return existing
        path = self.local_root(path)
        key = path_key(path)
        existing = self.one('SELECT * FROM libraries WHERE path_key=?', (key,))
        if existing:
            return existing
        self.check_library_root(path)
        library_id = new_id()
        self.execute('INSERT INTO libraries(id,name,path,path_key) VALUES(?,?,?,?)',
                     (library_id, name or path.name or str(path), str(path), key))
        return self.entity('libraries', library_id)

    def page(self, select, where, args, order, offset, limit, library_id):
        with contextlib.closing(self.connect()) as db, db:
            db.execute('BEGIN')
            total = db.execute(f'SELECT COUNT(*) n FROM ({select} {where})', args).fetchone()['n']
            rows = [dict(row) for row in db.execute(f'{select} {where} ORDER BY {order} LIMIT ? OFFSET ?',
                                                   (*args, limit, offset))]
            library = db.execute('SELECT revision FROM libraries WHERE id=?', (library_id,)).fetchone()
        return {'items': rows, 'total': total, 'offset': offset, 'limit': limit,
                'revision': library['revision'] if library else 0}

    @staticmethod
    def _group_select():
        return """SELECT d.*,COALESCE(r.state,'none') state,r.image_id resume_image_id,
          (SELECT json_object('id',f.id,'size',f.size,'mtime_ns',f.mtime_ns) FROM files f
           WHERE f.package_id=(SELECT p.id FROM packages p JOIN directories pd ON pd.id=p.directory_id
             WHERE p.group_id=d.id AND pd.present=1 AND EXISTS(SELECT 1 FROM files pf
               WHERE pf.package_id=p.id AND pf.present=1 AND pf.is_image=1)
             ORDER BY p.sort_key,p.id LIMIT 1) AND f.present=1 AND f.is_image=1
           ORDER BY f.sort_key,f.id LIMIT 1) cover
          FROM directories d LEFT JOIN review r ON r.group_id=d.id"""

    @staticmethod
    def _with_cover(row):
        cover = json.loads(row.pop('cover') or 'null')
        row['cover_id'] = cover['id'] if cover else None
        row['cover_version'] = content_version(cover['size'], cover['mtime_ns']) if cover else None
        return row

    def group(self, group_id):
        row = self.one(self._group_select() + ' WHERE d.id=? AND d.id=d.group_id AND d.present=1', (group_id,))
        if row:
            row['category'] = category(row['name'])
            self._with_cover(row)
        return row

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
        result = self.page(self._group_select(), where, args, 'bytes DESC,d.sort_key,d.id', offset, limit, library_id)
        for row in result['items']:
            row['category'] = category(row['name'])
            self._with_cover(row)
        return result

    @staticmethod
    def _package_select():
        return """SELECT p.*,d.rel,d.present,
          (SELECT COUNT(*) FROM files f WHERE f.package_id=p.id AND f.present=1 AND f.is_image=1) image_count,
          (SELECT json_object('id',f.id,'size',f.size,'mtime_ns',f.mtime_ns) FROM files f
           WHERE f.package_id=p.id AND f.present=1 AND f.is_image=1 ORDER BY f.sort_key,f.id LIMIT 1) cover
          FROM packages p JOIN directories d ON p.directory_id=d.id"""

    def package(self, package_id):
        row = self.one(self._package_select() + ' WHERE p.id=? AND d.present=1 AND EXISTS('
                       'SELECT 1 FROM files f WHERE f.package_id=p.id AND f.present=1 AND f.is_image=1)', (package_id,))
        return self._with_cover(row) if row else None

    def packages(self, group_id, offset, limit):
        group = self.entity('directories', group_id)
        result = self.page(self._package_select(), 'WHERE p.group_id=? AND d.present=1 AND EXISTS('
                           'SELECT 1 FROM files f WHERE f.package_id=p.id AND f.present=1 AND f.is_image=1)', [group_id],
                           'p.sort_key,p.id', offset, limit, group['library_id'])
        result['items'] = [self._with_cover(row) for row in result['items']]
        return result

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
                db.execute('UPDATE review SET image_id=?,updated=?,legacy_index=NULL WHERE group_id=?',
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
            row['targets'], row['scope'] = self.describe_targets(row['payload'])
        return row

    def describe_targets(self, payload):
        targets = payload.get('targets') or []
        if not targets:
            for keys, kind in ((('left_id', 'right_id', 'package_id'), 'package'),
                               (('group_id',), 'group'), (('directory_id',), 'directory'),
                               (('library_id',), 'library')):
                ids = [payload[key] for key in keys if payload.get(key)]
                if ids:
                    targets = [{'id': value, 'kind': kind} for value in ids]
                    break
        described = []
        with contextlib.closing(self.connect()) as db:
            for target in targets:
                table = {'library': 'libraries', 'directory': 'directories', 'group': 'directories',
                         'package': 'packages', 'image': 'files'}[target['kind']]
                row = db.execute(f'SELECT * FROM {table} WHERE id=?', (target['id'],)).fetchone()
                info = dict(row) if row else {}
                rel = info.get('rel', '')
                if target['kind'] == 'package' and row:
                    rel = db.execute('SELECT rel FROM directories WHERE id=?', (row['directory_id'],)).fetchone()[0]
                described.append({**target, 'label': info.get('name') or target['id'], 'rel': rel,
                                  'library_id': info.get('library_id', info.get('id')),
                                  'group_id': info.get('group_id')})
        libraries = {row['library_id'] for row in described}
        groups = {row['group_id'] for row in described}
        scope = {'library_id': next(iter(libraries)) if len(libraries) == 1 else None,
                 'group_id': next(iter(groups)) if len(groups) == 1 else None}
        return described, scope

    def tasks(self, offset, limit, kind=None, state=None, library_id=None, active=None):
        clauses, args = [], []
        for key, value in (('kind', kind), ('state', state)):
            if value:
                clauses.append(f'{key}=?')
                args.append(value)
        if active is not None:
            clauses.append("state " + ('' if active else 'NOT ') + "IN ('queued','running','paused','cancelling')")
        if library_id:
            clauses.append("""(json_extract(payload,'$.library_id')=? OR
              json_extract(payload,'$.group_id') IN (SELECT id FROM directories WHERE library_id=?) OR
              json_extract(payload,'$.package_id') IN (SELECT id FROM packages WHERE library_id=?) OR
              json_extract(payload,'$.left_id') IN (SELECT id FROM packages WHERE library_id=?) OR
              EXISTS(SELECT 1 FROM json_each(payload,'$.targets') t WHERE json_extract(t.value,'$.id') IN (
                SELECT id FROM directories WHERE library_id=? UNION ALL
                SELECT id FROM packages WHERE library_id=? UNION ALL SELECT id FROM files WHERE library_id=?)))""")
            args.extend([library_id] * 7)
        page = self.page('SELECT id FROM tasks', 'WHERE ' + ' AND '.join(clauses) if clauses else '',
                         args, 'created DESC,id', offset, limit, '')
        page['items'] = [self.task(row['id']) for row in page['items']]
        return page

    def save_findings(self, task_id, kind, items):
        with self.write() as db:
            db.executemany('INSERT INTO findings VALUES(?,?,?,?)',
                           ((task_id, kind, i, json.dumps(item, ensure_ascii=False)) for i, item in enumerate(items)))
