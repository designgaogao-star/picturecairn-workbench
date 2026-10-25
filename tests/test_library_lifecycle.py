"""Library registration changes use generated files only; no native deletion is exercised."""

import shutil
import sqlite3
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from gallery.app import create_app
from gallery.catalog import Catalog
from gallery.jobs import Busy
from gallery.paths import Settings


def finished(client, task_id):
    until = time.monotonic() + 10
    while time.monotonic() < until:
        task = client.get('/api/v1/tasks/' + task_id).json()
        if task['state'] not in ('queued', 'running', 'paused', 'cancelling'):
            assert task['state'] == 'completed', task
            return task
        time.sleep(.01)
    pytest.fail('Temporary library task did not finish')


@pytest.fixture
def world(tmp_path):
    root = tmp_path / 'original'
    package = root / '同名目录' / '图包'
    package.mkdir(parents=True)
    Image.new('RGB', (40, 60), '#345678').save(package / 'a.jpg')
    Image.new('RGB', (60, 40), '#987654').save(package / 'b.jpg')
    (package / 'notes.txt').write_text('non-image content', encoding='utf-8')
    app = create_app(Settings(tmp_path / 'data', root=root, watch=False))
    with TestClient(app) as client:
        for task in client.get('/api/v1/tasks').json()['items']:
            finished(client, task['id'])
        lib = client.get('/api/v1/libraries').json()['items'][0]
        group = client.get(f"/api/v1/libraries/{lib['id']}/groups").json()['items'][0]
        pkg = client.get(f"/api/v1/groups/{group['id']}/packages").json()['items'][0]
        images = client.get(f"/api/v1/packages/{pkg['id']}/images").json()['items']
        yield client, app.state.service, root, lib, group, pkg, images


def test_rename_changes_display_only_and_validates_name(world):
    client, service, root, lib, group, _pkg, images = world
    before = client.get('/api/v1/tasks').json()['total']
    response = client.patch(f"/api/v1/libraries/{lib['id']}", json={'name': '  我的图片  '})
    assert response.status_code == 200, response.text
    assert response.json()['name'] == '我的图片'
    assert response.json()['path'] == str(root.resolve())
    assert response.json()['revision'] > lib['revision']
    assert client.get('/api/v1/tasks').json()['total'] == before
    assert client.get(f"/api/v1/libraries/{lib['id']}").json()['name'] == '我的图片'
    assert client.get(f"/api/v1/images/{images[0]['id']}/context").json()['image']['group_id'] == group['id']
    assert service.catalog.one("SELECT name FROM directories WHERE library_id=? AND rel=''", (lib['id'],))['name'] == '我的图片'
    for name in ('', '   ', 'x' * 121):
        assert client.patch(f"/api/v1/libraries/{lib['id']}", json={'name': name}).status_code == 422


@pytest.mark.parametrize('copy', [False, True])
def test_reconnect_preserves_ids_position_and_reads_new_root(world, copy):
    client, _service, root, lib, group, pkg, images = world
    first = images[0]
    client.put(f"/api/v1/groups/{group['id']}/position", json={'image_id': first['id']}).raise_for_status()
    client.patch(f"/api/v1/groups/{group['id']}/review", json={'state': 'kept'}).raise_for_status()
    target = root.parent / 'relocated'
    if copy:
        shutil.copytree(root, target)
    else:
        root.rename(target)
        scan = client.post('/api/v1/tasks', json={'kind': 'scan', 'library_id': lib['id']}).json()
        assert not finished(client, scan['id'])['result']['online']
    response = client.post(f"/api/v1/libraries/{lib['id']}/reconnect", json={'path': str(target)})
    assert response.status_code == 202, response.text
    assert finished(client, response.json()['id'])['result']['online']
    updated = client.get(f"/api/v1/libraries/{lib['id']}").json()
    assert updated['path'] == str(target.resolve()) and updated['revision'] > lib['revision']
    assert client.get(f"/api/v1/libraries/{lib['id']}/groups").json()['items'][0]['id'] == group['id']
    assert client.get(f"/api/v1/groups/{group['id']}/packages").json()['items'][0]['id'] == pkg['id']
    assert [item['id'] for item in client.get(f"/api/v1/packages/{pkg['id']}/images").json()['items']] == [item['id'] for item in images]
    review = client.get(f"/api/v1/groups/{group['id']}/review").json()
    assert review['image_id'] == first['id'] and review['state'] == 'kept'
    assert client.get(f"/api/v1/images/{first['id']}/original").content == (target / first['rel']).read_bytes()
    assert (target / '同名目录/图包/notes.txt').read_text(encoding='utf-8') == 'non-image content'


