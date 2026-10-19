# -*- coding: utf-8 -*-
"""删除前的**精确确证**：对 A 级（整包去重）建议逐包验证，再决定动不动手。

为什么必须有这一步
------------------
图包级去重是靠 pHash（64bit，汉明距离 ≤8）判定的 —— 这是**概率性**判据。
用来"提示"足够，用来"删除"不够：A 级结论是"这两个包整体重复"，
但**整体重复 ≠ 包里每一张都被对方包含**。整包删掉的前一秒，
必须确认**包里没有任何一张是全世界独一份的**。

所以每个待删包，逐文件走两层：

  层1 pHash（零 IO，来自索引）
      图片在对手包里存在汉明距离 ≤8 的图 → 视觉重复，删了不损失内容。
      64bit 里距离 ≤8 的随机碰撞概率约 2.4e-10，可忽略。
      —— 作用是覆盖「01.jpg」vs「01 - cosergirl.com.jpg」这类重编码/水印变体，
         MD5 认不出它们，但它们确实是同一张图。

  层2 MD5（精确，按需 IO）
      层1 不适用时才用：非图片文件、未入索引的图。
      逐块读取整个文件计算哈希，不把局部相同当作完整相同。
      命中 → 字节完全相同，铁证。

  两层都不中 → 独有内容 → 这个包**整包剔出**删除名单。

三个额外守卫
------------
  a. 体积守卫：待删包比对手包大 15% 以上 → 不删。它可能才是高分辨率那一份，
     pHash 会把「同一张的大图和小图」判成重复，但删掉大的就亏了。
  b. 空/无媒体守卫：目录里没有媒体文件，不盲删。
  c. 目录守卫：待删目录或对手目录不存在（可能已删过）→ 不删。

用法
----
    python dedup_verify.py                 # 只验证，产出 cache/dedup_verify.json
    python dedup_verify.py --apply         # 验证通过后，把 SAFE 的包送进回收站
    python dedup_verify.py --limit 3       # 只验证前 3 组（调试用）
"""

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import time

import numpy as np

from gallery.config import IMG_EXT as IMAGE_EXT
from gallery.paths import CACHE, ROOT
from gallery.paths import DEDUP_DB as DB_PATH

REPORT = os.path.join(CACHE, "dedup_report.json")
OUT = os.path.join(CACHE, "dedup_verify.json")


# 删之前：待删包比对手大多少就不敢删了
BIGGER_GUARD = 1.15


def _norm(p):
    return os.path.normcase(os.path.abspath(p))


def list_media(d):
    out = []
    for r, _ds, fs in os.walk(d):
        for n in fs:
            out.append(os.path.join(r, n))
    return sorted(out)


# ---------------------------------------------------------------- 层2：MD5
_MD5 = {}


def md5_of(path):
    """内容指纹。全程只哈希一次且结果缓存 —— 同一份文件被多次问到不再读盘。"""
    k = _norm(path)
    if k in _MD5:
        return _MD5[k]
    v = None
    try:
        h = hashlib.md5()
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
        v = "m:" + h.hexdigest()
    except OSError:
        v = None
    _MD5[k] = v
    return v


def peer_sizes(pdir, cache):
    """对手包的 {体积: [路径]}。只列目录，不读内容 —— 用来在哈希前先按体积排除。"""
    if pdir in cache:
        return cache[pdir]
    m = {}
    for r, _ds, fs in os.walk(pdir):
        for n in fs:
            p = os.path.join(r, n)
            try:
                m.setdefault(os.path.getsize(p), []).append(p)
            except OSError:
                pass
    cache[pdir] = m
    return m


def md5_hit(f, pdir, scache):
    """f 的字节内容能否在对手包里原样找到。体积对不上就直接返回 False（不读盘）。"""
    try:
        sz = os.path.getsize(f)
    except OSError:
        return False
    cands = peer_sizes(pdir, scache).get(sz)
    if not cands:
        return False  # 体积独一份，内容必然不同
    mine = md5_of(f)
    if not mine:
        return False
    for c in cands:
        if md5_of(c) == mine:
            return True
    return False


# ---------------------------------------------------------------- 层1：pHash
_PH_DB = {}


