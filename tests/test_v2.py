"""V2 integration tests operate exclusively on temporary libraries and data."""

import io
import json
import os
import sqlite3
import time
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from gallery.app import create_app
from gallery.hashing import HASH_VERSION, neighbors, phash
from gallery.paths import Settings


@pytest.fixture
def world(tmp_path):
    root = tmp_path / 'library'
    album = root / '作者' / '图包'
    album.mkdir(parents=True)
    Image.new('RGB', (120, 180), '#487469').save(album / 'b.JPG')
    Image.new('RGBA', (90, 60), (200, 10, 20, 40)).save(album / 'a.png')
    (album / 'notes.txt').write_text('unique content', encoding='utf-8')
    settings = Settings(tmp_path / 'data', root=root, watch=False)
    app = create_app(settings)
    with TestClient(app) as client:
        wait_idle(client)
        yield client, app.state.service, root


def wait_task(client, task_id):
    until = time.monotonic() + 15
    while time.monotonic() < until:
        result = client.get('/api/v1/tasks/' + task_id).json()
        if result['state'] in ('completed', 'cancelled', 'failed', 'interrupted'):
            return result
        time.sleep(.01)
    raise AssertionError('Task did not finish')


def wait_idle(client):
    for task in client.get('/api/v1/tasks').json()['items']:
        result = wait_task(client, task['id'])
        assert result['state'] == 'completed', result


def scope(client):
    lib = client.get('/api/v1/libraries').json()[0]
    group = client.get(f"/api/v1/libraries/{lib['id']}/groups").json()['items'][0]
    package = client.get(f"/api/v1/groups/{group['id']}/packages").json()['items'][0]
    return lib, group, package


def rescan(client, lib):
    response = client.post('/api/v1/tasks', json={'kind': 'scan', 'library_id': lib['id']})
    assert response.status_code == 202, response.text
    result = wait_task(client, response.json()['id'])
    assert result['state'] == 'completed', result
    return result


def test_catalog_pagination_scope_and_boundary(world):
    client, service, root = world
    lib, group, package = scope(client)
    page = client.get(f"/api/v1/packages/{package['id']}/images?limit=1").json()
    assert page['total'] == 2 and page['items'][0]['name'] == 'a.png'
    first = client.get('/api/v1/images/' + page['items'][0]['id'] + '/context').json()
    assert first['previous_id'] is None and first['next_id']
    last = client.get('/api/v1/images/' + first['next_id'] + '/context').json()
    assert last['next_id'] is None and last['index'] == 1
    assert client.get(f"/api/v1/packages/{package['id']}/images?limit=501").status_code == 422
    (root / '作者' / '另一个图包').mkdir()
    Image.new('RGB', (16, 16)).save(root / '作者' / '另一个图包' / 'x.jpg')
    rescan(client, lib)
    assert client.get('/api/v1/images/' + first['next_id'] + '/context').json()['next_id'] is None
    other = root.parent / 'second'
    (other / '作者' / '图包').mkdir(parents=True)
    Image.new('RGB', (16, 16)).save(other / '作者' / '图包' / 'x.jpg')
    lib2 = client.post('/api/v1/libraries', json={'path': str(other)}).json()
    wait_idle(client)
    group2 = client.get(f"/api/v1/libraries/{lib2['id']}/groups").json()['items'][0]
    assert group2['id'] != group['id']
    assert client.post('/api/v1/libraries', json={'path': str(other / '作者')}).status_code == 409
    assert service.catalog.one('SELECT COUNT(*) n FROM files WHERE is_image=0')['n'] == 1


def test_stable_ids_position_and_deep_changes(world):
    client, _service, root = world
    lib, group, package = scope(client)
    items = client.get(f"/api/v1/packages/{package['id']}/images").json()['items']
    image_id = items[1]['id']
    assert client.put(f"/api/v1/groups/{group['id']}/position", json={'image_id': image_id}).status_code == 200
    album = root / '作者' / '图包'
    (album / 'b.JPG').rename(album / 'c.JPG')
    (album / 'nested').mkdir()
    Image.new('RGB', (12, 12)).save(album / 'nested' / '0.jpg')
    rescan(client, lib)
    assert client.get(f'/api/v1/images/{image_id}/context').json()['image']['name'] == 'c.JPG'
    (root / '作者' / '图包').rename(root / '作者' / '改名图包')
    rescan(client, lib)
    assert client.get(f'/api/v1/images/{image_id}/context').json()['image']['package_id'] == package['id']
    assert client.get(f"/api/v1/groups/{group['id']}/review").json()['image_id'] == image_id
    moved = root.with_name('offline')
    root.rename(moved)
    assert rescan(client, lib)['result']['online'] is False
    assert client.get(f"/api/v1/packages/{package['id']}/images").json()['total'] == 3
    moved.rename(root)
    rescan(client, lib)
    assert client.get('/api/v1/libraries').json()[0]['online'] is True


