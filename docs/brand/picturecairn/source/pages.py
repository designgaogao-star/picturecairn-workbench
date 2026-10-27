"""PictureCairn preview pages: one HTML page per PNG deliverable.

    python pages.py                 -> output/brand/pages/*.html + manifest.json
    node render.cjs <manifest.json> -> PNGs in docs/brand/picturecairn

Pages embed the delivered SVG files as data URIs, so every preview exercises the real files.
Small sizes are drawn into canvases at their true pixel size, then enlarged without smoothing.
"""
from __future__ import annotations

import base64
import json
import math
import os
import random
from urllib.parse import quote

import brandlib as b
import build_assets as A
from brandlib import INK, PAPER, SEAL, STONE, STONE_DARK, TILE_EDGE

ROOT = A.OUT
REPO = os.path.abspath(os.path.join(ROOT, '..', '..', '..'))
PAGES = os.path.join(REPO, 'output', 'brand', 'pages')
DATE = '2026-10-24'

# UI tokens from ui/src/styles/base.css (light, dark)
UI = {
    'light': dict(canvas='#f4f5f6', surface='#ffffff', subtle='#f8f9fa', hover='#edf0f1', active='#e3e7e8',
                  media='#e9eced', text='#1f2324', text2='#545d61', muted='#646d71', line='#dfe3e4',
                  control='#cdd3d6', accent='#0f6cbd', accent_soft='#ebf3fc', accent_text='#0f6cbd',
                  success='#28633d', title='#ffffff'),
    'dark': dict(canvas='#1b1d1f', surface='#232628', subtle='#1f2224', hover='#2e3335', active='#3a4144',
                 media='#141618', text='#e8eded', text2='#bbc3c5', muted='#a1adb0', line='#363c3f',
                 control='#4a5256', accent='#115ea3', accent_soft='#1a3651', accent_text='#62abf5',
                 success='#a1cdae', title='#202020'),
}


# ---------------------------------------------------------------- helpers

