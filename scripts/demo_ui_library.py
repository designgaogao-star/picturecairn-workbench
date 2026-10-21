"""Generate an isolated library for frontend QA; never writes into a registered library.

Covers nested packages, loose root images, a 620-image package for paging, GIF/WebP animation,
transparency, a broken file, exact and contained duplicate packages, and hidden/non-image files.
"""

import argparse
import shutil
from pathlib import Path

from PIL import Image, ImageDraw


def picture(seed, size=(1200, 1600)):
    hue = (seed * 47) % 255
    image = Image.new('RGB', size, (40 + hue // 3, 60 + (hue * 3) % 120, 90 + (hue * 7) % 140))
    draw = ImageDraw.Draw(image)
    w, h = size
    draw.polygon([(0, h * .66), (w * (.35 + (seed % 7) * .05), h * (.2 + (seed % 5) * .03)), (w, h * .7)], fill='#a4b6ae')
    draw.polygon([(0, h * .87), (w * .6, h * .4), (w, h * .75), (w, h), (0, h)], fill='#293e3b')
    draw.ellipse((w * .72, h * .08, w * .86, h * .18), fill='#e0c885')
    draw.text((40, 40), f'#{seed}', fill='white')
    return image


def save(path, seed, size=(1200, 1600)):
    path.parent.mkdir(parents=True, exist_ok=True)
    picture(seed, size).save(path, quality=88)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    root = args.output
    if root.exists():
        raise SystemExit('Choose a new, empty output directory')

    seed = 0
    for group, albums in (('山色', 6), ('城市', 4)):
        for album in range(albums):
            for index in range(8):
                seed += 1
                save(root / group / f'影集 {album + 1:02d}' / f'{index + 1:03d}.jpg', seed)

    # Nested real directories: packages two levels below the group.
    for season in ('第1季', '第2季'):
        for vol in range(3):
            for index in range(5):
                seed += 1
                save(root / '[R18]嵌套作者' / season / f'Vol.{vol + 1:02d}' / f'{index + 1:03d}.jpg', seed, (1600, 1000))
    for index in range(3):
        seed += 1
        save(root / '[R18]嵌套作者' / f'散图{index + 1}.jpg', seed)

    # Large package to exercise paging (> 500 images).
    big = root / '[非R18]大图包' / '整包620'
    for index in range(620):
        seed += 1
        save(big / f'{index + 1:04d}.jpg', seed, (300, 400))

    # Animation, transparency, broken file and mixed aspect ratios.
    motion = root / '[R16]动图' / '动图合集'
    motion.mkdir(parents=True)
    frames = [Image.new('RGB', (480, 640), color) for color in ('#508b7c', '#b5a76e', '#824d5c', '#3d5a99')]
    for i, frame in enumerate(frames):
        ImageDraw.Draw(frame).rectangle((40 + i * 90, 260, 120 + i * 90, 380), fill='white')
    frames[0].save(motion / '01-gif.gif', save_all=True, append_images=frames[1:], duration=250, loop=0)
    frames[0].save(motion / '02-webp.webp', save_all=True, append_images=frames[1:], duration=250, loop=0)
    alpha = Image.new('RGBA', (900, 900), (0, 0, 0, 0))
    ImageDraw.Draw(alpha).ellipse((100, 100, 800, 800), fill=(220, 120, 80, 200))
    alpha.save(motion / '03-alpha.png')
    save(motion / '04-wide.jpg', 991, (3200, 900))
    save(motion / '05-tall.jpg', 992, (800, 3000))
    (motion / '06-broken.jpg').write_bytes(b'\xff\xd8\xff\xe0 not really a jpeg')
    Image.new('RGB', (480, 640), '#2b2b2b').save(motion / '07-static.gif')

    # Duplicate evidence: exact copy, contained subset, and a package with a unique non-image file.
    dup = root / '[其他]重复样本'
    base = dup / 'A 原包'
    for index in range(10):
        save(base / f'{index + 1:03d}.jpg', 2000 + index)
    (base / '说明.txt').write_text('原包附带说明', encoding='utf-8')
    shutil.copytree(base, dup / 'B 完全相同')
    subset = dup / 'C 子集'
    subset.mkdir()
    for index in range(6):
        shutil.copy2(base / f'{index + 1:03d}.jpg', subset / f'{index + 1:03d}.jpg')
    extra = dup / 'D 有独有内容'
    shutil.copytree(base, extra)
    save(extra / '011.jpg', 2100)
    (extra / '.hidden-note').write_text('hidden', encoding='utf-8')
    (extra / '说明.txt').write_text('改过的说明', encoding='utf-8')

    # Disposable group for delete tests.
    for album in range(3):
        for index in range(4):
            seed += 1
            save(root / '[其他]删除测试' / f'包 {album + 1}' / f'{index + 1:03d}.jpg', seed, (800, 600))

    for index in range(4):
        seed += 1
        save(root / f'根目录散图{index + 1}.jpg', seed)
    print(root)


if __name__ == '__main__':
    main()