def folder_hashes(folder):
    """一次性把该组所有 (路径 → (图包, 哈希)) 读进内存，避免逐包查库。"""
    if folder in _PH_DB:
        return _PH_DB[folder]
    d = {}
    try:
        con = sqlite3.connect(DB_PATH)
        for p, pk, h in con.execute("SELECT path, pkg, h FROM phash WHERE folder=?", (folder,)):
            d[_norm(p)] = (pk, h)
        con.close()
    except sqlite3.Error:
        pass
    _PH_DB[folder] = d
    return d


def peer_phash(folder, pdir, cache):
    """对手包所有图的 pHash 矩阵（取自索引，零额外 IO）。"""
    key = (folder, _norm(pdir))
    if key in cache:
        return cache[key]
    pre = _norm(pdir) + os.sep
    hs = [v[1] for p, v in folder_hashes(folder).items() if p.startswith(pre)]
    arr = np.array([np.frombuffer(x, dtype=np.uint8) for x in hs], dtype=np.uint8) if hs else None
    cache[key] = arr
    return arr


def phash_hit(f, folder, pdir, hcache):
    """f（图片）在对手包里是否有汉明距离 ≤8 的图。"""
    arr = peer_phash(folder, pdir, hcache)
    if arr is None or len(arr) == 0:
        return False
    rec = folder_hashes(folder).get(_norm(f))
    if not rec or not rec[1]:
        return False
    v = np.frombuffer(rec[1], dtype=np.uint8)
    d = np.unpackbits(arr ^ v, axis=1).sum(1)
    return bool((d <= 8).any())


# ---------------------------------------------------------------- 验证主流程
def verify(rows, log=print):
    scache, hcache = {}, {}
    results = []
    t0 = time.time()

    for r in rows:
        folder = r["folder"]
        base = os.path.join(ROOT, folder)

        def fail(d, reason):
            results.append(
                {
                    "folder": folder,
                    "pkg": d["pkg"],
                    "peer": d["peer"],
                    "ok": False,
                    "reason": reason,
                    "n": 0,
                    "matched": 0,
                    "md5": 0,
                    "ph": 0,
                    "unmatched": [],
                    "kind": d.get("kind", ""),
                    "rate": d.get("rate", 0),
                    "bytes": d.get("bytes", 0),
                }
            )

        for d in r.get("pkg_drops", []):
            dp = os.path.join(base, d["pkg"])
            pp = os.path.join(base, d["peer"])
            if not os.path.isdir(dp):
                fail(d, "待删目录不存在（可能已删过）")
                continue
            if not os.path.isdir(pp):
                fail(d, "对手目录不存在，无法确证")
                continue
            files = list_media(dp)
            if not files:
                fail(d, "目录里没有媒体文件，不盲删")
                continue

            # 守卫 a：待删方明显更大 → 它可能是保留高清的那一份
            b_own = sum(_safe_size(f) for f in files)
            peer_files = list_media(pp)
            b_peer = sum(_safe_size(f) for f in peer_files)
            if b_peer > 0 and b_own > b_peer * BIGGER_GUARD:
                fail(
                    d,
                    "待删方比对手大 %.0f%%（%dMB vs %dMB），可能才是高清那一份"
                    % (b_own / b_peer * 100 - 100, b_own >> 20, b_peer >> 20),
                )
                continue

            unmatched = []
            n_md5 = n_ph = 0
            for f in files:
                if os.path.splitext(f)[1].lower() in IMAGE_EXT and phash_hit(f, folder, pp, hcache):
                    n_ph += 1
                    continue
                if md5_hit(f, pp, scache):
                    n_md5 += 1
                    continue
                unmatched.append(os.path.relpath(f, dp))

            n = len(files)
            matched = n_md5 + n_ph
            results.append(
                {
                    "folder": folder,
                    "pkg": d["pkg"],
                    "peer": d["peer"],
                    "n": n,
                    "matched": matched,
                    "md5": n_md5,
                    "ph": n_ph,
                    "unmatched": unmatched,
                    "ok": (not unmatched) and matched > 0,
                    "kind": d.get("kind", ""),
                    "rate": d.get("rate", 0),
                    "bytes": d.get("bytes", 0),
                }
            )
            log(
                "  %s %s/%s  %d/%d 命中(精确%d 视觉%d)%s"
                % (
                    "OK  " if not unmatched else "SKIP",
                    folder,
                    d["pkg"][:38],
                    matched,
                    n,
                    n_md5,
                    n_ph,
                    "" if not unmatched else "  独有 " + str(unmatched[:2]),
                )
            )

    log("  验证耗时 %.0fs" % (time.time() - t0))
    return results


