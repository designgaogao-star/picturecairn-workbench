"""Loading contention regressions use generated images and event-controlled workers."""

import asyncio
import contextlib
import socket
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
import uvicorn
from fastapi.testclient import TestClient
from PIL import Image, ImageOps
from starlette.requests import Request

from gallery.app import create_app
from gallery.jobs import Busy, Cancelled, Context, Resources
from gallery.paths import Settings


@pytest.fixture
def images(tmp_path):
    root = tmp_path / 'library'
    folder = root / 'group' / 'package'
    folder.mkdir(parents=True)
    for i in range(3):
        Image.new('RGB', (300, 200), (40 + i * 20, 80, 120)).save(folder / f'{i}.jpg')
    app = create_app(Settings(tmp_path / 'data', root=root, watch=False))
    with TestClient(app) as client:
        deadline = time.monotonic() + 10
        while client.get('/api/v1/tasks', params={'active': True}).json()['total']:
            assert time.monotonic() < deadline, 'Temporary catalog did not finish scanning'
            time.sleep(.01)
        service = app.state.service
        rows = service.catalog.rows('SELECT * FROM files WHERE is_image=1 ORDER BY name')
        assert len(rows) == 3
        yield service.images, rows, root


def test_encoding_releases_volume_but_keeps_decode_reservation(images, monkeypatch):
    loader, rows, _root = images
    entered, release, second_done = threading.Event(), threading.Event(), threading.Event()
    save = Image.Image.save
    first_key = loader.key(rows[0], 800)
    second_edge = next(edge for edge in (400, 800, 1600, 2560, 4200)
                       if int(loader.key(rows[1], edge)[:2], 16) % 64 != int(first_key[:2], 16) % 64)

    def gated_save(image, path, *args, **kwargs):
        if path.stem == first_key:
            entered.set()
            assert release.wait(10), 'Test encoder was not released'
        return save(image, path, *args, **kwargs)

    monkeypatch.setattr(Image.Image, 'save', gated_save)
    with ThreadPoolExecutor(max_workers=2) as workers:
        first = workers.submit(loader.get, rows[0]['id'], 800)
        try:
            assert entered.wait(3)
            second = workers.submit(loader.get, rows[1]['id'], second_edge)
            second.add_done_callback(lambda _future: second_done.set())
            assert second_done.wait(2), 'Encoding one image still blocks reading another from the same volume'
            assert second.result().is_file()
            assert loader.resources.decode_count == 1, 'Encoding must retain its memory reservation'
            assert loader.resources.decode_used > 0
        finally:
            release.set()
        assert first.result(timeout=3).is_file()
    assert loader.resources.decode_count == loader.resources.decode_used == 0


def test_waiting_for_decode_does_not_hold_source_volume(images, monkeypatch):
    loader, rows, root = images
    waiting = threading.Event()
    decode = loader.resources.decode

    @contextlib.contextmanager
    def observed_decode(*args, **kwargs):
        waiting.set()
        with decode(*args, **kwargs):
            yield

    monkeypatch.setattr(loader.resources, 'decode', observed_decode)
    with ThreadPoolExecutor(max_workers=1) as workers:
        with decode(loader.resources.decode_limit):
            future = workers.submit(loader.get, rows[0]['id'], 800)
            assert waiting.wait(3)
            deadline = time.monotonic() + 1

            def checkpoint():
                assert time.monotonic() < deadline, 'Waiting for decode holds the source volume'

            with loader.resources.io(root, foreground=True, checkpoint=checkpoint):
                pass
        assert future.result(timeout=3).is_file()


def test_foreground_decode_runs_before_waiting_background():
    resources = Resources(decode_bytes=128)
    background_waiting, foreground_waiting = threading.Event(), threading.Event()
    order = []

    def acquire(name, foreground, waiting):
        with resources.decode(128, checkpoint=waiting.set, foreground=foreground):
            order.append(name)

    with ThreadPoolExecutor(max_workers=2) as workers:
        with resources.decode(128):
            background = workers.submit(acquire, 'background', False, background_waiting)
            assert background_waiting.wait(1)
            foreground = workers.submit(acquire, 'foreground', True, foreground_waiting)
            assert foreground_waiting.wait(1)
        foreground.result(timeout=3)
        background.result(timeout=3)
    assert order == ['foreground', 'background']
    assert resources.decode_count == resources.decode_used == 0


def test_cancelled_foreground_decode_does_not_starve_background():
    resources = Resources(decode_bytes=128)
    waiting, cancel = threading.Event(), threading.Event()

    def checkpoint():
        waiting.set()
        if cancel.is_set():
            raise Cancelled()

    def foreground():
        with resources.decode(128, checkpoint=checkpoint, foreground=True):
            pytest.fail('Cancelled request acquired decode memory')

    with ThreadPoolExecutor(max_workers=1) as workers:
        with resources.decode(128):
            future = workers.submit(foreground)
            assert waiting.wait(1)
            cancel.set()
            with pytest.raises(Cancelled):
                future.result(timeout=2)
        with resources.decode(128):
            pass
    assert resources.decode_count == resources.decode_used == 0


