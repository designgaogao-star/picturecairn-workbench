"""Heuristic cleanup evidence. Nothing in this module deletes files."""

import re
from pathlib import Path

from gallery.hashing import HASH_VERSION

KNOWN_AD_STEMS = {'cosergirl.com', 'coser福利社'}


def declared(name):
    segments = re.findall(r'\[([^\[\]]+)\]', name)
    segment = segments[-1] if segments else name
    size = re.search(r'(\d+(?:\.\d+)?)\s*([kmg])b?', segment, re.I)
    photos = [int(n) for n in re.findall(r'(\d+)\s*p(?!\w)', segment, re.I)]
    return (int(float(size[1]) * {'k': 1024, 'm': 1024**2, 'g': 1024**3}[size[2].lower()]) if size else 0,
            max(photos) if photos else 0)


class Audit:
    def __init__(self, catalog):
        self.catalog = catalog

    def run(self, context, payload):
        group_id = payload['group_id']
        common = self.catalog.rows('SELECT phash FROM files WHERE present=1 AND is_image=1 AND size<? '
                                    'AND hash_version=? AND hash_mtime_ns=mtime_ns GROUP BY phash '
                                    'HAVING COUNT(DISTINCT package_id)>=6', (500 * 1024, HASH_VERSION))
        hashes = {row['phash'] for row in common}
        stems = set(KNOWN_AD_STEMS)
        for digest in hashes:
            sample = self.catalog.one('SELECT name FROM files WHERE phash=? AND hash_version=? LIMIT 1',
                                      (digest, HASH_VERSION))
            stems.add(Path(sample['name']).stem.lower())
        rows = self.catalog.rows('SELECT id,name,loose FROM packages WHERE group_id=?', (group_id,))
        shells, ads, incomplete = [], [], []
        for i, package in enumerate(rows):
            context.check()
            files = self.catalog.rows('SELECT id,name,size,is_image,phash,hash_version,hash_mtime_ns,mtime_ns FROM files '
                                      'WHERE package_id=? AND present=1', (package['id'],))
            if not files:
                continue
            images = [f for f in files if f['is_image']]
            hits = []
            for file in images:
                if file['size'] >= 500 * 1024 or Path(file['name']).stem.lower() not in stems:
                    continue
                verified = file['hash_version'] == HASH_VERSION and file['hash_mtime_ns'] == file['mtime_ns']
                if not verified or file['phash'] in hashes:
                    hits.append({'id': file['id'], 'verified': verified})
            size = sum(f['size'] for f in files)
            if hits and len(hits) == len(files) and size <= 20 * 1024**2 and not package['loose']:
                shells.append({'package_id': package['id'], 'bytes': size, 'images': hits,
                               'verified': all(h['verified'] for h in hits)})
            elif hits:
                ads.append({'package_id': package['id'], 'images': hits})
            expected_bytes, expected_images = declared(package['name'])
            if len(images) == len(files) and not package['loose'] and (
                expected_bytes >= 50 * 1024**2 and size <= expected_bytes * .01
                or expected_images >= 20 and len(images) <= max(2, expected_images * .2)
            ):
                incomplete.append({'package_id': package['id'], 'bytes': size, 'images': len(images),
                                   'declared_bytes': expected_bytes, 'declared_images': expected_images})
            context.update(i + 1, len(rows), package['name'])
        self.catalog.save_findings(context.id, 'shell', shells)
        self.catalog.save_findings(context.id, 'advertisement', ads)
        self.catalog.save_findings(context.id, 'incomplete', incomplete)
        return {'shells': shells[:100], 'advertisements': ads[:100], 'incomplete': incomplete[:100],
                'shells_total': len(shells), 'advertisements_total': len(ads), 'incomplete_total': len(incomplete),
                'evidence': 'heuristic-only'}
