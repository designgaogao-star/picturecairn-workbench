"""A portable release must include project and third-party licenses without replacing Electron's."""

import json
from pathlib import Path

import pytest

from scripts import collect_licenses


@pytest.fixture
def release_tree(tmp_path):
    pytest.importorskip('PyInstaller')
    project = tmp_path / 'project'
    project.mkdir()
    source = Path(__file__).resolve().parents[1]
    for name in ('LICENSE', 'THIRD_PARTY_NOTICES.md', 'pyproject.toml'):
        (project / name).write_bytes((source / name).read_bytes())
    for name in ('preact', '@preact/signals', '@preact/signals-core', 'lucide'):
        module = project / 'node_modules' / name
        module.mkdir(parents=True)
        (module / 'package.json').write_text(json.dumps({'name': name, 'version': 'test', 'license': 'MIT'}),
                                            encoding='utf-8')
        (module / 'LICENSE').write_text('Synthetic QA license for ' + name, encoding='utf-8')
    app = tmp_path / 'app'
    app.mkdir()
    (app / 'LICENSE').write_text('Electron license stays intact', encoding='utf-8')
    return project, app


def test_collects_transitive_runtime_and_build_licenses_without_overwriting_electron(release_tree):
    project, app = release_tree
    report = collect_licenses.collect(project, app)
    packages = {item['name']: item for item in report['packages']}
    assert {'fastapi', 'pydantic', 'pydantic-core', 'pillow', 'numpy', 'scipy', 'anyio'} <= packages.keys()
    assert packages['pydantic']['scope'] == 'runtime'
    assert packages['pyinstaller']['scope'] == 'build'
    assert (app / 'LICENSE').read_text(encoding='utf-8') == 'Electron license stays intact'
    assert (app / 'LICENSE.txt').read_bytes() == (project / 'LICENSE').read_bytes()
    for item in report['packages'] + report['javascript']:
        assert item['files'], item['name']
        assert all((app / file).is_file() and (app / file).stat().st_size for file in item['files'])
    assert (app / report['interpreter']['file']).is_file()
    saved = json.loads((app / 'licenses/index.json').read_text(encoding='utf-8'))
    assert saved == report
    # The distributed index uses relative locations and does not leak the builder's workspace path.
    assert str(project) not in json.dumps(report)


def test_missing_javascript_license_fails_the_release(release_tree):
    project, app = release_tree
    (project / 'node_modules/preact/LICENSE').unlink()
    with pytest.raises(FileNotFoundError, match='preact'):
        collect_licenses.collect(project, app)
