"""Build every Stillmark SVG asset into docs/brand/stillmark (run from this folder)."""
import math
import os

import brandlib as b
from brandlib import INK, PAPER, SEAL, STONE, STONE_DARK, TILE_EDGE

OUT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
EXTRA = os.path.join(OUT, 'extra')
EXPLORE = os.path.join(OUT, 'exploration')

ADAPT = '@media (prefers-color-scheme:dark){.ink{fill:%s}.stone{fill:%s}}' % (PAPER, STONE_DARK)
TITLE = 'Stillmark 影迹图片工作台'


def p(*parts):
    return os.path.join(*parts)


# ---------------------------------------------------------------- lockups

def lockup_parts():
    """Horizontal lockup on 560×128.

    The 64-grid mark is drawn at 2× so its visible box is (8, 8)–(120, 120).
    Text starts one seal width (48) after the mark. Cap height 64 = 2/3 of the still,
    cap top on the mark top, subtitle foot on the mark bottom, subtitle left edge on the S.
    """
    m = b.mark()
    still, seal = b.tf(m['still'], 2), b.tf(m['seal'], 2)
    text_x = 8 + 112 + 48
    word, _ = b.wordmark(b.RECOMMENDED_WORD, 64, 0, 8 + 64)
    word = b.tf(word, 1, text_x - word.bounds[0], 0)
    sub, _ = b.cjk(b.SUBTITLE, 28, 420, 180)
    sub = b.tf(sub, 1, text_x - sub.bounds[0], 120 - sub.bounds[3])
    return still, seal, word, sub


def lockup_svg(mode):
    still, seal, word, sub = lockup_parts()
    view = (560, 128)
    if mode == 'adaptive':
        layers = [(INK, still, 'ink'), (SEAL, seal, None), (INK, word, 'ink'), (STONE, sub, 'stone')]
        return b.svg(view, layers, TITLE, style=ADAPT)
    fg, sg = (PAPER, STONE_DARK) if mode == 'dark' else (INK, STONE)
    return b.svg(view, [(fg, still, None), (SEAL, seal, None), (fg, word, None), (sg, sub, None)], TITLE)


def stacked_parts():
    """Stacked lockup on 320×256: mark 112 centred, cap 48 (= 1/2 still), subtitle 20."""
    m = b.mark()
    top = 9
    still = b.tf(m['still'], 2, 160 - 64, top - 8)
    seal = b.tf(m['seal'], 2, 160 - 64, top - 8)
    baseline = top + 112 + 40 + 48
    word, _ = b.wordmark(b.RECOMMENDED_WORD, 48, 0, baseline)
    wb = word.bounds
    word = b.tf(word, 1, 160 - (wb[0] + wb[2]) / 2, 0)
    sub, _ = b.cjk(b.SUBTITLE, 20, 420, 180)
    sb = sub.bounds
    sub = b.tf(sub, 1, 160 - (sb[0] + sb[2]) / 2, baseline + 20 - sb[1])
    return still, seal, word, sub


def stacked_svg(dark=False):
    still, seal, word, sub = stacked_parts()
    fg, sg = (PAPER, STONE_DARK) if dark else (INK, STONE)
    return b.svg((320, 256), [(fg, still, None), (SEAL, seal, None), (fg, word, None), (sg, sub, None)], TITLE)


def wordmark_svg(mode):
    cap = 62.0
    word, _ = b.wordmark(b.RECOMMENDED_WORD, cap, 0, 0)
    x0, _, x1, _ = word.bounds
    # ink centred in 420×96; the cap band sits on the vertical centre
    word = b.tf(word, 1, (420 - (x1 - x0)) / 2 - x0, (96 + cap) / 2)
    if mode == 'adaptive':
        return b.svg((420, 96), [(INK, word, 'ink')], 'Stillmark', style=ADAPT)
    return b.svg((420, 96), [(PAPER if mode == 'dark' else INK, word, None)], 'Stillmark')


