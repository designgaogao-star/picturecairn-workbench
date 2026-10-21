"""Loading contention regressions use generated images and event-controlled workers."""

import contextlib
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageOps

from gallery.app import create_app
from gallery.jobs import Cancelled, Context, Resources
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
