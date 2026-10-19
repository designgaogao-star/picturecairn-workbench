# -*- coding: utf-8 -*-
"""找出两类"看着是内容、其实什么都没有"的东西。

## 通用水印/广告图
每个图包里都塞着一张 `cosergirl.com.jpg` / `coser福利社.webp` 之类的水印广告图。
它们不是素材，是发布者打的广告，但 pHash 会把它们算成"图片内容"——
它们还是 A 级假阳性的直接来源（黏黏团子兔 22 个 1.5GB 大包被判"互为副本"，
就是把各包里那张 51KB 水印图当成了共同内容）。

判据（两个都要满足，避免误伤真素材）：
  · 同一个 pHash 出现在 ≥ SPAM_MIN_PKGS 个**不同图包**里
    —— 用"分布在多少包"而不是"出现多少次"：真重复往往集中在 2~3 个包，
       水印图才会撒到几十个包。
  · 至少有一份副本 < SPAM_MAX_BYTES
    —— 水印图不会很大；真重复的高清图动辄 10MB+。

## 【红线】判广告图只能按哈希，不能只按文件名
`222.jpg` 被自动识别为水印图之后，按文件名匹配会把
`[222P+10V]` 这种包里的**第 222 张真照片**（12MB）一起判成广告。
文件名相同的未必是同一张图 —— 名字只是**线索**，哈希才是**证据**。
所以匹配顺序是：体积闸门 → 名字命中 → **索引里查得到就按哈希一票否决**。
查不到（没索引过）才降级信名字，并在结果里标 `verified:false`。

## 空壳包 / 残缺包（两条独立判据，分开报，不合并）
【S1 广告壳】名字里写着 `[1V-368MB]`，视频和素材全没了，只剩一张 50KB 广告图。
  判据：包内媒体文件**全是**已知水印/广告图。
  为什么不用"文件少"当判据：试过 ≤3 个文件 & <2MB，结果把
  「南宫-樱岛麻衣[2P]」这种真的只有 2 张图的小包也判成了空壳——
  **小包不等于空包**。真正的空壳是包里剩下的全是广告图。

【S2 缩水壳】包**自己声明了规格**（`[56P-252MB]`），实际只剩零头。
  这条**不依赖水印检测**，是独立证据。两条子判据，命中任一条即算：

  (a) 体积对不上：声明 ≥ SHRINK_MIN_DECLARE(50MB)，实到 ≤ SHRINK_MAX_RATIO，且无视频。
  (b) 张数对不上：声明 ≥ SHRINK_MIN_PHOTOS(20) 张，实到 ≤ 声明的 20%，且无视频。

  【S2 不叫"空壳"叫"残缺"】命中的包往往还有几十 MB 真图（比如声明 51P 只剩 4 张），
  不是空的，是**严重缺斤少两**。所以这里只报证据、不替你下结论：
  可能是你自己删过，也可能是当年就没下全。看一眼再决定。

  【为什么必须有 (b)，以及 1% 这条线是怎么定出来的】
  只用体积判据时，第一版 5% 阈值把 3 个**内容完好**的包判成了空壳：
    铃木美咲 神里绫华JK单人 [1v 28p+2.58G]  117MB / 声明 2641MB = 4.3%，但 28P 全在
    爆机少女喵小吉 NO.078 [89P 2V-1.83G]      88MB / 声明 1873MB = 4.6%，但 89P 全在
    铃木美咲 神里绫华双人 [1V30P+2.4G]       119MB / 声明 2457MB = 4.8%，但 30P 全在
  根因：这类包名的数字是**视频那一份**的体积，不是整包体积，做分母就系统性偏大。
  张数不受这个坑影响——声明 28P 就数有没有 28 张图，跟视频多大无关。
  实测分离度：真空壳 0.009%，被误判的活包最低 4.3%，中间是空的，
  所以 (a) 的阈值收到 1% 也照样够用，且离活包的下界还有 4 倍余量。

用法：
    python dedup_husk.py                 # 扫描并落盘 cache/dedup_husk.json
    python dedup_husk.py --top 20        # 打印更多
"""

import argparse
import json
import os
import re
import sqlite3
import time

from gallery.config import IMG_EXT as IMAGE_EXT
from gallery.paths import CACHE, ROOT, TOOL_DIR
from gallery.paths import DEDUP_DB as DB_PATH

OUT = os.path.join(CACHE, "dedup_husk.json")


