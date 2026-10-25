"""Validate delivered SVG sources and assemble the optically sized Windows ICO."""

import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image

ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)
REQUIRED = ('mark', 'mark-monochrome', 'mark-light', 'mark-dark', 'wordmark', 'lockup', 'favicon', 'tray', 'app-icon')


def validate_sources(source):
    source = Path(source)
    for name in REQUIRED:
        if not (source / f'stillmark-{name}.svg').is_file():
            raise FileNotFoundError(f'Missing brand source: {name}')
    records = []
    for file in sorted(source.rglob('*.svg')):
        root = ET.parse(file).getroot()
        box = [float(number) for number in root.attrib['viewBox'].split()]
        if len(box) != 4 or min(box[2:]) <= 0:
            raise ValueError(f'Invalid SVG viewBox: {file.name}')
        paths = 0
        for element in root.iter():
            tag = element.tag.rsplit('}', 1)[-1]
            if tag not in ('svg', 'path', 'title', 'style'):
                raise ValueError(f'Unexpected SVG element: {file.name}: {tag}')
            paths += tag == 'path'
            for name, value in element.attrib.items():
                if name.lower().startswith('on') or 'href' in name or 'url(' in value.lower():
                    raise ValueError(f'SVG must be self-contained: {file.name}: {name}')
            if tag == 'style' and any(token in (element.text or '').lower() for token in ('url(', '@import')):
                raise ValueError(f'SVG style has external resources: {file.name}')
        if not paths:
            raise ValueError(f'SVG has no paths: {file.name}')
        records.append({'file': file.relative_to(source).as_posix(), 'viewBox': box,
                        'sha256': hashlib.sha256(file.read_bytes()).hexdigest()})
    return records


def assemble_ico(output):
    output = Path(output)
    images = []
    try:
        for size in ICON_SIZES:
            with Image.open(output / f'app-{size}.png') as source:
                if source.size != (size, size):
                    raise ValueError(f'Unexpected app icon dimensions: {size}')
                images.append(source.convert('RGBA'))
        images[-1].save(output / 'app.ico', format='ICO', sizes=[(size, size) for size in ICON_SIZES],
                        append_images=images[:-1])
        with Image.open(output / 'app.ico') as icon:
            if icon.ico.sizes() != {(size, size) for size in ICON_SIZES}:
                raise ValueError('The ICO is missing an intended size')
            for size, expected in zip(ICON_SIZES, images, strict=True):
                actual = icon.ico.getimage((size, size)).convert('RGBA')
                if actual.tobytes() != expected.tobytes():
                    raise ValueError(f'The ICO resampled an optical variant: {size}')
    finally:
        for image in images:
            image.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1] / 'docs/brand/stillmark'
    records = validate_sources(source)
    assemble_ico(args.output)
    (args.output / 'sources.json').write_text(json.dumps({'direction': 'D Corner Seal', 'sources': records,
                                                       'ico_sizes': ICON_SIZES}, indent=2) + '\n', encoding='utf-8')
    print(f'Validated {len(records)} SVG sources and {len(ICON_SIZES)} exact ICO variants')


if __name__ == '__main__':
    main()
