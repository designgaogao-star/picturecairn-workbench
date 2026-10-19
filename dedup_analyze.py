# -*- coding: utf-8 -*-
"""基于 pHash 索引的重复分析：组内冗余 + 图包级整包重复。

为什么分成两个层次（这是本模块最关键的设计）：

实测发现冗余**几乎全是整包/子目录级**的，而不是零散的重复图 ——
  * [非R18]Pure：3 个图包各自存了两份（100% 匹配）
  * [非R18]一米八的大梨子：4 个小包被「散图部分 [2.12G]」整体包含
这两种形态的正确操作都是「删整个目录」，而不是逐张挑。所以除了常规的
"重复簇"结果，必须单独给出**图包与图包之间的包含/重复关系**，让用户一次点击解决。

复杂度：组内两两比对是 O(n²)。实测最大组 8,072 张 → 距离矩阵 int16 约 130MB，可接受；
超过 BLOCK 阈值时改用分块计算，避免一次性开出一个平方级的大矩阵。

用法：
    python dedup_analyze.py --folder "[非R18]Pure"      # 单组详细报告
    python dedup_analyze.py --all --out report.json     # 全部已索引组，汇总并落盘
"""

import argparse
import collections
import json
import os
import sqlite3
import sys

import numpy as np

import pkgpath
from gallery.config import IMG_EXT
from gallery.paths import DEDUP_DB as DB_PATH
from gallery.paths import ROOT

DEFAULT_TH = 8  # 汉明距离阈值：<=8 视为近重复（pHash 64bit 的经验值）
PKG_RATE = 0.6  # 图包间匹配率超过此值视为"整包重复/包含"
BLOCK = 6000  # 超过此规模改用分块算距离矩阵
# 图包要参与"整包关系"判定，两边都必须有这个比例的图被索引过。
# 低于它 → 判定建立在残缺样本上，结论一律作废。
# 来历：[非R18]黏黏团子兔 一组 8,506 张只索引了 113 张，各包只剩一张 51KB 水印图，
#       导致 22 个互不相关的 1.5GB 大包被两两判成 rate=1.00 的"互为副本"。
PKG_MIN_COVER = 0.8


def split_group(path):
    """(组, 图包)。实现在 pkgpath.py —— 三处共用同一份，不抄第二遍。"""
    return pkgpath.pkg_of(path, ROOT)


_DISK_CACHE = {}


def disk_counts(folder):
    """{图包名: 该包在磁盘上的图片数}。一次 walk 全组，只读元数据不读内容。

    有了它才能算"索引覆盖率"——不知道自己扫全了没，就不该拿结论去指导删除。
    """
    if folder in _DISK_CACHE:
        return _DISK_CACHE[folder]
    base = os.path.join(ROOT, folder)
    c = collections.Counter()
    for r, _ds, fs in os.walk(base):
        for f in fs:
            if os.path.splitext(f)[1].lower() in IMG_EXT:
                p = os.path.join(r, f)
                try:
                    c[split_group(p)[1]] += 1
                except ValueError:
                    pass
    _DISK_CACHE[folder] = c
    return c


class DSU:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[ra] = rb


def hamming_matrix(H, th=DEFAULT_TH):
    """返回布尔近邻矩阵（N×N），分块计算以控制内存。

    H: (N,8) uint8 —— 每行为一个 64bit pHash。
    """
    n = len(H)
    bits = np.unpackbits(H, axis=1).astype(np.float32)  # (N,64)
    sq = (bits * bits).sum(1)
    near = np.zeros((n, n), dtype=bool)
    step = BLOCK if n > BLOCK else n
    for i in range(0, n, step):
        j_end = min(i + step, n)
        # 用 |a-b|^2 展开避免逐对 popcount：sq_i + sq_j - 2·a·b
        d = sq[i:j_end, None] + sq[None, :] - 2.0 * (bits[i:j_end] @ bits.T)
        near[i:j_end] = np.round(d) <= th
    np.fill_diagonal(near, False)
    return near


