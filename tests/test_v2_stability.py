"""Production readiness regressions, using only generated temporary files."""

import shutil
import time
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from gallery.app import create_app
from gallery.catalog import Catalog
from gallery.events import Events
from gallery.jobs import Resources, Tasks
from gallery.paths import Settings
from scripts.prepare_live_data import prepare
from scripts.verify_library import verify


def wait_task(client, task_id):
    for _ in range(500):
        task = client.get('/api/v1/tasks/' + task_id).json()
        if task['state'] not in ('queued', 'running', 'paused', 'cancelling'):
            return task
        time.sleep(.01)
    pytest.fail('Task did not finish')


@pytest.fixture
def world(tmp_path):
    root = tmp_path / 'library'
    folder = root / 'group' / 'package'
    folder.mkdir(parents=True)
    for name in ('a.jpg', 'b.jpg'):
        Image.new('RGB', (20, 30), '#567e67').save(folder / name)
    app = create_app(Settings(tmp_path / 'data', root=root, watch=False))
    with TestClient(app) as client:
        for task in client.get('/api/v1/tasks').json()['items']:
            assert wait_task(client, task['id'])['state'] == 'completed'
        library = client.get('/api/v1/libraries').json()['items'][0]
        group = client.get(f"/api/v1/libraries/{library['id']}/groups").json()['items'][0]
        package = client.get(f"/api/v1/groups/{group['id']}/packages").json()['items'][0]
        images = client.get(f"/api/v1/packages/{package['id']}/images").json()['items']
        yield client, app.state.service, root, library, group, package, images


def test_restart_resets_orphaned_scan_state(world):
    client, service, _root, library, *_ = world
    service.catalog.execute("UPDATE libraries SET scan_status='scanning' WHERE id=?", (library['id'],))
    service.stop()
    app = create_app(replace(service.settings, scan_on_start=False))
    with TestClient(app) as restarted:
        assert restarted.get('/api/v1/libraries').json()['items'][0]['scan_status'] == 'interrupted'


def test_scan_exception_resets_library_state(world, monkeypatch):
    client, service, _root, library, *_ = world
    def fail(_context, _payload):
        service.catalog.execute("UPDATE libraries SET scan_status='scanning' WHERE id=?", (library['id'],))
        raise RuntimeError('scan enumeration failed')
    monkeypatch.setattr(service.indexer, '_scan', fail)
    response = client.post('/api/v1/tasks', json={'kind': 'scan', 'library_id': library['id']})
    assert wait_task(client, response.json()['id'])['state'] == 'failed'
    assert service.catalog.entity('libraries', library['id'])['scan_status'] == 'interrupted'


def test_no_scan_disables_periodic_scans(tmp_path):
    root = tmp_path / 'library'
    root.mkdir()
    settings = Settings(tmp_path / 'data', root=root, watch=False, scan_on_start=False, maintenance_interval=.02)
    with TestClient(create_app(settings)) as client:
        time.sleep(.12)
        assert not any(task['kind'] == 'scan' for task in client.get('/api/v1/tasks').json()['items'])


def test_missing_delete_item_is_logged_and_does_not_block_peers(world, monkeypatch):
    client, _service, root, _library, _group, _package, images = world
    (root / images[0]['rel']).unlink()
    monkeypatch.setattr('gallery.organize.recycle', lambda path: path.unlink())
    response = client.post('/api/v1/operations/delete', json={
        'targets': [{'kind': 'image', 'id': image['id']} for image in images],
    })
    task = wait_task(client, response.json()['id'])
    assert task['state'] == 'completed', task
    assert [item['state'] for item in task['result']['items']] == ['skipped', 'completed']
    assert client.get('/api/v1/operations', params={'task_id': task['id']}).json()['total'] == 2


def test_cancelled_delete_retains_completed_result(world, monkeypatch):
    client, service, root, _library, _group, _package, images = world
    def remove_and_cancel(path):
        path.unlink()
        task = service.catalog.one("SELECT id FROM tasks WHERE kind='delete' AND state='running'")
        service.tasks.control(task['id'], 'cancel')
    monkeypatch.setattr('gallery.organize.recycle', remove_and_cancel)
    response = client.post('/api/v1/operations/delete', json={
        'targets': [{'kind': 'image', 'id': image['id']} for image in images],
    })
    task = wait_task(client, response.json()['id'])
    assert task['state'] == 'cancelled'
    assert task['result'] and len(task['result']['items']) == 1
    assert task['result']['items'][0]['state'] == 'completed'
    assert (root / images[1]['rel']).exists()


