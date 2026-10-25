"""The 16/24px optical icons must survive ICO assembly without resampling."""

from pathlib import Path

import pytest
from PIL import Image

from scripts.brand_assets import ICON_SIZES, assemble_ico, validate_sources


def test_delivered_sources_are_self_contained_path_artwork():
    source = Path(__file__).resolve().parents[1] / 'docs/brand/stillmark'
    records = validate_sources(source)
    assert len(records) == 32
    assert any(record['file'] == 'extra/stillmark-mark-16.svg' for record in records)


def test_ico_keeps_all_optical_variants_and_rejects_missing_size(tmp_path):
    for index, size in enumerate(ICON_SIZES):
        Image.new('RGBA', (size, size), (index * 30, 100, 170, 255)).save(tmp_path / f'app-{size}.png')
    assemble_ico(tmp_path)
    with Image.open(tmp_path / 'app.ico') as icon:
        assert icon.ico.getimage((16, 16)).getpixel((0, 0))[:3] == (0, 100, 170)
        assert icon.ico.getimage((24, 24)).getpixel((0, 0))[:3] == (30, 100, 170)
    (tmp_path / 'app-24.png').unlink()
    with pytest.raises(FileNotFoundError):
        assemble_ico(tmp_path)
