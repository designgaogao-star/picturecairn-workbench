"""Explicit, repeatable legacy import from a consistent SQLite backup."""

import contextlib
import json
import shutil
import sqlite3
import time
from pathlib import Path

from gallery.catalog import image_sort_key, new_id, path_key


def backup_sqlite(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    with contextlib.closing(sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True)) as src:
        with contextlib.closing(sqlite3.connect(target)) as dst:
            src.backup(dst)


def import_legacy(catalog, source, root, indexer, context):
    from gallery.hashing import LEGACY_HASH_VERSION
    source = Path(source).resolve()
    marker = str(source)
    prior = catalog.one('SELECT report FROM imports WHERE source=?', (marker,))
    if prior:
        return json.loads(prior['report'])
    library = catalog.add_library(root)
    destination = catalog.path.parent / 'legacy' / time.strftime('%Y%m%d-%H%M%S')
    destination.mkdir(parents=True, exist_ok=True)
    for name in ('gallery.db', 'dedup.db'):
        old = source / 'cache' / name
        if old.is_file():
            backup_sqlite(old, destination / name)
    for relative in ('review_state.json', 'folders_meta.json', 'marks.json', 'cache/delete_journal.jsonl'):
        old = source / relative
        if old.is_file():
            shutil.copy2(old, destination / old.name)
    manifest = {'source': str(source), 'root': str(root), 'thumbs': str(source / 'thumbs')}
    (destination / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')
    root_id = new_id()
    directories, packages = {'': root_id}, {}
    def directory(db, rel):
        if rel in directories:
            return directories[rel]
        parent_rel = str(Path(rel).parent).replace('\\', '/')
        if parent_rel == '.':
            parent_rel = ''
        parent = directory(db, parent_rel)
        dir_id = new_id()
        group_rel = rel.split('/')[0]
        group_id = dir_id if '/' not in rel else directories[group_rel]
        db.execute('INSERT INTO directories(id,library_id,parent_id,group_id,rel,path_key,name,sort_key) '
                   'VALUES(?,?,?,?,?,?,?,?)', (dir_id, library['id'], parent, group_id, rel, path_key(rel),
                                              Path(rel).name, rel.lower()))
        directories[rel] = dir_id
        return dir_id

    old_db = destination / 'gallery.db'
    imported = hash_count = 0
    with catalog.write() as db:
        existing_root = db.execute('SELECT id FROM directories WHERE library_id=? AND rel=?',
                                   (library['id'], '')).fetchone()
        if existing_root:
            raise ValueError('Import requires a library that has not been scanned')
        db.execute('INSERT INTO directories(id,library_id,group_id,rel,path_key,name,sort_key) VALUES(?,?,?,?,?,?,?)',
                   (root_id, library['id'], root_id, '', '', library['name'], ''))
        if old_db.is_file():
            with contextlib.closing(sqlite3.connect(old_db)) as old:
                for folder, in old.execute('SELECT name FROM folders'):
                    directory(db, folder)
                cursor = old.execute("SELECT folder,rel,album,size FROM media WHERE kind='image'")
                for folder, rel, _album, size in cursor:
                    if imported % 500 == 0:
                        context.check()
                    relative = (folder + '/' + rel).replace('\\', '/')
                    if '..' in Path(relative).parts or Path(relative).is_absolute():
                        continue
                    group_id = directory(db, folder)
                    parent_rel = str(Path(relative).parent).replace('\\', '/')
                    parent_id = directory(db, parent_rel)
                    pkg_rel = folder + '/' + rel.split('/')[0] if '/' in rel else folder
                    package_dir = directory(db, pkg_rel)
                    package_id = packages.get(pkg_rel)
                    if not package_id:
                        package_id = indexer._package(db, library['id'], group_id, package_dir,
                                                      pkg_rel[len(folder) + 1:] if pkg_rel != folder else '',
                                                      pkg_rel == folder)
                        packages[pkg_rel] = package_id
                    from gallery.config import IMG_EXT
                    if Path(rel).suffix.lower() not in IMG_EXT:
                        continue
                    db.execute('INSERT OR IGNORE INTO files(id,library_id,directory_id,group_id,package_id,rel,'
                               'path_key,name,sort_key,size,mtime_ns,is_image) VALUES(?,?,?,?,?,?,?,?,?,?,0,1)',
                               (new_id(), library['id'], parent_id, group_id, package_id, relative,
                                path_key(relative), Path(rel).name, image_sort_key(rel), size))
                    imported += 1
        dedup = destination / 'dedup.db'
        if dedup.is_file():
            with contextlib.closing(sqlite3.connect(dedup)) as old:
                for absolute, h, size, mtime in old.execute('SELECT path,h,size,mtime FROM phash'):
                    try:
                        rel = Path(absolute).relative_to(root)
                    except ValueError:
                        continue
                    db.execute('UPDATE files SET phash=?,hash_version=?,hash_mtime_ns=? '
                               'WHERE library_id=? AND path_key=? AND size=?',
                               (h, LEGACY_HASH_VERSION, int(mtime) * 10**9, library['id'], path_key(rel), size))
                    hash_count += 1
        state_path = destination / 'review_state.json'
        if state_path.is_file():
            state = json.loads(state_path.read_text(encoding='utf-8-sig'))
            for folder, value in state.items():
                if folder not in directories or not isinstance(value, dict):
                    continue
                group_id = directories[folder]
                image = db.execute('SELECT id FROM files WHERE group_id=? ORDER BY sort_key,id LIMIT 1 OFFSET ?',
                                   (group_id, max(0, int(value.get('index', 0))))).fetchone()
                db.execute('INSERT OR REPLACE INTO review(group_id,state,image_id,updated,legacy_index) VALUES(?,?,?,?,?)',
                           (group_id, value.get('state', 'none'), image[0] if image else None, time.time(),
                            None if image else max(0, int(value.get('index', 0)))))
        report = {'library_id': library['id'], 'images': imported, 'legacy_hash_rows': hash_count,
                  'snapshot': str(destination), 'legacy_thumbs': str(source / 'thumbs')}
        for group in db.execute('SELECT id FROM directories WHERE library_id=? AND id=group_id', (library['id'],)).fetchall():
            catalog.refresh_group(db, group['id'])
        db.execute('INSERT INTO imports VALUES(?,?,?)', (marker, time.time(), json.dumps(report)))
    catalog.bump(library['id'])
    return report


def restore_pending_positions(catalog):
    """Resolve positions from legacy groups whose file lists were never stored in the old DB."""
    for imported in catalog.rows('SELECT report FROM imports'):
        report = json.loads(imported['report'])
        source = Path(report['snapshot']) / 'review_state.json'
        if not source.is_file():
            continue
        state = json.loads(source.read_text(encoding='utf-8-sig'))
        with catalog.write() as db:
            for folder, value in state.items():
                if not isinstance(value, dict):
                    continue
                row = db.execute('SELECT d.id FROM directories d JOIN review r ON r.group_id=d.id '
                                 'WHERE d.library_id=? AND d.path_key=? AND r.image_id IS NULL',
                                 (report['library_id'], path_key(folder))).fetchone()
                if row:
                    db.execute('UPDATE review SET legacy_index=? WHERE group_id=?',
                               (max(0, int(value.get('index', 0))), row['id']))
                    catalog.refresh_group(db, row['id'])
