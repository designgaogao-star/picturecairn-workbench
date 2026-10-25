"""Long-run evidence remains valid when real workload cycles exceed their ideal cadence."""

import hashlib
import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest


@pytest.fixture
def evidence(tmp_path, monkeypatch):
    scripts = Path(__file__).resolve().parents[1] / 'scripts/ui-qa'
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location('soak_audit', scripts / 'audit_soak.py')
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    monkeypatch.setattr(audit, 'check_exited', lambda _path: False)
    data = tmp_path / 'data'
    data.mkdir()
    with sqlite3.connect(data / 'catalog.sqlite') as db:
        db.execute('CREATE TABLE tasks(state TEXT)')
        db.execute("INSERT INTO tasks VALUES ('completed')")
    (data / 'server.log').write_text('Synthetic completed run\n', encoding='utf-8')
    run = {'minutes': 60, 'preflight': False, 'temporary': str(data)}
    result = {'elapsed_seconds': 3610, 'cycles': 171, 'passed': True, 'errors': []}
    renderer = [{'elapsed_seconds': .5 + i * 20 + (200 if i >= 107 else 0),
                 'cycle': i, 'phase': i % 6, 'liveDom': 300, 'errors': [],
                 'requests': 0, 'activeTasks': 0, 'cache': {'bytes': 1000, 'limit': 12000},
                 'performance': {'JSHeapUsedSize': 2 * 1024**2}} for i in range(result['cycles'])]
    processes = [{'elapsed_seconds': i * 30, 'processes': [
        {'private': 100 * 1024**2, 'rss': 90 * 1024**2, 'handles': 40}]} for i in range(123)]

    def save():
        for name, value in [('run', run), ('result', result)]:
            (tmp_path / (name + '.json')).write_text(json.dumps(value), encoding='utf-8')
        for name, value in [('renderer', renderer), ('processes', processes)]:
            (tmp_path / (name + '.jsonl')).write_text(''.join(json.dumps(row) + '\n' for row in value), encoding='utf-8')

    save()
    return audit, tmp_path, renderer, result, save


def test_completed_hour_with_slow_cycles_does_not_require_ideal_180_cycles(evidence):
    audit, directory, *_ = evidence
    report = audit.audit(directory)
    assert report['runtime_passed']
    assert report['cycles'] == 171
    assert report['max_cycle_gap_seconds'] == 220


@pytest.mark.parametrize('damage', ['missing_cycle', 'wrong_phase', 'short_run', 'failed_checkpoint'])
def test_rejects_incomplete_or_inconsistent_workload_evidence(evidence, damage):
    audit, directory, renderer, result, save = evidence
    if damage == 'missing_cycle':
        renderer.pop(30)
    elif damage == 'wrong_phase':
        renderer[30]['phase'] = 5
    elif damage == 'short_run':
        result['elapsed_seconds'] = 3590
    else:
        result['passed'] = False
    save()
    with pytest.raises(AssertionError):
        audit.audit(directory)


def test_rejects_unknown_failure_after_a_passed_checkpoint(evidence):
    audit, directory, *_ = evidence
    (directory / 'failure.txt').write_text('Unexpected automation failure after checkpoint\n', encoding='utf-8')
    with pytest.raises(AssertionError, match='Recorded automation failure'):
        audit.audit(directory)


def test_retains_verified_legacy_final_capture_failure(evidence):
    audit, directory, *_ = evidence
    executed = (b'// synthetic old driver\n'
                b'assert.ok(Date.now() - started >= minutes * 60000);\n'
                b"await page.screenshot({ path: path.join(output, 'final-desktop.png') });\n")
    (directory / 'executed-soak.mjs').write_bytes(executed)
    application = directory / 'legacy-app'
    application.mkdir()
    (application / 'release-manifest.json').write_text(json.dumps({'source': {'files': [
        {'path': 'scripts/ui-qa/soak.mjs', 'sha256': hashlib.sha256(executed).hexdigest()}
    ]}}), encoding='utf-8')
    run_path = directory / 'run.json'
    run = json.loads(run_path.read_text(encoding='utf-8'))
    run['executable'] = str(application / 'GalleryTool.exe')
    run_path.write_text(json.dumps(run), encoding='utf-8')
    (directory / 'result.json').unlink()
    failure = 'page.screenshot: Timeout 30000ms exceeded\n    at soak.mjs:3:1\n'
    (directory / 'failure.txt').write_text(failure, encoding='utf-8')
    (directory / 'failure.png').touch()

    report = audit.audit(directory)
    assert report['runtime_passed']
    assert report['automation_exit'] == 'capture_failure'
    assert report['capture_failure'] == failure