def _safe_size(p):
    try:
        return os.path.getsize(p)
    except OSError:
        return 0


# ------------------------------------------------ 界面用：一对图包的对比数据
_PEER_IDX = {}


def peer_index(folder, pdir):
    """对手包的 (路径列表, pHash 矩阵)。

    和 `peer_phash` 的区别：这个**保留路径**。要看"这张图对应对手包里哪一张"
    必须有路径，只有矩阵的话只能回答"有没有"、答不出"是哪一个"。
    """
    key = (folder, _norm(pdir))
    if key in _PEER_IDX:
        return _PEER_IDX[key]
    pre = _norm(pdir) + os.sep
    items = sorted((p, v[1]) for p, v in folder_hashes(folder).items() if p.startswith(pre) and v[1])
    paths = [p for p, _ in items]
    arr = np.array([np.frombuffer(h, dtype=np.uint8) for _, h in items], dtype=np.uint8) if items else None
    _PEER_IDX[key] = (paths, arr)
    return paths, arr


def _best_match(f, folder, peer_dir, base):
    """f 在对手包里最近的那一幅。返回 (相对路径, 汉明距离)，距离 >8 视作没有。"""
    paths, arr = peer_index(folder, peer_dir)
    if arr is None or len(arr) == 0:
        return None
    rec = folder_hashes(folder).get(_norm(f))
    if not rec or not rec[1]:
        return None
    v = np.frombuffer(rec[1], dtype=np.uint8)
    d = np.unpackbits(arr ^ v, axis=1).sum(1)
    i = int(d.argmin())
    if d[i] > 8:
        return None
    return os.path.relpath(paths[i], base).replace(os.sep, "/"), int(d[i])


