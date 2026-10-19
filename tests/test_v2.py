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
    lib = client.get('/api/v1/libraries').json()['items'][0]
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
    libraries = client.get('/api/v1/libraries?limit=1').json()
    assert libraries['total'] == 2 and len(libraries['items']) == 1
    second_page = client.get('/api/v1/libraries?offset=1&limit=1').json()
    assert second_page['items'][0]['id'] != libraries['items'][0]['id']
    assert client.get('/api/v1/libraries?limit=501').status_code == 422
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
    assert client.get('/api/v1/libraries').json()['items'][0]['online'] is True


def test_offline_restart_preserves_index_and_position(tmp_path):
    root = tmp_path / 'library'
    package = root / 'group' / 'package'
    package.mkdir(parents=True)
    Image.new('RGB', (16, 16)).save(package / 'image.jpg')
    settings = Settings(tmp_path / 'data', root=root, watch=False)
    with TestClient(create_app(settings)) as client:
        wait_idle(client)
        _library, group, album = scope(client)
        image_id = client.get(f"/api/v1/packages/{album['id']}/images").json()['items'][0]['id']
        client.put(f"/api/v1/groups/{group['id']}/position", json={'image_id': image_id}).raise_for_status()
    offline = root.with_name('offline')
    root.rename(offline)
    with TestClient(create_app(settings)) as client:
        wait_idle(client)
        assert client.get('/api/v1/libraries').json()['items'][0]['online'] is False
        assert client.get(f"/api/v1/packages/{album['id']}/images").json()['total'] == 1
        assert client.get(f"/api/v1/groups/{group['id']}/review").json()['image_id'] == image_id
    offline.rename(root)
    with TestClient(create_app(settings)) as client:
        wait_idle(client)
        assert client.get('/api/v1/libraries').json()['items'][0]['online'] is True
        assert client.get(f'/api/v1/images/{image_id}/original').status_code == 200


def test_large_package_pagination_and_id_location(world):
    client, _service, root = world
    library, _group, package = scope(client)
    folder = root / '作者' / '图包'
    content = (folder / 'b.JPG').read_bytes()
    for i in range(503):
        (folder / f'page-{i:04d}.jpg').write_bytes(content)
    rescan(client, library)
    default = client.get(f"/api/v1/packages/{package['id']}/images").json()
    assert len(default['items']) == 100 and default['total'] == 505
    first = client.get(f"/api/v1/packages/{package['id']}/images?limit=500").json()
    last = client.get(f"/api/v1/packages/{package['id']}/images?offset=500&limit=500").json()
    assert first['revision'] == last['revision']
    assert len(first['items']) == 500 and len(last['items']) == 5
    assert len({row['id'] for row in first['items'] + last['items']}) == 505
    context = client.get(f"/api/v1/images/{last['items'][-1]['id']}/context").json()
    assert context['index'] == 504 and context['next_id'] is None


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
    operations = client.get('/api/v1/operations?task_id=' + response.json()['id']).json()['items']
    assert operations[0]['state'] == 'failed' and operations[0]['task_id'] == response.json()['id']


def test_exact_comparison_includes_other_files(world):
    client, _service, root = world
    import shutil
    lib, group, package = scope(client)
    shutil.copytree(root / '作者' / '图包', root / '作者' / 'copy')
    (root / '作者' / 'copy' / 'notes.txt').unlink()
    (root / '作者' / '图包' / '.hidden.txt').write_bytes(b'also unique')
    rescan(client, lib)
    peer = next(p for p in client.get(f"/api/v1/groups/{group['id']}/packages").json()['items'] if p['name'] == 'copy')
    response = client.post('/api/v1/tasks', json={'kind': 'compare', 'left_id': package['id'], 'right_id': peer['id']})
    task = wait_task(client, response.json()['id'])
    assert task['state'] == 'completed', task
    assert task['result']['exact_equal'] is False
    assert {f['name'] for f in task['result']['left_unique']} == {'notes.txt', '.hidden.txt'}
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


