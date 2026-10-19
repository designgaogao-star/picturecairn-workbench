# -*- coding: utf-8 -*-
"""图库体检总报告 —— 一个命令出全景，不用挨个跑四个脚本再自己拼。

各工具各管一段（覆盖率 / 冗余 / 空壳 / 坏图 / 删前确证），但真正要用的是
**它们合起来说的那件事**：这个库现在健康吗、最该先动哪里。
本脚本只读各工具已经产出的 JSON，不重复算——所以几秒就出结果。

用法：
    python dedup_health.py                # 用现有缓存出报告
    python dedup_health.py --refresh      # 先重跑覆盖率扫描，再出报告
    python dedup_health.py --out 报告.md
"""

import argparse
import json
import os
import sys
import time

from gallery.paths import CACHE, TOOL_DIR


def _j(name):
    p = os.path.join(CACHE, name)
    if not os.path.exists(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except (ValueError, OSError):
        return None


def gb(n):
    return n / 1024**3


def mb(n):
    return n / 1024**2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="先重跑覆盖率扫描")
    ap.add_argument("--out", default=None)
    ap.add_argument("--top", type=int, default=10)
    a = ap.parse_args()

    if a.refresh:
        # 覆盖率扫描只列目录不读内容，1 分钟内出结果，可以放心每次刷。
        # 冗余分析（--all）要走 147 组，太重，不塞进这里，单独跑。
        import subprocess

        print("（先重跑覆盖率扫描）")
        subprocess.run(
            [sys.executable, os.path.join(TOOL_DIR, "dedup_cover.py"), "--min", "100", "--top", "0"],
            cwd=TOOL_DIR,
        )

    cover = _j("dedup_cover.json")
    report = _j("dedup_report.json")
    husk = _j("dedup_husk.json")
    broken = _j("dedup_broken.json")
    verify = _j("dedup_verify.json")

    lines = []
    w = lines.append
    w("# 图库体检报告")
    w("")
    w("> 生成时间 %s · 由 `dedup_health.py` 汇总" % time.strftime("%Y-%m-%d %H:%M"))
    w("")

    # ---------- 1 索引健康度 ----------
    w("## 一、索引健康度（其他所有数字的地基）")
    w("")
    if not cover:
        w("未扫描。先跑 `python dedup_cover.py`。")
        w("")
    else:
        td, ti = cover["total_disk"], cover["total_indexed"]
        w("| 项 | 数值 |")
        w("|---|---|")
        w("| 磁盘图片 | **%s 张** |" % f"{td:,}")
        w("| 已索引 | %s 张 |" % f"{ti:,}")
        w("| **覆盖率** | **%.1f%%** |" % (ti / max(td, 1) * 100))
        w("")
        gaps = [g for g in cover["groups"] if g["disk"] and g["cov"] < 99.9]
        gaps.sort(key=lambda g: g["disk"] - g["indexed"], reverse=True)
        if gaps:
            w("**还没扫全的组（按缺口从大到小）：**")
            w("")
            w("| 组 | 磁盘 | 已索引 | 覆盖率 |")
            w("|---|---:|---:|---:|")
            for g in gaps[: a.top]:
                w(
                    "| %s | %s | %s | %.1f%% |"
                    % (g["folder"], f"{g['disk']:,}", f"{g['indexed']:,}", g["cov"])
                )
            if len(gaps) > a.top:
                w("| … | （还有 %d 组） | | |" % (len(gaps) - a.top))
            w("")
        else:
            w("全库已扫全。下面所有数字都是**真值**，不是下界。")
            w("")

    # ---------- 2 冗余 ----------
    w("## 二、冗余")
    w("")
    if not report:
        w("未分析。先跑 `python dedup_analyze.py --all --out cache/dedup_report.json`。")
        w("")
    else:
        tot = sum(r.get("total", 0) for r in report)
        red = sum(r.get("redundant", 0) for r in report)
        w("| 项 | 数值 |")
        w("|---|---|")
        w("| 参与分析的 | %s 张 |" % f"{tot:,}")
        w("| 冗余 | %s 张 = **%.1f%%** |" % (f"{red:,}", red / max(tot, 1) * 100))
        w("| 可释放（整包删除） | %.2f GB |" % gb(sum(r.get("bytes_recoverable", 0) for r in report)))
        w("")
        # 覆盖率满了才能说"真值"。覆盖率不满时说真值就是撒谎 —— 这张嘴得跟着数据走。
        if cover and cover["total_indexed"] / max(cover["total_disk"], 1) >= 0.999:
            w("> 索引已扫全，这是**真值**。")
        else:
            w("> 这是**下界**：没扫过的图里还藏着多少重复，扫完才知道。")
        w("")

    # ---------- 3 整包删除建议 ----------
    w("## 三、整包删除建议（A 级）")
    w("")
    drops = []
    if report:
        for r in report:
            for d in r.get("pkg_drops", []):
                drops.append((r["folder"], d))
    if drops:
        w("| 项 | 数值 |")
        w("|---|---|")
        w("| 建议整包删除 | **%d 个** |" % len(drops))
        w("| 可释放 | **%.2f GB** |" % gb(sum(d["bytes"] for _, d in drops)))
        w("")
        w("**⚠ 删除前必须过 `python dedup_verify.py`** —— 它会逐文件确认包里没有一张是全世界独一份的。")
        if verify:
            ok = [x for x in verify if x.get("ok")]
            w("")
            w(
                "本次确证结果：**%d 个可删 / %.2f GB**，剔除 %d 个。"
                % (len(ok), gb(sum(x["bytes"] for x in ok)), len(verify) - len(ok))
            )
        w("")

    # ---------- 4 空壳与水印 ----------
    w("## 四、空壳包 / 残缺包 / 通用水印图")
    w("")
    if not husk:
        w("未扫描。跑 `python dedup_husk.py`。")
        w("")
    else:
        sp, hk, ad = husk.get("spam", []), husk.get("husks", []), husk.get("ad_in_pkg", [])
        sk = husk.get("shrunk", [])
        w("| 项 | 数值 |")
        w("|---|---|")
        w("| 通用水印/广告图 | %d 种 / 全库约 %d 份 |" % (len(sp), sum(x["copies"] for x in sp)))
        w("| **空壳包**（整包只剩广告图） | **%d 个** |" % len(hk))
        w("| **残缺包**（声明的规格 vs 实到严重不符） | **%d 个** |" % len(sk))
        w("| 包内夹广告图 | %d 个包 |" % len(ad))
        w("")
        if sk:
            w("残缺包清单（只提示、不代删——可能你删过，也可能当年就没下全）：")
            w("")
            for x in sk[: a.top]:
                ev = (
                    "体积只剩 %.2f%%（%dKB / 声明 %dMB）"
                    % (x["ratio"] * 100, x["bytes"] // 1024, x["declare"] // 1024**2)
                    if x.get("why") == "vol"
                    else "只剩 %d/%d 张（%.0f%%，%dKB）"
                    % (x["imgs"], x["declare_p"], x["keep_p"] * 100, x["bytes"] // 1024)
                )
                w("- `%s/%s` —— %s" % (x["folder"], x["pkg"], ev))
            if len(sk) > a.top:
                w("- …还有 %d 个" % (len(sk) - a.top))
            w("")
        if hk:
            w("空壳包清单：")
            w("")
            for x in hk[: a.top]:
                w(
                    "- `%s/%s`（%d 个文件 / %dKB · %s）"
                    % (x["folder"], x["pkg"], x["files"], x["bytes"] // 1024, ", ".join(x["names"]))
                )
            if len(hk) > a.top:
                w("- …还有 %d 个" % (len(hk) - a.top))
            w("")
        if sp:
            w(
                "通用水印图：%s"
                % ", ".join("`%s`(%d 份)" % (os.path.basename(x["sample"]), x["copies"]) for x in sp[:5])
            )
            w("")
            w("> 它们字节不多，但**是 A 级假阳性的直接来源**——各包只剩这一张图时会互相判成 100% 重复。")
            w("")

    # ---------- 5 坏图 ----------
    w("## 五、坏图")
    w("")
    if not broken:
        w("本次扫描没发现算不出哈希的图。")
        w("")
    else:
        w("**%d 张**（多为被截断的 JPEG）。它们对去重是**隐形**的。" % broken["count"])
        w("")
        for p in broken.get("files", [])[: a.top]:
            w("- `%s`" % p)
        if broken["count"] > a.top:
            w("- …还有 %d 张" % (broken["count"] - a.top))
        w("")

    # ---------- 6 建议动作 ----------
    w("## 六、建议动作（按当前状态排序）")
    w("")
    steps = []
    if cover and cover["total_indexed"] / max(cover["total_disk"], 1) < 0.999:
        steps.append("**补索引**（`--scope gap`，缺口大的先）。覆盖率不满，下面所有数字都只是下界。")
    if husk and husk.get("husks"):
        steps.append("**删空壳包** %d 个—— 它们没有内容，删掉零风险。" % len(husk["husks"]))
    if drops:
        steps.append("**过 `dedup_verify.py` 再删整包**—— 不要跳过确证。")
    if broken and broken.get("count"):
        steps.append("**处理坏图** %d 张（是删是留你自己定，但它们现在参与不了去重）。" % broken["count"])
    if not steps:
        steps.append("没有待办：索引已扫全、没有空壳、没有坏图。")
    for i, s in enumerate(steps, 1):
        w("%d. %s" % (i, s))
    w("")

    out = a.out or os.path.join(CACHE, "图库体检报告-%s.md" % time.strftime("%Y%m%d"))
    open(out, "w", encoding="utf-8").write("\n".join(lines))
    print("\n".join(lines))
    print("-" * 78)
    print("  报告：%s" % out)


if __name__ == "__main__":
    main()