def test_remove_and_readd_preserve_data_and_disable_resource_routes(world):
    client, service, root, lib, group, pkg, images = world
    image_id = images[0]['id']
    client.put(f"/api/v1/groups/{group['id']}/position", json={'image_id': image_id}).raise_for_status()
    assert client.get(f'/api/v1/images/{image_id}/thumbnail?edge=400').status_code == 200
    now = time.time()
    service.catalog.execute('INSERT INTO operations(id,target_id,target_kind,path,mode,state,error,created,updated) '
                            'VALUES(?,?,?,?,?,?,?,?,?)',
                            ('retained-log', image_id, 'image', str(root / images[0]['rel']), 'recycle',
                             'failed', 'synthetic failure; no deletion performed', now, now))
    counts = {table: service.catalog.one(f'SELECT COUNT(*) n FROM {table}')['n']
              for table in ('directories', 'packages', 'files', 'review', 'operations', 'cache_entries')}
    response = client.delete(f"/api/v1/libraries/{lib['id']}")
    assert response.status_code == 204, response.text
    assert client.get('/api/v1/libraries').json()['total'] == 0
    assert client.get('/api/v1/operations').json()['items'][0]['id'] == 'retained-log'
    assert client.get('/api/v1/tasks').json()['total'] > 0
    for endpoint in (f"libraries/{lib['id']}", f"libraries/{lib['id']}/groups", f"groups/{group['id']}",
                     f"packages/{pkg['id']}/images", f'images/{image_id}/context',
                     f'images/{image_id}/original', f'images/{image_id}/thumbnail?edge=400'):
        assert client.get('/api/v1/' + endpoint).status_code == 404, endpoint
    assert client.post('/api/v1/tasks', json={'kind': 'scan', 'library_id': lib['id']}).status_code == 404
    assert client.post('/api/v1/operations/delete', json={'targets': [{'kind': 'image', 'id': image_id}]}).status_code == 404
    assert client.patch(f"/api/v1/groups/{group['id']}/review", json={'state': 'marked'}).status_code == 404
    assert (root / images[0]['rel']).is_file()
    for table, count in counts.items():
        assert service.catalog.one(f'SELECT COUNT(*) n FROM {table}')['n'] == count
    response = client.post('/api/v1/libraries', json={'path': str(root)})
    assert response.status_code == 201 and response.json()['id'] == lib['id']
    for task in client.get('/api/v1/tasks?active=true').json()['items']:
        finished(client, task['id'])
    assert client.get(f"/api/v1/groups/{group['id']}/review").json()['image_id'] == image_id
    assert client.get(f'/api/v1/images/{image_id}/thumbnail?edge=400').status_code == 200


@pytest.mark.parametrize('kind', ['probe', 'migrate'])
def test_active_task_prevents_remove_and_reconnect(world, kind):
    client, service, root, lib, *_ = world
    release, entered = threading.Event(), threading.Event()

    def hold(context, _payload):
        entered.set()
        while not release.wait(.01):
            context.check()

    service.tasks.handlers[kind] = hold
    payload = {'root': str(root)} if kind == 'migrate' else {'library_id': lib['id']}
    task = service.tasks.submit(kind, payload)
    try:
        assert entered.wait(2)
        conflict = client.delete(f"/api/v1/libraries/{lib['id']}")
        assert conflict.status_code == 409
        assert conflict.json()['error']['code'] == 'library_busy'
        assert client.post(f"/api/v1/libraries/{lib['id']}/reconnect", json={'path': str(root)}).status_code == 409
        assert client.get(f"/api/v1/libraries/{lib['id']}").json()['path'] == str(root.resolve())
        assert client.patch(f"/api/v1/libraries/{lib['id']}", json={'name': 'Still managed'}).status_code == 200
    finally:
        release.set()
    finished(client, task['id'])


def test_removed_library_stays_removed_on_restart_with_configured_root(tmp_path):
    root = tmp_path / 'configured'
    root.mkdir()
    settings = Settings(tmp_path / 'data', root=root, watch=False)
    with TestClient(create_app(settings)) as client:
        for task in client.get('/api/v1/tasks').json()['items']:
            finished(client, task['id'])
        library = client.get('/api/v1/libraries').json()['items'][0]
        client.delete(f"/api/v1/libraries/{library['id']}").raise_for_status()
        scans = client.get('/api/v1/tasks?kind=scan').json()['total']
    restarted = create_app(Settings(settings.data, root=root, watch=False, maintenance_interval=.02))
    with TestClient(restarted) as client:
        time.sleep(.08)  # Several short maintenance cycles, without a real filesystem watcher.
        assert client.get('/api/v1/libraries').json()['total'] == 0
        assert client.get('/api/v1/tasks?kind=scan').json()['total'] == scans
        assert restarted.state.service.catalog.entity('libraries', library['id'])['managed'] == 0
        assert root.is_dir()


