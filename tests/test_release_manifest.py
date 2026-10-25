"""The release gate must notice source changes that occurred after packaging."""

import hashlib
import json
import zipfile

import pytest

from scripts import write_release_manifest as release


def test_release_verification_detects_added_runtime_source_and_changed_artifact(tmp_path, monkeypatch):
    project, app = tmp_path / 'project', tmp_path / 'app'
    (project / 'ui').mkdir(parents=True)
    app.mkdir()
    source = project / 'ui/main.ts'
    source.write_text('export const version = 1', encoding='utf-8')
    program = app / 'GalleryTool.exe'
    program.write_bytes(b'isolated artifact')
    recorded = {'version': 'test', 'source': {'sha256': 'test', 'files': [
        {'path': 'ui/main.ts', 'sha256': release.digest(source)}]},
        'artifacts': [{'path': program.name, 'sha256': release.digest(program)}]}
    (app / 'release-manifest.json').write_text(json.dumps(recorded), encoding='utf-8')
    monkeypatch.setattr(release, 'source_paths', lambda _root: {path.relative_to(project).as_posix()
                                                             for path in project.rglob('*') if path.is_file()})
    assert release.verify(project, app)['passed']
    (project / 'README.md').write_text('Updated acceptance notes', encoding='utf-8')
    report = release.verify(project, app)
    assert report['passed']
    assert report['all_source_changes_since_build'] == ['README.md']
    (project / 'ui/new.ts').write_text('export const later = true', encoding='utf-8')
    report = release.verify(project, app)
    assert not report['passed']
    assert report['runtime_source_mismatches'] == ['ui/new.ts']
    (project / 'docs/brand/stillmark').mkdir(parents=True)
    (project / 'docs/brand/stillmark/mark.svg').write_text('<svg/>', encoding='utf-8')
    assert release.verify(project, app)['runtime_source_mismatches'] == ['docs/brand/stillmark/mark.svg', 'ui/new.ts']
    program.write_bytes(b'modified artifact')
    assert release.verify(project, app)['artifact_mismatches'] == ['GalleryTool.exe']
    (app / 'unexpected-data.txt').write_text('This file was not part of the recorded build', encoding='utf-8')
    assert release.verify(project, app)['artifact_mismatches'] == ['GalleryTool.exe', 'unexpected-data.txt']


@pytest.mark.parametrize('changed', ['checksum', 'content', 'extra'])
def test_zip_verification_checks_checksum_contents_and_extra_files(tmp_path, changed):
    archive = tmp_path / 'preview.zip'
    program = b'original staged executable'
    manifest = {'artifacts': [{'path': 'GalleryTool.exe', 'sha256': hashlib.sha256(program).hexdigest()}]}

    def write(content, extra=False):
        with zipfile.ZipFile(archive, 'w') as package:
            package.writestr('GalleryTool.exe', content)
            package.writestr('release-manifest.json', json.dumps(manifest))
            if extra:
                package.writestr('unrecorded.txt', 'unexpected data')
        archive.with_name(archive.name + '.sha256').write_text(release.digest(archive) + '  preview.zip\n', encoding='ascii')

    write(program)
    assert release.verify_archive(archive)['passed']
    if changed == 'checksum':
        archive.with_name(archive.name + '.sha256').write_text('0' * 64 + '  preview.zip\n', encoding='ascii')
    else:
        write(b'changed executable' if changed == 'content' else program, changed == 'extra')
    assert not release.verify_archive(archive)['passed']


@pytest.mark.parametrize('recorded,local', [
    (b'export const value = 1;\n// same source\n', b'export const value = 1;\r\n// same source\r\n'),
    (b'export const value = 1;\r\n// same source\r\n', b'export const value = 1;\n// same source\n'),
])
def test_source_verification_reports_checkout_line_endings_without_ignoring_content(tmp_path, monkeypatch, recorded, local):
    project, app = tmp_path / 'project', tmp_path / 'app'
    (project / 'ui').mkdir(parents=True)
    app.mkdir()
    source = project / 'ui/main.ts'
    source.write_bytes(local)
    saved = {'version': 'preview', 'source': {'sha256': 'raw-build-digest', 'files': [
        {'path': 'ui/main.ts', 'sha256': hashlib.sha256(recorded).hexdigest()}]}, 'artifacts': []}
    (app / 'release-manifest.json').write_text(json.dumps(saved), encoding='utf-8')
    monkeypatch.setattr(release, 'source_paths', lambda _root: {'ui/main.ts'})
    report = release.verify(project, app)
    assert report['passed']
    assert report['source_line_ending_only_changes'] == ['ui/main.ts']
    assert report['runtime_source_mismatches'] == []
    source.write_bytes(local.replace(b'value = 1', b'value = 2'))
    report = release.verify(project, app)
    assert not report['passed']
    assert report['runtime_source_mismatches'] == ['ui/main.ts']
    assert report['source_line_ending_only_changes'] == []


@pytest.mark.parametrize('source_name,prefix', [('pixels.bin', b''), ('binary.ts', b'\0'), ('encoded.ts', b'\xff')])
def test_line_ending_allowance_never_applies_to_binary_sources_or_packaged_files(tmp_path, monkeypatch, source_name, prefix):
    project, app = tmp_path / 'project', tmp_path / 'app'
    (project / 'ui').mkdir(parents=True)
    app.mkdir()
    recorded, local = prefix + b'first\nsecond\n', prefix + b'first\r\nsecond\r\n'
    (project / 'ui' / source_name).write_bytes(local)
    (app / 'package.json').write_bytes(local)
    saved = {'version': 'preview', 'source': {'sha256': 'raw-build-digest', 'files': [
        {'path': f'ui/{source_name}', 'sha256': hashlib.sha256(recorded).hexdigest()}]},
        'artifacts': [{'path': 'package.json', 'sha256': hashlib.sha256(recorded).hexdigest()}]}
    (app / 'release-manifest.json').write_text(json.dumps(saved), encoding='utf-8')
    monkeypatch.setattr(release, 'source_paths', lambda _root: {f'ui/{source_name}'})
    report = release.verify(project, app)
    assert not report['passed']
    assert report['runtime_source_mismatches'] == [f'ui/{source_name}']
    assert report['artifact_mismatches'] == ['package.json']