def test_encoder_failure_releases_memory_volume_and_source_file(images, monkeypatch):
    loader, rows, root = images

    def fail(*_args, **_kwargs):
        raise OSError('Simulated cache write failure')

    with monkeypatch.context() as patch:
        patch.setattr(Image.Image, 'save', fail)
        with pytest.raises(OSError, match='Simulated cache write failure'):
            loader.get(rows[0]['id'], 800)
    assert loader.resources.decode_count == loader.resources.decode_used == 0
    assert not loader.resources.active
    assert not loader.resources.decode_waiters
    source = root / rows[0]['rel']
    held = source.with_suffix('.held')
    source.rename(held)
    held.rename(source)
    assert loader.get(rows[0]['id'], 800).is_file()


def test_changed_source_is_rejected_before_decoding(images):
    loader, rows, root = images
    (root / rows[0]['rel']).write_bytes(b'Changed file is no longer an image')
    with pytest.raises(ValueError, match='Image changed'):
        loader.get(rows[0]['id'], 800)
    assert loader.resources.decode_count == loader.resources.decode_used == 0


def test_source_changed_while_waiting_for_decode_is_rejected(images, monkeypatch):
    loader, rows, root = images
    waiting = threading.Event()
    decode = loader.resources.decode

    @contextlib.contextmanager
    def observed_decode(*args, **kwargs):
        waiting.set()
        with decode(*args, **kwargs):
            yield

    monkeypatch.setattr(loader.resources, 'decode', observed_decode)
    with ThreadPoolExecutor(max_workers=1) as workers:
        with decode(loader.resources.decode_limit):
            future = workers.submit(loader.get, rows[0]['id'], 800)
            assert waiting.wait(3)
            with Image.new('RGB', (160, 180), 'red') as replacement:
                replacement.save(root / rows[0]['rel'])
        with pytest.raises(ValueError, match='Image changed'):
            future.result(timeout=3)
    assert loader.resources.decode_count == loader.resources.decode_used == 0
    assert not loader.resources.active
    assert loader.cached(loader.key(rows[0], 800)) is None


@pytest.mark.parametrize('pause_at', ['before_read', 'after_read'])
def test_pausing_during_preview_does_not_retain_decode_reservation(images, monkeypatch, pause_at):
    loader, rows, _root = images
    context = Context(SimpleNamespace(stopping=threading.Event()), 'temporary-prewarm')
    paused, done = threading.Event(), threading.Event()
    decode, transpose = loader.resources.decode, ImageOps.exif_transpose

    def pause():
        context.paused.set()
        paused.set()

    @contextlib.contextmanager
    def pause_before_read(*args, **kwargs):
        with decode(*args, **kwargs):
            pause()
            yield

    def pause_after_read(*args, **kwargs):
        frame = transpose(*args, **kwargs)
        pause()
        return frame

    if pause_at == 'before_read':
        monkeypatch.setattr(loader.resources, 'decode', pause_before_read)
    else:
        monkeypatch.setattr(ImageOps, 'exif_transpose', pause_after_read)
    with ThreadPoolExecutor(max_workers=1) as workers:
        future = workers.submit(loader.generate, rows[0], 800, loader.key(rows[0], 800), context)
        future.add_done_callback(lambda _future: done.set())
        try:
            assert paused.wait(3)
            assert done.wait(1), 'Pause retained decode memory instead of finishing the current image'
        finally:
            context.paused.clear()
        assert future.result(timeout=3).is_file()
    assert loader.resources.decode_count == loader.resources.decode_used == 0
    with pytest.raises(Cancelled):
        context.cancel.set()
        context.check()


def test_cancelling_same_image_waiter_does_not_wait_for_encoder(images, monkeypatch):
    loader, rows, _root = images
    entered, release, waiting = threading.Event(), threading.Event(), threading.Event()
    save = Image.Image.save
    context = Context(SimpleNamespace(stopping=threading.Event()), 'temporary-prewarm')
    key = loader.key(rows[0], 800)

    def gated_save(image, path, *args, **kwargs):
        entered.set()
        assert release.wait(10)
        return save(image, path, *args, **kwargs)

    check = context.check

    def observed_check():
        waiting.set()
        check()

    monkeypatch.setattr(context, 'check', observed_check)
    monkeypatch.setattr(Image.Image, 'save', gated_save)
    with ThreadPoolExecutor(max_workers=2) as workers:
        first = workers.submit(loader.get, rows[0]['id'], 800)
        try:
            assert entered.wait(3)
            second = workers.submit(loader.generate, rows[0], 800, key, context)
            assert waiting.wait(2)
            context.cancel.set()
            with pytest.raises(Cancelled):
                second.result(timeout=1)
        finally:
            release.set()
        assert first.result(timeout=3).is_file()