@pytest.mark.parametrize('indexed', [True, False])
def test_legacy_import_backup_and_stable_position(tmp_path, indexed):
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
        if indexed:
            db.executemany('INSERT INTO media VALUES(?,?,?,?,?)', [('作者', f'图包/{s}.jpg', '图包', 100, 'image') for s in ('b', 'a')])
    (source / 'review_state.json').write_text(json.dumps({'作者': {'state': 'kept', 'index': 1}}), encoding='utf-8')
    catalog = Catalog(tmp_path / 'new' / 'catalog.sqlite')
    indexer = Indexer(catalog, Events())
    class Context:
        def check(self):
            pass
    report = import_legacy(catalog, source, root, indexer, Context())
    assert Path(report['snapshot'], 'gallery.db').exists()
    app = create_app(Settings(catalog.path.parent, root=root, watch=False))
    with TestClient(app) as client:
        wait_idle(client)
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


@pytest.mark.parametrize('relative', ['../outside.jpg', '../../outside.jpg', '作者/../../outside.jpg',
                                      'C:/Windows/notepad.exe', '作者/图包/../../../outside.jpg', '...'])
def test_path_boundary_rejects_outside_and_root(world, relative):
    client, service, _root = world
    _lib, _group, package = scope(client)
    file_id = client.get(f"/api/v1/packages/{package['id']}/images").json()['items'][0]['id']
    row = dict(service.catalog.entity('files', file_id))
    row['rel'] = relative
    with pytest.raises((ValueError, FileNotFoundError, OSError)):
        service.access.path(row)


def test_empty_package_boundary_and_sort_compatibility(world):
    client, service, root = world
    lib, group, _package = scope(client)
    Image.new('RGB', (10, 10)).save(root / '作者' / 'z.jpg')
    (root / '作者' / 'Empty').mkdir()
    rescan(client, lib)
    rows = service.catalog.rows('SELECT name FROM files WHERE group_id=? AND is_image=1 AND present=1 ORDER BY sort_key,id',
                                (group['id'],))
    assert [r['name'] for r in rows] == ['z.jpg', 'a.png', 'b.JPG']
    packages = client.get(f"/api/v1/groups/{group['id']}/packages").json()['items']
    assert len(packages) == 2
    loose = next(p for p in packages if p['loose'])
    response = client.post('/api/v1/operations/delete', json={'targets': [{'kind': 'package', 'id': loose['id']}]})
    assert wait_task(client, response.json()['id'])['state'] == 'failed'
    assert (root / '作者' / 'z.jpg').exists()


def test_notification_watches_nested_changes(tmp_path):
    root = tmp_path / 'library'
    (root / '作者' / '图包').mkdir(parents=True)
    app = create_app(Settings(tmp_path / 'data', root=root, watch=True))
    with TestClient(app) as client:
        wait_idle(client)
        time.sleep(.3)
        Image.new('RGB', (10, 10)).save(root / '作者' / '图包' / 'new.jpg')
        until = time.monotonic() + 8
        while time.monotonic() < until:
            row = app.state.service.catalog.one('SELECT id FROM files WHERE name=? AND present=1', ('new.jpg',))
            if row:
                break
            time.sleep(.05)
        else:
            pytest.fail('Nested change was not indexed')


def test_cache_budget_collection(world):
    client, service, _root = world
    _lib, _group, package = scope(client)
    items = client.get(f"/api/v1/packages/{package['id']}/images").json()['items']
    for image in items:
        assert client.get(f"/api/v1/images/{image['id']}/thumbnail").status_code == 200
    from dataclasses import replace
    service.images.settings = replace(service.settings, cache_limit=1)
    job = client.post('/api/v1/tasks', json={'kind': 'collect'}).json()
    assert wait_task(client, job['id'])['state'] == 'completed'
    assert service.catalog.one('SELECT COUNT(*) n FROM cache_entries')['n'] == 0


