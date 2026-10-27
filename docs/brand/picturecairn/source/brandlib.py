"""PictureCairn brand geometry, typography and SVG output.

Shapes are drawn on fixed grids (mark 64, small icons 16/24, app icon 256), turned into
filled outlines with pathops, and written as plain SVG paths: no strokes, filters, fonts or CSS
dependencies in the delivered files.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass

import pathops
import uharfbuzz as hb
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont
from shapely.geometry import JOIN_STYLE, MultiPolygon, box
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

# ---------------------------------------------------------------- palette

INK = '#1E2225'        # 墨: still, wordmark on light
PAPER = '#F3F2EE'      # 纸: still and wordmark on dark, brand light surface
SEAL = '#E2532A'       # 朱: the seal, the only brand accent
STONE = '#5E676B'      # 石: subtitle on light
STONE_DARK = '#A7B0B3'  # subtitle on dark
TILE_EDGE = '#3A4146'  # hairline that keeps the ink tile visible on dark taskbars

FONT_DIR = os.environ.get('PICTURECAIRN_FONTS', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fonts'))
FONTS = {
    'instrument': os.path.join(FONT_DIR, 'InstrumentSans.ttf'),
    'plex': os.path.join(FONT_DIR, 'IBMPlexSans.ttf'),
    'hanken': os.path.join(FONT_DIR, 'HankenGrotesk.ttf'),
    'source': os.path.join(FONT_DIR, 'SourceSans3.ttf'),
    'noto_sc': os.environ.get('PICTURECAIRN_CJK', 'C:/Windows/Fonts/NotoSansSC-VF.ttf'),
}

# ---------------------------------------------------------------- shapely + fillets

KAPPA = 0.5522847498


def R(x, y, w, h):
    return box(x, y, x + w, y + h)


def U(*gs):
    return unary_union([g for g in gs if g is not None])


def D(a, *bs):
    return a.difference(unary_union(bs))


def grow(g, d):
    return g.buffer(d, join_style=JOIN_STYLE.mitre)


def _clean(coords, eps=1e-6):
    pts = [tuple(p) for p in coords[:-1]]
    out = []
    for i in range(len(pts)):
        a, b, c = pts[i - 1], pts[i], pts[(i + 1) % len(pts)]
        cross = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
        if abs(cross) > eps and math.dist(a, b) > eps:
            out.append(b)
    return out


def _ring(pts, radius, path):
    n = len(pts)
    corners = []
    for i in range(n):
        a, b, c = pts[i - 1], pts[i], pts[(i + 1) % n]
        d1 = (b[0] - a[0], b[1] - a[1])
        d2 = (c[0] - b[0], c[1] - b[1])
        l1, l2 = math.hypot(*d1), math.hypot(*d2)
        u1, u2 = (d1[0] / l1, d1[1] / l1), (d2[0] / l2, d2[1] / l2)
        cross = u1[0] * u2[1] - u1[1] * u2[0]
        turn = math.atan2(cross, u1[0] * u2[0] + u1[1] * u2[1])
        r = radius(b, cross > 0)
        corners.append([b, u1, u2, turn, abs(r * math.tan(turn / 2)) if r > 0 else 0.0, l2])
    for _ in range(4):  # keep neighbouring tangents from overlapping
        for i in range(n):
            j = (i + 1) % n
            edge = corners[i][5]
            if corners[i][4] + corners[j][4] > edge + 1e-9:
                s = edge / (corners[i][4] + corners[j][4])
                corners[i][4] *= s
                corners[j][4] *= s
    first = True
    for b, u1, u2, turn, t, _ in corners:
        if t <= 1e-9:
            (path.moveTo if first else path.lineTo)(*b)
            first = False
            continue
        p1 = (b[0] - u1[0] * t, b[1] - u1[1] * t)
        p2 = (b[0] + u2[0] * t, b[1] + u2[1] * t)
        rr = t / abs(math.tan(turn / 2))
        h = 4 / 3 * math.tan(abs(turn) / 4) * rr
        (path.moveTo if first else path.lineTo)(*p1)
        first = False
        path.cubicTo(p1[0] + u1[0] * h, p1[1] + u1[1] * h, p2[0] - u2[0] * h, p2[1] - u2[1] * h, *p2)
    path.close()


def fillet(geom, convex=0.0, concave=0.0, at=None):
    """Polygon(s) -> pathops Path. `at` maps exact vertices to their own radius."""
    at = at or {}

    def radius(pt, is_convex):
        key = (round(pt[0], 4), round(pt[1], 4))
        if key in at:
            return at[key]
        return convex if is_convex else concave

    path = pathops.Path()
    for p in (geom.geoms if isinstance(geom, MultiPolygon) else [geom]):
        if p.is_empty:
            continue
        p = orient(p, sign=1.0)
        _ring(_clean(list(p.exterior.coords)), radius, path)
        for hole in p.interiors:
            _ring(_clean(list(hole.coords)), radius, path)
    return path


# ---------------------------------------------------------------- pathops helpers

def centerline(points, radius=0.0):
    p = pathops.Path()
    p.moveTo(*points[0])
    for i in range(1, len(points) - 1):
        a, b, c = points[i - 1], points[i], points[i + 1]
        if radius <= 0:
            p.lineTo(*b)
            continue
        d1 = (b[0] - a[0], b[1] - a[1])
        l1 = math.hypot(*d1)
        d2 = (c[0] - b[0], c[1] - b[1])
        l2 = math.hypot(*d2)
        u1, u2 = (d1[0] / l1, d1[1] / l1), (d2[0] / l2, d2[1] / l2)
        turn = abs(math.atan2(u1[0] * u2[1] - u1[1] * u2[0], u1[0] * u2[0] + u1[1] * u2[1]))
        t = radius * math.tan(turn / 2)
        h = 4 / 3 * math.tan(turn / 4) * radius
        p1 = (b[0] - u1[0] * t, b[1] - u1[1] * t)
        p2 = (b[0] + u2[0] * t, b[1] + u2[1] * t)
        p.lineTo(*p1)
        p.cubicTo(p1[0] + u1[0] * h, p1[1] + u1[1] * h, p2[0] - u2[0] * h, p2[1] - u2[1] * h, *p2)
    p.lineTo(*points[-1])
    return p


def stroke(path, width):
    q = pathops.Path(path)
    q.stroke(width, pathops.LineCap.BUTT_CAP, pathops.LineJoin.MITER_JOIN, 4)
    q.simplify()
    return q


def union(*ps):
    out = pathops.Path()
    for p in ps:
        out = pathops.op(out, p, pathops.PathOp.UNION)
    return out


def diff(a, *bs):
    out = pathops.Path(a)
    for b in bs:
        out = pathops.op(out, b, pathops.PathOp.DIFFERENCE)
    return out


def tf(p, s=1.0, tx=0.0, ty=0.0, sy=None):
    return p.transform(s, 0, 0, s if sy is None else sy, tx, ty)


def rrect(x, y, w, h, r=0.0):
    return fillet(R(x, y, w, h), r)


def contours(p):
    rec = RecordingPen()
    p.draw(rec)
    out, cur = [], None
    for op, args in rec.value:
        if op == 'moveTo':
            cur = pathops.Path()
            pen = cur.getPen()
            out.append(cur)
        getattr(pen, op)(*args)
    return out


def to_d(path, nd=2):
    def num(v):
        s = f'{round(v, nd):.{nd}f}'.rstrip('0').rstrip('.')
        return '0' if s in ('-0', '') else s

    pen = SVGPathPen(None, ntos=num)
    path.draw(pen)
    return pen.getCommands()


def bounds(*ps):
    bs = [p.bounds for p in ps if p.bounds != (0, 0, 0, 0)]
    return (min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs))


# ---------------------------------------------------------------- the mark (recommended: 压角印)

@dataclass(frozen=True)
class Grid:
    """Corner-seal construction on an n-unit square.

    still  : the image, a square with three soft corners
    seal   : vermilion square pressed over the still's lower-left corner
    gap    : channel cut around the seal, kept even with a concentric inner corner
    """
    n: float
    still: tuple
    seal: tuple
    gap: float
    r_still: float
    r_seal: float
    r_notch: float


MASTER = Grid(64, still=(12, 4, 48, 48), seal=(4, 36, 24, 24), gap=4, r_still=6, r_seal=3, r_notch=2)
# pixel-snapped masters for small sizes: integer edges at 1x (and 2x)
SMALL16 = Grid(16, still=(3, 1, 12, 12), seal=(1, 9, 6, 6), gap=1, r_still=1.25, r_seal=0.75, r_notch=0.4)
SMALL20 = Grid(20, still=(4, 1, 15, 15), seal=(1, 11, 8, 8), gap=1, r_still=1.5, r_seal=0.9, r_notch=0.45)
SMALL24 = Grid(24, still=(5, 2, 18, 18), seal=(2, 14, 9, 9), gap=1, r_still=1.75, r_seal=1, r_notch=0.5)
# favicon/app icon plate on 16: the mark sits inside an ink tile
PLATE16 = Grid(16, still=(4, 2, 10, 10), seal=(2, 9, 5, 5), gap=1, r_still=1, r_seal=0.6, r_notch=0.35)
PLATE24 = Grid(24, still=(6, 3, 15, 15), seal=(3, 13, 8, 8), gap=1, r_still=1.5, r_seal=0.9, r_notch=0.4)


def mark(g: Grid = MASTER):
    sx, sy, sw, sh = g.still
    kx, ky, kw, kh = g.seal
    still = R(sx, sy, sw, sh)
    seal = R(kx, ky, kw, kh)
    body = D(still, grow(seal, g.gap))
    # inner corner of the channel follows the seal corner (concentric), others stay crisp
    inner = (round(kx + kw + g.gap, 4), round(ky - g.gap, 4))
    at = {inner: g.r_seal + g.gap}
    notch = [(round(sx, 4), round(ky - g.gap, 4)), (round(kx + kw + g.gap, 4), round(sy + sh, 4))]
    for v in notch:
        at[v] = g.r_notch
    return {'still': fillet(body, g.r_still, g.r_notch, at), 'seal': fillet(seal, g.r_seal)}


# ---------------------------------------------------------------- exploration marks (A/B/C)

def mark_index_print(hollow=False):
    """A 索引印相: a 3×3 index print, one frame marked."""
    cells, marked = [], None
    for j in range(3):
        for i in range(3):
            c = R(4 + i * 20, 4 + j * 20, 16, 16)
            if (j, i) == (1, 2):
                marked = c
            else:
                cells.append(c)
    out = {'still': fillet(U(*cells), 2)}
    if hollow:
        out['seal'] = fillet(D(marked, R(48, 28, 8, 8)), 2, 1)
    else:
        out['seal'] = fillet(marked, 2)
    return out


def mark_resume_path():
    """B 续看径: browsing path through three rows, ending at the remembered still."""
    pts = [(60, 8), (8, 8), (8, 30), (56, 30), (56, 52), (24, 52)]
    return {'still': stroke(centerline(pts, 8), 8), 'seal': rrect(4, 44, 16, 16, 2)}


def mark_proof_line():
    """C 对照线: two stills compared across one vermilion proof line."""
    stills = U(R(4, 16, 22, 32), R(38, 16, 22, 32))
    return {'still': fillet(stills, 3), 'seal': rrect(30, 8, 4, 48, 1)}


# ---------------------------------------------------------------- typography

_faces: dict = {}


def _font(path):
    if path not in _faces:
        _faces[path] = (hb.Face(hb.Blob.from_file_path(path)), TTFont(path, lazy=True))
    face, tt = _faces[path]
    return face, hb.Font(face), tt


def font_metrics(path):
    face, _, tt = _font(path)
    os2 = tt['OS/2']
    return {'upem': face.upem, 'cap': os2.sCapHeight, 'x': os2.sxHeight}


def shape(path, text, size, wght=None, tracking=0.0, x=0.0, baseline=0.0):
    """Shape text and return [(glyph name, Path)] plus advance; tracking in 1/1000 em."""
    face, font, _ = _font(path)
    if wght is not None:
        font.set_variations({'wght': wght})
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(font, buf, {'kern': True, 'liga': False, 'calt': False})
    s = size / face.upem
    pen_x, out = 0.0, []
    infos = list(zip(buf.glyph_infos, buf.glyph_positions))
    for i, (info, pos) in enumerate(infos):
        p = pathops.Path()
        rec = RecordingPen()
        font.draw_glyph_with_pen(info.codepoint, rec)
        pen = p.getPen()
        ox = x + (pen_x + pos.x_offset) * s
        oy = baseline - pos.y_offset * s
        for op, args in rec.value:
            pts = [(ox + a[0] * s, oy - a[1] * s) if a is not None else None for a in args]
            getattr(pen, op)(*pts)
        out.append((font.glyph_to_string(info.codepoint), p))
        pen_x += pos.x_advance + (tracking * face.upem / 1000 if i < len(infos) - 1 else 0)
    return out, pen_x * s


@dataclass(frozen=True)
class Wordface:
    font: str
    wght: float
    tracking: float
    square_dot: bool = False
    text: str = 'PictureCairn'


RECOMMENDED_WORD = Wordface('instrument', 560, 10, square_dot=True)


def wordmark(face: Wordface, cap: float, x=0.0, baseline=0.0):
    """Wordmark outlines sized by cap height. Returns (Path, advance)."""
    path = FONTS[face.font]
    m = font_metrics(path)
    size = cap * m['upem'] / m['cap']
    glyphs, adv = shape(path, face.text, size, face.wght, face.tracking, x, baseline)
    xh = m['x'] * size / m['upem']
    parts = []
    for name, p in glyphs:
        if face.square_dot and name == 'i':
            cs = contours(p)
            stem = [c for c in cs if c.bounds[3] > baseline - xh - 1]
            dot = [c for c in cs if c.bounds[3] <= baseline - xh - 1]
            sx0, sx1 = min(c.bounds[0] for c in stem), max(c.bounds[2] for c in stem)
            cy = (min(c.bounds[1] for c in dot) + max(c.bounds[3] for c in dot)) / 2
            w = sx1 - sx0
            p = union(*stem, rrect(sx0, cy - w / 2, w, w))
        parts.append(p)
    return union(*parts), adv


def cjk(text, size, wght=420, tracking=180, x=0.0, baseline=0.0):
    glyphs, adv = shape(FONTS['noto_sc'], text, size, wght, tracking, x, baseline)
    return union(*[p for _, p in glyphs]), adv


SUBTITLE = '影标图片工作台'


# ---------------------------------------------------------------- SVG writing

def svg(view, layers, title, width=None, height=None, style=None, extra_attrs=''):
    """layers: [(fill, Path, class or None)]; view: (w, h) or (x, y, w, h)."""
    if len(view) == 2:
        view = (0, 0, *view)
    vb = ' '.join(f'{v:g}' for v in view)
    w = width if width is not None else view[2]
    h = height if height is not None else view[3]
    body = []
    if style:
        body.append(f'<style>{style}</style>')
    for fill, p, cls in layers:
        c = f' class="{cls}"' if cls else ''
        body.append(f'<path{c} fill="{fill}" d="{to_d(p)}"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}" width="{w:g}" height="{h:g}"{extra_attrs}>'
            f'<title>{title}</title>' + ''.join(body) + '</svg>\n')


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
