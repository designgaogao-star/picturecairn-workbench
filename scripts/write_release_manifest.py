"""Describe a local build without claiming it has passed runtime acceptance."""

import argparse
import hashlib
import json
import platform
import subprocess
import zipfile
from datetime import UTC, datetime
from pathlib import Path

SOURCE_TEXT_SUFFIXES = {'.py', '.ps1', '.spec', '.ts', '.tsx', '.mts', '.js', '.mjs', '.cjs',
                        '.json', '.lock', '.toml', '.yml', '.yaml', '.css', '.html', '.svg',
                        '.sql', '.md', '.txt', '.bat', '.vbs'}


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def source_line_endings_match(path, expected):
    """Recognize LF/CRLF checkout changes in UTF-8 source, preserving the recorded raw hash."""
    if not path.is_file() or path.suffix.lower() not in SOURCE_TEXT_SUFFIXES:
        return False
    data = path.read_bytes()
    if b'\0' in data:
        return False
    try:
        data.decode('utf-8')
    except UnicodeDecodeError:
        return False
    lf = data.replace(b'\r\n', b'\n')
    return expected in {hashlib.sha256(lf).hexdigest(), hashlib.sha256(lf.replace(b'\n', b'\r\n')).hexdigest()}


def source_paths(project):
    names = subprocess.check_output(
        ['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=project)
    return {name for name in names.decode('utf-8').split('\0') if name and (project / name).is_file()}


def manifest(project, app):
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=project).decode('utf-8').strip()

    sources = [{'path': name, 'sha256': digest(project / name)} for name in sorted(source_paths(project))]
    source_digest = hashlib.sha256()
    for entry in sources:
        source_digest.update(f"{entry['path']}\0{entry['sha256']}\n".encode())
    artifacts = [{'path': path.relative_to(app).as_posix(), 'size': path.stat().st_size, 'sha256': digest(path)}
                 for path in sorted(app.rglob('*')) if path.is_file() and path.name != 'release-manifest.json']
    package = json.loads((project / 'package.json').read_text(encoding='utf-8'))
    return {'created_utc': datetime.now(UTC).isoformat(), 'version': package['version'],
            'release_channel': package.get('releaseChannel', 'development'),
            'release_label': package.get('releaseLabel', '开发预览（未发布）'),
            'product_name': package.get('productName', package['name']), 'code_signing': 'unsigned preview',
            'platform': platform.platform(), 'python': platform.python_version(),
            'electron': package['devDependencies']['electron'],
            'source': {'branch': git('branch', '--show-current'), 'head': git('rev-parse', 'HEAD'),
                       'status': git('status', '--short'), 'sha256': source_digest.hexdigest(), 'files': sources},
            'artifacts': artifacts, 'acceptance': 'pending; see the separate runtime verification report'}


def verify(project, app):
    saved = json.loads((app / 'release-manifest.json').read_text(encoding='utf-8'))
    def changed(root, entries):
        return [entry['path'] for entry in entries
                if not (root / entry['path']).is_file() or digest(root / entry['path']) != entry['sha256']]

    recorded_artifacts = {entry['path'] for entry in saved['artifacts']}
    actual_artifacts = {path.relative_to(app).as_posix() for path in app.rglob('*')
                        if path.is_file() and path.name != 'release-manifest.json'}
    artifacts = sorted(set(changed(app, saved['artifacts'])) | (actual_artifacts - recorded_artifacts))
    recorded_paths = {entry['path'] for entry in saved['source']['files']}
    raw_source_changes = set(changed(project, saved['source']['files']))
    source_hashes = {entry['path']: entry['sha256'] for entry in saved['source']['files']}
    line_endings = {name for name in raw_source_changes
                    if source_line_endings_match(project / name, source_hashes[name])}
    source_changes = sorted((raw_source_changes - line_endings) | (source_paths(project) - recorded_paths))
    runtime_changes = [name for name in source_changes if name.startswith(('gallery/', 'ui/', 'electron/', 'contracts/'))
                       or name.startswith('docs/brand/stillmark/') and name.endswith('.svg')
                       or name in ('pyproject.toml', 'uv.lock', 'package.json', 'package-lock.json', 'gallery_server.py')]
    return {'version': saved['version'], 'source_sha256_at_build': saved['source']['sha256'],
            'artifact_files_checked': len(saved['artifacts']), 'artifact_mismatches': artifacts,
            'source_line_ending_only_changes': sorted(line_endings),
            'runtime_source_mismatches': runtime_changes, 'all_source_changes_since_build': source_changes,
            'passed': not artifacts and not runtime_changes}


def verify_archive(archive):
    expected = archive.with_name(archive.name + '.sha256').read_text(encoding='ascii').split()[0]
    checksum = digest(archive)
    with zipfile.ZipFile(archive) as package:
        saved = json.loads(package.read('release-manifest.json'))
        recorded = {item['path'] for item in saved['artifacts']}
        actual = {item.filename for item in package.infolist() if not item.is_dir()} - {'release-manifest.json'}
        mismatches = set(recorded ^ actual)
        for item in saved['artifacts']:
            if item['path'] in actual:
                with package.open(item['path']) as stream:
                    if hashlib.file_digest(stream, 'sha256').hexdigest() != item['sha256']:
                        mismatches.add(item['path'])
    return {'archive': archive.name, 'sha256': checksum, 'checksum_matches': checksum == expected,
            'artifact_files_checked': len(recorded), 'artifact_mismatches': sorted(mismatches),
            'passed': checksum == expected and not mismatches}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--app', type=Path)
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    if args.archive:
        if args.app:
            parser.error('--app and --archive are mutually exclusive')
        report = verify_archive(args.archive)
        if args.output:
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit(0 if report['passed'] else 1)
    if not args.app:
        parser.error('--app or --archive is required')
    project = Path(__file__).resolve().parents[1]
    if not (args.app / 'GalleryTool.exe').is_file():
        parser.error('--app must contain the assembled GalleryTool.exe')
    if args.verify:
        report = verify(project, args.app)
        if args.output:
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit(0 if report['passed'] else 1)
    if not args.output:
        parser.error('--output is required when writing a build manifest')
    report = manifest(project, args.app)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f"Build manifest: {args.output}; source SHA256 {report['source']['sha256']}")


if __name__ == '__main__':
    main()