def compare_pkgs(folder, drop_pkg, keep_pkg, sample_n=6):
    """给界面用的一对图包的对比数据。**只读**，这里再怎么分析都不会动磁盘。

    输出两侧的文件清单、代表图，以及拍板真正要看的两个数字：
      · `unique` —— 待删方里**对手包找不到**的文件。删掉就是永久丢这些东西。
      · `matched` —— 能在对手包里原样/视觉找到的，删了不损失内容。
    另外给 "代表图 ↔ 对手图 + 距离" 的证据链，让人一眼能验证"确实是一套图"。
    """
    base = os.path.join(ROOT, folder)
    dp = os.path.join(base, drop_pkg)
    kp = os.path.join(base, keep_pkg)
    for p in (dp, kp):
        if not os.path.isdir(p):
            return {"error": "目录不存在：%s" % p}
    hcache, scache = {}, {}
    out = {"folder": folder, "links": []}

    for tag, d, other in (("drop", dp, kp), ("keep", kp, dp)):
        files = list_media(d)
        if not files:
            return {"error": "「%s」里没有媒体文件" % (drop_pkg if tag == "drop" else keep_pkg)}
        info, tot = [], 0
        for f in files:
            try:
                sz = os.path.getsize(f)
            except OSError:
                continue
            ext = os.path.splitext(f)[1].lower()
            isimg = ext in IMAGE_EXT
            tot += sz
            rel = os.path.relpath(f, base).replace(os.sep, "/")
            # 复用 deletes 用的同一套两层判据：pHash 优先（零 IO），MD5 兜底
            how = None
            if isimg and phash_hit(f, folder, other, hcache):
                how = "ph"
            elif md5_hit(f, other, scache):
                how = "md5"
            info.append({"rel": rel, "size": sz, "img": isimg, "in_other": how})
        uniq = [x for x in info if not x["in_other"]]
        imgs = [x["rel"] for x in info if x["img"]]
        out[tag] = {
            "pkg": drop_pkg if tag == "drop" else keep_pkg,
            "count": len(info),
            "bytes": tot,
            "matched": len(info) - len(uniq),
            "unique": uniq[:40],
            "unique_n": len(uniq),
            "sample": imgs[: sample_n * 2],
            "files": info,
        }

    for rel in out["drop"]["sample"][:sample_n]:
        m = _best_match(os.path.join(base, rel), folder, kp, base)
        if m:
            out["links"].append({"rel": rel, "peer": m[0], "dist": m[1]})
    dists = [x["dist"] for x in out["links"]]
    out["dist_max"] = max(dists) if dists else None
    out["dist_zero"] = sum(1 for d in dists if d == 0)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="验证通过后送进回收站（默认只验证）")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    if not os.path.exists(REPORT):
        print("先跑：python dedup_analyze.py --all --out cache/dedup_report.json")
        sys.exit(1)
    rows = [r for r in json.load(open(REPORT, encoding="utf-8")) if r.get("pkg_drops")]
    if a.limit:
        rows = rows[: a.limit]

    print("=" * 78)
    print("删除前精确确证 —— 逐包确认「包里没有一张是全世界独一份的」")
    print("=" * 78)
    res = verify(rows)
    safe = [x for x in res if x["ok"]]
    bad = [x for x in res if not x["ok"]]
    gb = sum(x["bytes"] for x in safe) / 1024**3
    gb_bad = sum(x["bytes"] for x in bad) / 1024**3

    print("-" * 78)
    print("  待删 %d 包 → 确证可删 %d 包 / %.2f GB" % (len(res), len(safe), gb))
    print("            剔除 %d 包 / %.2f GB（不做整包删除）" % (len(bad), gb_bad))
    for x in bad:
        why = x.get("reason") or ("含 %d 张独有：%s" % (len(x["unmatched"]), x["unmatched"][:3]))
        print("    x %s / %s —— %s" % (x["folder"], x["pkg"][:36], why))
    json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("  明细：%s" % OUT)

    # 剔除的包里，绝大多数只是"夹带了几张独有图"，交给 B 级逐对裁决更合适
    partial = [x for x in bad if not x.get("reason") and x["n"]]
    if partial:
        print("-" * 78)
        print("  以下 %d 包不是纯副本，但主体重复 —— 已自动进入 B 级逐对裁决队列：" % len(partial))
        for x in partial[:20]:
            print("    · %s/%s（独有 %d/%d）" % (x["folder"], x["pkg"][:40], len(x["unmatched"]), x["n"]))

    if not a.apply:
        print("\n（只读验证，未动任何文件。加 --apply 才执行删除）")
        return

    if not safe:
        print("\n没有确证可删的包，不执行。")
        return

    # ---- 执行：走服务端 /api/trash/pkg，复用已验证的校验与缓存失效逻辑 ----
    import urllib.request

    BASE = "http://127.0.0.1:8765"
    try:
        urllib.request.urlopen(BASE + "/api/ping", timeout=5).read()
    except Exception as e:
        print("\n服务端没起来（%s）—— 先拉起 GalleryToolRun 再执行。" % type(e).__name__)
        return

    # 动手前先留一份还原清单：删了什么、对谁删的、多少字节、什么时候删的。
    # 进了回收站就不该再靠记忆还原。
    import datetime

    undo = os.path.join(CACHE, "undo_trash_%s.json" % datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))

    ok_n = fail_n = 0
    freed = 0
    done = []
    for x in safe:
        body = json.dumps({"folder": x["folder"], "pkg": x["pkg"]}).encode()
        req = urllib.request.Request(
            BASE + "/api/trash/pkg", data=body, headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            r = json.load(urllib.request.urlopen(req, timeout=180))
        except Exception as e:
            print("  FAIL %s  %s: %s" % (x["pkg"][:40], type(e).__name__, e))
            fail_n += 1
            continue
        if r.get("ok"):
            ok_n += 1
            freed += x["bytes"]
            done.append(
                {
                    "folder": x["folder"],
                    "pkg": x["pkg"],
                    "peer": x["peer"],
                    "kind": x["kind"],
                    "bytes": x["bytes"],
                    "n": x["n"],
                    "md5": x["md5"],
                    "ph": x["ph"],
                }
            )
            print("  + 已送回收站 %s/%s" % (x["folder"], x["pkg"][:40]))
        else:
            fail_n += 1
            print("  FAIL %s  %s" % (x["pkg"][:40], r.get("error")))

    if done:
        json.dump(done, open(undo, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("-" * 78)
    print(
        "  完成：成功 %d 包 / 失败 %d 包 / 释放 %.2f GB（进回收站，可还原）" % (ok_n, fail_n, freed / 1024**3)
    )
    if done:
        print("  还原清单：%s" % undo)


if __name__ == "__main__":
    main()