SPAM_MIN_PKGS = 6  # 同一个哈希撒到 ≥6 个不同图包才算通用图
SPAM_MAX_BYTES = 500 * 1024  # 且至少有一份 < 500KB
SHRINK_MIN_DECLARE = 50 * 1024**2  # S2(a)：包名声明 ≥50MB 才拿来做分母
SHRINK_MAX_RATIO = 0.01  # S2(a)：实到 ≤ 声明的 1%
SHRINK_MIN_PHOTOS = 20  # S2(b)：声明张数 ≥20 才拿来做分母
SHRINK_PHOTO_KEEP = 0.20  # S2(b)：实到 ≤ 声明张数的 20%
HUSK_MAX_TOTAL = 20 * 1024**2  # S1 兜底：整包 ≤20MB（真空壳都只有几十 KB）

# 已确认的广告图文件名（不含扩展名，小写比较）。
# 其余的由通用图检测自动发现，不用手工维护名单。
KNOWN_AD_STEMS = {"cosergirl.com", "coser福利社"}

_BRACKET = re.compile(r"\[([^\[\]]+)\]")
_DECLARE = re.compile(r"(\d+(?:\.\d+)?)\s*([kmg])b?", re.I)
_PHOTOS = re.compile(r"(\d+)\s*p(?!\w)", re.I)
_UNIT = {"k": 1024, "m": 1024**2, "g": 1024**3}


def _safe_size(p):
    """取体积。扫描途中文件可能被删掉/被占用，os.path.getsize 会抛异常 ——
    不接住的话整个 find_husks 挂掉、/api/dedup/husk 返回 500，
    空壳面板直接打不开。统一走这个函数，宁可算 0 也别让面板挂。"""
    try:
        return os.path.getsize(p)
    except OSError:
        return 0


def top_groups():
    return sorted(
        d
        for d in os.listdir(ROOT)
        if os.path.isdir(os.path.join(ROOT, d))
        and not d.startswith(("_", "."))
        and os.path.abspath(os.path.join(ROOT, d)) != TOOL_DIR
    )


def find_spam(db):
    """通用水印/广告图：一句 GROUP BY 让 sqlite 自己算，不要 Python 遍历。

    【为什么换成 SQL】全库 23 万行时，Python 里建两个 dict 再逐行塞，
    光是对象开销就要几秒；而面板每次打开都要问一次"哪些是广告图"。
    一句 GROUP BY 交给 sqlite，配合 (行数, 最大 ts) 缓存，第二次问是 0 毫秒。
    """
    out = []
    # 【先按体积把输入砍掉 99%】水印图都是几十 KB 的小图，全库真正 <500KB 的
    # 只是少数。不先过滤的话，15 万行做 COUNT(DISTINCT 字符串拼接) 要 50 秒，
    # 会把每次开面板都卡住。过滤完是毫秒级。
    rows = db.execute(
        """SELECT h, COUNT(DISTINCT folder || '/' || COALESCE(pkg,'')) AS npkg
             FROM phash WHERE size < ?
            GROUP BY h HAVING npkg >= ?""",
        (SPAM_MAX_BYTES, SPAM_MIN_PKGS),
    ).fetchall()
    for h, npkg in rows:
        r = db.execute(
            "SELECT path, size FROM phash WHERE h=? AND size < ? LIMIT 1", (h, SPAM_MAX_BYTES)
        ).fetchone()
        if not r:
            continue
        copies = db.execute("SELECT COUNT(*) FROM phash WHERE h=?", (h,)).fetchone()[0]
        out.append({"h": h.hex(), "pkgs": npkg, "copies": copies, "sample": r[0], "size": r[1]})
    out.sort(key=lambda x: -x["pkgs"])
    return out


def _stem(p):
    return os.path.splitext(os.path.basename(p))[0].lower()


def _declared_bytes(name):
    """从包名里读出"这个包本来该有多大"。读不出来返回 0（不拿它当证据）。

    只在**最后一对中括号**里找：`[ATFM] Tsubaki Album Vol 030 ... [36P-346MB]`
    这种名字里前半截的 `[ATFM]` 不带数字，取最后一段才不会抓错。
    """
    segs = _BRACKET.findall(name)
    seg = segs[-1] if segs else name
    m = _DECLARE.search(seg)
    if not m:
        return 0
    try:
        return int(float(m.group(1)) * _UNIT[m.group(2).lower()])
    except (ValueError, KeyError):
        return 0


def _declared_photos(name):
    """从包名里读出"这个包本来该有几张图"。读不出来返回 0。

    `(?!\\w)` 是必须的：不加会把 `28p+2.58G` 之外的东西也吃进来，
    更重要的是要能正确匹配 `28p` 这种小写、后面紧跟着 `+` 的写法。
    """
    segs = _BRACKET.findall(name)
    seg = segs[-1] if segs else name
    vs = [int(x) for x in _PHOTOS.findall(seg)]
    return max(vs) if vs else 0


