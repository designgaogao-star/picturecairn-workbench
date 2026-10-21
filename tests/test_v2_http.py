"""Source and packaged HTTP smoke test using the same temporary fixture."""

import json
import os
import subprocess
import sys
import time
from html.parser import HTMLParser
from pathlib import Path

import httpx2 as httpx
import pytest
from PIL import Image


@pytest.fixture(scope='module')
def running(tmp_path_factory):
    temporary = tmp_path_factory.mktemp('v2-process')
    root, data = temporary / 'library', temporary / 'data'
    package = root / '作者' / '图包'
    package.mkdir(parents=True)
    Image.new('RGB', (1600, 2000), '#66785d').save(package / 'a.jpg')
    Image.new('RGB', (800, 600), '#c58993').save(package / 'b.png')
    (package / 'not-an-image.mp4').write_bytes(b'keep all non-image files')
    ready = temporary / 'ready.json'
    backend = os.environ.get('GALLERY_TEST_BACKEND')
    command = [backend] if backend else [sys.executable, '-m', 'gallery']
    command += ['--port', '0', '--data', str(data), '--root', str(root), '--ready-file', str(ready), '--no-watch', '--no-open']
    project = Path(__file__).resolve().parents[1]
    environment = {**os.environ, 'GALLERY_DESKTOP_TOKEN': 'temporary-test-token'}
    environment.pop('GALLERY_LEGACY', None)
    with (temporary / 'process.log').open('w', encoding='utf-8') as log:
        start = time.perf_counter()
        process = subprocess.Popen(command, cwd=project, env=environment, stdout=log, stderr=log)
        try:
            until = time.monotonic() + 30
            while True:
                assert process.poll() is None, (temporary / 'process.log').read_text(encoding='utf-8')
                if time.monotonic() > until:
                    pytest.fail('Backend did not publish its handshake')
                try:
                    descriptor = json.loads(ready.read_text(encoding='utf-8'))
                    break
                except (FileNotFoundError, PermissionError):
                    pass
                time.sleep(.02)
            startup = time.perf_counter() - start
            with httpx.Client(base_url=descriptor['url'], timeout=15) as client:
                for _ in range(500):
                    tasks = client.get('/api/v1/tasks').json()['items']
                    if tasks and all(t['state'] == 'completed' for t in tasks):
                        break
                    time.sleep(.02)
                else:
                    pytest.fail(str(tasks))
                yield client, descriptor, data, startup
                with client.stream('GET', '/api/v1/events') as events:
                    assert next(events.iter_lines())
                    response = client.post('/api/v1/system/shutdown', headers={'X-Gallery-Desktop': 'temporary-test-token'})
                    assert response.status_code == 202
                    process.wait(timeout=8)
            assert process.returncode == 0
            assert not ready.exists()
            assert ' ERROR ' not in (data / 'server.log').read_text(encoding='utf-8')
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)


def test_process_handshake_and_index(running):
    client, descriptor, data, startup = running
    health = client.get('/api/v1/health').json()
    assert health['instance_id'] == descriptor['instance_id']
    assert health['api_version'] == '1'
    assert (data / 'catalog.sqlite').is_file()
    assert startup < 10
    lib = client.get('/api/v1/libraries').json()['items'][0]
    group = client.get(f"/api/v1/libraries/{lib['id']}/groups").json()['items'][0]
    assert group['image_count'] == 2


def test_process_image_and_static_assets(running):
    client, _descriptor, _data, _startup = running
    lib = client.get('/api/v1/libraries').json()['items'][0]
    group = client.get(f"/api/v1/libraries/{lib['id']}/groups").json()['items'][0]
    package = client.get(f"/api/v1/groups/{group['id']}/packages").json()['items'][0]
    image = client.get(f"/api/v1/packages/{package['id']}/images").json()['items'][0]
    response = client.get(f"/api/v1/images/{image['id']}/thumbnail?edge=800")
    assert response.status_code == 200 and response.headers['content-type'] == 'image/jpeg'
    response = client.get(f"/api/v1/images/{image['id']}/original", headers={'Range': 'bytes=0-15'})
    assert response.status_code == 206 and len(response.content) == 16
    response = client.get('/')
    assert response.status_code == 200
    assert '<div id="app">' in response.text

    class Assets(HTMLParser):
        def __init__(self):
            super().__init__()
            self.scripts = []
            self.styles = []

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == 'script' and attrs.get('src'):
                self.scripts.append(attrs['src'])
            if tag == 'link' and attrs.get('rel') == 'stylesheet':
                self.styles.append(attrs['href'])

    assets = Assets()
    assets.feed(response.text)
    assert assets.scripts and assets.styles
    for asset in assets.scripts + assets.styles:
        assert asset.startswith('/assets/')
        assert client.get(asset).status_code == 200
    assert client.get('/openapi.json').json()['info']['version'] == '2.0.0'


def test_process_sse_and_shutdown_protection(running):
    client, descriptor, _data, _startup = running
    with client.stream('GET', '/api/v1/events') as response:
        assert response.status_code == 200
        assert response.headers['content-type'].startswith('text/event-stream')
        lines = iter(response.iter_lines())
        first = [next(lines) for _ in range(2)]
        assert any('snapshot' in line for line in first)
    assert client.post('/api/v1/system/shutdown').status_code == 403
    assert descriptor['pid'] > 0


def test_process_sse_reconnect_after_instance_restart(running):
    client, _descriptor, _data, _startup = running
    with client.stream('GET', '/api/v1/events', headers={'Last-Event-ID': '999999999'}) as response:
        events = []
        for line in response.iter_lines():
            if line.startswith('event: '):
                events.append(line.removeprefix('event: '))
                if len(events) == 2:
                    break
        assert events == ['snapshot', 'reset']
    assert client.get('/api/v1/events', headers={'Last-Event-ID': 'invalid'}).status_code == 422


def test_process_sse_repeated_disconnects(running):
    client, _descriptor, _data, _startup = running
    for _ in range(8):
        with client.stream('GET', '/api/v1/events') as response:
            assert next(response.iter_lines()).startswith('event: snapshot')
        assert client.get('/api/v1/health').status_code == 200


@pytest.mark.skipif(os.name != 'nt', reason='Windows Recycle Bin')
def test_process_recycles_temporary_image(running):
    client, _descriptor, _data, _startup = running
    library = client.get('/api/v1/libraries').json()['items'][0]
    group = client.get(f"/api/v1/libraries/{library['id']}/groups").json()['items'][0]
    package = client.get(f"/api/v1/groups/{group['id']}/packages").json()['items'][0]
    image = client.get(f"/api/v1/packages/{package['id']}/images").json()['items'][0]
    request = client.post('/api/v1/operations/delete', json={'targets': [{'kind': 'image', 'id': image['id']}]})
    assert request.status_code == 202
    for _ in range(500):
        job = client.get('/api/v1/tasks/' + request.json()['id']).json()
        if job['state'] in ('completed', 'failed'):
            break
        time.sleep(.02)
    assert job['state'] == 'completed', job
    assert job['result']['failed'] == 0, job
    assert client.get(f"/api/v1/images/{image['id']}/original").status_code == 404