def analyze_folder(db, folder, th=DEFAULT_TH, pkg_rate=PKG_RATE, top=10):
    rows = db.execute("SELECT path, pkg, h FROM phash WHERE folder=? ORDER BY path", (folder,)).fetchall()
    if not rows:
        return None
    paths = [r[0] for r in rows]
    pkgs = [r[1] for r in rows]
    H = np.array([np.frombuffer(r[2], dtype=np.uint8) for r in rows], dtype=np.uint8)
    n = len(rows)
    if n > 20000:
        return {"folder": folder, "error": f"规模过大（{n} 张），跳过"}

    near = hamming_matrix(H, th)
    dsu = DSU(n)
    for i in range(n):
        # 只连上三角，避免重复
        js = np.nonzero(near[i, i + 1 :])[0] + i + 1
        for j in js:
            dsu.union(i, int(j))

    clusters = {}
    for i in range(n):
        clusters.setdefault(dsu.find(i), []).append(i)
    multi = [v for v in clusters.values() if len(v) > 1]
    redundant = sum(len(v) - 1 for v in clusters.values())

    # ---- 图包级：包与包之间的匹配率 ----
    pkg_names = sorted(set(pkgs))
    pidx = {p: i for i, p in enumerate(pkg_names)}
    po = np.array([pidx[p] for p in pkgs])
    # 每个图包的总字节（后面算"删掉这几个包能释放多少"要用，按包算一次就够）
    pkg_bytes = {
        p: int(
            db.execute("SELECT SUM(size) FROM phash WHERE folder=? AND pkg=?", (folder, p)).fetchone()[0] or 0
        )
        for p in pkg_names
    }
    # 覆盖率：这个图包在磁盘上有多少张、索引里真正算过多少张
    disk = disk_counts(folder)

    def cov_of(i, idxs):
        d = disk.get(pkg_names[i], 0)
        return min(len(idxs) / d, 1.0) if d else 0.0

    pkg_pairs = []
    for a in range(len(pkg_names)):
        ia = np.where(po == a)[0]
        for b in range(a + 1, len(pkg_names)):
            ib = np.where(po == b)[0]
            # 【覆盖率守卫】两边但凡有一边没扫全，这条"整包关系"就不算数。
            # 各只剩一张水印图的两个包，会因为那一张恰好撞进同簇而被判成 100% 重复
            # （黏黏团子兔 22 个 1.5GB 大包就是这么被判成"互为副本"的）。
            if min(cov_of(a, ia), cov_of(b, ib)) < PKG_MIN_COVER:
                continue
            rate_a = near[np.ix_(ia, ib)].any(1).mean()  # a 的图在 b 里能找到近邻的比例
            rate_b = near[np.ix_(ib, ia)].any(1).mean()
            hi, lo = max(rate_a, rate_b), min(rate_a, rate_b)
            if hi < pkg_rate:
                continue
            # hi≈lo 且都高 → 互为副本；hi 高 lo 低 → lo 侧被 hi 侧包含
            kind = "互为副本" if lo >= pkg_rate else "被包含"
            # 建议删掉的那个：
            #   被包含  → 删被包含的一侧（rate 高的那侧是冗余的，它的内容对方都有）
            #   互为副本 → 删**体积小**的一侧，留高清那一份。
            #     以前这里写的是 rate_b >= rate_a 就删 b，互为副本时两侧 rate 都等于 1，
            #     于是退化为"删名字排序在后面的那个"——实测把 133MB 的原图判成该删、
            #     10MB 的压缩版反而留下了（河豚抚子 5 个包全中招）。
            if abs(rate_a - rate_b) > 1e-6:
                cand = pkg_names[b] if rate_b > rate_a else pkg_names[a]
            else:
                cand = (
                    pkg_names[a]
                    if pkg_bytes.get(pkg_names[a], 0) <= pkg_bytes.get(pkg_names[b], 0)
                    else pkg_names[b]
                )
            if not cand:
                # 根散图（pkg==""）不是一个可删的子目录，删它等于动组的根目录文件。
                # 这种关系只作为证据保留（小包被散图包含 → 删小包），绝不删散图。
                continue
            pkg_pairs.append(
                {
                    "a": pkg_names[a],
                    "b": pkg_names[b],
                    "rate_a": round(float(rate_a), 3),
                    "rate_b": round(float(rate_b), 3),
                    "n_a": len(ia),
                    "n_b": len(ib),
                    "kind": kind,
                    "suggest_drop": cand,
                    "bytes_droppable": pkg_bytes.get(cand, 0),
                }
            )

    # ---- 定唯一的删除集合 ----
    # 直接拿 pkg_pairs 去删会出两个事故：
    #   1) 同一个包在多对里重复出现 → 可释放字节被累加成天文数字（实测 304 对 → 虚高）；
    #   2) 互为副本时，A 因与 B 的关系要删、B 又因与 C 的关系要删，两个副本可能全被删光。
    # 所以按置信度从高到低过一遍：定了"要留"的就绝不再删。
    order = sorted(pkg_pairs, key=lambda p: -max(p["rate_a"], p["rate_b"]))
    drops, keep = set(), set()
    for pp in order:
        cand = pp["suggest_drop"]
        other = pp["b"] if cand == pp["a"] else pp["a"]
        if cand in keep or other in drops:
            continue
        drops.add(cand)
        keep.add(other)
    # 每个待删图包只留一条最硬的证据，前端提示框才不会只显示其中一个邻居
    best = {}
    for pp in order:
        d = pp["suggest_drop"]
        if d in drops and d not in best:
            best[d] = pp
    pkg_drops = [
        {
            "pkg": d,
            "peer": (pp["b"] if pp["a"] == d else pp["a"]),
            "kind": pp["kind"],
            "rate": max(pp["rate_a"], pp["rate_b"]),
            "bytes": pkg_bytes.get(d, 0),
        }
        for d, pp in best.items()
    ]
    pkg_drops.sort(key=lambda x: -x["bytes"])

    size_of = dict(db.execute("SELECT path, size FROM phash WHERE folder=?", (folder,)).fetchall())

    multi.sort(key=lambda v: -len(v))
    sample = []
    for v in multi[:top]:
        sample.append(
            {
                "n": len(v),
                "files": [os.path.relpath(paths[i], ROOT) for i in v[:8]],
            }
        )

    # 整组的索引覆盖率。低于 1 就说明"冗余率"这个数是**下界**，不是真值：
    # 没扫过的图里可能还藏着成堆的重复，只是没人看过它们。
    d_all = sum(disk.values())
    cov_all = min(n / d_all, 1.0) if d_all else 0.0

    return {
        "folder": folder,
        "total": n,
        "unique": len(clusters),
        "redundant": redundant,
        "rate": round(redundant / n, 4),
        "clusters": len(multi),
        "clusters_sample": sample,
        "pkg_count": len(pkg_names),
        "pkg_pairs": pkg_pairs,
        "pkg_drops": pkg_drops,
        # 磁盘上真实有几张图、扫了几张 —— 没这个数就不知道结论值不值钱
        "disk_images": d_all,
        "indexed": n,
        "coverage": round(cov_all, 3),
        "bytes_total": int(sum(size_of.get(p, 0) for p in paths)),
        # 按【唯一】的删除集合算，不是按对数累加
        "bytes_recoverable": int(sum(pkg_bytes.get(d, 0) for d in drops)),
    }


