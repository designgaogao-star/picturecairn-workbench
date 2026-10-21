"""Read-only browsing benchmark; only derivative cache and the report are written."""

import argparse
import contextlib
import json
import statistics
import time
from collections import Counter
from pathlib import Path

import httpx2 as httpx

from scripts.compare_loading import process_metrics


def distribution(values):
    values = sorted(values)
    return {'p50_ms': round(statistics.median(values), 2),
            'p95_ms': round(values[min(len(values) - 1, int(len(values) * .95))], 2), 'samples': len(values)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('url')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--category', choices=('R16', 'R18', '非R18', '其他'))
    parser.add_argument('--pid', type=int)
    parser.add_argument('--offset', type=int, default=0)
    parser.add_argument('--package')
    args = parser.parse_args()
    report = {'notes': 'First preview requests do not flush the OS cache. Process IO is not physical disk IO.'}
    metrics = process_metrics(args.pid) if args.pid else contextlib.nullcontext({})
    with metrics as resources, httpx.Client(base_url=args.url, timeout=30) as client:
        def measure(path, samples):
            timings = []
            for _ in range(samples):
                start = time.perf_counter()
                response = client.get(path)
                response.raise_for_status()
                timings.append((time.perf_counter() - start) * 1000)
            return distribution(timings)
        report['health'] = measure('/api/v1/health', 80)
        library = client.get('/api/v1/libraries').json()['items'][0]
        report['scan_status'] = library['scan_status']
        report['groups_page'] = measure(f"/api/v1/libraries/{library['id']}/groups?limit=100", 30)
        if args.package:
            response = client.get('/api/v1/packages/' + args.package)
            response.raise_for_status()
            package = response.json()
            group = client.get('/api/v1/groups/' + package['group_id']).json()
            if args.category and group['category'] != args.category:
                raise ValueError('Package does not match the requested category')
        else:
            query = {'limit': 100, **({'category': args.category} if args.category else {})}
            group = client.get(f"/api/v1/libraries/{library['id']}/groups", params=query).json()['items'][0]
            packages = client.get(f"/api/v1/groups/{group['id']}/packages?limit=100").json()['items']
            package = max(packages, key=lambda p: p['image_count'])
        report['package_images'] = package['image_count']
        path = f"/api/v1/packages/{package['id']}/images?limit=100"
        report['images_page'] = measure(path, 30)
        images = client.get(f"/api/v1/packages/{package['id']}/images", params={'offset': args.offset, 'limit': 12}).json()['items']
        if not images:
            raise ValueError('No images at the selected offset')
        report['preview_offset'] = args.offset
        timings = []
        for image in images:
            path = f"/api/v1/images/{image['id']}/thumbnail?edge=1600"
            start = time.perf_counter()
            client.get(path).raise_for_status()
            timings.append((time.perf_counter() - start) * 1000)
        report['first_preview_requests'] = distribution(timings)
        report['warm_preview'] = measure(f"/api/v1/images/{images[0]['id']}/thumbnail?edge=1600", 50)
        client.get(f"/api/v1/images/{images[0]['id']}/thumbnail?edge=400").raise_for_status()
        report['warm_thumbnail'] = measure(f"/api/v1/images/{images[0]['id']}/thumbnail?edge=400", 50)
        report['task_states'] = dict(Counter(t['kind'] + ':' + t['state'] for t in client.get('/api/v1/tasks').json()['items']))
    report['process_metrics'] = resources
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
