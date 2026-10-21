"""Read-only comparison of a live catalog with an independent disk enumeration."""

import argparse
import contextlib
import json
import os
import sqlite3
import time
from pathlib import Path

from gallery.config import IMG_EXT


def verify(data, project):
    database = data / 'catalog.sqlite'
    with contextlib.closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        libraries = [dict(row) for row in db.execute('SELECT * FROM libraries')]
        sources = [Path(row[0]).resolve() for row in db.execute('SELECT source FROM imports')]
        positions = db.execute('SELECT COUNT(*) FROM review WHERE image_id IS NOT NULL').fetchone()[0]
        reports = []
        for library in libraries:
            root = Path(library['path']).resolve()
            excluded = {data.resolve(), project.resolve()}
            for source in sources:
                excluded.update([source / 'cache', source / 'thumbs'] if source == root else [source])
            indexed = {row['rel'].replace('\\', '/').lower(): row['size'] for row in db.execute(
                'SELECT rel,size FROM files WHERE library_id=? AND present=1 AND is_image=1', (library['id'],))}
            disk, errors, directories = {}, [], 0
            stack = [root]
            while stack:
                directory = stack.pop()
                try:
                    with os.scandir(directory) as entries:
                        for entry in entries:
                            if entry.is_symlink() or os.path.isjunction(entry.path):
                                continue
                            path = Path(entry.path)
                            if entry.is_dir(follow_symlinks=False):
                                if path.resolve() in excluded or directory == root and entry.name.startswith('.'):
                                    continue
                                stack.append(path)
                            elif path.suffix.lower() in IMG_EXT:
                                disk[path.relative_to(root).as_posix().lower()] = entry.stat().st_size
                    directories += 1
                except OSError as exc:
                    errors.append({'path': str(directory), 'error': str(exc)})
            missing = sorted(disk.keys() - indexed.keys())
            stale = sorted(indexed.keys() - disk.keys())
            changed = sorted(key for key in disk.keys() & indexed.keys() if disk[key] != indexed[key])
            reports.append({'library_id': library['id'], 'root': str(root), 'disk_images': len(disk),
                            'indexed_images': len(indexed), 'disk_directories': directories,
                            'missing_from_index': missing, 'missing_from_disk': stale,
                            'size_mismatches': changed, 'read_errors': errors,
                            'ok': not (missing or stale or changed or errors)})
        integrity = db.execute('PRAGMA quick_check').fetchone()[0]
        return {'time': time.time(), 'integrity': integrity, 'positions': positions,
                'libraries': reports, 'ok': integrity == 'ok' and all(row['ok'] for row in reports)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--project', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    report = verify(args.data.resolve(), args.project)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'ok': report['ok'], 'integrity': report['integrity'], 'positions': report['positions'],
                      'libraries': [{key: row[key] for key in ('library_id', 'disk_images', 'indexed_images',
                                                               'disk_directories', 'ok')}
                                    for row in report['libraries']]}, ensure_ascii=False))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