def _hamming(a, b):
    """两个 8 字节 pHash 的汉明距离（仅用于展示，主流程用矩阵）。"""
    return int(np.unpackbits(np.frombuffer(a, dtype=np.uint8) ^ np.frombuffer(b, dtype=np.uint8)).sum())


def pair_queue(db, folder, th=DEFAULT_TH, exclude_pkgs=(), limit=0):
    """重复对裁决队列：每个重复簇给出「留哪个 / 删哪个」的建议。

    为什么是「对」而不是「簇」—— 这是本功能的全部立论依据：

      实测 24,226 张里，冗余 2,177 张中 **1,777 张处于 size-2 的簇（成对，82%）**，
      ≥3 张的簇只有 160 个 / 560 张（2.3%）。
      所以「每簇自动精选一张」在本图库上收益很小，正确的交互是**逐对裁决**；
      簇 >2 时展开成多条 (keep, drop_i)，逐条裁决。

    保留规则 —— 能自动判的绝不让人选：
      * 体积比 ≥1.5（实测占 25%）：大的那份是原图/高分辨率，留大的；
      * 体积接近（<1.05，实测占 59%）：两份基本是同一个文件的拷贝，
        留路径字典序靠前的那个（确定性，删哪个都一样）。

    exclude_pkgs：A 级（图包级去重）建议整包删除的图包。这些包里的内容
    会被整包带走，不该再占用裁决次数 —— 先 A 后 B，否则重叠计数。
    """
    allrows = db.execute(
        "SELECT path, pkg, size, h FROM phash WHERE folder=? ORDER BY path", (folder,)
    ).fetchall()
    excl = set(exclude_pkgs or ())
    rows = [r for r in allrows if r[1] not in excl]
    out = {
        "folder": folder,
        "total": len(rows),
        "excluded_pkgs": len(excl),
        "clusters": 0,
        "pairs": [],
        "bytes": 0,
    }
    if len(rows) < 2:
        return out
    if len(rows) > 20000:
        out["error"] = f"规模过大（{len(rows):,} 张），跳过"
        return out

    H = np.array([np.frombuffer(r[3], dtype=np.uint8) for r in rows], dtype=np.uint8)
    near = hamming_matrix(H, th)
    n = len(rows)
    dsu = DSU(n)
    for i in range(n):
        for j in np.nonzero(near[i, i + 1 :])[0] + i + 1:
            dsu.union(i, int(j))

    groups = {}
    for i in range(n):
        groups.setdefault(dsu.find(i), []).append(i)
    multi = [v for v in groups.values() if len(v) > 1]
    out["clusters"] = len(multi)

    base = os.path.join(ROOT, folder)
    pairs = []
    far = 0  # 被剔掉的假对（只靠传递相连、彼此其实不相似）
    for v in multi:
        # 体积大的优先保留；体积相同时按路径，保证每次结果一模一样（可复现）
        members = sorted(v, key=lambda i: (-rows[i][2], rows[i][0]))
        keep = members[0]
        kp, kpkg, ksz, kh = rows[keep]
        for d in members[1:]:
            dp, dpkg, dsz, dh = rows[d]
            # 【簇 ≠ 两两相似】簇是传递闭包连出来的：A~B 距离 8、B~C 距离 8，
            # 但 A 与 C 可能差 16 bit —— 那是两张完全不同的图。
            # 把它们配成一对让人裁决，等于让人在两张无关的图里选一张删掉。
            # 实测 13,561 条里有 1,309 条（9.7%）是这种假对，距离最大到 26。
            kk, kkp, kks, khh = kp, kpkg, ksz, kh
            dist = _hamming(khh, dh)
            if dist > th:
                # 还有救：d 也许和簇里**另一个**成员真的相似（A~C~D 里的 C）。
                # 换它当保留方 —— 但必须比 d 更大（或等大且路径更靠前），
                # 否则会出现"这两条互相判对方该删"的死循环。
                alt = next(
                    (
                        i
                        for i in v
                        if i != d
                        and _hamming(rows[i][3], dh) <= th
                        and (rows[i][2] > dsz or (rows[i][2] == dsz and rows[i][0] < dp))
                    ),
                    None,
                )
                if alt is None:
                    far += 1
                    continue  # 宁可不删，也不能瞎删
                kk, kkp, kks, khh = rows[alt]
                dist = _hamming(khh, dh)
            ratio = (kks / dsz) if dsz else 1.0
            pairs.append(
                {
                    "keep": {
                        "rel": os.path.relpath(kk, base).replace(os.sep, "/"),
                        "pkg": kkp,
                        "size": int(kks),
                    },
                    "drop": {
                        "rel": os.path.relpath(dp, base).replace(os.sep, "/"),
                        "pkg": dpkg,
                        "size": int(dsz),
                    },
                    "ratio": round(float(ratio), 3),
                    "hamming": dist,
                    "why": (
                        "另一份体积明显更大（高分辨率/原图），删这份小的"
                        if ratio >= 1.5
                        else "两份几乎一样大，删哪份都行"
                    ),
                    "bytes": int(dsz),
                }
            )
    # 按「保留方」的路径排序：同一个图包里的重复会挨在一起，裁决时上下文连贯
    pairs.sort(key=lambda p: (p["keep"]["rel"], p["drop"]["rel"]))
    out["total_pairs"] = len(pairs)
    out["dropped_far"] = far  # 只靠传递相连的假对，已剔除（不是重复，不入队）
    if limit and limit > 0:
        pairs = pairs[:limit]
    out["pairs"] = pairs
    out["bytes"] = int(sum(p["bytes"] for p in pairs))
    # 队列也是算在索引上的：没扫全就说明"还有很多对你没看见"
    d_all = sum(disk_counts(folder).values())
    out["disk_images"] = d_all
    out["indexed"] = n
    out["coverage"] = round(min(n / d_all, 1.0) if d_all else 0.0, 3)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", default=None)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--th", type=int, default=DEFAULT_TH)
    ap.add_argument("--out", default=None)
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--pairs", action="store_true", help="输出重复对裁决队列而不是整包报告")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    if not os.path.exists(DB_PATH):
        print(f"索引库不存在：{DB_PATH}\n先跑：python dedup_build.py --scope unreviewed")
        sys.exit(1)
    db = sqlite3.connect(DB_PATH)

    if a.folder and a.pairs:
        excl = [d["pkg"] for d in (analyze_folder(db, a.folder, th=a.th) or {}).get("pkg_drops", [])]
        r = pair_queue(db, a.folder, th=a.th, exclude_pkgs=excl, limit=a.limit)
        if r.get("error"):
            print(r["error"])
            sys.exit(1)
        print(f"\n=== {r['folder']} · 重复对裁决队列 ===")
        print(
            f"  {r['total']:,} 张 · {r['clusters']} 个重复簇 · "
            f"{r['total_pairs']} 条待裁决 · 可释放 {r['bytes'] / 1024**3:.2f} GB"
        )
        if r.get("excluded_pkgs"):
            print(f"  （已排除 A 级建议整包删除的 {r['excluded_pkgs']} 个图包，不重复占用裁决）")
        for p in r["pairs"][:40]:
            k, d = p["keep"], p["drop"]
            print(f"   留 {k['size'] / 1048576:8.1f}MB  {k['rel'][:56]}")
            print(
                f"   删 {d['size'] / 1048576:8.1f}MB  {d['rel'][:56]}   "
                f"[×{p['ratio']:.1f} 距离{p['hamming']}]"
            )
        return

    if a.folder:
        r = analyze_folder(db, a.folder, th=a.th, top=a.top)
        if not r:
            print(f"{a.folder}: 无索引数据")
            sys.exit(1)
        print(f"\n=== {r['folder']} ===")
        cov = r.get("coverage", 1.0)
        print(
            f"  总 {r['total']:,} 张 · 唯一 {r['unique']:,} · 冗余 {r['redundant']:,} "
            f"= {r['rate'] * 100:.1f}% · 重复簇 {r['clusters']}"
        )
        if cov < 0.999:
            print(
                f"  ⚠ 索引覆盖率 {cov * 100:.1f}%（磁盘 {r['disk_images']:,} 张 / 已扫 {r['indexed']:,} 张）"
                f" —— 上面的冗余率是**下界**，没扫过的图里可能还有重复"
            )
        print(
            f"  图包 {r['pkg_count']} 个 · 命中整包关系 {len(r['pkg_pairs'])} 对 "
            f"→ 去重后建议删 {len(r['pkg_drops'])} 个"
        )
        for d in r["pkg_drops"]:
            print(
                f"    删 [{d['kind']}] {d['rate'] * 100:.0f}% 重复于「{d['peer'][:40]}」"
                f"  {d['bytes'] / 1024**3:.2f} GB"
            )
            print(f"        {d['pkg'][:60]}")
        if r["clusters_sample"]:
            print(f"  最大的重复簇（前 {len(r['clusters_sample'])}）：")
            for s in r["clusters_sample"]:
                print(f"    {s['n']} 张: {s['files'][0][:60]}")
        print(
            f"  可释放合计 {r['bytes_recoverable'] / 1024**3:.2f} GB / "
            f"本组 {r['bytes_total'] / 1024**3:.2f} GB"
        )
        return

    folders = [r[0] for r in db.execute("SELECT folder FROM phash GROUP BY folder ORDER BY folder")]
    out = []
    tot = tot_red = tot_bytes = 0
    print(f"共 {len(folders)} 组已索引\n")
    print(f"{'组':<34} {'张数':>7} {'冗余':>7} {'占比':>7} {'删包数':>6} {'可释放':>9}")
    print("-" * 76)
    for f in folders:
        r = analyze_folder(db, f, th=a.th, top=a.top)
        if not r or r.get("error"):
            continue
        out.append(r)
        tot += r["total"]
        tot_red += r["redundant"]
        tot_bytes += r["bytes_recoverable"]
        print(
            f"  {r['folder'][:32]:<34} {r['total']:>7,} {r['redundant']:>7,} "
            f"{r['rate'] * 100:>6.1f}% {len(r['pkg_drops']):>6} "
            f"{r['bytes_recoverable'] / 1024**3:>7.2f}G"
        )
    print("-" * 76)
    print(
        f"  合计 {tot:,} 张 · 冗余 {tot_red:,} = "
        f"{tot_red / max(tot, 1) * 100:.1f}% · 整包可释放 {tot_bytes / 1024**3:.1f} GB"
    )

    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        print(f"\n明细已写入 {a.out}")


if __name__ == "__main__":
    main()