def test_alpha_animation_bad_image_and_warm_cache(world):
    client, _service, root = world
    lib, _group, package = scope(client)
    png = client.get(f"/api/v1/packages/{package['id']}/images").json()['items'][0]
    response = client.get(f"/api/v1/images/{png['id']}/thumbnail?edge=400")
    assert response.status_code == 200, response.text
    image = Image.open(io.BytesIO(response.content))
    assert image.mode == 'RGBA' and image.getpixel((0, 0))[3] == 40
    assert client.get(f"/api/v1/images/{png['id']}/thumbnail", headers={'If-None-Match': response.headers['etag']}).status_code == 304
    path = root / png['rel']
    path.rename(path.with_suffix('.held'))
    assert client.get(f"/api/v1/images/{png['id']}/thumbnail").status_code == 200
    path.with_suffix('.held').rename(path)
    a, b = Image.new('RGB', (16, 16), 'red'), Image.new('RGB', (16, 16), 'blue')
    for ext in ('gif', 'webp'):
        a.save(path.parent / ('motion.' + ext), save_all=True, append_images=[b], duration=100, loop=0)
    (path.parent / 'broken.jpg').write_bytes(b'not an image')
    rescan(client, lib)
    rows = client.get(f"/api/v1/packages/{package['id']}/images").json()['items']
    for item in rows:
        response = client.get(f"/api/v1/images/{item['id']}/thumbnail")
        if item['name'] == 'broken.jpg':
            assert response.status_code == 422
        elif item['name'].startswith('motion.'):
            assert response.status_code == 200
            context = client.get(f"/api/v1/images/{item['id']}/context").json()
            assert context['image']['animated'] is True
            assert client.get(f"/api/v1/images/{item['id']}/original").content == (root / item['rel']).read_bytes()


def test_security_ranges_and_review(world):
    client, _service, _root = world
    lib, group, package = scope(client)
    item = client.get(f"/api/v1/packages/{package['id']}/images").json()['items'][0]
    url = f"/api/v1/images/{item['id']}/original"
    full = client.get(url)
    assert client.get(url, headers={'Range': 'bytes=-20'}).content == full.content[-20:]
    assert client.get(url, headers={'If-None-Match': full.headers['etag']}).status_code == 304
    assert client.post('/api/v1/operations/delete', json={'targets': [{'kind': 'image', 'id': item['id']}],
                                                        'permanent': True}).status_code == 422
    assert client.get('/api/v1/health', headers={'Host': 'evil.example'}).status_code == 403
    assert client.post('/api/v1/libraries', json={'path': 'C:/Windows'},
                       headers={'Origin': 'https://evil.example'}).status_code == 403
    assert client.patch(f"/api/v1/groups/{group['id']}/review", json={'state': 'kept'}).status_code == 200
    assert client.get(f"/api/v1/libraries/{lib['id']}/groups?state=marked").json()['total'] == 0
    assert len(client.get(f"/api/v1/groups/{group['id']}/samples?seed=4").json()) == 2


def test_recycle_failure_preserves_source_and_records_error(world, monkeypatch):
    client, service, root = world
    _lib, _group, package = scope(client)
    item = client.get(f"/api/v1/packages/{package['id']}/images").json()['items'][0]
    def unavailable(_path):
        raise OSError('Recycle Bin unavailable')
    monkeypatch.setattr('gallery.organize.recycle', unavailable)
    response = client.post('/api/v1/operations/delete', json={'targets': [{'kind': 'image', 'id': item['id']}]})
    result = wait_task(client, response.json()['id'])
    assert result['result']['failed'] == 1
    assert (root / item['rel']).exists()
    assert service.catalog.entity('files', item['id'])['present'] == 1
    assert client.get('/api/v1/operations').json()['items'][0]['state'] == 'failed'