def asset(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read().strip()


def uri(svg):
    return 'data:image/svg+xml;charset=utf-8,' + quote(svg, safe='')


def img(svg, w=None, h=None, cls='', style=''):
    attrs = ''
    if w:
        attrs += f' width="{w:g}"'
    if h:
        attrs += f' height="{h:g}"'
    if cls:
        attrs += f' class="{cls}"'
    if style:
        attrs += f' style="{style}"'
    return f'<img src="{uri(svg)}"{attrs} alt="">'


def px(svg, size, zoom=1, cls=''):
    """Canvas with the true-size raster of an SVG, enlarged without smoothing."""
    return (f'<canvas class="px {cls}" data-src="{uri(svg)}" data-size="{size}" '
            f'style="width:{size * zoom}px;height:{size * zoom}px"></canvas>')


def inline(svg, h, cls=''):
    """Inline SVG sized by height, for parts whose colour comes from CSS (currentColor files)."""
    vb = svg.split('viewBox="', 1)[1].split('"', 1)[0].split()
    w = h * float(vb[2]) / float(vb[3])
    return svg.replace('<svg ', f'<svg class="{cls}" style="width:{w:.2f}px;height:{h}px" ', 1)


def recolor(svg, color):
    """currentColor files carry color="#1E2225"; swap it for a dark-surface preview."""
    return svg.replace(f'color="{INK}"', f'color="{color}"')


def glyph(code):
    return f'<i class="g">&#x{code};</i>'


def luminance(hex_):
    rgb = [int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a, c):
    la, lc = sorted((luminance(a), luminance(c)), reverse=True)
    return (la + 0.05) / (lc + 0.05)


_FACE = None


def font_face():
    global _FACE
    if _FACE is None:
        with open(b.FONTS['instrument'], 'rb') as f:
            data = base64.b64encode(f.read()).decode()
        _FACE = ('@font-face{font-family:"Instrument Sans";src:url(data:font/ttf;base64,' + data +
                 ') format("truetype");font-weight:400 700}')
    return _FACE


READY = '''<script>
const loaded = (i) => i.complete ? Promise.resolve() : new Promise((r) => { i.onload = i.onerror = r; });
const draw = (c) => new Promise((r) => {
  const i = new Image();
  i.onload = () => { const n = +c.dataset.size; c.width = n; c.height = n; c.getContext('2d').drawImage(i, 0, 0, n, n); r(); };
  i.onerror = r; i.src = c.dataset.src;
});
window.__ready = Promise.all([...[...document.images].map(loaded), ...[...document.querySelectorAll('canvas[data-src]')].map(draw)]);
</script>'''

BASE_CSS = '''
*{box-sizing:border-box;margin:0;padding:0}
html{-webkit-font-smoothing:antialiased}
body{font:14px/1.6 "Instrument Sans","Noto Sans SC","Microsoft YaHei UI",sans-serif;color:#1E2225;background:#ECEBE6}
img,canvas{display:block}
canvas.px{image-rendering:pixelated}
.g{font:normal 16px/1 "Segoe Fluent Icons","Segoe MDL2 Assets";display:inline-block}
.muted{color:#5E676B}
'''


def page(title, css, body, width):
    return (f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>{title}</title>'
            f'<style>{font_face()}{BASE_CSS}body{{width:{width}px}}{css}</style></head>'
            f'<body>{body}{READY}</body></html>')


def tray(icon, dark, size=16):
    mode = 'dark' if dark else 'light'
    return (f'<div class="tray {mode}">{glyph("E70E")}{img(icon, size, size)}'
            f'<span class="qs">{glyph("E701")}{glyph("E767")}{glyph("E83F")}</span>'
            f'<span class="clock">21:48<br>2026/10/24</span></div>')


TRAY_CSS = '''
.tray{display:flex;align-items:center;gap:12px;height:48px;padding:0 12px;border-radius:10px;white-space:nowrap;
  font:12px/1.3 "Segoe UI Variable Text","Segoe UI","Microsoft YaHei UI",sans-serif}
.tray.dark{background:#1C1C1C;color:#fff}
.tray.light{background:#EEF0F3;color:#1B1B1B}
.tray .qs{display:flex;gap:9px;padding:0 2px}
.tray .clock{text-align:right}
'''


# ---------------------------------------------------------------- exploration directions

DIRECTIONS = [
    dict(key='A', title='档案 / 索引', name='索引印相', en='Index Print', logic='矩阵',
         mark=lambda: b.mark_index_print(False), mono=lambda: b.mark_index_print(True),
         face=b.Wordface('plex', 500, 0), face_note='IBM Plex Sans 500 · PictureCairn · 副标题宽字距，像索引标签',
         layout='below', sub=(24, 360), verdict='放弃', score=(4, 3, 2, 3, 2, 2, 1),
         build='3×3 等距方格，像暗房里的索引印相（contact sheet）；右中一格换成朱色，表示“这一帧被标记”。',
         says='图片＝九格画面；位置＝被标的那一格；检阅＝在小样上挑帧；长期使用＝网格的秩序。',
         feel='档案室、索引卡、整齐可靠。',
         risk='九宫格是“全部应用 / 缩略图视图”的通用图标，与 Lucide grid、Fluent Apps 几乎同形；黑白时朱格消失，'
              '只剩普通网格（单色稿只能改成空心格补救）；16px 下每格 4px，容易糊成灰块。'),
    dict(key='B', title='路径 / 续看', name='续看径', en='Resume Path', logic='单线',
         mark=b.mark_resume_path, mono=b.mark_resume_path,
         face=b.Wordface('hanken', 560, 0, text='picturecairn'), face_note='Hanken Grotesk 560 · 全小写 picturecairn',
         layout='below', sub=(24, 120), verdict='放弃', score=(1, 4, 5, 1, 3, 3, 2),
         build='一条等粗路径从右上起，逐行折返穿过三行，停在左下的朱色方印上；整体是 Still 的 S。',
         says='续看＝沿目录一行行往下走；位置＝终点方印“上次看到这里”；图片属性较弱。',
         feel='流畅、有方向感、轻快。',
         risk='像 S 字母标（首字母 S 的品牌很多）、贪吃蛇、管线或流程图；路线感接近需求里要避开的“地图”；'
              '图片属性只能靠文字补。'),
    dict(key='C', title='检阅 / 核验', name='对照线', en='Proof Line', logic='对称并置',
         mark=b.mark_proof_line, mono=b.mark_proof_line,
         face=b.Wordface('source', 600, 20), face_note='Source Sans 3 600 · 字距 +20 · 副标题与字标同一基线',
         layout='inline', sub=(24, 60), verdict='放弃', score=(3, 1, 1, 5, 2, 2, 2),
         build='两张等大的竖幅画面左右并置，中间一条朱色对照线，表示双图包逐项核对。',
         says='检阅＝左右对照、逐项核验；图片＝两幅画面；位置和续看几乎不表达。',
         feel='严谨、对称、工具感强。',
         risk='最大风险是被读成“暂停键 ‖”（媒体播放器，而本产品不涉及视频）；也像分栏视图、diff 工具、打开的书；'
              '16px 下朱线只剩 1px，还落在半像素上，颜色信息丢失。'),
    dict(key='D', title='纯抽象', name='压角印', en='Corner Seal', logic='压叠切口',
         mark=b.mark, mono=b.mark,
         face=b.RECOMMENDED_WORD, face_note='Instrument Sans 560 · 字距 +10 · i 点收成竖笔宽的正方形（与印同形）',
         layout='seal', sub=None, verdict='推荐', score=(4, 4, 3, 4, 5, 4, 4),
         build='一张方形画面（Still）的左下角被一枚朱色小方印压住（Mark）；画面为印让出一圈等宽留白，内角与印同心。'
               '不画山、日或镜头，只有两块方形和一道切口。',
         says='图片＝大方块；位置／书签＝压在角上的印（“读到这里”）；检阅＝钤印核验；长期使用＝方正、少细节、耐看。',
         feel='安静、可靠，有档案与钤印的东方气质，但不复古、不花哨。',
         risk='两块错位方形可能让人想到“复制”“还原窗口”图标；靠 2:1 的尺度差、朱印、等宽切口和同心内角区分。'
              '黑白时更像抽象几何，但轮廓仍然独特。'),
]
CRITERIA = ('图片', '位置', '续看', '检阅', '16px', '黑白', '独特')


def mark_set(d):
    m, mm = d['mark'](), d['mono']()
    both = b.union(mm['still'], mm['seal'])
    s = 0.5 * 512 / 56
    off = 256 - 32 * s
    return {
        'light': b.svg((64, 64), [(INK, m['still'], None), (SEAL, m['seal'], None)], d['en']),
        'dark': b.svg((64, 64), [(PAPER, m['still'], None), (SEAL, m['seal'], None)], d['en']),
        'black': b.svg((64, 64), [('#000000', both, None)], d['en']),
        'white': b.svg((64, 64), [('#FFFFFF', both, None)], d['en']),
        'avatar': b.svg((512, 512), [(INK, b.rrect(0, 0, 512, 512), None),
                                     (PAPER, b.tf(m['still'], s, off, off), None),
                                     (SEAL, b.tf(m['seal'], s, off, off), None)], d['en']),
    }


def explore_lockup(d, dark=False):
    """Each direction gets its own wordmark and subtitle arrangement on the 128-high lockup grid."""
    if d['layout'] == 'seal':
        return A.lockup_svg('dark' if dark else 'light')
    fg, sg = (PAPER, STONE_DARK) if dark else (INK, STONE)
    m = d['mark']()
    still, seal = b.tf(m['still'], 2), b.tf(m['seal'], 2)
    tx = 8 + 112 + 48
    size, tracking = d['sub']
    if d['layout'] == 'below':
        word, _ = b.wordmark(d['face'], 60, 0, 68)
        word = b.tf(word, 1, tx - word.bounds[0], 0)
        sub, _ = b.cjk(b.SUBTITLE, size, 420, tracking)
        sub = b.tf(sub, 1, tx - sub.bounds[0], 120 - sub.bounds[3])
    else:
        base = 64 + 26
        word, _ = b.wordmark(d['face'], 52, 0, base)
        word = b.tf(word, 1, tx - word.bounds[0], 0)
        sub, _ = b.cjk(b.SUBTITLE, size, 420, tracking, 0, base)
        sub = b.tf(sub, 1, word.bounds[2] + 30 - sub.bounds[0], 0)
    x1 = b.bounds(still, seal, word, sub)[2]
    return b.svg((math.ceil(x1 + 8), 128), [(fg, still, None), (SEAL, seal, None), (fg, word, None), (sg, sub, None)],
                 'PictureCairn')


def dots(n, total=5):
    return '<span class="dots">' + '<i class="on"></i>' * n + '<i></i>' * (total - n) + '</span>'


def direction_block(d):
    s = mark_set(d)
    pick = d['verdict'] == '推荐'
    sizes_l = ''.join(img(s['light'], n, n) for n in (64, 32, 24, 16))
    sizes_d = ''.join(img(s['dark'], n, n) for n in (64, 32, 24, 16))
    head = ''.join(f'<th>{c}</th>' for c in CRITERIA)
    cells = ''.join(f'<td>{dots(v)}</td>' for v in d['score'])
    mono_note = '黑白（空心格）' if d['key'] == 'A' else '黑白'
    return f'''
<section class="dir{' pick' if pick else ''}">
  <header><span class="key">{d['key']}</span><h2>{d['title']} · {d['name']}</h2>
    <span class="en">{d['en']} · 构形逻辑：{d['logic']}</span><span class="verdict">{d['verdict']}</span></header>
  <div class="body">
    <div class="hero">
      <div class="tile white">{img(s['light'], 116, 116)}</div>
      <div class="tile ink">{img(s['dark'], 116, 116)}</div>
    </div>
    <div class="mid">
      <div class="pair">
        <div class="tile white lk">{img(explore_lockup(d), h=60)}</div>
        <div class="tile ink lk">{img(explore_lockup(d, True), h=60)}</div>
      </div>
      <div class="pair">
        <div class="tile soft strip">{sizes_l}<span class="z">{px(s['light'], 16, 5)}<em>16px ×5</em></span>
          <span class="z">{px(s['black'], 16, 5)}<em>{mono_note}</em></span></div>
        <div class="tile dim strip">{sizes_d}<span class="z">{px(s['dark'], 16, 5)}<em>16px ×5</em></span>
          <span class="z">{px(s['white'], 16, 5)}<em>反白</em></span></div>
      </div>
      <div class="ctx">
        {tray(s['white'], True)}{tray(s['black'], False)}
        <div class="gh">{img(s['avatar'], 64, 64, 'circle')}{img(s['avatar'], 40, 40, 'rounded')}{img(s['avatar'], 20, 20, 'circle')}
          <em>GitHub 头像</em></div>
      </div>
      <p class="face">字标与副标题：{d['face_note']}</p>
    </div>
    <div class="text">
      <h3>构形</h3><p>{d['build']}</p>
      <h3>如何表达图片 / 位置 / 续看 / 核验</h3><p>{d['says']}</p>
      <h3>用户印象</h3><p>{d['feel']}</p>
      <h3>可能的误解</h3><p>{d['risk']}</p>
      <table class="score"><tr>{head}</tr><tr>{cells}</tr></table>
    </div>
  </div>
</section>'''


DIRECTIONS_CSS = TRAY_CSS + '''
body{padding:40px 44px 48px}
.top{display:flex;align-items:flex-end;justify-content:space-between;margin-bottom:24px}
.top h1{font-size:30px;font-weight:600;letter-spacing:-.005em}
.top p{color:#5E676B;font-size:14px}
.dir{background:#F7F6F2;border:1px solid #DCDBD4;border-radius:14px;padding:20px 22px 22px;margin-bottom:18px}
.dir.pick{border:2px solid #1E2225}
.dir header{display:flex;align-items:center;gap:14px;margin-bottom:16px}
.dir .key{width:28px;height:28px;border-radius:6px;background:#1E2225;color:#F3F2EE;display:grid;place-items:center;font-weight:600}
.dir h2{font-size:21px;font-weight:600}
.dir .en{color:#5E676B;font-size:13px}
.dir .verdict{margin-left:auto;font-size:13px;font-weight:600;padding:2px 14px;border-radius:999px;background:#E3E2DC;color:#5E676B}
.dir.pick .verdict{background:#1E2225;color:#F3F2EE}
.body{display:grid;grid-template-columns:160px 1fr 430px;gap:16px}
.hero{display:flex;flex-direction:column;gap:12px}
.hero .tile{height:160px}
.tile{border-radius:10px;display:flex;align-items:center;justify-content:center}
.white{background:#fff}.ink{background:#1E2225}.soft{background:#F4F5F6}.dim{background:#1B1D1F}
.mid{display:flex;flex-direction:column;gap:12px;min-width:0}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.lk{height:96px}
.strip{height:112px;justify-content:flex-start;gap:16px;padding:0 18px}
.z{display:flex;flex-direction:column;align-items:center;gap:4px}
.z em,.gh em{font-style:normal;font-size:11px;color:#5E676B}
.dim .z em{color:#A7B0B3}
.ctx{display:flex;gap:12px;align-items:center}
.gh{display:flex;align-items:center;gap:12px;background:#fff;border-radius:10px;height:84px;padding:0 16px;flex:1}
.circle{border-radius:50%}.rounded{border-radius:8px}
.face{font-size:12px;color:#5E676B}
.text h3{font-size:12px;font-weight:600;color:#5E676B;margin-bottom:1px}
.text p{font-size:13.5px;line-height:1.6;margin-bottom:9px}
.score{border-collapse:collapse;margin-top:4px}
.score th{font-weight:500;font-size:11.5px;color:#5E676B;text-align:left;padding:0 10px 2px 0}
.score td{padding-right:10px}
.dots{display:inline-flex;gap:2px}
.dots i{width:7px;height:7px;border-radius:1.5px;background:#D5D4CD}
.dots i.on{background:#1E2225}
.sum{display:grid;grid-template-columns:560px 1fr;gap:24px;background:#fff;border-radius:14px;padding:24px 26px}
.sum h2{font-size:19px;margin-bottom:10px}
.sum table{border-collapse:collapse;width:100%}
.sum th{font-size:12px;color:#5E676B;font-weight:500;text-align:left;padding:4px 8px 6px 0}
.sum td{padding:7px 8px 7px 0;border-top:1px solid #ECEBE6;font-size:13.5px}
.sum tr.pick td{font-weight:600}
.sum ol{padding-left:20px;font-size:13.5px;line-height:1.65}
.sum li{margin-bottom:3px}
.sum .drop{margin-top:10px;font-size:13.5px;line-height:1.65}
.note{margin-top:14px;font-size:12px;color:#5E676B}
'''


def directions_page():
    blocks = ''.join(direction_block(d) for d in DIRECTIONS)
    rows = ''
    for d in DIRECTIONS:
        cls = ' class="pick"' if d['verdict'] == '推荐' else ''
        rows += f'<tr{cls}><td>{d["key"]} · {d["name"]}</td>' + ''.join(f'<td>{dots(v)}</td>' for v in d['score']) + '</tr>'
    head = '<tr><th>方向</th>' + ''.join(f'<th>{c}</th>' for c in CRITERIA) + '</tr>'
    body = f'''
<div class="top"><div><h1>PictureCairn · 四个 Logo 方向</h1>
  <p>四种构形逻辑：矩阵（A）、单线（B）、对称并置（C）、压叠切口（D）。同一套墨＋朱配色，只比较形状。</p></div>
  <p>影标图片工作台 · 探索稿 · {DATE}</p></div>
{blocks}
<div class="sum">
  <div><h2>对照</h2><table>{head}{rows}</table>
    <p class="note">评分为设计自评（1–5）。对比页统一用 64 网格母版直接缩小；推荐方向另有 16/20/24px 像素对齐版本。</p></div>
  <div><h2>推荐 D · 压角印</h2><ol>
    <li>小尺寸最稳：16px 下仍是“大方块＋小方块＋一道缝”三个清楚的元素，直边都落在整像素上；托盘单色照样成立。</li>
    <li>概念最完整：一个图形里同时有 Still（画面）和 Mark（印记、位置、核验）。</li>
    <li>不靠颜色：黑白、反白都能认出；朱色是加分，不是前提，也不依赖蓝色。</li>
    <li>与通用图形拉开距离：不是九宫格、不是 S 字母、不是暂停键；同类图片工具里少见“方块＋压角朱印”的构形。</li>
    <li>规则简单：边长都是 4 的倍数，印＝画面的 1/2，缝＝印的 1/6，圆角＝边长的 1/8，工程好复刻，长期看不累。</li></ol>
    <p class="drop"><b>放弃 A</b>：通用网格图标，独特性最弱；黑白时失去标记；16px 发糊。<br>
    <b>放弃 B</b>：图片属性弱；S 字母和路线感容易被看成导航或地图类产品。<br>
    <b>放弃 C</b>：暂停键误读风险高；1px 朱线在小尺寸失效；不表达位置与续看。</p></div>
</div>'''
    return page('PictureCairn directions', DIRECTIONS_CSS, body, 1800)


# ---------------------------------------------------------------- wordmark exploration

WORDS = [
    (b.Wordface('instrument', 560, 0), 'PictureCairn · Instrument Sans 560 · 默认字距 · 原字 i 点', ''),
    (b.Wordface('instrument', 560, 0, text='picturecairn'), 'picturecairn · 全小写', ''),
    (b.RECOMMENDED_WORD, 'PictureCairn · 定制：字重 560 · 字距 +10 · i 点收成竖笔宽的正方形', '推荐'),
    (b.Wordface('plex', 500, 0), 'IBM Plex Sans 500（方向 A 用）', ''),
    (b.Wordface('hanken', 560, 0, text='picturecairn'), 'Hanken Grotesk 560 · 全小写（方向 B 用）', ''),
    (b.Wordface('source', 600, 20), 'Source Sans 3 600 · 字距 +20（方向 C 用）', ''),
    (b.Wordface('instrument', 560, 60, text='PICTURECAIRN'), 'PICTURECAIRN · 全大写 +60（只作对照，不作默认）', '不用'),
]


def word_svg(face, color):
    """Tight wordmark on a 100-unit cap; returns (svg, height per unit cap)."""
    p, _ = b.wordmark(face, 100, 0, 100)
    x0, y0, x1, y1 = p.bounds
    return b.svg((x0, y0, x1 - x0, y1 - y0), [(color, p, None)], face.text), (y1 - y0) / 100


WORDS_CSS = '''
body{padding:40px 44px 48px}
h1{font-size:28px;font-weight:600;margin-bottom:6px}
.lead{color:#5E676B;margin-bottom:22px;max-width:1100px}
.wrow{display:grid;grid-template-columns:300px 1fr 190px 190px 150px;gap:12px;align-items:stretch;margin-bottom:10px}
.wrow>div{border-radius:10px;display:flex;align-items:center;padding:0 22px;min-height:104px}
.wrow .info{background:transparent;padding:0;flex-direction:column;align-items:flex-start;justify-content:center;font-size:13.5px}
.wrow .info b{font-size:12px;font-weight:600;padding:1px 10px;border-radius:999px;background:#1E2225;color:#F3F2EE;margin-top:6px}
.wrow .info b.no{background:#D5D4CD;color:#5E676B}
.wrow.pick .big{outline:2px solid #1E2225;outline-offset:-2px}
.white{background:#fff}.ink{background:#1E2225}.soft{background:#F4F5F6}
.cap{font-size:11px;color:#5E676B;display:block;margin-top:6px}
.ink .cap{color:#A7B0B3}
.sm{flex-direction:column;align-items:flex-start!important;justify-content:center}
.hdr{display:grid;grid-template-columns:300px 1fr 190px 190px 150px;gap:12px;font-size:12px;color:#5E676B;margin-bottom:6px}
.detail{display:grid;grid-template-columns:1fr 520px;gap:16px;margin-top:22px}
.detail>div{background:#fff;border-radius:12px;padding:24px 28px}
.detail p{font-size:14px;line-height:1.7;margin-bottom:8px}
.detail h2{font-size:17px;margin-bottom:10px}
.zoomrow{display:flex;align-items:flex-end;gap:72px}
'''


def words_page():
    rows = ''
    for face, note, tag in WORDS:
        light, ratio = word_svg(face, INK)
        dark, _ = word_svg(face, PAPER)
        badge = f'<b class="{"no" if tag == "不用" else ""}">{tag}</b>' if tag else ''
        pick = ' pick' if tag == '推荐' else ''
        rows += f'''
<div class="wrow{pick}">
  <div class="info">{note}{badge}</div>
  <div class="white big">{img(light, h=round(48 * ratio, 2))}</div>
  <div class="white sm">{img(light, h=round(11 * ratio, 2))}<span class="cap">cap 11px · 侧栏</span></div>
  <div class="ink sm">{img(dark, h=round(11 * ratio, 2))}<span class="cap">cap 11px · 深色</span></div>
  <div class="soft sm">{img(light, h=round(8 * ratio, 2))}<span class="cap">cap 8px · 极小</span></div>
</div>'''
    rec, ratio = word_svg(b.RECOMMENDED_WORD, INK)
    stock, ratio2 = word_svg(b.Wordface('instrument', 560, 0), INK)
    sti0, r0 = word_svg(b.Wordface('instrument', 560, 0, text='Sti'), INK)
    sti1, r1 = word_svg(b.Wordface('instrument', 560, 10, square_dot=True, text='Sti'), INK)
    body = f'''
<h1>Wordmark 探索</h1>
<p class="lead">英文名固定为 PictureCairn。比较首字母大写、全小写和定制字标；不用科技感、手写或霓虹字体，全大写只作对照。
所有字标都已转成路径，运行环境不需要安装字体。</p>
<div class="hdr"><span></span><span>cap 48px</span><span>侧栏尺寸</span><span>深色侧栏</span><span>标题栏级别</span></div>
{rows}
<div class="detail">
  <div><h2>定制细节</h2>
    <div class="zoomrow">
      <div>{img(sti0, h=round(120 * r0, 2))}<p class="muted" style="font-size:12px;margin-top:8px">原字：i 点 128 × 130，比竖笔（117）宽</p></div>
      <div>{img(sti1, h=round(120 * r1, 2))}<p class="muted" style="font-size:12px;margin-top:8px">定制：i 点 117 × 117，与竖笔等宽的正方形</p></div></div>
    <div style="margin-top:22px;display:flex;flex-direction:column;align-items:flex-start;gap:10px">{img(stock, h=round(40 * ratio2, 2))}{img(rec, h=round(40 * ratio, 2))}</div>
    <p class="muted" style="font-size:12px;margin-top:8px">上：Instrument Sans 原字、默认字距；下：定制字标（字距 +10）。单位为 1000 em。</p></div>
  <div><h2>为什么选定制版</h2>
    <p><b>PictureCairn</b>（首字母大写）与产品名、窗口标题、README 标题保持一致；全小写更柔和，但在中文句子里容易被当成普通单词；全大写像机构标牌，只作对照。</p>
    <p>原字的 i 点本来就是方点，但比竖笔略宽；定制版把它收成与竖笔等宽的正方形，i 读起来像“竖笔＋一枚小印”，呼应图形；字距 +10/1000 让 ll 与 m 之间更透气；字重 560 介于 Medium 与 SemiBold 之间，小尺寸不发虚，大尺寸不显笨。</p>
    <p>Instrument Sans 为 SIL OFL 1.1 授权，可商用、可修改；字标已转曲，不随软件分发字体文件。</p></div>
</div>'''
    return page('PictureCairn wordmarks', WORDS_CSS, body, 1600)


# ---------------------------------------------------------------- brand sheet

def construction_svg():
    m = b.mark()
    grid = ''.join(f'M{i} 0V64M0 {i}H64' for i in range(0, 65, 4))
    channel = b.rrect(0, 32, 32, 32, 7)

    def dim(x1, y1, x2, y2, label, lx, ly, anchor='middle'):
        tick = 1.4
        if y1 == y2:
            ticks = f'M{x1} {y1 - tick}V{y1 + tick}M{x2} {y2 - tick}V{y2 + tick}'
        else:
            ticks = f'M{x1 - tick} {y1}H{x1 + tick}M{x2 - tick} {y2}H{x2 + tick}'
        return (f'<path d="M{x1} {y1}L{x2} {y2}{ticks}" stroke="#5E676B" stroke-width="0.3" fill="none"/>'
                f'<text x="{lx}" y="{ly}" text-anchor="{anchor}">{label}</text>')

    lead = 'stroke="#5E676B" stroke-width="0.25" fill="none"'
    ann = (dim(12, -3, 60, -3, '画面 48', 36, -5.2) +
           dim(4, 67, 28, 67, '印 24 = ½ 画面', 16, 72) +
           dim(-3, 36, -3, 52, '压入 16 = ⅔ 印', -4.6, 45, 'end') +
           # gap: measured inside the channel, label below the still
           f'<path d="M28 44H32M28 42.8V45.2M32 42.8V45.2M30 44V57.5H33.5" {lead}/>'
           '<text x="34.2" y="58.4" text-anchor="start">缝 4 = ⅙ 印</text>'
           # concentric inner corner, label on the left through the empty channel
           f'<path d="M-3 34H31" {lead} stroke-dasharray="0.6 0.6"/><circle cx="31" cy="34" r="0.5" fill="#5E676B"/>'
           '<text x="-4.6" y="34.9" text-anchor="end">内角 r 7 = 3 + 4，与印同心</text>'
           '<text x="61.5" y="8" text-anchor="start">r 6 = ⅛</text>')
    return (f'<svg viewBox="-36 -10 118 86" width="560" height="408" font-size="2.6" '
            f'font-family="Instrument Sans, Noto Sans SC, sans-serif" fill="#5E676B">'
            f'<path d="{grid}" stroke="#DCDBD5" stroke-width="0.12" fill="none"/>'
            f'<path d="{b.to_d(m["still"])}" fill="#1E2225"/><path d="{b.to_d(m["seal"])}" fill="#E2532A"/>'
            f'<path d="{b.to_d(channel)}" fill="none" stroke="#E2532A" stroke-width="0.3" stroke-dasharray="1 0.8"/>'
            f'{ann}</svg>')


def clearspace_svg():
    still, seal, word, sub = A.lockup_parts()
    x0, y0, x1, y1 = 8, 8, b.bounds(still, seal, word, sub)[2], 120
    x = 48
    ox0, oy0, ox1, oy1 = x0 - x, y0 - x, x1 + x, y1 + x
    view = (ox0 - 12, oy0 - 12, ox1 - ox0 + 24, oy1 - oy0 + 24)
    band = b.diff(b.rrect(ox0, oy0, ox1 - ox0, oy1 - oy0), b.rrect(x0, y0, x1 - x0, y1 - y0))
    squares = ''.join(f'<path d="{b.to_d(b.rrect(sx, sy, x, x, 3))}" fill="#E2532A" fill-opacity="0.28"/>'
                      for sx, sy in ((ox0, (y0 + y1) / 2 - x / 2), ((x0 + x1) / 2 - x / 2, oy0), (x1, (y0 + y1) / 2 - x / 2)))
    w = 640
    h = w * view[3] / view[2]
    vb = ' '.join(f'{v:g}' for v in view)
    return (f'<svg viewBox="{vb}" width="{w}" height="{h:.0f}" font-family="Instrument Sans, sans-serif">'
            f'<path d="{b.to_d(band)}" fill="#E2532A" fill-opacity="0.07"/>{squares}'
            f'<rect x="{ox0}" y="{oy0}" width="{ox1 - ox0:.2f}" height="{oy1 - oy0}" fill="none" stroke="#5E676B" '
            f'stroke-width="1.2" stroke-dasharray="6 5"/>'
            f'<path fill="{INK}" d="{b.to_d(still)}"/><path fill="{SEAL}" d="{b.to_d(seal)}"/>'
            f'<path fill="{INK}" d="{b.to_d(word)}"/><path fill="{STONE}" d="{b.to_d(sub)}"/>'
            f'<text x="{ox0 + x / 2}" y="{(y0 + y1) / 2 + 7}" text-anchor="middle" font-size="20" fill="#9A3A1C">x</text>'
            f'</svg>')


SWATCHES = [
    ('墨 Ink', INK, '画面块、字标（浅底）、应用图标底板'),
    ('纸 Paper', PAPER, '画面块、字标（深底）、品牌浅底'),
    ('朱 Seal', SEAL, '只用于印；不进界面状态色'),
    ('石 Stone', STONE, '副标题（浅底）'),
    ('浅石 Stone light', STONE_DARK, '副标题（深底）'),
    ('边线 Edge', TILE_EDGE, '应用图标底板的 2/256 边线'),
]

MISUSE_CSS = '''
.mis{display:grid;grid-template-columns:repeat(5,1fr);gap:12px}
.mis figure{background:#fff;border-radius:10px;overflow:hidden}
.mis .stage{height:132px;display:flex;align-items:center;justify-content:center;background:#F4F5F6}
.mis figcaption{font-size:12.5px;padding:8px 12px}
.mis figcaption::before{content:"✕";display:inline-block;width:16px;height:16px;line-height:16px;text-align:center;
  border-radius:50%;background:#1E2225;color:#fff;font-size:10px;margin-right:6px;vertical-align:1px}
.fake-word{display:flex;align-items:center;gap:8px}
.fake-sub{display:flex;align-items:center;gap:8px;line-height:1.1}
.fake-sub small{display:block;font-size:11px;color:#5E676B}
.fake-sub b{font:700 22px "Microsoft YaHei UI",sans-serif}
.busy{width:100%;height:100%;display:grid;place-items:center;
  background:repeating-linear-gradient(35deg,#c8553d 0 14px,#2d4059 14px 28px,#f2a541 28px 42px,#7aa095 42px 56px)}
.fake-ui{display:flex;gap:10px;align-items:center;font:13px "Segoe UI","Microsoft YaHei UI",sans-serif}
.fake-ui .btn{background:#E2532A;color:#fff;border-radius:4px;padding:6px 14px}
.fake-ui .badge{border:1px solid #E2532A;color:#C2441F;border-radius:999px;padding:1px 10px;font-size:12px}
'''


def misuse_cards():
    ml = asset('picturecairn-mark-light.svg')
    lk = asset('extra/picturecairn-lockup-light.svg')
    blue = ml.replace(SEAL, '#0F6CBD')
    outline = (ml.replace(f'fill="{INK}"', f'fill="none" stroke="{INK}" stroke-width="2"')
                 .replace(f'fill="{SEAL}"', f'fill="none" stroke="{SEAL}" stroke-width="2"'))
    grad = (ml.replace('<title>', '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
                                  '<stop offset="0" stop-color="#8b5cf6"/><stop offset="1" stop-color="#22d3ee"/>'
                                  '</linearGradient></defs><title>')
              .replace(f'fill="{INK}"', 'fill="url(#g)"'))
    items = [
        (img(ml, 72, 72, style='transform:scaleX(1.55)'), '拉伸或压扁'),
        (img(ml, 72, 72, style='transform:rotate(-14deg)'), '旋转、倾斜'),
        (img(blue, 72, 72), '改印色（蓝、绿或跟随主题色）'),
        (img(grad, 72, 72, style='filter:drop-shadow(0 7px 6px rgb(0 0 0 / 35%))'), '加渐变、阴影、玻璃或 3D'),
        (img(ml, 72, 72, style='transform:scaleX(-1)'), '镜像，或把印挪到别的角'),
        (img(outline, 72, 72), '改成线框'),
        ('<div class="fake-word">' + img(ml, 38, 38) +
         '<span style="font:900 25px \'Arial Black\',\'Segoe UI Black\',sans-serif">PICTURECAIRN</span></div>', '换字体或改成全大写'),
        ('<div class="fake-sub">' + img(ml, 42, 42) + '<div><small>PictureCairn</small><b>影标图片工作台</b></div></div>',
         '副标题压过主名'),
        ('<div class="busy">' + img(lk, h=40) + '</div>', '放在杂乱图片上且不加底'),
        ('<div class="fake-ui"><span class="btn">删除 3 项</span><span class="badge">已核验</span></div>',
         '把朱色用作按钮、链接或状态色'),
    ]
    return '<div class="mis">' + ''.join(f'<figure><div class="stage">{h}</div><figcaption>{t}</figcaption></figure>'
                                         for h, t in items) + '</div>'


SHEET_CSS = TRAY_CSS + MISUSE_CSS + '''
body{background:#ECEBE6;padding:0 0 56px}
.wrap{padding:0 48px}
.hdr{background:#F3F2EE;padding:40px 48px 36px;display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}
.hdr .meta{text-align:right;font-size:14px;line-height:1.7;color:#5E676B}
.hdr .meta b{display:block;font-size:20px;color:#1E2225;font-weight:600}
section{margin-top:34px}
h2{font-size:19px;font-weight:600;margin-bottom:12px;display:flex;align-items:baseline;gap:12px}
h2 small{font-size:12.5px;font-weight:500;color:#5E676B}
.g2{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.card{border-radius:12px;display:flex;align-items:center;justify-content:center;position:relative}
.white{background:#fff}.ink{background:#1E2225}.paper{background:#F3F2EE}.stone{background:#5E676B}
.soft{background:#F4F5F6}.dim{background:#1B1D1F}
.cap{position:absolute;left:14px;bottom:10px;font-size:11.5px;color:#5E676B}
.ink .cap,.stone .cap,.dim .cap{color:#C9CFD1}
.big{height:220px}
.variants{display:grid;grid-template-columns:repeat(7,1fr);gap:12px}
.variants .card{height:190px}
.g4{display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:14px}
.icons{display:grid;grid-template-columns:300px 300px 1fr;gap:14px}
.icons .card{min-height:300px}
.stackv{display:flex;flex-direction:column;gap:14px}
.mini{display:flex;align-items:center;gap:18px;padding:18px 20px;border-radius:12px;flex-wrap:wrap}
.mini .item{display:flex;flex-direction:column;align-items:center;gap:6px;font-size:11px;color:#5E676B}
.dim .item,.ink .item{color:#A7B0B3}
.mini .item .pair{display:flex;align-items:flex-end;gap:10px}
.tab{display:flex;align-items:center;gap:8px;background:#fff;border-radius:8px 8px 0 0;padding:8px 14px;width:220px;
  font:12px "Segoe UI Variable Text","Segoe UI",sans-serif;color:#1B1B1B;box-shadow:0 1px 0 #E1E1E1}
.tabbar{background:#E8EAED;padding:8px 10px 0;border-radius:10px 10px 0 0;width:300px}
.sw{display:grid;grid-template-columns:repeat(6,1fr);gap:12px}
.sw figure{background:#fff;border-radius:12px;overflow:hidden}
.sw .chip{height:96px;box-shadow:inset 0 -1px 0 #E2E1DB}
.sw figcaption{padding:10px 14px 12px;font-size:12.5px;line-height:1.55}
.sw figcaption b{display:block;font-size:14px}
.sw code{font:12.5px "Cascadia Mono",Consolas,monospace}
.type{display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px}
.type>div{background:#fff;border-radius:12px;padding:22px 24px}
.type .spec{font-size:40px;line-height:1.15;margin:6px 0 10px}
.type p{font-size:12.5px;color:#5E676B;line-height:1.6}
.cons{display:grid;grid-template-columns:600px 1fr;gap:14px}
.cons>div{background:#fff;border-radius:12px;padding:20px 24px}
.cons ul{font-size:13.5px;line-height:1.75;padding-left:18px}
.minsize{border-collapse:collapse;width:100%;font-size:13px;margin-top:10px}
.minsize th{text-align:left;color:#5E676B;font-weight:500;padding:4px 10px 6px 0}
.minsize td{border-top:1px solid #ECEBE6;padding:7px 10px 7px 0}
.coexist{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.coexist>div{background:#fff;border-radius:12px;padding:20px 24px}
.chips{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0 12px}
.chips span{display:flex;align-items:center;gap:6px;font-size:12px;padding:4px 10px 4px 4px;border-radius:999px;background:#F4F5F6}
.chips i{width:18px;height:18px;border-radius:50%;display:block}
.coexist ul{font-size:13.5px;line-height:1.75;padding-left:18px}
'''


def brand_sheet():
    lk_l, lk_d = asset('extra/picturecairn-lockup-light.svg'), asset('extra/picturecairn-lockup-dark.svg')
    st_l, st_d = asset('extra/picturecairn-lockup-stacked.svg'), asset('extra/picturecairn-lockup-stacked-dark.svg')
    wm_l, wm_d = asset('extra/picturecairn-wordmark-light.svg'), asset('extra/picturecairn-wordmark-dark.svg')
    mark, ml, md = asset('picturecairn-mark.svg'), asset('picturecairn-mark-light.svg'), asset('picturecairn-mark-dark.svg')
    mono = asset('picturecairn-mark-monochrome.svg')
    black, white, rev = (asset('extra/picturecairn-mark-black.svg'), asset('extra/picturecairn-mark-white.svg'),
                         asset('extra/picturecairn-mark-reverse.svg'))
    app, app24, fav = asset('picturecairn-app-icon.svg'), asset('extra/picturecairn-app-icon-24.svg'), asset('picturecairn-favicon.svg')
    avatar = asset('extra/picturecairn-avatar.svg')
    t16, t20, t24 = asset('picturecairn-tray.svg'), asset('extra/picturecairn-tray-20.svg'), asset('extra/picturecairn-tray-24.svg')
    w16, w20, w24 = (asset('extra/picturecairn-tray-white.svg'), asset('extra/picturecairn-tray-20-white.svg'),
                     asset('extra/picturecairn-tray-24-white.svg'))
    m16, m24 = asset('extra/picturecairn-mark-16.svg'), asset('extra/picturecairn-mark-24.svg')

    variants = [
        ('white', mark, '彩色 · 自动深浅'),
        ('paper', ml, '浅色背景'),
        ('ink', md, '深色背景'),
        ('white', black, '纯黑'),
        ('stone', white, '纯白'),
        ('white', rev, '单色反白（镂空）'),
        ('soft', mono, '单色 · 跟随文字色'),
    ]
    var_html = ''.join(f'<div class="card {bg}">{img(svg, 104, 104)}<span class="cap">{cap}</span></div>'
                       for bg, svg, cap in variants)

    def item(label, *canvases):
        return f'<div class="item"><div class="pair">{"".join(canvases)}</div>{label}</div>'

    small_light = ''.join([
        item('64 网格直接缩到 16', px(ml, 16), px(ml, 16, 6)),
        item('16 像素对齐版', px(m16, 16), px(m16, 16, 6)),
        item('24 像素对齐版', px(m24, 24), px(m24, 24, 4)),
        item('32（母版，整像素）', px(ml, 32), px(ml, 32, 3)),
    ])
    small_dark = ''.join([
        item('16 像素对齐版', px(recolor(m16, PAPER), 16), px(recolor(m16, PAPER), 16, 6)),
        item('24 像素对齐版', px(recolor(m24, PAPER), 24), px(recolor(m24, PAPER), 24, 4)),
        item('32（母版）', px(md, 32), px(md, 32, 3)),
    ])
    tray_light = ''.join([item('托盘 16 · 100%', px(t16, 16), px(t16, 16, 6)), item('20 · 125%', px(t20, 20), px(t20, 20, 5)),
                          item('24 · 150%', px(t24, 24), px(t24, 24, 4)), item('32 · 200%', px(t16, 32), px(t16, 32, 3))])
    tray_dark = ''.join([item('托盘 16 · 100%', px(w16, 16), px(w16, 16, 6)), item('20 · 125%', px(w20, 20), px(w20, 20, 5)),
                         item('24 · 150%', px(w24, 24), px(w24, 24, 4)), item('32 · 200%', px(w16, 32), px(w16, 32, 3))])
    favs = ''.join([item('favicon 16', px(fav, 16), px(fav, 16, 6)), item('favicon 32', px(fav, 32), px(fav, 32, 3)),
                    item('应用图标 24', px(app24, 24), px(app24, 24, 4))])

    swatches = ''
    for name, hex_, role in SWATCHES:
        r, g, bb = (int(hex_[i:i + 2], 16) for i in (1, 3, 5))
        on_paper = contrast(hex_, PAPER)
        on_ink = contrast(hex_, INK)
        swatches += (f'<figure><div class="chip" style="background:{hex_}"></div><figcaption><b>{name}</b>'
                     f'<code>{hex_}</code> · RGB {r} {g} {bb}<br>{role}<br>'
                     f'<span class="muted">对纸 {on_paper:.1f}:1 · 对墨 {on_ink:.1f}:1</span></figcaption></figure>')

    sample_sub = '<span style="font:420 30px \'Noto Sans SC\',\'Microsoft YaHei UI\',sans-serif;letter-spacing:.18em">影标图片工作台</span>'
    body = f'''
<div class="hdr">{img(lk_l, h=96)}
  <div class="meta"><b>品牌速览 · Brand sheet</b>PictureCairn 影标图片工作台 · v1.0 · {DATE}<br>原目录浏览，随时续看，核实再整理。</div></div>
<div class="wrap">
<section><h2>主标志 <small>横版组合 · viewBox 560 × 128 · 图形标＋字标＋中文副标题</small></h2>
  <div class="g2"><div class="card white big">{img(lk_l, h=128)}</div><div class="card ink big">{img(lk_d, h=128)}</div></div></section>

<section><h2>图形标 <small>Mark · viewBox 64 × 64 · 彩色 / 浅底 / 深底 / 纯黑 / 纯白 / 单色反白 / 单色</small></h2>
  <div class="variants">{var_html}</div></section>

<section><h2>字标与竖版组合 <small>Wordmark 420 × 96 · Stacked 320 × 256</small></h2>
  <div class="g4">
    <div class="card white" style="height:240px">{img(wm_l, 336, 76.8)}</div>
    <div class="card ink" style="height:240px">{img(wm_d, 336, 76.8)}</div>
    <div class="card white" style="height:240px">{img(st_l, h=190)}</div>
    <div class="card ink" style="height:240px">{img(st_d, h=190)}</div></div></section>

<section><h2>图标 <small>应用图标 256 网格 · GitHub 头像 512 · favicon 16 · 托盘 16 / 20 / 24</small></h2>
  <div class="icons">
    <div class="card soft">{img(app, 200, 200)}<span class="cap">应用图标 · 浅色桌面</span></div>
    <div class="card dim">{img(app, 200, 200)}<span class="cap">应用图标 · 深色桌面（2/256 边线）</span></div>
    <div class="stackv">
      <div class="mini white">{img(avatar, 120, 120, style='border-radius:50%')}{img(avatar, 120, 120, style='border-radius:16px')}
        {img(avatar, 40, 40, style='border-radius:50%')}{img(avatar, 20, 20, style='border-radius:50%')}
        <div class="tabbar"><div class="tab">{img(fav, 16, 16)}PictureCairn · 图库</div></div></div>
      <div class="mini soft">{favs}</div>
    </div></div>
  <div class="g2" style="margin-top:14px"><div class="mini" style="background:#EEF0F3">{tray_light}</div>
    <div class="mini" style="background:#1C1C1C">{tray_dark}</div></div></section>

<section><h2>小尺寸 <small>16 / 24 / 32px 实际像素与放大；小尺寸请用像素对齐版</small></h2>
  <div class="g2"><div class="mini soft">{small_light}</div><div class="mini dim">{small_dark}</div></div></section>

<section><h2>颜色 <small>墨＋纸是主体，朱只用于印；对比度按 WCAG 公式计算</small></h2><div class="sw">{swatches}</div></section>

<section><h2>字体 <small>字标与副标题都已转曲，运行时不需要字体</small></h2>
  <div class="type">
    <div><b>Instrument Sans · 字标原型</b><div class="spec" style="font-weight:560;letter-spacing:.01em">PictureCairn Aa 0123</div>
      <p>字重 560，字距 +10/1000，i 点收成与竖笔等宽的正方形。SIL OFL 1.1，可商用、可修改、可嵌入。</p></div>
    <div><b>Noto Sans SC · 中文副标题</b><div class="spec">{sample_sub}</div>
      <p>字重 420，字距 +180/1000；思源黑体同源字形。SIL OFL 1.1。</p></div>
    <div><b>界面文字（不属于标志）</b><div class="spec" style="font:600 34px 'Segoe UI Variable Display','Segoe UI','Microsoft YaHei UI',sans-serif">PictureCairn 图库</div>
      <p>界面继续用 Segoe UI Variable / Microsoft YaHei UI；标志不改变界面字体。窗口标题栏只能用系统字体显示“PictureCairn”。</p></div>
  </div></section>

<section><h2>构造、留白与最小尺寸</h2>
  <div class="cons">
    <div>{construction_svg()}</div>
    <div><ul>
      <li>64 × 64 网格，所有直边落在 4 的倍数上，32px 和 16px 时仍是整像素。</li>
      <li>画面 48 × 48，圆角 6（边长 1/8）；印 24 × 24（画面的 1/2），圆角 3。</li>
      <li>印压入画面 16（印的 2/3）；切缝 4（印的 1/6）；切缝内角圆角 7 = 3 + 4，与印同心。</li>
      <li>可见范围 56 × 56，四周各留 4。</li>
      <li>留白：组合四周至少留 1 个印宽 x（横版组合里 x = 48/560）。</li></ul>
      <div style="margin-top:12px">{clearspace_svg()}</div>
      <table class="minsize"><tr><th>资产</th><th>屏幕最小</th><th>印刷最小</th></tr>
        <tr><td>图形标</td><td>16 px（16 / 20 / 24 用像素对齐版）</td><td>6 mm</td></tr>
        <tr><td>横版组合（含副标题）</td><td>高 56 px（副标题约 12 px）</td><td>宽 45 mm</td></tr>
        <tr><td>竖版组合</td><td>宽 180 px</td><td>宽 30 mm</td></tr>
        <tr><td>字标单用</td><td>cap 8 px（约 11 px 字号）</td><td>宽 18 mm</td></tr></table></div>
  </div></section>

<section><h2>错误用法</h2>{misuse_cards()}</section>

<section><h2>与现有界面配色共存</h2>
  <div class="coexist">
    <div><b>品牌色</b><div class="chips"><span><i style="background:{INK}"></i>墨 {INK}</span><span><i style="background:{PAPER};border:1px solid #ddd"></i>纸 {PAPER}</span><span><i style="background:{SEAL}"></i>朱 {SEAL} · 只在标志里</span></div>
      <b>界面语义色（保持不变）</b><div class="chips"><span><i style="background:#0f6cbd"></i>选择 / 焦点 #0f6cbd</span><span><i style="background:#b33835"></i>删除 / 错误 #b33835</span><span><i style="background:#86500c"></i>警告 #86500c</span><span><i style="background:#28633d"></i>完成 #28633d</span><span><i style="background:#6c42b8"></i>动图 #6c42b8</span></div></div>
    <div><ul>
      <li>朱色只出现在标志里，不做按钮、链接、选中、进度或提醒。删除色 #b33835 与朱色同属红橙，混用会让“删除”和“品牌”难以区分。</li>
      <li>选择、焦点、链接继续用蓝色 accent；标志不依赖蓝色，也不为配合界面改成蓝色。</li>
      <li>侧栏品牌区：画面块跟随正文色（浅 #1f2324 / 深 #e8eded），印保持朱色；不再给图标套 accent 蓝。</li>
      <li>查看器固定深色画布：顶部只用纯白单色标（不透明度 70–80%），不出现朱色，不干扰看图。</li></ul></div>
  </div></section>
</div>'''
    return page('PictureCairn brand sheet', SHEET_CSS, body, 1600)


# ---------------------------------------------------------------- scene previews

SKY = ['#C9D3D8', '#D8CFC4', '#B9C4C9', '#DAD6CC', '#C4CCC2', '#CDC6BE', '#AEB9BF', '#D5D9DB']
GROUND = ['#6E7F73', '#8B7766', '#5E6E77', '#7C8A6E', '#9A8F80', '#5C5A53', '#73808A', '#837466']
OBJ = ['#EFE9DD', '#3F4A51', '#B89F7E', '#E7E3DA', '#4E5A4A']


def photo(seed, w=160, h=120):
    """Flat placeholder picture (no user images)."""
    r = random.Random(seed)
    sky, ground, obj = r.choice(SKY), r.choice(GROUND), r.choice(OBJ)
    hz = r.uniform(0.5, 0.72) * h
    kind = r.random()
    if kind < 0.4:
        shape = f'<circle cx="{r.uniform(.2, .8) * w:.0f}" cy="{r.uniform(.15, .38) * h:.0f}" r="{r.uniform(.06, .12) * w:.0f}" fill="{obj}"/>'
    elif kind < 0.75:
        x, parts = r.uniform(.05, .3) * w, []
        for _ in range(r.randint(2, 4)):
            bw, bh = r.uniform(.1, .2) * w, r.uniform(.15, .45) * h
            parts.append(f'<rect x="{x:.0f}" y="{hz - bh:.0f}" width="{bw:.0f}" height="{bh:.0f}" fill="{obj}"/>')
            x += bw + r.uniform(.02, .08) * w
        shape = ''.join(parts)
    else:
        shape = f'<path d="M0 {hz:.0f}Q{w * .4:.0f} {hz - h * .4:.0f} {w * .8:.0f} {hz:.0f}Z" fill="{obj}"/>'
    return (f'<svg viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid slice"><rect width="{w}" height="{h}" fill="{sky}"/>'
            f'{shape}<rect y="{hz:.0f}" width="{w}" height="{h - hz:.0f}" fill="{ground}"/></svg>')


WIN_CSS = TRAY_CSS + '''
body{background:#E6E6E2;padding:32px 40px 40px;font-family:"Segoe UI Variable Text","Segoe UI","Microsoft YaHei UI",sans-serif}
h1{font:600 22px "Instrument Sans","Noto Sans SC",sans-serif;margin-bottom:4px}
.lead{color:#5E676B;margin-bottom:18px;font-size:13px}
.desk{position:relative;height:430px;border-radius:12px;overflow:hidden;margin-bottom:18px}
.desk.light{background:#C9D5DC}
.desk.dark{background:#22303A}
.deskicon{position:absolute;left:28px;top:24px;width:76px;display:flex;flex-direction:column;align-items:center;gap:4px;
  color:#fff;font-size:12px;text-shadow:0 1px 2px rgb(0 0 0 / 60%)}
.win{position:absolute;left:150px;top:28px;width:620px;height:330px;border-radius:8px;overflow:hidden;
  box-shadow:0 12px 32px rgb(0 0 0 / 28%);border:1px solid rgb(0 0 0 / 12%)}
.light .win{background:#f4f5f6}.dark .win{background:#1b1d1f;border-color:#3a3a3a}
.titlebar{height:32px;display:flex;align-items:center;gap:10px;padding-left:12px;font-size:12px}
.light .titlebar{background:#fff;color:#1b1b1b;border-bottom:1px solid #e5e5e5}
.dark .titlebar{background:#202020;color:#fff;border-bottom:1px solid #2d2d2d}
.titlebar .ctl{margin-left:auto;display:flex}
.titlebar .ctl .g{width:46px;text-align:center;font-size:10px}
.wb{display:flex;height:calc(100% - 32px)}
.wb .side{width:200px;padding:12px 14px;border-right:1px solid}
.light .wb .side{background:#f8f9fa;border-color:#dfe3e4}.dark .wb .side{background:#1f2224;border-color:#363c3f}
.brandrow{display:flex;align-items:center;gap:10px;height:28px}
.brandrow svg{color:var(--t)}
.light{--t:#1f2324;--t2:#646d71}.dark{--t:#e8eded;--t2:#a1adb0}
.bt{display:flex;flex-direction:column;gap:3px}
.bt small{font-size:10.5px;color:var(--t2);letter-spacing:.06em;line-height:1}
.skel{height:10px;border-radius:3px;margin:14px 0 0;opacity:.6}
.light .skel{background:#dfe3e4}.dark .skel{background:#363c3f}
.wb .main{flex:1;padding:16px;display:grid;grid-template-columns:repeat(4,1fr);gap:8px;align-content:start}
.wb .main svg{width:100%;height:72px;display:block;border-radius:4px}
.taskbar{position:absolute;left:0;right:0;bottom:0;height:48px;display:flex;align-items:center;justify-content:center}
.light .taskbar{background:#EEF0F3;border-top:1px solid #dcdcdc}
.dark .taskbar{background:#1C1C1C;border-top:1px solid #2b2b2b}
.tb{display:flex;gap:4px;align-items:center}
.tbtn{position:relative;width:40px;height:40px;border-radius:4px;display:grid;place-items:center}
.tbtn i.ph{width:24px;height:24px;border-radius:6px;display:block}
.tbtn.on::after{content:"";position:absolute;bottom:2px;left:50%;width:16px;height:3px;border-radius:2px;transform:translateX(-50%)}
.light .tbtn.on{background:rgb(255 255 255 / 70%)}.dark .tbtn.on{background:rgb(255 255 255 / 7%)}
.light .tbtn.on::after{background:#005FB8}.dark .tbtn.on::after{background:#4CC2FF}
.taskbar .tray{position:absolute;right:6px;top:0;background:transparent!important;height:48px}
.zoom{display:grid;grid-template-columns:repeat(6,1fr);gap:12px}
.zoom>div{border-radius:10px;padding:14px;display:flex;flex-direction:column;align-items:center;gap:8px;font-size:11.5px}
'''


def windows_page():
    app, app24, fav = asset('picturecairn-app-icon.svg'), asset('extra/picturecairn-app-icon-24.svg'), asset('picturecairn-favicon.svg')
    t16, w16 = asset('picturecairn-tray.svg'), asset('extra/picturecairn-tray-white.svg')
    m24, wm = asset('extra/picturecairn-mark-24.svg'), asset('extra/picturecairn-wordmark-ui.svg')
    others_l = ['#7A8D9C', '#A9B4BC', '#8E9A86', '#B7A58E']
    others_d = ['#56636D', '#6F7A82', '#66705F', '#7E715F']

    def desk(mode):
        dark = mode == 'dark'
        cols = others_d if dark else others_l
        def ph(c):
            return f'<span class="tbtn"><i class="ph" style="background:{c}"></i></span>'
        thumbs = ''.join(photo(i * 7 + 3, 120, 72) for i in range(12))
        return f'''
<div class="desk {mode}">
  <div class="deskicon">{img(app, 48, 48)}<span>PictureCairn</span></div>
  <div class="win">
    <div class="titlebar">{img(fav, 16, 16)}<span>PictureCairn</span><span class="ctl">{glyph('E921')}{glyph('E922')}{glyph('E8BB')}</span></div>
    <div class="wb"><div class="side">
      <div class="brandrow">{inline(m24, 24)}<div class="bt">{inline(wm, 12)}<small>影标图片工作台</small></div></div>
      <div class="skel" style="width:80%"></div><div class="skel" style="width:62%"></div><div class="skel" style="width:70%"></div></div>
      <div class="main">{thumbs}</div></div>
  </div>
  <div class="taskbar"><div class="tb">{ph(cols[0])}{ph(cols[1])}<span class="tbtn on">{img(app24, 24, 24)}</span>{ph(cols[2])}{ph(cols[3])}</div>
    {tray(w16 if dark else t16, dark)}</div>
</div>'''

    zooms = [
        ('#EEF0F3', '#1b1b1b', px(app24, 24, 5), '任务栏 24 · 浅'),
        ('#1C1C1C', '#ddd', px(app24, 24, 5), '任务栏 24 · 深'),
        ('#EEF0F3', '#1b1b1b', px(t16, 16, 7), '托盘 16 · 黑'),
        ('#1C1C1C', '#ddd', px(w16, 16, 7), '托盘 16 · 白'),
        ('#ffffff', '#1b1b1b', px(fav, 16, 7), '标题栏 16'),
        ('#C9D5DC', '#1b1b1b', px(app, 48, 2.5), '桌面 48'),
    ]
    zoom_html = ''.join(f'<div style="background:{bg};color:{fg}">{c}<span>{t}</span></div>' for bg, fg, c, t in zooms)
    body = f'''
<h1>Windows 场景 · 应用图标、标题栏、任务栏、托盘</h1>
<p class="lead">按 100% 缩放渲染。任务栏用 24px 像素对齐图标，标题栏用 16px favicon，桌面用 256 网格应用图标；托盘按系统深浅切换黑 / 白单色。</p>
{desk('light')}{desk('dark')}
<div class="zoom">{zoom_html}</div>'''
    return page('PictureCairn on Windows', WIN_CSS, body, 1300)


APP_CSS = '''
body{background:#E6E6E2;padding:28px 36px 36px;font-family:"Segoe UI Variable Text","Segoe UI","Microsoft YaHei UI",sans-serif}
.app{width:1200px;height:740px;border-radius:8px;overflow:hidden;box-shadow:0 14px 40px rgb(0 0 0 / 22%);
  background:var(--canvas);color:var(--text);font-size:13px;display:flex;flex-direction:column}
.titlebar{height:32px;flex:none;display:flex;align-items:center;gap:10px;padding-left:12px;font-size:12px;
  background:var(--title);border-bottom:1px solid var(--line)}
.titlebar .ctl{margin-left:auto;display:flex}
.titlebar .ctl .g{width:46px;text-align:center;font-size:10px}
.shell{flex:1;display:flex;min-height:0}
.sidebar{width:232px;flex:none;background:var(--subtle);border-right:1px solid var(--line);display:flex;flex-direction:column}
.side-head{height:52px;flex:none;display:flex;align-items:center;gap:8px;padding:0 8px 0 16px;border-bottom:1px solid var(--line)}
.brand{flex:1;display:flex;align-items:center;gap:10px}
.brand svg{color:var(--text)}
.brand .bt{display:flex;flex-direction:column;gap:4px}
.brand small{font-size:11px;line-height:1;color:var(--muted);letter-spacing:.08em}
.icon-btn{width:32px;height:32px;border-radius:4px;display:grid;place-items:center;color:var(--text2)}
.icon-btn .g{font-size:16px}
.libs{padding:8px 6px;border-bottom:1px solid var(--line);display:flex;flex-direction:column;gap:1px}
.lib{height:34px;display:flex;align-items:center;gap:10px;padding:0 10px;border-radius:4px;color:var(--text2)}
.lib.on{background:var(--active);color:var(--text);font-weight:600}
.dot{width:8px;height:8px;border-radius:50%;background:var(--success);flex:none}
.sec{display:flex;justify-content:space-between;align-items:center;padding:8px 6px 4px 16px;font-size:12px;font-weight:600;color:var(--text2)}
.filters{display:flex;gap:8px;padding:2px 10px 8px;border-bottom:1px solid var(--line)}
.sel{flex:1;height:28px;border:1px solid var(--control);border-radius:4px;background:var(--surface);font-size:12.5px;
  display:flex;align-items:center;justify-content:space-between;padding:0 8px;color:var(--text)}
.sel .g{font-size:10px;color:var(--muted)}
.groups{padding:6px;display:flex;flex-direction:column;gap:2px;flex:1}
.grp{height:50px;padding:0 10px;border-radius:4px;display:flex;flex-direction:column;justify-content:center;gap:3px}
.grp.on{background:var(--accent-soft)}
.grp b{font-weight:500}
.grp span{font-size:11.5px;color:var(--muted)}
.foot{height:36px;display:flex;align-items:center;gap:8px;padding:0 16px;border-top:1px solid var(--line);font-size:12px;color:var(--text2)}
.main{flex:1;display:flex;flex-direction:column;min-width:0}
.topbar{height:52px;flex:none;display:flex;align-items:center;gap:8px;padding:0 12px 0 20px;border-bottom:1px solid var(--line);background:var(--surface)}
.crumb{font-size:15px;font-weight:600;flex:1;display:flex;gap:8px;align-items:center}
.crumb span{color:var(--muted);font-weight:400}
.search{width:240px;height:32px;border:1px solid var(--control);border-radius:4px;display:flex;align-items:center;gap:8px;padding:0 10px;color:var(--muted);background:var(--surface)}
.search .g{font-size:14px}
.toolbar{height:44px;flex:none;display:flex;align-items:center;justify-content:space-between;padding:0 20px;border-bottom:1px solid var(--line);color:var(--text2);font-size:12.5px}
.wall{flex:1;padding:16px 20px;display:grid;grid-template-columns:repeat(6,1fr);gap:10px;align-content:start;overflow:hidden}
.cell{position:relative;border-radius:6px;overflow:hidden;background:var(--media)}
.cell svg{width:100%;height:118px;display:block}
.cell p{font-size:11.5px;padding:5px 2px 0;color:var(--text2);background:var(--canvas)}
.cell.picked{outline:2px solid var(--accent);outline-offset:2px}
.cell .check{position:absolute;left:6px;top:6px;width:20px;height:20px;border-radius:50%;background:var(--accent);color:#fff;
  display:grid;place-items:center}
.cell .check .g{font-size:11px}
.caption{font:12.5px "Instrument Sans","Noto Sans SC",sans-serif;color:#5E676B;margin-top:12px}
'''


def theme_vars(mode):
    t = UI[mode]
    return (f'--canvas:{t["canvas"]};--surface:{t["surface"]};--subtle:{t["subtle"]};--hover:{t["hover"]};'
            f'--active:{t["active"]};--media:{t["media"]};--text:{t["text"]};--text2:{t["text2"]};--muted:{t["muted"]};'
            f'--line:{t["line"]};--control:{t["control"]};--accent:{t["accent"]};--accent-soft:{t["accent_soft"]};'
            f'--success:{t["success"]};--title:{t["title"]}')


def workbench_page(mode):
    fav, m24, wm = asset('picturecairn-favicon.svg'), asset('extra/picturecairn-mark-24.svg'), asset('extra/picturecairn-wordmark-ui.svg')
    libs = [('摄影素材', True), ('设计参考', False), ('扫描档案', False)]
    lib_html = ''.join(f'<div class="lib{" on" if on else ""}"><span class="dot"></span>{n}</div>' for n, on in libs)
    groups = [('2023-春季', '248 张 · 看到第 37 张', True), ('2023-夏季', '512 张', False), ('2023-秋季', '196 张', False),
              ('2024-城市', '1,204 张 · 12 个图包', False), ('2024-海边', '388 张', False), ('2025-山路', '275 张', False),
              ('未整理', '64 张', False)]
    grp_html = ''.join(f'<div class="grp{" on" if on else ""}"><b>{n}</b><span>{meta}</span></div>' for n, meta, on in groups)
    cells = ''
    for i in range(18):
        sel = ' picked' if i == 8 else ''
        check = f'<span class="check">{glyph("E73E")}</span>' if i == 8 else ''
        cells += f'<div class="cell{sel}">{photo(100 + i * 13, 160, 118)}{check}<p>DSC_{423 + i:04d}.jpg</p></div>'
    label = '浅色工作台' if mode == 'light' else '深色工作台'
    body = f'''
<div class="app" style="{theme_vars(mode)}">
  <div class="titlebar">{img(fav, 16, 16)}<span>PictureCairn</span><span class="ctl">{glyph('E921')}{glyph('E922')}{glyph('E8BB')}</span></div>
  <div class="shell">
    <aside class="sidebar">
      <div class="side-head"><div class="brand">{inline(m24, 24)}<div class="bt">{inline(wm, 13)}<small>影标图片工作台</small></div></div>
        <span class="icon-btn">{glyph('E8F4')}</span></div>
      <div class="libs">{lib_html}</div>
      <div class="sec"><span>文件夹</span><span style="display:flex;gap:10px">{glyph('E72C')}{glyph('E712')}</span></div>
      <div class="filters"><span class="sel">全部状态{glyph('E70D')}</span><span class="sel">全部分类{glyph('E70D')}</span></div>
      <div class="groups">{grp_html}</div>
      <div class="foot"><span class="dot"></span>已是最新 · 21:40</div>
    </aside>
    <div class="main">
      <div class="topbar"><div class="crumb">摄影素材 <span>›</span> 2023-春季</div>
        <div class="search">{glyph('E721')}搜索文件名</div><span class="icon-btn">{glyph('E71C')}</span><span class="icon-btn">{glyph('E946')}</span></div>
      <div class="toolbar"><span>248 张 · 已选 1 张</span><span>按名称排序 {glyph('E70D')}</span></div>
      <div class="wall">{cells}</div>
    </div>
  </div>
</div>
<p class="caption">{label}：侧栏品牌区 = 24px 像素对齐图形标（画面块跟随正文色）＋ 转曲字标＋副标题；选中与焦点仍用界面蓝色，朱色只在印上。缩略图为占位色块。</p>'''
    return page(f'PictureCairn {label}', APP_CSS, body, 1272)


SPLASH_CSS = '''
body{background:#E6E6E2;padding:32px 36px 36px}
.row{display:grid;grid-template-columns:1fr 1fr;gap:24px}
.splash{height:360px;border-radius:10px;box-shadow:0 14px 40px rgb(0 0 0 / 22%);display:flex;flex-direction:column;
  align-items:center;justify-content:center;position:relative;overflow:hidden}
.splash.light{background:#F3F2EE}.splash.dark{background:#1E2225}
.bar{width:168px;height:3px;border-radius:2px;margin-top:26px;overflow:hidden}
.light .bar{background:#E1E0DA}.dark .bar{background:#2E3438}
.bar i{display:block;width:38%;height:100%;border-radius:2px;margin-left:24%}
.light .bar i{background:#5E676B}.dark .bar i{background:#A7B0B3}
.status{font:12px "Segoe UI Variable Text","Segoe UI","Microsoft YaHei UI",sans-serif;margin-top:10px}
.light .status{color:#5E676B}.dark .status{color:#A7B0B3}
.promise{position:absolute;bottom:16px;left:0;right:0;text-align:center;font:12px "Noto Sans SC","Microsoft YaHei UI",sans-serif;letter-spacing:.06em}
.light .promise{color:#8A9296}.dark .promise{color:#7D878B}
.caption{font-size:12.5px;color:#5E676B;margin-top:14px}
'''


def splash_page():
    st_l, st_d = asset('extra/picturecairn-lockup-stacked.svg'), asset('extra/picturecairn-lockup-stacked-dark.svg')

    def splash(mode, svg):
        return (f'<div class="splash {mode}">{img(svg, h=176)}<div class="bar"><i></i></div>'
                f'<div class="status">正在打开图库…</div><div class="promise">原目录浏览，随时续看，核实再整理。</div></div>')

    body = (f'<div class="row">{splash("light", st_l)}{splash("dark", st_d)}</div>'
            '<p class="caption">启动页：竖版组合居中，底色用品牌纸 / 墨；进度条用中性石色，不用朱色也不用界面蓝。</p>')
    return page('PictureCairn splash', SPLASH_CSS, body, 1180)


VIEWER_CSS = '''
body{background:#E6E6E2;padding:28px 36px 36px}
.viewer{width:1200px;height:680px;background:#161718;border-radius:8px;overflow:hidden;position:relative;color:#E8EDED;
  font:13px "Segoe UI Variable Text","Segoe UI","Microsoft YaHei UI",sans-serif;box-shadow:0 14px 40px rgb(0 0 0 / 30%)}
.vtop{height:48px;display:flex;align-items:center;gap:14px;padding:0 10px 0 14px;background:rgb(22 23 24 / 92%);border-bottom:1px solid #2A2D2F}
.vtop .g{font-size:16px;color:#CBD2D4}
.vtop .mk{opacity:.78}
.vtop .sep{width:1px;height:20px;background:#3A3F42}
.vtop .name{font-weight:600}
.vtop .meta{color:#9AA4A8}
.vtop .tools{margin-left:auto;display:flex;align-items:center;gap:18px;padding-right:6px}
.vtop .zoomv{color:#CBD2D4;font-size:12.5px}
.stage{position:absolute;top:48px;bottom:84px;left:0;right:0;display:grid;place-items:center}
.stage svg{width:690px;height:460px;display:block}
.film{position:absolute;bottom:0;left:0;right:0;height:84px;display:flex;align-items:center;justify-content:center;gap:6px;
  background:#121314;border-top:1px solid #2A2D2F}
.film svg{width:64px;height:48px;display:block;border-radius:3px;opacity:.55}
.film .on svg{opacity:1;outline:2px solid #fff;outline-offset:1px}
.caption{font:12.5px "Instrument Sans","Noto Sans SC",sans-serif;color:#5E676B;margin-top:12px}
'''


def viewer_page():
    white = asset('extra/picturecairn-tray-white.svg')
    strip = ''.join(f'<span class="{"on" if i == 5 else ""}">{photo(300 + i * 11, 64, 48)}</span>' for i in range(11))
    body = f'''
<div class="viewer">
  <div class="vtop">{glyph('E72B')}{img(white, 16, 16, 'mk')}<span class="sep"></span>
    <span class="name">DSC_0431.jpg</span><span class="meta">2023-春季 · 第 37 / 248 张 · 4000 × 3000</span>
    <span class="tools"><span class="zoomv">100%</span>{glyph('E71F')}{glyph('E8A3')}{glyph('E7AD')}{glyph('E946')}{glyph('E740')}{glyph('E8BB')}</span></div>
  <div class="stage">{photo(431, 690, 460)}</div>
  <div class="film">{strip}</div>
</div>
<p class="caption">查看器顶部：只放纯白单色标（16px 像素对齐，78% 不透明度）作为“回到工作台”的锚点；画布固定深色，朱色不出现在看图区域。</p>'''
    return page('PictureCairn viewer', VIEWER_CSS, body, 1272)


GH_CSS = '''
body{background:#E6E6E2;padding:28px 36px 36px;font-family:-apple-system,"Segoe UI","Noto Sans SC","Microsoft YaHei UI",sans-serif}
.gh{border-radius:10px;overflow:hidden;margin-bottom:22px;box-shadow:0 8px 24px rgb(0 0 0 / 14%)}
.gh.light{background:#fff;color:#1f2328}.gh.dark{background:#0d1117;color:#e6edf3}
.ghhead{padding:16px 24px 0;border-bottom:1px solid}
.light .ghhead{background:#f6f8fa;border-color:#d1d9e0}.dark .ghhead{background:#010409;border-color:#3d444d}
.repo{display:flex;align-items:center;gap:8px;font-size:20px}
.repo img{border-radius:50%}
.repo b{font-weight:600}
.repo .pub{font-size:12px;border:1px solid;border-radius:999px;padding:0 8px;margin-left:6px}
.light .repo .pub{border-color:#d1d9e0;color:#59636e}.dark .repo .pub{border-color:#3d444d;color:#9198a1}
.tabs{display:flex;gap:22px;font-size:14px;margin-top:14px}
.tabs span{padding:8px 2px 10px}
.tabs .on{border-bottom:2px solid #fd8c73;font-weight:600}
.ghbody{display:grid;grid-template-columns:1fr 280px;gap:24px;padding:20px 24px 24px}
.readme{border:1px solid;border-radius:6px}
.light .readme{border-color:#d1d9e0}.dark .readme{border-color:#3d444d}
.readme .rh{padding:8px 16px;font-size:14px;font-weight:600;border-bottom:1px solid}
.light .rh{border-color:#d1d9e0}.dark .rh{border-color:#3d444d}
.readme .rb{padding:28px 32px}
.readme p{font-size:15px;line-height:1.6;margin-top:14px}
.readme hr{border:0;height:1px;margin-top:14px}
.light hr{background:#d1d9e0}.dark hr{background:#3d444d}
.about h3{font-size:16px;margin-bottom:8px}
.about p{font-size:14px;line-height:1.5}
.light .about .m{color:#59636e}.dark .about .m{color:#9198a1}
.avs{display:flex;gap:20px;align-items:flex-end;padding:22px 24px;border-radius:10px}
.avs .it{display:flex;flex-direction:column;align-items:center;gap:6px;font-size:12px}
.avs.light{background:#fff;color:#59636e}.avs.dark{background:#0d1117;color:#9198a1}
.row2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.caption{font:12.5px "Instrument Sans","Noto Sans SC",sans-serif;color:#5E676B;margin-top:12px}
'''


def github_page():
    avatar = asset('extra/picturecairn-avatar.svg')
    lk_l, lk_d = asset('extra/picturecairn-lockup-light.svg'), asset('extra/picturecairn-lockup-dark.svg')

    def repo(mode, lockup):
        return f'''
<div class="gh {mode}">
  <div class="ghhead"><div class="repo">{img(avatar, 24, 24)}<span>your-name</span><span>/</span><b>picturecairn</b><span class="pub">Public</span></div>
    <div class="tabs"><span class="on">Code</span><span>Issues</span><span>Pull requests</span><span>Actions</span><span>Releases</span></div></div>
  <div class="ghbody"><div class="readme"><div class="rh">README</div><div class="rb">{img(lockup, h=84)}<hr>
    <p><b>原目录浏览，随时续看，核实再整理。</b>PictureCairn 是 Windows 本地图片工作台：按真实文件夹浏览大图库，记住看到哪里，
    删除前先核实。</p></div></div>
    <div class="about"><h3>About</h3><p>PictureCairn 影标图片工作台 · Windows 本地图片工作台</p>
      <p class="m" style="margin-top:10px">windows · image-viewer · electron · local-first</p></div></div>
</div>'''

    def avs(mode):
        return (f'<div class="avs {mode}">'
                f'<div class="it">{img(avatar, 160, 160, style="border-radius:50%")}个人头像 160</div>'
                f'<div class="it">{img(avatar, 96, 96, style="border-radius:12px")}组织头像 96</div>'
                f'<div class="it">{img(avatar, 40, 40, style="border-radius:50%")}40</div>'
                f'<div class="it">{img(avatar, 20, 20, style="border-radius:50%")}20</div></div>')

    body = (repo('light', lk_l) + repo('dark', lk_d) + f'<div class="row2">{avs("light")}{avs("dark")}</div>'
            '<p class="caption">README 标题用 &lt;picture&gt; 按 GitHub 主题切换横版组合深浅稿；头像用 512 网格墨底版，圆形与圆角裁切都不会切到图形。</p>')
    return page('PictureCairn on GitHub', GH_CSS, body, 1272)


SMALL_CSS = '''
body{background:#E6E6E2;padding:32px 40px 40px}
h1{font-size:22px;font-weight:600;margin-bottom:4px}
.lead{color:#5E676B;margin-bottom:18px;font-size:13px}
table{border-collapse:separate;border-spacing:10px 10px;margin-left:-10px}
th{font-size:12px;font-weight:500;color:#5E676B;text-align:left;padding-left:4px}
td{border-radius:10px;padding:14px 16px;vertical-align:bottom}
td .c{display:flex;align-items:flex-end;gap:12px}
td small{display:block;font-size:11px;margin-top:6px;color:#5E676B}
.d small{color:#A7B0B3}
'''


def small_page():
    ml, md = asset('picturecairn-mark-light.svg'), asset('picturecairn-mark-dark.svg')
    m16, m24 = asset('extra/picturecairn-mark-16.svg'), asset('extra/picturecairn-mark-24.svg')
    fav, app24, app = asset('picturecairn-favicon.svg'), asset('extra/picturecairn-app-icon-24.svg'), asset('picturecairn-app-icon.svg')
    t16, t20, t24 = asset('picturecairn-tray.svg'), asset('extra/picturecairn-tray-20.svg'), asset('extra/picturecairn-tray-24.svg')
    w16, w20, w24 = (asset('extra/picturecairn-tray-white.svg'), asset('extra/picturecairn-tray-20-white.svg'),
                     asset('extra/picturecairn-tray-24-white.svg'))

    def cell(bg, svg, size, zoom, note, dark=False):
        cls = ' class="d"' if dark else ''
        return (f'<td{cls} style="background:{bg}"><div class="c">{px(svg, size)}{px(svg, size, zoom)}</div>'
                f'<small>{note}</small></td>')

    rows = [
        ('图形标 · 浅色界面', [cell('#f4f5f6', m16, 16, 6, '16 像素对齐'), cell('#f4f5f6', m24, 24, 4, '24 像素对齐'),
                          cell('#f4f5f6', ml, 32, 3, '32 母版'), cell('#f4f5f6', ml, 16, 6, '对照：64 母版直接缩到 16')]),
        ('图形标 · 深色界面', [cell('#1b1d1f', recolor(m16, PAPER), 16, 6, '16 像素对齐', True),
                          cell('#1b1d1f', recolor(m24, PAPER), 24, 4, '24 像素对齐', True),
                          cell('#1b1d1f', md, 32, 3, '32 母版', True), cell('#1b1d1f', md, 16, 6, '对照：母版直接缩到 16', True)]),
        ('托盘 · 浅色任务栏', [cell('#EEF0F3', t16, 16, 6, '16 · 100%'), cell('#EEF0F3', t20, 20, 5, '20 · 125%'),
                          cell('#EEF0F3', t24, 24, 4, '24 · 150%'), cell('#EEF0F3', t16, 32, 3, '32 · 200%（16 网格 ×2）')]),
        ('托盘 · 深色任务栏', [cell('#1C1C1C', w16, 16, 6, '16 · 100%', True), cell('#1C1C1C', w20, 20, 5, '20 · 125%', True),
                          cell('#1C1C1C', w24, 24, 4, '24 · 150%', True), cell('#1C1C1C', w16, 32, 3, '32 · 200%', True)]),
        ('应用图标 · 浅色', [cell('#f4f5f6', fav, 16, 6, '16 · favicon'), cell('#f4f5f6', app24, 24, 4, '24 · 任务栏'),
                         cell('#f4f5f6', fav, 32, 3, '32 · favicon ×2'), cell('#f4f5f6', app, 48, 2, '48 · 256 网格')]),
        ('应用图标 · 深色', [cell('#1b1d1f', fav, 16, 6, '16 · favicon', True), cell('#1b1d1f', app24, 24, 4, '24 · 任务栏', True),
                         cell('#1b1d1f', fav, 32, 3, '32 · favicon ×2', True), cell('#1b1d1f', app, 48, 2, '48 · 256 网格', True)]),
    ]
    trs = ''.join(f'<tr><th>{name}</th>{"".join(cells)}</tr>' for name, cells in rows)
    body = f'''<h1>小尺寸检查 · 16 / 20 / 24 / 32px</h1>
<p class="lead">每格左边是实际像素（100% 缩放），右边是同一张位图无平滑放大。16/20/24 用像素对齐版，所有直边落在整像素上；对照列是 64 母版直接缩小的效果。</p>
<table>{trs}</table>'''
    return page('PictureCairn small sizes', SMALL_CSS, body, 1180)


# ---------------------------------------------------------------- main

def main():
    os.makedirs(PAGES, exist_ok=True)
    jobs = [
        ('directions', directions_page(), os.path.join(ROOT, 'exploration', 'picturecairn-directions.png'), 1800, 1),
        ('wordmarks', words_page(), os.path.join(ROOT, 'exploration', 'picturecairn-wordmarks.png'), 1600, 1),
        ('brand-sheet', brand_sheet(), os.path.join(ROOT, 'picturecairn-brand-sheet.png'), 1600, 2),
        ('windows', windows_page(), os.path.join(ROOT, 'previews', 'picturecairn-windows.png'), 1300, 1),
        ('workbench-light', workbench_page('light'), os.path.join(ROOT, 'previews', 'picturecairn-workbench-light.png'), 1272, 2),
        ('workbench-dark', workbench_page('dark'), os.path.join(ROOT, 'previews', 'picturecairn-workbench-dark.png'), 1272, 2),
        ('splash', splash_page(), os.path.join(ROOT, 'previews', 'picturecairn-splash.png'), 1180, 2),
        ('viewer', viewer_page(), os.path.join(ROOT, 'previews', 'picturecairn-viewer.png'), 1272, 2),
        ('github', github_page(), os.path.join(ROOT, 'previews', 'picturecairn-github.png'), 1272, 2),
        ('small-sizes', small_page(), os.path.join(ROOT, 'previews', 'picturecairn-small-sizes.png'), 1180, 1),
    ]
    manifest = []
    for name, html_, png, width, scale in jobs:
        path = os.path.join(PAGES, f'{name}.html')
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(html_)
        manifest.append({'html': path, 'png': png, 'width': width + 0, 'scale': scale})
    with open(os.path.join(PAGES, 'manifest.json'), 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    print(os.path.join(PAGES, 'manifest.json'))


if __name__ == '__main__':
    main()
