"""Copy licenses from the locked build environment into a portable application."""

import argparse
import importlib.metadata
import json
import platform
import shutil
import sys
import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

JAVASCRIPT = ('preact', '@preact/signals', '@preact/signals-core', 'lucide')


def dependencies(requirements):
    result, pending = {}, list(requirements)
    while pending:
        requirement = Requirement(pending.pop())
        if requirement.marker and not requirement.marker.evaluate({'extra': ''}):
            continue
        name = canonicalize_name(requirement.name)
        if name in result:
            continue
        distribution = importlib.metadata.distribution(name)
        result[name] = distribution
        pending.extend(distribution.requires or ())
    return result


def collect(project, app):
    project, app = Path(project), Path(app)
    settings = tomllib.loads((project / 'pyproject.toml').read_text(encoding='utf-8'))
    runtime = dependencies(settings['project']['dependencies'])
    packages = {**dependencies(['PyInstaller']), **runtime}
    app.mkdir(parents=True, exist_ok=True)

    def copy(source, relative):
        target = app / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return target.relative_to(app).as_posix()

    # Electron's root LICENSE is deliberately retained; the project license has its own name.
    copy(project / 'LICENSE', 'LICENSE.txt')
    copy(project / 'THIRD_PARTY_NOTICES.md', 'THIRD_PARTY_NOTICES.md')
    interpreter = copy(Path(sys.base_prefix) / 'LICENSE.txt', 'licenses/python-interpreter.txt')
    report = {'interpreter': {'version': platform.python_version(), 'file': interpreter},
              'packages': [], 'javascript': []}
    for name, distribution in sorted(packages.items()):
        files = []
        for entry in distribution.files or ():
            if not any(token in entry.name.lower() for token in ('license', 'licence', 'copying', 'notice')):
                continue
            if entry.is_absolute() or '..' in entry.parts:
                raise ValueError(f'License path must stay within its distribution: {name}: {entry}')
            files.append(copy(distribution.locate_file(entry), Path('licenses/python') / name / entry))
        if not files:
            raise FileNotFoundError(f'No license files in installed distribution: {name}')
        report['packages'].append({'name': name, 'version': distribution.version,
                                   'scope': 'runtime' if name in runtime else 'build',
                                   'license_expression': distribution.metadata.get('License-Expression'),
                                   'files': sorted(files)})
    for name in JAVASCRIPT:
        source = project / 'node_modules' / name
        package = json.loads((source / 'package.json').read_text(encoding='utf-8'))
        license_path = source / 'LICENSE'
        if not license_path.is_file():
            raise FileNotFoundError(f'JavaScript license is missing: {name}')
        license_file = copy(license_path, Path('licenses/javascript') / name.replace('/', '__') / 'LICENSE')
        report['javascript'].append({'name': name, 'version': package['version'], 'license': package.get('license'),
                                     'files': [license_file]})
    (app / 'licenses/index.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--app', required=True, type=Path)
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    report = collect(project, args.app)
    print(f"Collected licenses: {len(report['packages'])} Python distributions, "
          f"{len(report['javascript'])} JavaScript packages")


if __name__ == '__main__':
    main()
