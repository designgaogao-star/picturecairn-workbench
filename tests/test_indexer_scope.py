"""A subtree refresh must not enumerate or update unrelated library directories."""

import os
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from gallery.catalog import Catalog, new_id
from gallery.events import Events
from gallery.indexer import Indexer
from gallery.jobs import Context, Resources


@pytest.fixture
def indexed(tmp_path):
    root = tmp_path / 'library'
    (root / 'group/package/empty/deep').mkdir(parents=True)
    (root / 'unrelated/package').mkdir(parents=True)
    for relative in ('group/package/image.png', 'unrelated/package/old.png'):
        with Image.new('RGB', (16, 16), 'navy') as image:
            image.save(root / relative)
    catalog = Catalog(tmp_path / 'data/catalog.sqlite')
    events = Events()
    resources = Resources()
    manager = SimpleNamespace(catalog=catalog, events=events, resources=resources, stopping=threading.Event())
    indexer = Indexer(catalog, events)
    library = catalog.add_library(root)
    try:
        indexer.scan(Context(manager, new_id()), {'library_id': library['id'], 'force': True})
        yield root, catalog, indexer, manager, library
    finally:
        catalog.close()


def track_enumeration(monkeypatch):
    visited = []
    original = os.scandir

    def scandir(path):
        visited.append(Path(path).resolve())
        return original(path)

    monkeypatch.setattr(os, 'scandir', scandir)
    return visited


@pytest.mark.parametrize('relative,package_relative', [
    ('group', 'group'),
    ('group/package/empty/deep', 'group/package'),
])
def test_scoped_scan_uses_original_package_without_scanning_siblings(indexed, monkeypatch,
                                                                    relative, package_relative):
    root, catalog, indexer, manager, library = indexed
    target = root / relative
    directory = catalog.one('SELECT * FROM directories WHERE rel=?', (relative,))
    package = catalog.one('SELECT p.id FROM packages p JOIN directories d ON d.id=p.directory_id WHERE d.rel=?',
                          (package_relative,))
    with Image.new('RGB', (16, 16), 'orange') as image:
        image.save(target / 'new.png')
        image.save(root / 'unrelated/package/later.png')
    visited = track_enumeration(monkeypatch)

    result = indexer.scan(Context(manager, new_id()), {'library_id': library['id'],
                          'directory_id': directory['id'], 'force': True})

    assert result['online'] and result['failed_directories'] == 0
    assert visited and all(path.is_relative_to(target) for path in visited), visited
    added = catalog.one('SELECT * FROM files WHERE rel=?', (relative + '/new.png',))
    assert added['package_id'] == package['id'] and added['group_id'] == directory['group_id']
    assert catalog.one("SELECT id FROM files WHERE rel='unrelated/package/later.png'") is None


def test_dedup_build_refreshes_only_its_selected_group(indexed, monkeypatch):
    from gallery.dedup import Dedup

    root, catalog, indexer, manager, _library = indexed
    group = catalog.one("SELECT * FROM directories WHERE rel='group'")
    second = root / 'group/second'
    second.mkdir()
    with Image.new('RGB', (16, 16), 'orange') as image:
        image.save(second / 'peer.png')
        image.save(root / 'unrelated/package/later.png')
    visited = track_enumeration(monkeypatch)
    dedup = Dedup(catalog, indexer.access, manager.resources, indexer)

    result = dedup.build(Context(manager, new_id()), {'group_id': group['id']})

    assert result['indexed'] == 2 and result['failed'] == 0
    assert visited and all(path.is_relative_to(root / 'group') for path in visited), visited
    assert catalog.one("SELECT id FROM files WHERE rel='group/second/peer.png'") is not None
    assert catalog.one("SELECT id FROM files WHERE rel='unrelated/package/later.png'") is None
