"""Reproducible mixed-image HTTP benchmark with independent temporary data."""

import argparse
import contextlib
import errno
import hashlib
import json
import math
import os
import shutil
import statistics
import struct
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx2 as httpx
import numpy as np
from PIL import Image, ImageCms

from scripts.compare_loading import process_metrics


def distribution(values):
    ordered = sorted(values)
    return {'p50_ms': round(statistics.median(ordered), 2),
            'p95_ms': round(ordered[math.ceil(len(ordered) * .95) - 1], 2), 'samples': len(ordered)}


def make_library(root, copies):
    folder = root / 'group' / 'package'
    folder.mkdir(parents=True)
    profile = bytearray(ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes())
    # ICC header creation time must not make otherwise identical fixtures differ between runs.
    struct.pack_into('>6H', profile, 24, 2026, 1, 1, 0, 0, 0)
    profile = bytes(profile)
    manifest = {}
    for kind, size, mode, extension in (
        ('jpeg', (4800, 3200), 'RGB', 'jpg'), ('oriented', (3200, 4800), 'RGB', 'jpg'),
        ('alpha', (3600, 2400), 'RGBA', 'png'), ('webp', (3600, 2400), 'RGB', 'webp'),
        ('gif', (800, 600), 'RGB', 'gif'), ('motion', (1200, 800), 'RGBA', 'webp'),
    ):
        width, height = size
        pixels = np.random.default_rng(142).integers(0, 24, (height, width, 3), dtype=np.uint8)
        pixels[:, :, 0] += (np.arange(width, dtype=np.uint16) % 200).astype(np.uint8)
        pixels[:, :, 1] += (np.arange(height, dtype=np.uint16) % 200).astype(np.uint8)[:, None]
        with Image.fromarray(pixels) as rgb, rgb.convert(mode) as image:
            options = {}
            if mode == 'RGBA':
                image.putalpha(140)
            if extension == 'webp':
                options.update(quality=85, method=1)
            elif extension == 'jpg':
                options.update(quality=90)
            if kind == 'oriented':
                exif = image.getexif()
                exif[274] = 6
                options['exif'] = exif
            if kind == 'alpha':
                options['icc_profile'] = profile
            source = folder / f'00-{kind}.{extension}'
            if kind in ('gif', 'motion'):
                with image.transpose(Image.Transpose.FLIP_LEFT_RIGHT) as second:
                    image.save(source, save_all=True, append_images=[second], duration=100, loop=0, **options)
            else:
                image.save(source, **options)
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        for i in range(copies):
            target = folder / f'{i:02}-{kind}.{extension}'
            if target != source:
                shutil.copyfile(source, target)
            manifest[target.name] = {'sha256': digest, 'size': target.stat().st_size}
    return manifest


@contextlib.contextmanager
def backend(directory, executable=None, source_tree=None):
    ready = directory / 'ready.json'
    environment = dict(os.environ)
    for key in ('GALLERY_ROOT', 'GALLERY_DATA', 'GALLERY_LEGACY', 'GALLERY_APPLICATION'):
        environment.pop(key, None)
    token = 'pipeline-benchmark'
    environment['GALLERY_DESKTOP_TOKEN'] = token
    command = [str(executable.resolve())] if executable else [sys.executable, '-m', 'gallery']
    command += ['--data', str(directory), '--port', '0', '--ready-file', str(ready),
                '--no-scan', '--no-watch', '--no-open']
    log = directory / 'process.log'
    with log.open('w', encoding='utf-8') as output:
        process = subprocess.Popen(command, cwd=source_tree, env=environment, stdout=output, stderr=output)
        try:
            deadline = time.monotonic() + 30
            while True:
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError(log.read_text(encoding='utf-8'))
                try:
                    descriptor = json.loads(ready.read_text(encoding='utf-8'))
                    break
                except OSError as error:
                    if error.errno not in (errno.ENOENT, errno.EACCES, errno.EPERM):
                        raise
                time.sleep(.01)
            with httpx.Client(base_url=descriptor['url'], timeout=120) as client:
                try:
                    yield client, descriptor['pid']
                finally:
                    if process.poll() is None:
                        client.post('/api/v1/system/shutdown', headers={'X-Gallery-Desktop': token}).raise_for_status()
                        process.wait(timeout=30)
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)


