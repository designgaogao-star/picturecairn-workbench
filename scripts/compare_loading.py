"""Compare first and warm preview requests for the same files in V1 and V2."""

import argparse
import contextlib
import json
import math
import statistics
import threading
import time
from pathlib import Path

import httpx2 as httpx
import psutil


def stats(samples):
    ordered = sorted(samples)
    return {'p50_ms': round(statistics.median(samples), 2), 'p95_ms': round(ordered[math.ceil(len(ordered) * .95) - 1], 2)}


@contextlib.contextmanager
def process_metrics(pid):
    process = psutil.Process(pid)
    initial = process.io_counters()
    before = peak = process.memory_info().rss
    stopped = threading.Event()
    result = {}
    def sample():
        nonlocal peak
        while not stopped.wait(.01):
            peak = max(peak, process.memory_info().rss)
    worker = threading.Thread(target=sample, daemon=True)
    worker.start()
    try:
        yield result
    finally:
        stopped.set()
        worker.join()
        after = process.io_counters()
        result.update(rss_before_mib=round(before / 1024**2, 1),
                      peak_sampled_rss_mib=round(peak / 1024**2, 1),
                      rss_after_mib=round(process.memory_info().rss / 1024**2, 1),
                      process_read_bytes=after.read_bytes - initial.read_bytes,
                      process_write_bytes=after.write_bytes - initial.write_bytes,
                      process_read_count=after.read_count - initial.read_count,
                      process_write_count=after.write_count - initial.write_count)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('current')
    parser.add_argument('legacy')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--offset', type=int, default=20)
    parser.add_argument('--current-pid', type=int)
    parser.add_argument('--legacy-pid', type=int)
    args = parser.parse_args()
    if bool(args.current_pid) != bool(args.legacy_pid):
        parser.error('Provide both process IDs to measure memory and process IO')
    report = {'sample_count': 12, 'edge': 1600, 'order': 'alternating-v1-first-v2-first',
              'v1_first': [], 'v2_first': [], 'v1_warm': [], 'v2_warm': []}
    with contextlib.ExitStack() as measurements, httpx.Client(timeout=30) as client:
        if args.current_pid:
            report['process_metrics'] = {
                'v1': measurements.enter_context(process_metrics(args.legacy_pid)),
                'v2': measurements.enter_context(process_metrics(args.current_pid)),
            }
            report['measurement_notes'] = ('RSS sampled every 10 ms during the comparison; process IO includes '
                                           'concurrent background work and is not physical disk IO. First request '
                                           'means derivative-cache miss only when separately verified; OS caches are not flushed.')
        library = client.get(args.current + '/api/v1/libraries').json()['items'][0]
        group = client.get(args.current + f"/api/v1/libraries/{library['id']}/groups").json()['items'][0]
        packages = client.get(args.current + f"/api/v1/groups/{group['id']}/packages").json()['items']
        package = max(packages, key=lambda p: p['image_count'])
        images = client.get(args.current + f"/api/v1/packages/{package['id']}/images?offset={args.offset}&limit=12").json()['items']
        report['sample_count'] = len(images)
        if not images:
            raise ValueError('No images at the selected offset')
        for i, image in enumerate(images):
            relative = image['rel'][len(group['rel']) + 1:]
            requests = [('v1', args.legacy + '/thumb', {'folder': group['name'], 'file': relative, 'edge': 1600, 'q': 80}),
                        ('v2', args.current + f"/api/v1/images/{image['id']}/thumbnail", {'edge': 1600})]
            if i % 2:
                requests.reverse()
            for version, url, params in requests:
                start = time.perf_counter()
                response = client.get(url, params=params)
                response.raise_for_status()
                report[version + '_first'].append((time.perf_counter() - start) * 1000)
            for version, url, params in requests:
                start = time.perf_counter()
                client.get(url, params=params).raise_for_status()
                report[version + '_warm'].append((time.perf_counter() - start) * 1000)
        for key in ('v1_first', 'v2_first', 'v1_warm', 'v2_warm'):
            report[key] = stats(report[key])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
