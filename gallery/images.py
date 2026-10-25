"""Fixed-size, versioned derivatives with bounded cold reads and decode memory."""

import contextlib
import hashlib
import json
import os
import shutil
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageCms, ImageOps

from gallery.catalog import content_version
from gallery.jobs import Busy, Cancelled

EDGES = (400, 800, 1600, 2560, 4200)
PIPELINE = 'pillow-srgb-exif-jpeg-alpha-webp-v2'


@dataclass
class PendingImage:
    cancelled: threading.Event = field(default_factory=threading.Event)
    subscribers: int = 0
    future: Future | None = None


class Images:
    def __init__(self, catalog, access, resources, settings):
        self.catalog, self.access, self.resources, self.settings = catalog, access, resources, settings
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='gallery-image')
        self.slots = threading.BoundedSemaphore(64)
        self.lock = threading.RLock()
        self.pending = {}
        self.stopping = threading.Event()
        self.generation_locks = [threading.Lock() for _ in range(64)]
        self.cache_pressure = lambda: None
        self.generated = 0

    def key(self, image, edge):
        return hashlib.sha256(f"{image['id']}|{image['size']}|{image['mtime_ns']}|{edge}|{PIPELINE}".encode()).hexdigest()

    def cached(self, key):
        entry = self.catalog.one('SELECT * FROM cache_entries WHERE key=?', (key,))
        if entry and Path(entry['path']).is_file():
            if time.time() - entry['accessed'] > 60:
                self.catalog.execute('UPDATE cache_entries SET accessed=? WHERE key=?', (time.time(), key))
            return Path(entry['path'])
        return None

    def get(self, image_id, edge, version=None, *, cancelled=None):
        self._check(cancelled)
        image = self.catalog.entity('files', image_id)
        if not image or not image['is_image'] or not image['present']:
            raise FileNotFoundError('Image not found')
        self.access.library(image['library_id'])
        if edge not in EDGES:
            raise ValueError('Unsupported image size')
        if not image['mtime_ns']:
            path = self.access.path(image)
            with self.resources.io(path, foreground=True, checkpoint=lambda: self._check(cancelled)):
                stat = path.stat()
            self.catalog.execute('UPDATE files SET size=?,mtime_ns=? WHERE id=? AND mtime_ns=0',
                                 (stat.st_size, stat.st_mtime_ns, image_id))
            image['size'], image['mtime_ns'] = stat.st_size, stat.st_mtime_ns
        if version and version != content_version(image['size'], image['mtime_ns']):
            raise ValueError('Image version changed; refresh the image list')
        key = self.key(image, edge)
        cached = self.cached(key)
        if cached:
            return cached
        with self.lock:
            pending = self.pending.get(key)
            if pending is None or pending.cancelled.is_set():
                if self.stopping.is_set() or not self.slots.acquire(blocking=False):
                    raise Busy('Image queue is full')
                pending = PendingImage()
                self.pending[key] = pending
                try:
                    pending.future = self.pool.submit(self.generate, image, edge, key, cancelled=pending.cancelled)
                except RuntimeError:
                    self._finish(key, pending)
                    raise Busy('Image service is stopping') from None
                pending.future.add_done_callback(lambda _f: self._finish(key, pending))
            pending.subscribers += 1
        try:
            if cancelled is None:
                return pending.future.result()
            while True:
                self._check(cancelled)
                try:
                    return pending.future.result(timeout=.05)
                except TimeoutError:
                    if pending.future.done():
                        return pending.future.result()
        finally:
            with self.lock:
                pending.subscribers -= 1
                if not pending.subscribers:
                    pending.cancelled.set()

    def _finish(self, key, pending):
        with self.lock:
            if self.pending.get(key) is pending:
                self.pending.pop(key)
            # A cancelled executor item still occupies the queue until a worker consumes it.
            self.slots.release()

    def _check(self, cancelled=None):
        if cancelled is not None and cancelled.is_set():
            raise Cancelled()
        if self.stopping.is_set():
            raise Busy('Image service is stopping')

    def generate(self, image, edge, key, context=None, *, cancelled=None):
        checkpoint = context.check if context else lambda: self._check(cancelled)
        checkpoint()
        lock = self.generation_locks[int(key[:2], 16) % 64]
        while not lock.acquire(timeout=.05):
            checkpoint()
        try:
            return self._generate(image, edge, key, context, cancelled=cancelled)
        finally:
            lock.release()

    def _generate(self, image, edge, key, context=None, *, cancelled=None):
        cached = self.cached(key)
        if cached:
            return cached
        # Pause at image boundaries; pausing with a generation lock or memory held would stall browsing.
        checkpoint = context.check_cancelled if context else lambda: self._check(cancelled)
        checkpoint()
        legacy = self._reuse_legacy(image, edge, key)
        if legacy:
            return legacy
        path = self.access.path(image)
        cache_dir = self.settings.data / 'derivatives' / key[:2]
        cache_dir.mkdir(parents=True, exist_ok=True)
        target = cache_dir / (key + '.webp')
        try:
            with contextlib.ExitStack() as cleanup:
                with self.resources.io(path, foreground=context is None, checkpoint=checkpoint):
                    stat = path.stat()
                    if (stat.st_size, stat.st_mtime_ns) != (image['size'], image['mtime_ns']):
                        raise ValueError('Image changed; refresh the library')
                    opened = cleanup.enter_context(Image.open(path))
                    width, height = opened.size
                    animated = bool(getattr(opened, 'is_animated', False))
                    orientation = opened.getexif().get(274, 1)
                    if orientation in (5, 6, 7, 8):
                        width, height = height, width
                    opened.draft('RGB', (edge, edge))
                    estimate = opened.width * opened.height * 8 + edge * edge * 8
                # Never hold a source volume while waiting for memory or encoding to the local cache.
                cleanup.enter_context(self.resources.decode(estimate, checkpoint, foreground=context is None))
                with self.resources.io(path, foreground=context is None, checkpoint=checkpoint):
                    stat = path.stat()
                    if (stat.st_size, stat.st_mtime_ns) != (image['size'], image['mtime_ns']):
                        raise ValueError('Image changed; refresh the library')
                    frame = cleanup.enter_context(ImageOps.exif_transpose(opened))
                opened.close()
                checkpoint()
                frame.thumbnail((edge, edge), Image.Resampling.LANCZOS)
                profile = frame.info.get('icc_profile')
                if profile:
                    import io
                    try:
                        source = ImageCms.ImageCmsProfile(io.BytesIO(profile))
                        frame = cleanup.enter_context(ImageCms.profileToProfile(
                            frame, source, ImageCms.createProfile('sRGB'),
                            outputMode='RGBA' if 'A' in frame.getbands() else 'RGB'))
                    except (ImageCms.PyCMSError, OSError):
                        pass
                if frame.mode not in ('RGB', 'RGBA'):
                    frame = cleanup.enter_context(frame.convert('RGBA' if 'transparency' in frame.info else 'RGB'))
                opaque = frame.mode == 'RGB'
                if opaque:
                    target = target.with_suffix('.jpg')
                temporary = target.with_suffix('.tmp')
                checkpoint()
                try:
                    if opaque:
                        frame.save(temporary, 'JPEG', quality=82 if edge > 800 else 75, optimize=False)
                    else:
                        frame.save(temporary, 'WEBP', quality=82 if edge > 800 else 75, method=1)
                    checkpoint()
                    os.replace(temporary, target)
                finally:
                    with contextlib.suppress(OSError):
                        temporary.unlink(missing_ok=True)
            self.catalog.execute('UPDATE files SET width=?,height=?,animated=?,error=NULL WHERE id=? AND mtime_ns=?',
                                 (width, height, int(animated), image['id'], image['mtime_ns']))
            self.catalog.execute('INSERT OR REPLACE INTO cache_entries VALUES(?,?,?,?)',
                                 (key, str(target), target.stat().st_size, time.time()))
            self.generated += 1
            if self.generated % 64 == 0:
                self.cache_pressure()
            return target
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            self.catalog.execute('UPDATE files SET error=? WHERE id=?', (str(exc), image['id']))
            raise

    def _reuse_legacy(self, image, edge, key):
        if Path(image['name']).suffix.lower() not in ('.jpg', '.jpeg') or not image['mtime_ns']:
            return None
        library = self.catalog.entity('libraries', image['library_id'])
        target = str(Path(library['path']) / image['rel'])
        for imported in self.catalog.rows('SELECT report FROM imports'):
            report = json.loads(imported['report'])
            if report['library_id'] != image['library_id']:
                continue
            for quality in (72, 80, 84):
                old_key = hashlib.md5(f"{target}|{image['mtime_ns']}|{image['size']}|{edge}|{quality}".encode()).hexdigest()
                old_path = Path(report['legacy_thumbs']) / (old_key + '.jpg')
                if old_path.is_file():
                    destination = self.settings.data / 'derivatives' / key[:2] / (key + '.jpg')
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(old_path, destination)
                    self.catalog.execute('INSERT OR REPLACE INTO cache_entries VALUES(?,?,?,?)',
                                         (key, str(destination), destination.stat().st_size, time.time()))
                    self.cache_pressure()
                    return destination
        return None

    def prewarm(self, context, payload):
        scope, scope_id = ('package_id', payload['package_id']) if payload.get('package_id') else ('group_id', payload['group_id'])
        total = self.catalog.one(f'SELECT COUNT(*) n FROM files WHERE {scope}=? AND present=1 AND is_image=1', (scope_id,))['n']
        last, done, failed = None, 0, 0
        while True:
            cursor = 'AND (p.sort_key,p.id,f.sort_key,f.id)>(?,?,?,?)' if last else ''
            rows = self.catalog.rows(f'SELECT f.*,p.sort_key package_sort FROM files f JOIN packages p ON p.id=f.package_id '
                                     f'WHERE f.{scope}=? AND f.present=1 AND f.is_image=1 {cursor} '
                                     'ORDER BY p.sort_key,p.id,f.sort_key,f.id LIMIT 100', (scope_id, *(last or ())))
            if not rows:
                break
            for image in rows:
                context.check()
                try:
                    self.generate(image, payload.get('edge', 400), self.key(image, payload.get('edge', 400)), context)
                except (OSError, ValueError):
                    failed += 1
                done += 1
                context.update(done, total, image['name'])
            tail = rows[-1]
            last = tail['package_sort'], tail['package_id'], tail['sort_key'], tail['id']
            self.collect(context)
        return {'generated_or_cached': done - failed, 'failed': failed}

    def collect(self, context=None, _payload=None):
        total = self.catalog.one('SELECT COALESCE(SUM(size),0) n FROM cache_entries')['n']
        removed = 0
        if total > self.settings.cache_limit:
            for entry in self.catalog.rows('SELECT * FROM cache_entries ORDER BY accessed'):
                if context:
                    context.check()
                if total <= self.settings.cache_limit * .85:
                    break
                try:
                    path = Path(entry['path']).resolve()
                    if path.is_relative_to((self.settings.data / 'derivatives').resolve()):
                        path.unlink(missing_ok=True)
                except OSError:
                    continue
                self.catalog.execute('DELETE FROM cache_entries WHERE key=?', (entry['key'],))
                total -= entry['size']
                removed += 1
        return {'bytes': total, 'removed': removed, 'limit': self.settings.cache_limit}

    def stop(self):
        self.stopping.set()
        self.pool.shutdown(wait=True, cancel_futures=True)