def test_hard_links_are_distinct_images(world):
    client, _service, root = world
    lib, _group, package = scope(client)
    original = root / '作者' / '图包' / 'b.JPG'
    os.link(original, original.with_name('hard-link.jpg'))
    rescan(client, lib)
    items = client.get(f"/api/v1/packages/{package['id']}/images").json()['items']
    assert len(items) == 3 and len({i['id'] for i in items}) == 3


def test_audit_does_not_recommend_removing_other_files(world):
    client, _service, root = world
    lib, group, _package = scope(client)
    ad = root / '作者' / 'shell [100P-100MB]'
    ad.mkdir()
    Image.new('RGB', (8, 8)).save(ad / 'cosergirl.com.jpg')
    (ad / 'unique.txt').write_bytes(b'keep me')
    rescan(client, lib)
    job = client.post('/api/v1/tasks', json={'kind': 'audit', 'group_id': group['id']}).json()
    result = wait_task(client, job['id'])['result']
    assert result['shells'] == [] and result['incomplete'] == []
    assert len(result['advertisements'][0]['images']) == 1


def test_second_instance_does_not_interrupt_active_tasks(world):
    _client, service, _root = world
    from gallery.service import Service
    with pytest.raises(OSError, match='Another backend'):
        Service(service.settings)


def test_queue_limit_and_immediate_queued_cancellation(world):
    client, service, _root = world
    import threading

    from gallery.jobs import Busy
    gate = threading.Event()
    def wait(context, _payload):
        while not gate.wait(.02):
            context.check()
    service.tasks.handlers['probe'] = wait
    jobs = []
    try:
        for i in range(135):
            try:
                jobs.append(service.tasks.submit('probe', {'index': i}))
            except Busy:
                break
        assert 128 <= len(jobs) <= 130
        last = jobs[-1]['id']
        response = client.post(f'/api/v1/tasks/{last}/control', json={'action': 'cancel'})
        assert response.json()['state'] == 'cancelled'
    finally:
        gate.set()


def test_foreground_read_preempts_large_directory_scan(world, monkeypatch):
    client, service, root = world
    import threading
    library, _group, _package = scope(client)
    folder = root / '作者' / '图包'
    started, queued, foreground_done = (threading.Event() for _ in range(3))
    original_stat = os.stat
    metadata_reads = 0
    def stat(path, *args, **kwargs):
        nonlocal metadata_reads
        if isinstance(path, (str, os.PathLike)) and Path(path).parent == folder:
            metadata_reads += 1
            if metadata_reads == 1:
                started.set()
                assert queued.wait(2), 'Foreground reader did not queue'
            elif metadata_reads == 2:
                assert foreground_done.wait(2), 'Scan held the volume across file metadata reads'
        return original_stat(path, *args, **kwargs)
    def read():
        if started.wait(2):
            with service.resources.io(folder, foreground=True, checkpoint=queued.set):
                foreground_done.set()
    monkeypatch.setattr('gallery.indexer.os.stat', stat)
    worker = threading.Thread(target=read)
    worker.start()
    try:
        rescan(client, library)
        assert foreground_done.is_set()
    finally:
        worker.join(timeout=3)


