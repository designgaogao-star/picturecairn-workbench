"""Source and packaged HTTP smoke test using the same temporary fixture."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
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
                response = client.post('/api/v1/system/shutdown', headers={'X-Gallery-Desktop': 'temporary-test-token'})
                assert response.status_code == 202
            process.wait(timeout=25)
            assert process.returncode == 0
            assert not ready.exists()
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
    lib = client.get('/api/v1/libraries').json()[0]
    group = client.get(f"/api/v1/libraries/{lib['id']}/groups").json()['items'][0]
    assert group['image_count'] == 2


def test_process_image_and_static_assets(running):
    client, _descriptor, _data, _startup = running
    lib = client.get('/api/v1/libraries').json()[0]
    group = client.get(f"/api/v1/libraries/{lib['id']}/groups").json()['items'][0]
    package = client.get(f"/api/v1/groups/{group['id']}/packages").json()['items'][0]
    image = client.get(f"/api/v1/packages/{package['id']}/images").json()['items'][0]
    response = client.get(f"/api/v1/images/{image['id']}/thumbnail?edge=800")
    assert response.status_code == 200 and response.headers['content-type'] == 'image/webp'
    response = client.get(f"/api/v1/images/{image['id']}/original", headers={'Range': 'bytes=0-15'})
    assert response.status_code == 206 and len(response.content) == 16
    assert client.get('/').status_code == 200
    assert 'lucide' in client.get('/lucide.js').text.lower()
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
