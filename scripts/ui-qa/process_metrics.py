"""Sample only the process tree owned by one isolated Electron acceptance run."""

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import psutil


def identity(process):
    return process.pid, process.create_time()


def sample(root, backend):
    processes = {process.pid: process for process in [root, *root.children(recursive=True)]}
    if backend not in processes:
        processes[backend] = psutil.Process(backend)
    records = []
    for process in processes.values():
        try:
            with process.oneshot():
                command = process.cmdline()
                role = 'main' if process.pid == root.pid else 'backend' if process.pid == backend else next(
                    (value.removeprefix('--type=') for value in command if value.startswith('--type=')), 'child')
                memory, io = process.memory_info(), process.io_counters()
                records.append({'pid': process.pid, 'created': process.create_time(), 'role': role,
                                'rss': memory.rss, 'private': getattr(memory, 'private', memory.vms),
                                'handles': process.num_handles(), 'threads': process.num_threads(),
                                'read_bytes': io.read_bytes, 'write_bytes': io.write_bytes})
        except psutil.NoSuchProcess:
            continue
    return records


def check_exited(source):
    identities = {(record['pid'], record['created']) for line in source.read_text(encoding='utf-8').splitlines()
                  for record in json.loads(line)['processes']}
    alive = []
    for pid, created in identities:
        try:
            if identity(psutil.Process(pid)) == (pid, created):
                alive.append(pid)
        except psutil.NoSuchProcess:
            pass
    print(json.dumps({'sampled_identities': len(identities), 'alive': alive}))
    return bool(alive)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=int)
    parser.add_argument('--backend', type=int)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--interval', type=float, default=30)
    parser.add_argument('--check-exited', type=Path)
    args = parser.parse_args()
    if args.check_exited:
        raise SystemExit(check_exited(args.check_exited))
    if not args.root or not args.backend or not args.output or args.interval < 1:
        parser.error('--root, --backend, --output and interval >= 1 are required')
    root = psutil.Process(args.root)
    original, started = identity(root), time.monotonic()
    with args.output.open('w', encoding='utf-8', buffering=1) as output:
        while True:
            try:
                if identity(root) != original:
                    return
                records = sample(root, args.backend)
            except psutil.NoSuchProcess:
                return
            output.write(json.dumps({'utc': datetime.now(UTC).isoformat(),
                                     'elapsed_seconds': round(time.monotonic() - started, 3), 'processes': records}) + '\n')
            for _ in range(round(args.interval * 5)):
                if not root.is_running():
                    return
                time.sleep(.2)


if __name__ == '__main__':
    main()
