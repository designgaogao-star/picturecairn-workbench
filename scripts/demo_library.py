"""Generate isolated test images for browser QA; never writes into a registered library."""

import argparse
from pathlib import Path

from PIL import Image, ImageDraw


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('Choose a new, empty output directory')
    for group, base in (('山色', '#476968'), ('城市', '#916f60')):
        for album in range(8):
            folder = args.output / group / f'影集 {album + 1:02d}'
            folder.mkdir(parents=True)
            for index in range(6):
                image = Image.new('RGB', (1200, 1600), base)
                draw = ImageDraw.Draw(image)
                draw.polygon([(0, 1050), (550 + album * 30, 350 + index * 30), (1200, 1100)], fill='#a4b6ae')
                draw.polygon([(0, 1400), (750 - index * 30, 650), (1200, 1200), (1200, 1600), (0, 1600)], fill='#293e3b')
                draw.ellipse((900, 150, 1040, 290), fill='#e0c885')
                image.save(folder / f'{index + 1:03d}.jpg', quality=90)
    motion = args.output / '山色' / '影集 01' / 'motion.gif'
    frames = [Image.new('RGB', (240, 320), color) for color in ('#508b7c', '#b5a76e', '#824d5c')]
    frames[0].save(motion, save_all=True, append_images=frames[1:], duration=200, loop=0)
    print(args.output)


if __name__ == '__main__':
    main()
