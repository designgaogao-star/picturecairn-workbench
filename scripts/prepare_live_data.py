"""Create an independent live catalog without modifying an earlier installation."""

import argparse
import contextlib
import json
import shutil
import sqlite3
from pathlib import Path


def prepare(source: Path, destination: Path):
    source, destination = source.resolve(strict=True), destination.resolve()
    if source == destination or destination.is_relative_to(source) or source.is_relative_to(destination):
        raise ValueError('Source and destination must be independent directories')
    if destination.exists():
        raise FileExistsError('Choose a new destination; an existing catalog will not be replaced')
    destination.mkdir(parents=True)
    snapshot = destination / 'catalog.sqlite'
    with contextlib.closing(sqlite3.connect((source / 'catalog.sqlite').as_uri() + '?mode=ro', uri=True)) as original:
        with contextlib.closing(sqlite3.connect(snapshot)) as copied:
            original.backup(copied)
    copied_cache = missing_cache = 0
    with contextlib.closing(sqlite3.connect(snapshot)) as db, db:
        for key, path in db.execute('SELECT key,path FROM cache_entries').fetchall():
            original = Path(path)
            target = destination / 'derivatives' / key[:2] / (key + original.suffix)
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(original, target)
            except OSError:
                missing_cache += 1
                db.execute('DELETE FROM cache_entries WHERE key=?', (key,))
            else:
                copied_cache += 1
                db.execute('UPDATE cache_entries SET path=? WHERE key=?', (str(target), key))
        images = db.execute('SELECT COUNT(*) FROM files WHERE present=1 AND is_image=1').fetchone()[0]
        positions = db.execute('SELECT COUNT(*) FROM review WHERE image_id IS NOT NULL').fetchone()[0]
        assert db.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
    for name in ('delete_journal.jsonl', 'review_state.json', 'folders_meta.json'):
        if (source / name).is_file():
            shutil.copy2(source / name, destination / name)
    report = {'source': str(source), 'destination': str(destination), 'images': images,
              'positions': positions, 'copied_cache': copied_cache, 'missing_cache': missing_cache}
    (destination / 'migration-source.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.source, args.destination), ensure_ascii=False))


if __name__ == '__main__':
    main()