def test_offline_delete_fails_without_removing_index(world, monkeypatch):
    client, service, root, _library, _group, _package, images = world
    monkeypatch.setattr('gallery.organize.recycle', lambda _path: pytest.fail('Offline files cannot be recycled'))
    offline = root.with_name('offline')
    root.rename(offline)
    try:
        response = client.post('/api/v1/operations/delete', json={'targets': [{'kind': 'image', 'id': images[0]['id']}]})
        result = wait_task(client, response.json()['id'])['result']
        assert result['failed'] == 1 and result['items'][0]['state'] == 'failed'
        assert service.catalog.entity('files', images[0]['id'])['present'] == 1
    finally:
        offline.rename(root)


def test_loose_delete_is_rejected_before_submission(world):
    client, service, root, library, group, *_ = world
    Image.new('RGB', (10, 10)).save(root / 'group' / 'loose.jpg')
    scan = client.post('/api/v1/tasks', json={'kind': 'scan', 'library_id': library['id']}).json()
    assert wait_task(client, scan['id'])['state'] == 'completed'
    loose = service.catalog.one('SELECT id FROM packages WHERE group_id=? AND loose=1', (group['id'],))
    assert client.post('/api/v1/operations/delete', json={
        'targets': [{'kind': 'package', 'id': loose['id']}],
    }).status_code == 409


def test_busy_registration_has_no_half_created_library(world, monkeypatch, tmp_path):
    client, service, *_ = world
    other = tmp_path / 'other'
    other.mkdir()
    monkeypatch.setattr(service.tasks.queue, 'full', lambda: True)
    assert client.post('/api/v1/libraries', json={'path': str(other)}).status_code == 503
    assert client.get('/api/v1/libraries').json()['total'] == 1


def test_finished_task_keeps_counts_and_rejects_control(world):
    client, service, *_ = world
    def probe(context, _payload):
        context.update(3, 3, 'last item', force=True)
        return {'bytes': 0, 'removed': 0, 'limit': 1}
    service.tasks.handlers['probe'] = probe
    task = wait_task(client, service.tasks.submit('probe', {})['id'])
    assert (task['progress'], task['total'], task['current']) == (3, 3, 'last item')
    for action in ('pause', 'resume', 'cancel'):
        assert client.post(f"/api/v1/tasks/{task['id']}/control", json={'action': action}).status_code == 409


def test_missing_scanned_subtree_is_a_removal(world):
    client, _service, root, library, _group, package, *_ = world
    shutil.rmtree(root / 'group' / 'package')
    task = client.post('/api/v1/tasks', json={'kind': 'scan', 'library_id': library['id'],
                                           'directory_id': package['directory_id']}).json()
    result = wait_task(client, task['id'])
    assert result['state'] == 'completed'
    assert result['result']['failed_directories'] == 0
    assert client.get(f"/api/v1/packages/{package['id']}/images").status_code == 404


def test_direct_details_covers_versions_and_immutable_cache(world):
    client, _service, root, library, group, package, images = world
    detail = client.get('/api/v1/groups/' + group['id']).json()
    assert detail['cover_id'] == images[0]['id'] and detail['cover_version'] == images[0]['version']
    assert client.get('/api/v1/packages/' + package['id']).json()['cover_version'] == images[0]['version']
    image = images[0]
    url = f"/api/v1/images/{image['id']}/thumbnail?version={image['version']}"
    response = client.get(url)
    assert response.status_code == 200 and 'immutable' in response.headers['cache-control']
    assert client.get(url, headers={'If-None-Match': response.headers['etag']}).status_code == 304
    Image.new('RGB', (32, 48), 'red').save(root / image['rel'])
    scan = client.post('/api/v1/tasks', json={'kind': 'scan', 'library_id': library['id']}).json()
    assert wait_task(client, scan['id'])['state'] == 'completed'
    conflict = client.get(url)
    assert conflict.status_code == 409 and conflict.json()['error']['code'] == 'conflict'
    assert client.get('/api/v1/groups/' + group['id']).json()['cover_version'] != image['version']
    shutil.rmtree(root / 'group' / 'package')
    scan = client.post('/api/v1/tasks', json={'kind': 'scan', 'library_id': library['id']}).json()
    assert wait_task(client, scan['id'])['state'] == 'completed'
    assert client.get('/api/v1/packages/' + package['id']).status_code == 404


