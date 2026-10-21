"""Measure backend startup with a consistent copy of an existing catalog."""

import argparse
import contextlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx2 as httpx
import psutil


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('catalog', type=Path)
    parser.add_argument('--backend', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    results = []
    with tempfile.TemporaryDirectory(prefix='gallery-startup-') as temporary:
        directory = Path(temporary)
        with contextlib.closing(sqlite3.connect(args.catalog.resolve().as_uri() + '?mode=ro', uri=True)) as source:
            with contextlib.closing(sqlite3.connect(directory / 'catalog.sqlite')) as target:
                source.backup(target)
        for _ in range(3):
            ready = directory / 'ready.json'
            environment = {**os.environ, 'GALLERY_DESKTOP_TOKEN': 'startup-measurement'}
            environment.pop('GALLERY_LEGACY', None)
            environment.pop('GALLERY_ROOT', None)
            command = [str(args.backend)] if args.backend else [sys.executable, '-m', 'gallery']
            command += ['--data', str(directory), '--port', '0', '--ready-file', str(ready), '--no-watch', '--no-scan', '--no-open']
            with (directory / 'process.log').open('a', encoding='utf-8') as output:
                start = time.perf_counter()
                process = subprocess.Popen(command, env=environment, stdout=output, stderr=output)
                try:
                    until = time.monotonic() + 30
                    while True:
                        if process.poll() is not None or time.monotonic() > until:
                            raise RuntimeError((directory / 'process.log').read_text(encoding='utf-8'))
                        try:
                            descriptor = json.loads(ready.read_text(encoding='utf-8'))
                            break
                        except (FileNotFoundError, PermissionError):
                            time.sleep(.01)
                    elapsed = time.perf_counter() - start
                    memory = psutil.Process(descriptor['pid']).memory_info().rss
                    with httpx.Client(base_url=descriptor['url']) as client:
                        client.get('/api/v1/health').raise_for_status()
                        client.post('/api/v1/system/shutdown', headers={'X-Gallery-Desktop': 'startup-measurement'}).raise_for_status()
                    process.wait(timeout=25)
                    results.append({'ready_ms': round(elapsed * 1000, 2), 'rss_mib': round(memory / 1024**2, 1)})
                finally:
                    if process.poll() is None:
                        process.terminate()
                        process.wait(timeout=10)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