def wordmark_ui_svg():
    """Tight wordmark for in-app use: cap 32, ink centred in an integer box, fill follows CSS color."""
    word, _ = b.wordmark(b.RECOMMENDED_WORD, 32, 0, 0)
    x0, y0, x1, y1 = word.bounds
    w, h = math.ceil(x1 - x0), math.ceil(y1 - y0)
    word = b.tf(word, 1, (w - (x1 - x0)) / 2 - x0, (h - (y1 - y0)) / 2 - y0)
    return b.svg((w, h), [('currentColor', word, None)], 'Stillmark', extra_attrs=f' color="{INK}"')


# ---------------------------------------------------------------- icons

def plate(g, fill_tile=INK):
    """Mark on an ink tile, pixel-snapped grid (favicon 16, app icon 24)."""
    n = g.n
    m = b.mark(g)
    layers = [(fill_tile, b.rrect(0, 0, n, n, n * 0.1875), None), (PAPER, m['still'], None), (SEAL, m['seal'], None)]
    return b.svg((n, n), layers, 'Stillmark')


def app_icon_svg():
    """256 grid: tile inset 12, radius 46, 2-unit edge, mark at 60 % of the tile."""
    n = 256
    margin = 12.0
    t = n - 2 * margin
    r = 46.0
    edge = b.rrect(margin, margin, t, t, r)
    inner = b.rrect(margin + 2, margin + 2, t - 4, t - 4, r - 2)
    m = b.mark()
    s = 0.6 * t / 56
    off = n / 2 - 32 * s
    still = b.tf(m['still'], s, off, off)
    seal = b.tf(m['seal'], s, off, off)
    layers = [(TILE_EDGE, edge, None), (INK, inner, None), (PAPER, still, None), (SEAL, seal, None)]
    return b.svg((n, n), layers, 'Stillmark')


def avatar_svg():
    n = 512
    m = b.mark()
    s = 0.5 * n / 56
    off = n / 2 - 32 * s
    layers = [(INK, b.rrect(0, 0, n, n, 0), None), (PAPER, b.tf(m['still'], s, off, off), None),
              (SEAL, b.tf(m['seal'], s, off, off), None)]
    return b.svg((n, n), layers, 'Stillmark')


def reverse_svg():
    """单色反白: the mark knocked out of one ink plate (single colour, background shows through)."""
    m = b.mark()
    plate_ = b.rrect(0, 0, 64, 64, 12)
    s = 44 / 56
    off = 32 - 32 * s
    cut = b.union(b.tf(m['still'], s, off, off), b.tf(m['seal'], s, off, off))
    return b.svg((64, 64), [(INK, b.diff(plate_, cut), None)], 'Stillmark')


def mono(g, color):
    m = b.mark(g)
    return b.svg((g.n, g.n), [(color, b.union(m['still'], m['seal']), None)], 'Stillmark')


def small_color(g):
    """Pixel-snapped colour mark for UI chrome: still follows CSS color (ink by default), seal stays vermilion."""
    m = b.mark(g)
    return b.svg((g.n, g.n), [('currentColor', m['still'], None), (SEAL, m['seal'], None)], 'Stillmark',
                 extra_attrs=f' color="{INK}"')


def mark_svg(mode):
    m = b.mark()
    if mode == 'adaptive':
        return b.svg((64, 64), [(INK, m['still'], 'ink'), (SEAL, m['seal'], None)], 'Stillmark', style=ADAPT)
    if mode == 'mono':
        both = b.union(m['still'], m['seal'])
        return b.svg((64, 64), [('currentColor', both, None)], 'Stillmark', extra_attrs=f' color="{INK}"')
    if mode in ('black', 'white'):
        return b.svg((64, 64), [('#000000' if mode == 'black' else '#FFFFFF', b.union(m['still'], m['seal']), None)],
                     'Stillmark')
    fg = PAPER if mode == 'dark' else INK
    return b.svg((64, 64), [(fg, m['still'], None), (SEAL, m['seal'], None)], 'Stillmark')


