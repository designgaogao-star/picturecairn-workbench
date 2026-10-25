"""Read-only audit of one recorded long run, retaining any automation capture failure."""

import argparse
import hashlib
import json
import re
import sqlite3
import statistics
from pathlib import Path

from process_metrics import check_exited


def records(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line]


def trend(rows, value):
    x, y = [row['elapsed_seconds'] / 60 for row in rows], [value(row) for row in rows]
    mx, my = statistics.mean(x), statistics.mean(y)
    return {'slope_per_minute': sum((a - mx) * (b - my) for a, b in zip(x, y)) / sum((a - mx) ** 2 for a in x),
            'median_change': statistics.median(y[len(y) // 2:]) - statistics.median(y[:len(y) // 2])}


def audit(directory):
    run = json.loads((directory / 'run.json').read_text(encoding='utf-8'))
    process_rows, renderer = records(directory / 'processes.jsonl'), records(directory / 'renderer.jsonl')
    failure = (directory / 'failure.txt').read_text(encoding='utf-8') if (directory / 'failure.txt').exists() else None
    result = json.loads((directory / 'result.json').read_text(encoding='utf-8')) if (directory / 'result.json').exists() else None
    # This recovery path is deliberately specific: a known script reached every workload assertion,
    # then failed on its final screenshot. Other failures cannot be reclassified as successful runs.
    capture_only = False
    if failure and (directory / 'executed-soak.mjs').exists():
        executed = directory / 'executed-soak.mjs'
        manifest = json.loads((Path(run['executable']).parent / 'release-manifest.json').read_text(encoding='utf-8'))
        expected = next(item['sha256'] for item in manifest['source']['files'] if item['path'] == 'scripts/ui-qa/soak.mjs')
        line = re.search(r'soak\.mjs:(\d+):\d+', failure)
        source = executed.read_text(encoding='utf-8').splitlines()
        capture_only = (hashlib.sha256(executed.read_bytes()).hexdigest() == expected
                        and failure.startswith('page.screenshot: Timeout') and line is not None
                        and "path.join(output, 'final-desktop.png')" in source[int(line[1]) - 1]
                        and "assert.ok(Date.now() - started >= minutes * 60000)" in source[int(line[1]) - 2]
                        and (directory / 'failure.png').is_file())
    assert not failure or capture_only, 'Recorded automation failure is not a verified capture-only exception'
    duration = run['minutes'] * 60
    assert duration >= 3600 and not run['preflight'], 'A preflight is not a long-run acceptance'
    assert (result and result['passed'] and not result['errors'] and result['elapsed_seconds'] >= duration
            or capture_only), 'No verified completed-workload checkpoint'
    assert renderer and renderer[-1]['elapsed_seconds'] >= duration - 30, 'Workload ended before the final interval'
    # Twenty seconds is the minimum cycle interval, not a deadline: two sequential
    # analysis/compare jobs can each take up to 120s. Audit recorded work and its
    # completed checkpoint instead of requiring an impossible ideal sample count.
    assert all(row['cycle'] == index and row['phase'] == index % 6 for index, row in enumerate(renderer)), \
        'Workload cycles are missing or out of order'
    gaps = [right['elapsed_seconds'] - left['elapsed_seconds'] for left, right in zip(renderer, renderer[1:])]
    assert gaps and all(gap > 0 for gap in gaps), 'Workload timestamps must increase'
    assert all(not row['errors'] for row in renderer), 'Recorded renderer errors'
    if result:
        assert result['cycles'] == len(renderer), 'Completed checkpoint does not match the recorded cycles'
    assert process_rows[-1]['elapsed_seconds'] >= duration
    assert {row['phase'] for row in renderer} == set(range(6))
    latter = [row for row in process_rows if row['elapsed_seconds'] >= process_rows[-1]['elapsed_seconds'] - 1800]
    private = trend(latter, lambda row: sum(item['private'] for item in row['processes']) / 1024**2)
    handles = trend(latter, lambda row: sum(item['handles'] for item in row['processes']))
    heap = trend([row for row in renderer if row['elapsed_seconds'] >= duration - 1800],
                 lambda row: row['performance']['JSHeapUsedSize'] / 1024**2)
    assert private['slope_per_minute'] < 2 and private['median_change'] < 96
    assert handles['slope_per_minute'] < 2 and handles['median_change'] < 100
    assert heap['slope_per_minute'] < 1 and heap['median_change'] < 32
    assert all(row['cache']['bytes'] <= row['cache']['limit'] and row['requests'] <= 16 and row['activeTasks'] <= 6 for row in renderer)
    data = Path(run['temporary'])
    with sqlite3.connect((data / 'catalog.sqlite').as_uri() + '?mode=ro', uri=True) as db:
        tasks = dict(db.execute('SELECT state,COUNT(*) FROM tasks GROUP BY state'))
    assert set(tasks) <= {'completed', 'cancelled'}, tasks
    assert ' ERROR ' not in (data / 'server.log').read_text(encoding='utf-8')
    assert not check_exited(directory / 'processes.jsonl'), 'Some owned process remains alive'
    return {'runtime_passed': True, 'automation_exit': 'capture_failure' if capture_only else 'passed',
            'capture_failure': failure, 'workload_minutes': run['minutes'],
            'process_observed_seconds': process_rows[-1]['elapsed_seconds'], 'cycles': len(renderer),
            'max_cycle_gap_seconds': max(gaps),
            'process_samples': len(process_rows), 'process_private_mib': private, 'handles': handles,
            'renderer_heap_mib': heap, 'max_live_dom': max(row['liveDom'] for row in renderer),
            'sampled_peak_total_rss_mib': max(sum(item['rss'] for item in row['processes']) for row in process_rows) / 1024**2,
            'sampled_peak_total_private_mib': max(sum(item['private'] for item in row['processes']) for row in process_rows) / 1024**2,
            'final_processes': process_rows[-1]['processes'],
            'max_inflight_requests': max(row['requests'] for row in renderer), 'final_task_states': tasks,
            'owned_processes_exited': True, 'cache': renderer[-1]['cache']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    report = audit(args.directory.resolve())
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    (args.directory / 'runtime-audit.json').write_text(encoded, encoding='utf-8')
    print(encoded)


if __name__ == '__main__':
    main()