def test_restore_and_reconnect_reject_paths_owned_by_other_library(world):
    client, service, root, lib, *_ = world
    client.delete(f"/api/v1/libraries/{lib['id']}").raise_for_status()
    nested = root / '同名目录'
    child = client.post('/api/v1/libraries', json={'path': str(nested)}).json()
    for task in client.get('/api/v1/tasks?active=true').json()['items']:
        finished(client, task['id'])
    assert client.post('/api/v1/libraries', json={'path': str(root)}).status_code == 409
    assert service.catalog.entity('libraries', lib['id'])['managed'] == 0
    assert client.post(f"/api/v1/libraries/{child['id']}/reconnect", json={'path': str(root)}).status_code == 409
    assert client.get(f"/api/v1/libraries/{child['id']}").json()['path'] == str(nested.resolve())


def test_watcher_stops_old_root_and_ignores_its_late_notifications(world, monkeypatch):
    client, service, root, lib, *_ = world
    watches = []
    started = threading.Condition()

    def watch(path, *, stop_event, **_options):
        exited = threading.Event()
        with started:
            watches.append((path, stop_event, exited))
            started.notify_all()
        stop_event.wait(5)
        exited.set()
        yield from ()

    monkeypatch.setattr('gallery.watcher.watch', watch)
    watcher = service.watcher
    watcher.enabled = True
    old = service.libraries.get(lib['id'])
    watcher.add(old)
    with started:
        assert started.wait_for(lambda: len(watches) == 1, timeout=2)
    relocated = root.parent / 'new-location'
    shutil.copytree(root, relocated)
    response = client.post(f"/api/v1/libraries/{lib['id']}/reconnect", json={'path': str(relocated)})
    response.raise_for_status()
    finished(client, response.json()['id'])
    with started:
        assert started.wait_for(lambda: len(watches) == 2, timeout=2)
    assert watches[0][1].is_set() and watches[0][2].wait(2)
    assert watches[1][0] == relocated.resolve() and not watches[1][1].is_set()
    count = client.get('/api/v1/tasks?kind=scan').json()['total']
    watcher.add(old)
    watcher._submit(old)
    assert client.get('/api/v1/tasks?kind=scan').json()['total'] == count
    client.delete(f"/api/v1/libraries/{lib['id']}").raise_for_status()
    assert watches[1][1].is_set() and watches[1][2].wait(2)
    watcher._submit(service.catalog.entity('libraries', lib['id']))
    assert client.get('/api/v1/tasks?kind=scan').json()['total'] == count
    assert lib['id'] not in watcher.threads


def test_reconnect_invalid_overlap_and_queue_full_do_not_change_root(world, monkeypatch):
    client, service, root, lib, *_ = world
    other = root.parent / 'other'
    other.mkdir()
    registered = client.post('/api/v1/libraries', json={'path': str(other)}).json()
    for task in client.get('/api/v1/tasks?active=true').json()['items']:
        finished(client, task['id'])
    route = f"/api/v1/libraries/{lib['id']}/reconnect"
    for target in (other, other / 'nested', root.parent):
        target.mkdir(exist_ok=True)
        assert client.post(route, json={'path': str(target)}).status_code == 409
    assert client.post(route, json={'path': str(root.parent / 'missing')}).status_code in (404, 422)
    assert client.get(f"/api/v1/libraries/{lib['id']}").json()['path'] == str(root.resolve())
    assert client.get(f"/api/v1/libraries/{registered['id']}").status_code == 200
    target = root.parent / 'available'
    target.mkdir()

    def full():
        raise Busy('isolated queue limit')

    monkeypatch.setattr(service.tasks, 'ensure_capacity', full)
    assert client.post(route, json={'path': str(target)}).status_code == 503
    assert client.get(f"/api/v1/libraries/{lib['id']}").json()['path'] == str(root.resolve())


def test_v7_catalog_migration_keeps_existing_library(tmp_path):
    path = tmp_path / 'old.sqlite'
    sql = Path(__file__).resolve().parents[1] / 'gallery/sql'
    with sqlite3.connect(path) as db:
        for migration in sorted(sql.glob('00[1-7]_*.sql')):
            db.executescript(migration.read_text(encoding='utf-8'))
        db.execute('PRAGMA user_version=7')
        db.execute('INSERT INTO libraries(id,name,path,path_key) VALUES(?,?,?,?)',
                   ('old-id', 'Old library', str(tmp_path), str(tmp_path).lower()))
    catalog = Catalog(path)
    assert catalog.one('PRAGMA user_version')['user_version'] == 8
    assert catalog.libraries()[0]['id'] == 'old-id'
    assert catalog.entity('libraries', 'old-id')['managed'] == 1