def test_task_targets_filters_and_full_findings_pagination(world):
    client, service, _root, library, group, package, images = world
    job = service.tasks.submit('prewarm', {'package_id': package['id'], 'edge': 400})
    task = wait_task(client, job['id'])
    assert task['targets'][0]['label'] == 'package'
    assert task['targets'][0]['rel'] == 'group/package'
    assert task['scope'] == {'library_id': library['id'], 'group_id': group['id']}
    page = client.get('/api/v1/tasks', params={'kind': 'prewarm', 'state': 'completed',
                                             'library_id': library['id'], 'limit': 1}).json()
    assert page['total'] == 1 and page['items'][0]['id'] == task['id']
    assert client.get('/api/v1/tasks', params={'library_id': 'absent'}).json()['total'] == 0
    assert client.get('/api/v1/tasks', params={'active': 'true'}).json()['total'] == 0
    findings = [{'left_id': str(i), 'right_id': 'peer', 'left_match_rate': 1, 'right_match_rate': 1,
                 'left_coverage': 1, 'right_coverage': 1, 'evidence': 'similarity', 'exact_verified': False}
                for i in range(605)]
    service.catalog.save_findings(task['id'], 'package_pair', findings)
    page = client.get(f"/api/v1/tasks/{task['id']}/findings?kind=package_pair&offset=600&limit=10").json()
    assert page['total'] == 605 and len(page['items']) == 5 and page['items'][0]['left_id'] == '600'
    service.catalog.execute('INSERT INTO similar_pairs VALUES(?,?,?,?)', (task['id'], images[0]['id'], images[1]['id'], 0))
    pair = client.get(f"/api/v1/tasks/{task['id']}/pairs").json()['items'][0]
    assert pair['left_package_id'] == pair['right_package_id'] == package['id']


def test_prewarm_uses_display_order_and_cache_does_not_delete_foreign_files(world, monkeypatch, tmp_path):
    client, service, _root, _library, group, _package, images = world
    order = []
    monkeypatch.setattr(service.images, 'generate', lambda image, *_args: order.append(image['name']))
    task = wait_task(client, service.tasks.submit('prewarm', {'group_id': group['id'], 'edge': 400})['id'])
    assert task['state'] == 'completed' and order == [row['name'] for row in images]
    external = tmp_path / 'preserved-old-cache.jpg'
    external.write_bytes(b'preserve')
    service.catalog.execute('INSERT INTO cache_entries VALUES(?,?,?,?)', ('external', str(external), 10**12, 0))
    service.images.collect()
    assert external.read_bytes() == b'preserve'
    assert service.catalog.one('SELECT * FROM cache_entries WHERE key=?', ('external',)) is None


def test_audit_rejects_unused_parameter_and_errors_have_codes(world):
    client, _service, _root, _library, group, *_ = world
    response = client.post('/api/v1/tasks', json={'kind': 'audit', 'group_id': group['id'], 'threshold': 8})
    assert response.status_code == 422 and response.json()['error']['code'] == 'invalid_request'
    assert client.get('/api/v1/groups/absent').json()['error']['code'] == 'http_404'


def test_live_snapshot_preserves_ids_positions_and_independent_cache(world, tmp_path):
    client, service, _root, _library, group, _package, images = world
    client.put(f"/api/v1/groups/{group['id']}/position", json={'image_id': images[1]['id']}).raise_for_status()
    client.get(f"/api/v1/images/{images[0]['id']}/thumbnail").raise_for_status()
    source_cache = service.catalog.one('SELECT path FROM cache_entries')['path']
    service.catalog.execute('INSERT INTO cache_entries VALUES(?,?,?,?)', ('missing', str(tmp_path / 'absent.jpg'), 1, 0))
    destination = tmp_path / 'independent-live'
    report = prepare(service.settings.data, destination)
    assert report['images'] == 2 and report['positions'] == 1
    assert report['copied_cache'] == report['missing_cache'] == 1
    copied = Catalog(destination / 'catalog.sqlite')
    assert copied.entity('files', images[1]['id'])['present'] == 1
    assert copied.one('SELECT image_id FROM review WHERE group_id=?', (group['id'],))['image_id'] == images[1]['id']
    from pathlib import Path
    cloned_cache = Path(copied.one('SELECT path FROM cache_entries')['path'])
    assert cloned_cache.is_relative_to(destination) and str(cloned_cache) != source_cache
    cloned_cache.unlink()
    assert Path(source_cache).is_file()
    assert verify(destination, tmp_path / 'not-the-library')['ok'] is True
    with pytest.raises(FileExistsError):
        prepare(service.settings.data, destination)
    copied.close()


def test_pending_scans_merge_across_trigger_and_subtree(tmp_path):
    catalog = Catalog(tmp_path / 'catalog.sqlite')
    tasks = Tasks(catalog, Events(), Resources())
    first = tasks.submit('scan', {'library_id': 'qa', 'directory_id': 'a'}, trigger='watcher')
    second = tasks.submit('scan', {'library_id': 'qa', 'directory_id': 'b', 'force': True}, trigger='maintenance')
    assert first['id'] == second['id']
    assert tasks.queue.qsize() == 1
    assert second['payload']['force'] is True and not second['payload'].get('directory_id')
    catalog.close()