def exploration_svgs():
    out = {}
    for key, fn in (('a-index-print', b.mark_index_print), ('b-resume-path', b.mark_resume_path),
                    ('c-proof-line', b.mark_proof_line), ('d-corner-seal', b.mark)):
        m = fn()
        out[key] = b.svg((64, 64), [(INK, m['still'], None), (SEAL, m['seal'], None)], key)
    return out


def main():
    files = {
        p(OUT, 'stillmark-mark.svg'): mark_svg('adaptive'),
        p(OUT, 'stillmark-mark-monochrome.svg'): mark_svg('mono'),
        p(OUT, 'stillmark-mark-light.svg'): mark_svg('light'),
        p(OUT, 'stillmark-mark-dark.svg'): mark_svg('dark'),
        p(OUT, 'stillmark-wordmark.svg'): wordmark_svg('adaptive'),
        p(OUT, 'stillmark-lockup.svg'): lockup_svg('adaptive'),
        p(OUT, 'stillmark-favicon.svg'): plate(b.PLATE16),
        p(OUT, 'stillmark-tray.svg'): mono(b.SMALL16, '#000000'),
        p(OUT, 'stillmark-app-icon.svg'): app_icon_svg(),
        p(EXTRA, 'stillmark-mark-black.svg'): mark_svg('black'),
        p(EXTRA, 'stillmark-mark-white.svg'): mark_svg('white'),
        p(EXTRA, 'stillmark-mark-reverse.svg'): reverse_svg(),
        p(EXTRA, 'stillmark-mark-16.svg'): small_color(b.SMALL16),
        p(EXTRA, 'stillmark-mark-24.svg'): small_color(b.SMALL24),
        p(EXTRA, 'stillmark-wordmark-light.svg'): wordmark_svg('light'),
        p(EXTRA, 'stillmark-wordmark-dark.svg'): wordmark_svg('dark'),
        p(EXTRA, 'stillmark-wordmark-ui.svg'): wordmark_ui_svg(),
        p(EXTRA, 'stillmark-lockup-light.svg'): lockup_svg('light'),
        p(EXTRA, 'stillmark-lockup-dark.svg'): lockup_svg('dark'),
        p(EXTRA, 'stillmark-lockup-stacked.svg'): stacked_svg(False),
        p(EXTRA, 'stillmark-lockup-stacked-dark.svg'): stacked_svg(True),
        p(EXTRA, 'stillmark-tray-white.svg'): mono(b.SMALL16, '#FFFFFF'),
        p(EXTRA, 'stillmark-tray-20.svg'): mono(b.SMALL20, '#000000'),
        p(EXTRA, 'stillmark-tray-20-white.svg'): mono(b.SMALL20, '#FFFFFF'),
        p(EXTRA, 'stillmark-tray-24.svg'): mono(b.SMALL24, '#000000'),
        p(EXTRA, 'stillmark-tray-24-white.svg'): mono(b.SMALL24, '#FFFFFF'),
        p(EXTRA, 'stillmark-app-icon-24.svg'): plate(b.PLATE24),
        p(EXTRA, 'stillmark-avatar.svg'): avatar_svg(),
    }
    for key, text in exploration_svgs().items():
        files[p(EXPLORE, f'{key}.svg')] = text
    for path, text in files.items():
        b.write(path, text)
        print(f'{os.path.relpath(path, OUT):45s} {len(text.encode()):6d} B')
    # layout report: lockup ink must stay inside its box
    for name, parts, box in (('lockup', lockup_parts(), (560, 128)), ('stacked', stacked_parts(), (320, 256))):
        x0, y0, x1, y1 = b.bounds(*parts)
        print(f'{name}: ink {x0:.2f},{y0:.2f} – {x1:.2f},{y1:.2f} in {box}')


if __name__ == '__main__':
    main()
