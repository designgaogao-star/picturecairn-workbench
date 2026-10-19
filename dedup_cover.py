# -*- coding: utf-8 -*-
"""索引覆盖率体检 —— 在相信任何去重结论之前，先问一句"你扫全了没"。

为什么需要它
------------
去重的所有结论（冗余率、整包关系、重复对）都算在 pHash 索引上。
索引是**残缺**的话，结论会往两个方向同时错：

  · 漏报：两个真副本包，各只剩 1 条索引且恰好撞进同一簇 → 被判成 100% 重复
        （这就是 [非R18]黏黏团子兔 那一组 160 个包全部只索引了 1 条水印图，
          导致 22 个互不相关的 1.5GB 大包被建议整包删掉的由来）；
  · 也会把真实重复**看不见**，把冗余率严重低估。

所以：覆盖率不够的组，它的去重结论一律不许拿来指导删除。
用法：
    python dedup_cover.py            # 全库体检
    python dedup_cover.py --min 60   # 只列覆盖率低于 60% 的组
"""

import argparse
import collections
import json
import os
import sqlite3
import sys
import time

from gallery.config import IMG_EXT
from gallery.paths import CACHE, ROOT, TOOL_DIR
from gallery.paths import DEDUP_DB as DB_PATH


def folder_of(p):
    r = os.path.relpath(p, ROOT)
    return r.split(os.sep)[0] if os.sep in r else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min", type=float, default=100.0, help="只列覆盖率低于此值的组（默认全列）")
    ap.add_argument("--top", type=int, default=40)
    a = ap.parse_args()

    if not os.path.exists(DB_PATH):
        print("没有索引：先跑 python dedup_build.py")
        sys.exit(1)
    con = sqlite3.connect(DB_PATH)
    idx = collections.Counter()
    for (g,) in con.execute("SELECT folder FROM phash"):
        idx[g] += 1
    con.close()

    groups = sorted(
        d
        for d in os.listdir(ROOT)
        if os.path.isdir(os.path.join(ROOT, d))
        and not d.startswith(("_", "."))
        and os.path.abspath(os.path.join(ROOT, d)) != TOOL_DIR
    )

    print("=" * 86)
    print("索引覆盖率体检 —— 磁盘上的图 vs 索引里真正算过哈希的图")
    print("=" * 86)
    t0 = time.time()
    rows = []
    for g in groups:
        disk = 0
        for r, _ds, fs in os.walk(os.path.join(ROOT, g)):
            for f in fs:
                if os.path.splitext(f)[1].lower() in IMG_EXT:
                    disk += 1
        n = idx.get(g, 0)
        rows.append(
            {"folder": g, "disk": disk, "indexed": n, "cov": round(n / disk * 100, 1) if disk else 0.0}
        )

    tot_d = sum(r["disk"] for r in rows)
    tot_i = sum(r["indexed"] for r in rows)
    print("-" * 86)
    print(
        "  合计：磁盘 %s 张 · 已索引 %s 张 · 覆盖率 %.1f%% · 耗时 %.0fs"
        % (f"{tot_d:,}", f"{tot_i:,}", tot_i / max(tot_d, 1) * 100, time.time() - t0)
    )

    bad = sorted(
        [r for r in rows if r["disk"] and r["cov"] < a.min],
        key=lambda r: r["disk"] - r["indexed"],
        reverse=True,
    )
    miss = sum(r["disk"] - r["indexed"] for r in bad)
    print("-" * 86)
    print("  需要补索引的组（覆盖率 < %.0f%%）：%d 个 / 缺 %s 张" % (a.min, len(bad), f"{miss:,}"))
    for r in bad[: a.top]:
        print(
            "    %-46s %6d 张 · 已索引 %6d · %5.1f%%" % (r["folder"][:44], r["disk"], r["indexed"], r["cov"])
        )
    if bad:
        print("\n  一条命令补齐（按缺口从大到小）：")
        print("  " + " ; ".join('python dedup_build.py --folder "%s"' % r["folder"] for r in bad[: a.top]))
    json.dump(
        {"total_disk": tot_d, "total_indexed": tot_i, "groups": sorted(rows, key=lambda r: r["cov"])},
        open(os.path.join(CACHE, "dedup_cover.json"), "w", encoding="utf-8"),
        ensure_ascii=False,
        indent=1,
    )
    print("  明细：%s" % os.path.join(CACHE, "dedup_cover.json"))


if __name__ == "__main__":
    main()
