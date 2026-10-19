"""Read-only browsing benchmark; only derivative cache and the report are written."""

import argparse
import json
import statistics
import time
from pathlib import Path

import httpx2 as httpx


def distribution(values):
    values = sorted(values)
    return {'p50_ms': round(statistics.median(values), 2),
            'p95_ms': round(values[min(len(values) - 1, int(len(values) * .95))], 2), 'samples': len(values)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('url')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = {}
    with httpx.Client(base_url=args.url, timeout=30) as client:
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
        group = client.get(f"/api/v1/libraries/{library['id']}/groups?limit=100").json()['items'][0]
        packages = client.get(f"/api/v1/groups/{group['id']}/packages?limit=100").json()['items']
        package = max(packages, key=lambda p: p['image_count'])
        path = f"/api/v1/packages/{package['id']}/images?limit=100"
        report['images_page'] = measure(path, 30)
        images = client.get(path).json()['items'][:12]
        timings = []
        for image in images:
            path = f"/api/v1/images/{image['id']}/thumbnail?edge=1600"
            start = time.perf_counter()
            client.get(path).raise_for_status()
            timings.append((time.perf_counter() - start) * 1000)
        report['first_preview_requests'] = distribution(timings)
        report['warm_preview'] = measure(f"/api/v1/images/{images[0]['id']}/thumbnail?edge=1600", 50)
        report['warm_thumbnail'] = measure(f"/api/v1/images/{images[0]['id']}/thumbnail?edge=400", 50)
        report['tasks'] = [{'kind': t['kind'], 'state': t['state']} for t in client.get('/api/v1/tasks').json()['items']]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
