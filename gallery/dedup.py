"""Canonical hashes, streaming candidate discovery and exact all-file package comparisons."""

import hashlib
from collections import Counter

import numpy as np
from PIL import Image

from gallery.hashing import HASH_VERSION, neighbors, phash


class Dedup:
    def __init__(self, catalog, access, resources, indexer):
        self.catalog, self.access, self.resources, self.indexer = catalog, access, resources, indexer

    def build(self, context, payload):
        group_id = payload['group_id']
        group = self.catalog.entity('directories', group_id)
        scanned = self.indexer.scan(context, {'library_id': group['library_id'], 'directory_id': group_id, 'force': True})
        if not scanned['online'] or scanned['failed_directories']:
            raise OSError('The group could not be fully indexed')
        rows = self.catalog.rows('SELECT * FROM files WHERE group_id=? AND present=1 AND is_image=1 ORDER BY sort_key',
                                  (group_id,))
        done = failed = 0
        for i, row in enumerate(rows):
            context.check()
            if row['phash'] and row['hash_version'] == HASH_VERSION and row['hash_mtime_ns'] == row['mtime_ns']:
                context.update(i + 1, len(rows), row['name'])
                continue
            try:
                path = self.access.path(row)
                with context.io(path):
                    stat = path.stat()
                    if (stat.st_size, stat.st_mtime_ns) != (row['size'], row['mtime_ns']):
                        raise ValueError('Image changed; refresh the library')
                    with Image.open(path) as image:
                        image.draft('RGB', (64, 64))
                        estimate = image.width * image.height * 8 + 1024**2
                    with self.resources.decode(estimate, context.check):
                        digest = phash(path)
                if digest is None:
                    raise ValueError('Cannot decode image')
                self.catalog.execute('UPDATE files SET phash=?,hash_version=?,hash_mtime_ns=? WHERE id=? AND mtime_ns=?',
                                     (digest, HASH_VERSION, row['mtime_ns'], row['id'], row['mtime_ns']))
                done += 1
            except (OSError, ValueError, Image.DecompressionBombError):
                failed += 1
            context.update(i + 1, len(rows), row['name'])
        return {'indexed': done, 'failed': failed, 'hash_version': HASH_VERSION}

    def analyze(self, context, payload):
        build = self.build(context, payload)
        group_id = payload['group_id']
        rows = self.catalog.rows('SELECT id,package_id,phash FROM files WHERE group_id=? AND present=1 AND is_image=1 '
                                  'AND phash IS NOT NULL AND hash_version=? AND hash_mtime_ns=mtime_ns ORDER BY sort_key,id',
                                  (group_id, HASH_VERSION))
        total = self.catalog.one('SELECT COUNT(*) n FROM files WHERE group_id=? AND present=1 AND is_image=1',
                                 (group_id,))['n']
        hashes = np.array([np.frombuffer(row['phash'], dtype=np.uint8) for row in rows], dtype=np.uint8)
        pending, pair_count = [], 0
        # BLAS threads otherwise compete with foreground decode and can allocate one workspace per core.
        from threadpoolctl import threadpool_limits
        with threadpool_limits(limits=1, user_api='blas'):
            for i, matches in neighbors(hashes, payload.get('threshold', 8), checkpoint=context.check):
                left = int.from_bytes(rows[i]['phash'], 'big')
                for j in matches:
                    distance = (left ^ int.from_bytes(rows[int(j)]['phash'], 'big')).bit_count()
                    pending.append((context.id, rows[i]['id'], rows[int(j)]['id'], distance))
                    pair_count += 1
                    if len(pending) == 1000:
                        with self.catalog.write() as db:
                            db.executemany('INSERT OR IGNORE INTO similar_pairs VALUES(?,?,?,?)', pending)
                        pending.clear()
                        context.check()
                context.update(i + 1, len(rows), 'Comparing image hashes')
        if pending:
            with self.catalog.write() as db:
                db.executemany('INSERT OR IGNORE INTO similar_pairs VALUES(?,?,?,?)', pending)
        package_counts = self.catalog.rows('SELECT p.id,p.name,COUNT(f.id) total,'
                                           'SUM(CASE WHEN f.hash_version=? AND f.phash IS NOT NULL '
                                           'AND f.hash_mtime_ns=f.mtime_ns THEN 1 ELSE 0 END) indexed_count '
                                           'FROM packages p LEFT JOIN files f ON f.package_id=p.id AND f.present=1 '
                                           'AND f.is_image=1 WHERE p.group_id=? GROUP BY p.id', (HASH_VERSION, group_id))
        rates = self.catalog.rows('WITH edges AS ('
                                  'SELECT a.package_id a,b.package_id b,a.id image FROM similar_pairs e '
                                  'JOIN files a ON a.id=e.left_id JOIN files b ON b.id=e.right_id WHERE e.task_id=? '
                                  'UNION ALL SELECT b.package_id,a.package_id,b.id FROM similar_pairs e '
                                  'JOIN files a ON a.id=e.left_id JOIN files b ON b.id=e.right_id WHERE e.task_id=?) '
                                  'SELECT a,b,COUNT(DISTINCT image) matched FROM edges WHERE a<>b GROUP BY a,b',
                                  (context.id, context.id))
        counts = {r['id']: r for r in package_counts}
        package_pairs = []
        by_pair = {(r['a'], r['b']): r['matched'] for r in rates}
        for (a, b), matched in by_pair.items():
            if a >= b:
                continue
            ca, cb = counts[a], counts[b]
            package_pairs.append({'left_id': a, 'right_id': b,
                                  'left_match_rate': matched / max(1, ca['total']),
                                  'right_match_rate': by_pair.get((b, a), 0) / max(1, cb['total']),
                                  'left_coverage': (ca['indexed_count'] or 0) / max(1, ca['total']),
                                  'right_coverage': (cb['indexed_count'] or 0) / max(1, cb['total']),
                                  'evidence': 'similarity', 'exact_verified': False})
        package_pairs.sort(key=lambda x: -max(x['left_match_rate'], x['right_match_rate']))
        return {**build, 'images': total, 'coverage': len(rows) / max(1, total), 'pairs': pair_count,
                'package_pairs': package_pairs[:500], 'package_pairs_total': len(package_pairs),
                'pair_task_id': context.id}

    def compare(self, context, payload):
        a = self.catalog.entity('packages', payload['left_id'])
        b = self.catalog.entity('packages', payload['right_id'])
        if not a or not b or a['group_id'] != b['group_id'] or a['id'] == b['id']:
            raise ValueError('Select two different packages in the same group')
        group = self.catalog.entity('directories', a['group_id'])
        # Refresh both trees before exact verification, so non-image additions cannot be missed.
        for package in (a, b):
            scanned = self.indexer.scan(context, {'library_id': group['library_id'], 'directory_id': package['directory_id'], 'force': True})
            if not scanned['online'] or scanned['failed_directories']:
                raise OSError('Package enumeration is incomplete; exact comparison refused')
        sides = []
        for package in (a, b):
            rows = self.catalog.rows('SELECT * FROM files WHERE package_id=? AND present=1 ORDER BY sort_key',
                                      (package['id'],))
            hashes = []
            for i, row in enumerate(rows):
                context.check()
                path = self.access.path(row)
                digest = hashlib.sha256()
                with context.io(path):
                    before = path.stat()
                    stream = path.open('rb')
                with stream:
                    while True:
                        with context.io(path):
                            chunk = stream.read(1024**2)
                        if not chunk:
                            break
                        digest.update(chunk)
                    with context.io(path):
                        after = path.stat()
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise ValueError('File changed during exact comparison')
                hashes.append({'id': row['id'], 'name': row['name'], 'is_image': bool(row['is_image']),
                               'size': after.st_size, 'sha256': digest.hexdigest()})
                context.update(i + 1, len(rows), row['name'])
            sides.append(hashes)
        def unique(rows, peers):
            available = Counter((r['size'], r['sha256']) for r in peers)
            result = []
            for row in rows:
                key = row['size'], row['sha256']
                if available[key]:
                    available[key] -= 1
                else:
                    result.append(row)
            return result
        left_unique, right_unique = unique(sides[0], sides[1]), unique(sides[1], sides[0])
        self.catalog.save_findings(context.id, 'left_unique', left_unique)
        self.catalog.save_findings(context.id, 'right_unique', right_unique)
        return {'left_id': a['id'], 'right_id': b['id'], 'left_files': len(sides[0]), 'right_files': len(sides[1]),
                'left_unique': left_unique[:100], 'right_unique': right_unique[:100],
                'left_unique_total': len(left_unique), 'right_unique_total': len(right_unique),
                'exact_equal': bool(sides[0]) and not left_unique and not right_unique,
                'left_contained': bool(sides[0]) and not left_unique,
                'right_contained': bool(sides[1]) and not right_unique, 'algorithm': 'sha256-all-files',
                'revision': self.catalog.revision(group['library_id'])}