def wait_until(predicate, message):
    deadline = time.monotonic() + 3
    while not predicate():
        assert time.monotonic() < deadline, message
        time.sleep(.01)


def test_cancelled_queued_preview_never_reads_source_and_retains_queue_bound(images, monkeypatch):
    loader, rows, _root = images
    release, cancelled = threading.Event(), threading.Event()
    occupied = [threading.Event(), threading.Event()]
    loader.slots = threading.BoundedSemaphore(1)
    opened = []
    original_open = Image.open

    def occupy(index):
        occupied[index].set()
        assert release.wait(10)

    def observe_open(*args, **kwargs):
        opened.append(args[0])
        return original_open(*args, **kwargs)

    monkeypatch.setattr(Image, 'open', observe_open)
    blockers = [loader.pool.submit(occupy, index) for index in range(2)]
    with ThreadPoolExecutor(max_workers=1) as workers:
        request = workers.submit(loader.get, rows[0]['id'], 800, cancelled=cancelled)
        try:
            assert all(event.wait(3) for event in occupied)
            wait_until(lambda: loader.pending or request.done(), 'Preview was not queued')
            cancelled.set()
            with pytest.raises(Cancelled):
                request.result(timeout=1)
            assert not opened
            with pytest.raises(Busy):
                loader.get(rows[1]['id'], 800)
        finally:
            release.set()
            for blocker in blockers:
                blocker.result(timeout=3)
        wait_until(lambda: not loader.pending, 'Cancelled queue entry did not drain')
    assert not opened, 'A queued preview read its source after its last subscriber left'
    assert loader.get(rows[1]['id'], 800).is_file()
    assert loader.resources.decode_count == loader.resources.decode_used == 0


def test_cancelling_one_preview_subscriber_keeps_shared_generation(images, monkeypatch):
    loader, rows, _root = images
    entered, release, cancelled = threading.Event(), threading.Event(), threading.Event()
    save = Image.Image.save
    saves = []

    def gated_save(image, path, *args, **kwargs):
        saves.append(path)
        entered.set()
        assert release.wait(10)
        return save(image, path, *args, **kwargs)

    monkeypatch.setattr(Image.Image, 'save', gated_save)
    with ThreadPoolExecutor(max_workers=2) as workers:
        first = workers.submit(loader.get, rows[0]['id'], 800, cancelled=cancelled)
        try:
            assert entered.wait(3)
            second = workers.submit(loader.get, rows[0]['id'], 800)
            key = loader.key(rows[0], 800)
            wait_until(lambda: loader.pending[key].subscribers == 2, 'Second subscriber did not join')
            cancelled.set()
            with pytest.raises(Cancelled):
                first.result(timeout=1)
            assert not second.done()
        finally:
            release.set()
        assert second.result(timeout=3).is_file()
    assert len(saves) == 1
    assert loader.resources.decode_count == loader.resources.decode_used == 0


def test_cancelled_preview_releases_decode_waiter_without_poisoning_image(images, monkeypatch):
    loader, rows, _root = images
    waiting, cancelled = threading.Event(), threading.Event()
    decode = loader.resources.decode

    @contextlib.contextmanager
    def observed_decode(*args, **kwargs):
        waiting.set()
        with decode(*args, **kwargs):
            yield

    monkeypatch.setattr(loader.resources, 'decode', observed_decode)
    with ThreadPoolExecutor(max_workers=1) as workers:
        with decode(loader.resources.decode_limit):
            future = workers.submit(loader.get, rows[0]['id'], 800, cancelled=cancelled)
            try:
                assert waiting.wait(3)
                cancelled.set()
                with pytest.raises(Cancelled):
                    future.result(timeout=1)
                wait_until(lambda: not loader.pending, 'Cancelled decode waiter did not exit')
                assert loader.resources.decode_waiters == 0
                assert not loader.resources.active
                assert not loader.catalog.entity('files', rows[0]['id'])['error']
            finally:
                cancelled.set()
    assert loader.resources.decode_count == loader.resources.decode_used == 0
    assert loader.get(rows[0]['id'], 800).is_file()