def test_desktop_and_legacy_data_are_excluded_after_migration_and_restart(tmp_path, monkeypatch):
    from dataclasses import replace
    root = tmp_path / 'library'
    package = root / 'group' / 'package'
    package.mkdir(parents=True)
    Image.new('RGB', (16, 16)).save(package / 'image.jpg')
    application = root / 'desktop'
    resources = application / 'resources' / 'backend' / '_internal'
    resources.mkdir(parents=True)
    Image.new('RGB', (16, 16)).save(application / 'icon.png')
    legacy = root / '_old_tool'
    (legacy / 'cache').mkdir(parents=True)
    (legacy / 'thumbs').mkdir()
    Image.new('RGB', (16, 16)).save(legacy / 'thumbs' / 'cached.jpg')
    with sqlite3.connect(legacy / 'cache' / 'gallery.db') as db:
        db.executescript('CREATE TABLE folders(name);CREATE TABLE media(folder,rel,album,size,kind);')
        db.execute('INSERT INTO folders VALUES(?)', ('group',))
        db.execute('INSERT INTO media VALUES(?,?,?,?,?)', ('group', 'package/image.jpg', 'package',
                                                         (package / 'image.jpg').stat().st_size, 'image'))
    monkeypatch.setenv('GALLERY_ROOT', str(root))
    monkeypatch.setenv('GALLERY_DATA', str(tmp_path / 'data'))
    monkeypatch.setenv('GALLERY_LEGACY', str(legacy))
    monkeypatch.setenv('GALLERY_APPLICATION', str(application))
    settings = replace(Settings.environment(), resources=resources, watch=False)
    app = create_app(settings)
    with TestClient(app) as client:
        until = time.monotonic() + 10
        while time.monotonic() < until:
            tasks = client.get('/api/v1/tasks').json()['items']
            if any(t['kind'] == 'scan' for t in tasks) and all(t['state'] == 'completed' for t in tasks):
                break
            time.sleep(.01)
        else:
            pytest.fail(str(tasks))
        files = app.state.service.catalog.rows('SELECT id,rel FROM files WHERE is_image=1 AND present=1')
        assert [row['rel'] for row in files] == ['group/package/image.jpg']
        image_id = files[0]['id']
    restarted = create_app(replace(settings, legacy=None))
    with TestClient(restarted) as client:
        wait_idle(client)
        files = restarted.state.service.catalog.rows('SELECT id,rel FROM files WHERE is_image=1 AND present=1')
        assert files == [{'id': image_id, 'rel': 'group/package/image.jpg'}]


@pytest.mark.skipif(os.name != 'nt', reason='Windows junctions')
def test_subtree_scan_rejects_directory_replaced_by_junction(world):
    import subprocess
    client, service, root = world
    library, _group, package = scope(client)
    folder = root / '作者' / '图包'
    held, outside = root.parent / 'held', root.parent / 'outside'
    outside.mkdir()
    Image.new('RGB', (16, 16)).save(outside / 'outside.jpg')
    folder.rename(held)
    try:
        link = subprocess.run(['cmd', '/c', 'mklink', '/J', str(folder), str(outside)], capture_output=True)
        assert link.returncode == 0, link.stderr.decode(errors='replace')
        job = client.post('/api/v1/tasks', json={'kind': 'scan', 'library_id': library['id'],
                                                'directory_id': package['directory_id']}).json()
        result = wait_task(client, job['id'])
        assert service.catalog.one('SELECT COUNT(*) n FROM files WHERE name=?', ('outside.jpg',))['n'] == 0
        assert result['state'] == 'completed' and result['result']['failed_directories'] == 1
        assert service.catalog.entity('directories', package['directory_id'])['error']
    finally:
        if folder.is_junction():
            folder.rmdir()
        held.rename(folder)


def test_scan_cancelled_while_waiting_for_io_clears_scan_status(world):
    client, service, root = world
    library, _group, _package = scope(client)
    with service.resources.io(root, foreground=True):
        job = client.post('/api/v1/tasks', json={'kind': 'scan', 'library_id': library['id']}).json()
        until = time.monotonic() + 2
        while time.monotonic() < until:
            if service.catalog.entity('libraries', library['id'])['scan_status'] == 'scanning':
                break
            time.sleep(.01)
        else:
            pytest.fail('Scan did not start')
        client.post(f"/api/v1/tasks/{job['id']}/control", json={'action': 'cancel'})
        assert wait_task(client, job['id'])['state'] == 'cancelled'
        assert service.catalog.entity('libraries', library['id'])['scan_status'] == 'interrupted'