def wait_task(client, task_id):
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        task = client.get('/api/v1/tasks/' + task_id).json()
        if task['state'] not in ('queued', 'running', 'paused', 'cancelling'):
            if task['state'] != 'completed':
                raise RuntimeError(task)
            return task
        time.sleep(.02)
    raise TimeoutError('Benchmark background task did not finish')


def run(client, images, package, library):
    report, outputs = {}, {}
    stopped = threading.Event()
    health, lists = [], []

    def responsiveness():
        while not stopped.is_set():
            for path, values in (('/api/v1/health', health),
                                 (f"/api/v1/packages/{package['id']}/images?limit=100", lists)):
                start = time.perf_counter()
                client.get(path).raise_for_status()
                values.append((time.perf_counter() - start) * 1000)
            stopped.wait(.05)

    def request(item, edge):
        start = time.perf_counter()
        response = client.get(f"/api/v1/images/{item['id']}/thumbnail", params={'edge': edge})
        response.raise_for_status()
        elapsed = (time.perf_counter() - start) * 1000
        return item['name'], elapsed, hashlib.sha256(response.content).hexdigest()

    def measure(name, items, edge, concurrency=1):
        start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=concurrency) as workers:
            results = list(workers.map(lambda item: request(item, edge), items))
        report[name] = {**distribution([elapsed for _, elapsed, _ in results]),
                        'wall_ms': round((time.perf_counter() - start) * 1000, 2),
                        'concurrency': concurrency, 'edge': edge}
        for filename, _, digest in results:
            outputs[f'{filename}:{edge}'] = digest

    with ThreadPoolExecutor(max_workers=1) as monitor:
        responsive = monitor.submit(responsiveness)
        try:
            measure('serial_first', images, 1600)
            measure('concurrent_first', images, 800, 4)
            job = client.post('/api/v1/tasks', json={'kind': 'prewarm', 'package_id': package['id'], 'edge': 400})
            job.raise_for_status()
            scan = client.post('/api/v1/tasks', json={'kind': 'scan', 'library_id': library['id']})
            scan.raise_for_status()
            measure('foreground_during_prewarm', list(reversed(images)), 2560, 4)
            report['prewarm_result'] = wait_task(client, job.json()['id'])['result']
            wait_task(client, scan.json()['id'])
            measure('warm_preview', images * 3, 1600, 4)
            measure('warm_thumbnail', images * 5, 400, 4)
        finally:
            stopped.set()
            responsive.result(timeout=10)
    report['health_under_load'] = distribution(health)
    report['list_under_load'] = distribution(lists)
    report['output_sha256'] = outputs
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source-parent', type=Path)
    parser.add_argument('--backend', type=Path)
    parser.add_argument('--source-tree', type=Path)
    parser.add_argument('--copies', type=int, default=4)
    args = parser.parse_args()
    if not 1 <= args.copies <= 40:
        parser.error('--copies must be between 1 and 40')
    if args.backend and args.source_tree:
        parser.error('--backend and --source-tree are mutually exclusive')
    with tempfile.TemporaryDirectory(prefix='gallery-pipeline-source-', dir=args.source_parent) as source_dir:
        with tempfile.TemporaryDirectory(prefix='gallery-pipeline-data-') as data_dir:
            source = Path(source_dir)
            manifest = make_library(source, args.copies)
            with backend(Path(data_dir), args.backend, args.source_tree) as (client, pid):
                library_response = client.post('/api/v1/libraries', json={'path': str(source)})
                library_response.raise_for_status()
                library = library_response.json()
                for task in client.get('/api/v1/tasks').json()['items']:
                    wait_task(client, task['id'])
                group = client.get(f"/api/v1/libraries/{library['id']}/groups").json()['items'][0]
                package = client.get(f"/api/v1/groups/{group['id']}/packages").json()['items'][0]
                images = client.get(f"/api/v1/packages/{package['id']}/images?limit=500").json()['items']
                with process_metrics(pid) as resources:
                    report = run(client, images, package, library)
                report.update(process_metrics=resources, source_manifest=manifest,
                              source_volume=source.anchor, cache_volume=Path(data_dir).anchor,
                              notes='Generated fixtures. Derivative misses only; OS cache not flushed. '
                                    'Process IO is not physical disk IO. RSS excludes Electron.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in report.items()
                      if key not in ('source_manifest', 'output_sha256')}, indent=2))


if __name__ == '__main__':
    main()