def _scan_pkgs(groups=None):
    """列出图包内所有文件；未知类型也参与整包安全判断。"""
    for g in groups if groups is not None else top_groups():
        base = os.path.join(ROOT, g)
        try:
            names = sorted(os.listdir(base))
        except OSError:
            continue
        for name in names:
            d = os.path.join(base, name)
            if not os.path.isdir(d):
                continue
            files, tot = [], 0
            for r, _ds, fs in os.walk(d):
                for f in fs:
                    p = os.path.join(r, f)
                    try:
                        tot += _safe_size(p)
                    except OSError:
                        continue
                    files.append(p)
            yield g, name, files, tot


def ad_stems_of(db):
    """广告图文件名集合（去扩展名，小写）。通用图检测出来的 + 内置已确认的。"""
    stems = set(KNOWN_AD_STEMS)
    if db is None:
        return stems
    try:
        for x in find_spam(db):
            stems.add(_stem(x["sample"]))
    except sqlite3.Error:
        pass
    return stems


class AdMatcher:
    """判断一个文件是不是广告图。三级，逐级收紧：

        1. 体积闸门：≥ SPAM_MAX_BYTES 直接否（挡掉 `[222P]` 里 12MB 的真照片）
        2. 名字闸门：文件名不在已知广告名里直接否（便宜，先挡掉 99% 的文件）
        3. 哈希判决：索引里查得到 → **哈希说了算**，不是同一个哈希就不是广告；
           查不到（没索引过）才降级信名字，并标 verified=False

    命中后返回 (是否广告, 是否经过哈希确证)。
    """

    def __init__(self, stems, hashes=None, db=None):
        self.stems = set(stems)
        self.hashes = set(hashes or ())
        self.db = db
        self.n_hash = 0  # 走哈希判决的次数（体检用）
        self.n_guess = 0  # 降级信名字的次数

    def __call__(self, path, size):
        if size >= SPAM_MAX_BYTES:
            return False, False
        if _stem(path) not in self.stems:
            return False, False
        if self.db is not None:
            try:
                row = self.db.execute("SELECT h FROM phash WHERE path=?", (path,)).fetchone()
            except sqlite3.Error:
                row = None
            if row is not None:
                self.n_hash += 1
                return (row[0] in self.hashes), True
        self.n_guess += 1
        return True, False


def find_husks(ad_stems, groups=None, db=None, hashes=None):
    """空壳包 + 包内广告图 + 残缺包。返回 (husks, ads, shrunk) 三份，互不重叠。"""
    match = AdMatcher(ad_stems, hashes, db)
    husks, ads, shrunk = [], [], []
    for g, name, files, tot in _scan_pkgs(groups):
        if not files:
            continue
        images = [p for p in files if os.path.splitext(p)[1].lower() in IMAGE_EXT]
        hit = [(p, match(p, _safe_size(p))) for p in images]
        adf = [p for p, (yes, _v) in hit if yes]
        has_other_files = len(images) != len(files)
        if adf and len(adf) == len(files) and tot <= HUSK_MAX_TOTAL:
            # 全包只剩广告图、而且整包也没多少字节 → S1 空壳
            # 最后那道 tot 闸门是兜底：万一哪个包凑巧所有图都叫 222.jpg，
            # 20MB 的上限也不会让一个装满真素材的包被整包端掉。
            # 【kind 别叫 'ad'】前端用 kind 区分"整包删 / 只删广告图"两种后果，
            # 这里叫 ad 会和"包内夹广告图"撞车（实测 7 个空壳被显示成广告图，
            # 点下去只删水印、空壳永远清不掉）。叫 'shell' 才不会歧义。
            vmap = {p: v for p, (y, v) in hit if y}
            husks.append(
                {
                    "folder": g,
                    "pkg": name,
                    "kind": "shell",
                    "files": len(files),
                    "bytes": tot,
                    "verified": all(vmap.values()),
                    "names": [os.path.basename(p) for p in files],
                }
            )
            continue
        if adf:
            # 还有真素材，但夹着广告图 → 只删广告图，包留着
            ads.append(
                {
                    "folder": g,
                    "pkg": name,
                    "drop": [os.path.relpath(p, os.path.join(ROOT, g)).replace(os.sep, "/") for p in adf],
                    "verified": all(v for p, (y, v) in hit if y),
                    "bytes": sum(_safe_size(p) for p in adf),
                }
            )
        # S2：包自己声明的规格对不上盘上的实际内容
        nimg = len(images)
        dec = _declared_bytes(name)
        dp = _declared_photos(name)
        why = ""
        if not has_other_files:
            if dec >= SHRINK_MIN_DECLARE and tot <= dec * SHRINK_MAX_RATIO:
                why = "vol"  # (a) 体积对不上
            elif dp >= SHRINK_MIN_PHOTOS and nimg <= max(2, dp * SHRINK_PHOTO_KEEP):
                why = "cnt"  # (b) 张数对不上
        if why:
            shrunk.append(
                {
                    "folder": g,
                    "pkg": name,
                    "kind": "shrink",
                    "why": why,
                    "files": len(files),
                    "imgs": nimg,
                    "bytes": tot,
                    "declare": dec,
                    "ratio": round(tot / dec, 4) if dec else 0.0,
                    "declare_p": dp,
                    "keep_p": round(nimg / dp, 3) if dp else 0.0,
                    "names": [os.path.basename(p) for p in files[:4]],
                }
            )
    husks.sort(key=lambda x: -x["bytes"])
    ads.sort(key=lambda x: -x["bytes"])
    shrunk.sort(key=lambda x: x["ratio"])
    return husks, ads, shrunk