def test_thumbnail_http_disconnect_releases_its_subscriber(tmp_path, monkeypatch):
    app = create_app(Settings(tmp_path / 'data', watch=False))
    endpoint = next(route.endpoint for route in app.routes
                    if getattr(route, 'path', '') == '/api/v1/images/{image_id}/thumbnail')
    entered, stopped = threading.Event(), threading.Event()

    def wait_for_disconnect(_image_id, _edge, _version, *, cancelled):
        entered.set()
        assert cancelled.wait(3), 'HTTP disconnect did not reach image loading'
        stopped.set()
        raise Cancelled()

    monkeypatch.setattr(app.state.service.images, 'get', wait_for_disconnect)

    async def exercise():
        disconnected = asyncio.Event()

        async def receive():
            await disconnected.wait()
            return {'type': 'http.disconnect'}

        request = Request({'type': 'http', 'method': 'GET', 'headers': []}, receive)
        response = asyncio.create_task(endpoint(request, 'temporary-image'))
        assert await asyncio.to_thread(entered.wait, 3)
        disconnected.set()
        assert (await asyncio.wait_for(response, 3)).status_code == 499
        assert stopped.is_set()

    with TestClient(app):
        asyncio.run(exercise())


def test_source_timeout_is_not_mistaken_for_a_pending_future(images, monkeypatch):
    loader, rows, _root = images
    cancelled = threading.Event()

    def fail_open(*_args, **_kwargs):
        raise TimeoutError('Simulated source timeout')

    monkeypatch.setattr(Image, 'open', fail_open)
    with ThreadPoolExecutor(max_workers=1) as workers:
        request = workers.submit(loader.get, rows[0]['id'], 800, cancelled=cancelled)
        try:
            with pytest.raises(TimeoutError, match='Simulated source timeout'):
                request.result(timeout=1)
        finally:
            cancelled.set()
    assert loader.resources.decode_count == loader.resources.decode_used == 0


def test_real_http_disconnect_reaches_preview_through_middleware(tmp_path, monkeypatch):
    app = create_app(Settings(tmp_path / 'data', watch=False))
    entered, stopped = threading.Event(), threading.Event()

    def wait_for_disconnect(_image_id, _edge, _version, *, cancelled):
        entered.set()
        assert cancelled.wait(3), 'Socket disconnect was lost in the HTTP middleware'
        stopped.set()
        raise Cancelled()

    monkeypatch.setattr(app.state.service.images, 'get', wait_for_disconnect)
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, log_config=None, access_log=False))

        def serve():
            asyncio.run(server.serve(sockets=[listener]),
                        loop_factory=asyncio.SelectorEventLoop if sys.platform == 'win32' else None)

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        try:
            wait_until(lambda: server.started, 'Isolated HTTP server did not start')
            with socket.create_connection(('127.0.0.1', port), timeout=3) as client:
                client.sendall(f'GET /api/v1/images/temporary-image/thumbnail HTTP/1.1\r\n'
                               f'Host: 127.0.0.1:{port}\r\n\r\n'.encode())
                assert entered.wait(3)
            assert stopped.wait(1), 'HTTP peer closed but its preview kept waiting'
        finally:
            server.should_exit = True
            thread.join(timeout=5)
            assert not thread.is_alive(), 'Isolated HTTP server did not shut down'


def test_new_subscriber_replaces_cancelled_generation_without_losing_shared_entry(images, monkeypatch):
    loader, rows, _root = images
    entered = [threading.Event(), threading.Event()]
    release = [threading.Event(), threading.Event()]
    cancelled = threading.Event()
    loader.slots = threading.BoundedSemaphore(2)
    save = Image.Image.save
    calls = []
    key = loader.key(rows[0], 800)

    def gated_save(image, path, *args, **kwargs):
        index = len(calls)
        calls.append(path)
        entered[index].set()
        assert release[index].wait(10)
        return save(image, path, *args, **kwargs)

    monkeypatch.setattr(Image.Image, 'save', gated_save)
    with ThreadPoolExecutor(max_workers=2) as workers:
        first = workers.submit(loader.get, rows[0]['id'], 800, cancelled=cancelled)
        try:
            assert entered[0].wait(3)
            previous = loader.pending[key]
            cancelled.set()
            with pytest.raises(Cancelled):
                first.result(timeout=1)
            second = workers.submit(loader.get, rows[0]['id'], 800)
            wait_until(lambda: loader.pending.get(key) is not previous, 'New request joined cancelled work')
            replacement = loader.pending[key]
            release[0].set()
            assert entered[1].wait(3)
            # The barrier runs only after the old worker's completion callback has returned.
            loader.pool.submit(lambda: None).result(timeout=3)
            assert loader.pending[key] is replacement
            assert loader.cached(key) is None, 'Cancelled encoding was published as a completed derivative'
            third = workers.submit(loader.get, rows[0]['id'], 800)
            wait_until(lambda: replacement.subscribers == 2, 'New subscribers no longer share the replacement')
        finally:
            for event in release:
                event.set()
        assert second.result(timeout=3) == third.result(timeout=3)
    assert len(calls) == 2
    assert not loader.catalog.entity('files', rows[0]['id'])['error']
    assert loader.resources.decode_count == loader.resources.decode_used == 0