def test_exact_comparison_includes_other_files(world):
    client, _service, root = world
    import shutil
    lib, group, package = scope(client)
    shutil.copytree(root / '作者' / '图包', root / '作者' / 'copy')
    (root / '作者' / 'copy' / 'notes.txt').unlink()
    rescan(client, lib)
    peer = next(p for p in client.get(f"/api/v1/groups/{group['id']}/packages").json()['items'] if p['name'] == 'copy')
    response = client.post('/api/v1/tasks', json={'kind': 'compare', 'left_id': package['id'], 'right_id': peer['id']})
    task = wait_task(client, response.json()['id'])
    assert task['state'] == 'completed', task
    assert task['result']['exact_equal'] is False
    assert task['result']['left_unique'][0]['name'] == 'notes.txt'
    response = client.post('/api/v1/tasks', json={'kind': 'analyze', 'group_id': group['id']})
    task = wait_task(client, response.json()['id'])
    assert task['state'] == 'completed', task
    assert task['result']['hash_version'] == HASH_VERSION
    assert task['result']['pairs'] >= 2


def test_hamming_stream_matches_exact_reference():
    rng = np.random.default_rng(9)
    hashes = rng.integers(0, 256, size=(200, 8), dtype=np.uint8)
    hashes[1] = hashes[0]
    actual = {(i, int(j)) for i, matches in neighbors(hashes, 8, block=7) for j in matches}
    values = [int.from_bytes(row.tobytes(), 'big') for row in hashes]
    expected = {(i, j) for i in range(len(values)) for j in range(i + 1, len(values))
                if (values[i] ^ values[j]).bit_count() <= 8}
    assert actual == expected and (0, 1) in actual


def test_legacy_import_backup_and_stable_position(tmp_path):
    from gallery.catalog import Catalog
    from gallery.events import Events
    from gallery.indexer import Indexer
    from gallery.migration import import_legacy
    source, root = tmp_path / 'old', tmp_path / 'library'
    (source / 'cache').mkdir(parents=True)
    album = root / '作者' / '图包'
    album.mkdir(parents=True)
    Image.new('RGB', (16, 16), 'red').save(album / 'b.jpg')
    Image.new('RGB', (16, 16), 'blue').save(album / 'a.jpg')
    with sqlite3.connect(source / 'cache' / 'gallery.db') as db:
        db.executescript('CREATE TABLE folders(name);CREATE TABLE media(folder,rel,album,size,kind);')
        db.execute('INSERT INTO folders VALUES(?)', ('作者',))
        db.executemany('INSERT INTO media VALUES(?,?,?,?,?)', [('作者', f'图包/{s}.jpg', '图包', 100, 'image') for s in ('b', 'a')])
    (source / 'review_state.json').write_text(json.dumps({'作者': {'state': 'kept', 'index': 1}}), encoding='utf-8')
    catalog = Catalog(tmp_path / 'new' / 'catalog.sqlite')
    indexer = Indexer(catalog, Events())
    class Context:
        def check(self):
            pass
    report = import_legacy(catalog, source, root, indexer, Context())
    assert Path(report['snapshot'], 'gallery.db').exists()
    row = catalog.one('SELECT f.name,r.state FROM review r JOIN files f ON f.id=r.image_id')
    assert row == {'name': 'b.jpg', 'state': 'kept'}
    assert import_legacy(catalog, source, root, indexer, Context()) == report


def test_job_pause_resume_cancel_and_persistence(world):
    client, service, _root = world
    import threading
    started = threading.Event()
    def run(context, _payload):
        started.set()
        for i in range(200):
            context.update(i, 200, force=True)
            time.sleep(.01)
    service.tasks.handlers['probe'] = run
    job = service.tasks.submit('probe', {})
    assert started.wait(2)
    url = f"/api/v1/tasks/{job['id']}/control"
    client.post(url, json={'action': 'pause'})
    time.sleep(.1)
    first = client.get('/api/v1/tasks/' + job['id']).json()['progress']
    time.sleep(.1)
    assert client.get('/api/v1/tasks/' + job['id']).json()['progress'] == first
    client.post(url, json={'action': 'resume'})
    time.sleep(.1)
    assert client.get('/api/v1/tasks/' + job['id']).json()['progress'] > first
    client.post(url, json={'action': 'cancel'})
    assert wait_task(client, job['id'])['state'] == 'cancelled'


@pytest.mark.skipif(os.name != 'nt', reason='Windows Recycle Bin')
def test_windows_recycles_only_temporary_file(tmp_path):
    from gallery.recycle import recycle
    path = tmp_path / 'recycle-probe.txt'
    path.write_text('temporary test file', encoding='utf-8')
    recycle(path)
    assert not path.exists()


def test_frozen_phash_fixture(tmp_path):
    image = np.arange(64 * 64, dtype=np.uint8).reshape(64, 64)
    path = tmp_path / 'gradient.png'
    Image.fromarray(image).save(path)
    # Captured from the Python 3.12 / Pillow 12.2 baseline before replacing the backend.
    assert phash(path).hex() == 'aa00000000000000'