def scan(groups=None, with_spam=True):
    """一次性拿到全部结果（服务端/CLI 共用）。"""
    spam, stems, hashes, db = [], set(KNOWN_AD_STEMS), set(), None
    if with_spam and os.path.exists(DB_PATH):
        try:
            db = sqlite3.connect(DB_PATH, timeout=30)
        except sqlite3.Error:
            db = None
    if db is not None:
        try:
            spam = find_spam(db)
            for x in spam:
                stems.add(_stem(x["sample"]))
                hashes.add(bytes.fromhex(x["h"]))
        except sqlite3.Error:
            pass
    try:
        husks, ads, shrunk = find_husks(stems, groups, db=db, hashes=hashes)
    finally:
        if db is not None:
            db.close()
    return {"spam": spam, "husks": husks, "shrunk": shrunk, "ad_in_pkg": ads, "ad_stems": sorted(stems)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=12)
    a = ap.parse_args()

    print("=" * 78)
    print("空壳包 / 通用水印图 扫描")
    print("=" * 78)

    t0 = time.time()
    res = scan()
    spam = res["spam"]
    husks, ads, shrunk = res["husks"], res["ad_in_pkg"], res["shrunk"]
    print(
        f"  通用水印图：{len(spam)} 种 · 空壳 {len(husks)} 个"
        f" · 残缺 {len(shrunk)} 个 · 夹广告图 {len(ads)} 个"
        f"（耗时 {time.time() - t0:.1f}s）"
    )
    nv = sum(1 for x in husks if x.get("verified")) + sum(1 for x in ads if x.get("verified"))
    print(f"  其中哈希确证 {nv}/{len(husks) + len(ads)} 条（其余只按文件名+体积推断，索引补上后会转确证）")

    print("-" * 78)
    print("通用水印/广告图 TOP（撒在图包数越多越确定）：")
    for x in spam[: a.top]:
        print(
            f"    {x['pkgs']:>3} 个包 / {x['copies']:>3} 份 · {x['size'] // 1024:>4}KB · "
            f"{os.path.basename(x['sample'])[:34]}"
        )
    if spam:
        print(
            f"    → 全库约 {sum(x['copies'] for x in spam)} 份（字节上不算多，但它们是 A 级假阳性的直接来源）"
        )

    print("-" * 78)
    print(f"S1 广告壳（整包只剩广告图，共 {len(husks)} 个）：")
    for x in husks[: a.top]:
        print(f"    {x['folder']}/{x['pkg'][:44]}")
        print(f"      {x['files']} 个文件 / {x['bytes'] // 1024}KB · {x['names']}")

    print("-" * 78)
    print(f"S2 残缺包（声明的规格 vs 实到严重不符，共 {len(shrunk)} 个）：")
    for x in shrunk[: a.top]:
        ev = (
            f"体积 {x['ratio'] * 100:.3f}%（{x['bytes'] // 1024}KB / 声明 {x['declare'] // 1024**2}MB）"
            if x.get("why") == "vol"
            else f"张数 {x['imgs']}/{x['declare_p']} 张（剩 {x['keep_p'] * 100:.0f}%，"
            f"{x['bytes'] // 1024}KB）"
        )
        print(f"    [{x.get('why')}] {ev}")
        print(f"          {x['folder']}/{x['pkg'][:52]}")
        print(f"          剩：{x['names']}")

    print("-" * 78)
    print(f"包内夹着广告图的（共 {len(ads)} 个包，只删那张广告图，包留着）：")
    for x in ads[: a.top]:
        print(
            f"    {'[确证]' if x.get('verified') else '[推断]'} "
            f"{x['folder']}/{x['pkg'][:34]}  {x['bytes'] // 1024}KB  "
            f"{[d.split('/')[-1] for d in x['drop'][:2]]}"
        )
    if ads:
        print(f"    → 合计 {sum(x['bytes'] for x in ads) // 1024}KB （字节少，但能让每个包干净）")

    json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("-" * 78)
    print(f"  明细：{OUT}")


if __name__ == "__main__":
    main()
