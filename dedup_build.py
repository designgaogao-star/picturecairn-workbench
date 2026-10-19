# -*- coding: utf-8 -*-
"""图库感知哈希（pHash）索引构建器。

产出用于「图包级去重」和「跨组查重」的基础数据。设计要点：

1. **独立可跑**：不依赖服务在不在跑，命令行直接跑；服务后续也 import 它。
2. **断点续跑**：按 (path, size, mtime) 判定，已算过且文件没变就跳过。
   全库 23 万张在机械硬盘上要 4 小时以上，中途断了必须能接着跑。
3. **IO 是瓶颈，不是 CPU**：实测 F 盘（机械盘）吞吐恒定在 ~100 MB/s，
   1 线程 83.9ms/张、24 线程 60.3ms/张 —— 并行只带来约 30% 收益。
   默认 16 线程是实测里最好的一档（124 MB/s），再多线程只是增加寻道。
4. **pHash 算法**：灰度 → draft 降采样 → 32×32 → DCT → 低频 8×8 与中位数比较 → 64bit。
   draft() 让 JPEG 解码器直接降采样，避免为一张 8.5MB 的图做全尺寸解码（顺序不能变）。

用法：
    python dedup_build.py --scope gap               # 按缺口从大到小补（默认，推荐）
    python dedup_build.py --scope all               # 全库（约 4 小时）
    python dedup_build.py --folder "[非R18]Pure"    # 单组
    python dedup_build.py --scope gap --workers 16 --log run.log

【选目标必须按"索引缺口"，不能按"判定状态"】
    旧默认是 --scope unreviewed，选的是 (未判定过的组)。
    而"判定过"和"索引过"是两件不相干的事：用户整理完的组被永久排除在扫描外，
    恰恰是内容最多的那批。实测后果——全库 231,149 张只索引了 40,398 张（17.5%），
    [非R18]黏黏团子兔 8,506 张只索引了 113 张（1.3%），
    并因此凭空产出 22 个 1.5GB 大包"互为副本"的假阳性。
"""

import argparse
import collections
import json
import os
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from PIL import Image, ImageFile
from scipy.fft import dct as scipy_dct

import pkgpath
from gallery.config import IMG_EXT
from gallery.paths import CACHE, GALLERY_DB, ROOT, STATE_PATH, TOOL_DIR
from gallery.paths import DEDUP_DB as DB_PATH

# 【必须开】图库里有被截断的 JPEG（实测 [非R18]是阿朱啊 一组就有 23 张，
# 例如 20190614-DSC_0121.jpg 末尾少了 5 字节）。PIL 打开能读到尺寸，
# 但 load() 会抛 OSError("image file is truncated")，导致这一张**永远算不出哈希**
# —— 对去重而言它就成了隐形图：既认不出它是谁的副本，也不会被建议删除。
# 开了这个开关，PIL 会用已读到的部分继续解码，照样算得出 pHash。
ImageFile.LOAD_TRUNCATED_IMAGES = True

# 每算完这么多张就落一次盘（分块提交，理由见 build() 里的注释）
CHUNK = 1500
HASH_SIZE = 8
HIGHFREQ = 4

_write_lock = threading.Lock()


def log(msg, path=None):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    if path:
        with _write_lock:
            try:
                with open(path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except OSError:
                pass


def thumb_cache_file(path):
    """返回该图已缓存的 400px 缩略图路径（没有则返回 None）。

    与浏览器缩略图共用 gallery.thumbs 的缓存键。
    """
    try:
        from gallery.config import THUMB_LONG_EDGE, THUMB_QUALITY
        from gallery.thumbs import thumb_cache_path
    except Exception:
        return None
    try:
        p, _ = thumb_cache_path(path, THUMB_LONG_EDGE, THUMB_QUALITY)
        return p if p and os.path.exists(p) else None
    except Exception:
        return None


def phash_from_thumb(tf, hash_size=HASH_SIZE, highfreq=HIGHFREQ):
    """从 400px 缩略图算 pHash。

    为什么敢这么做（先测后做）—— 实测 42 张：
      与「原图 draft(64,64)」的汉明距离 **中位 0 / 平均 0.29 / 最大 2**，100% ≤2，
      而判定阈值是 8。这与换 libvips（**最大 6**）完全不是一回事：
      libvips 因为会把既有索引搞得互相认不出真副本而被否掉，缩略图则安全。
    代价只是一次 ~40KB 小文件的读盘：实测 **17.8ms vs 101.4ms = 5.7x**。
    """
    try:
        with Image.open(tf) as im:
            im = im.convert("L").resize((highfreq * hash_size,) * 2, Image.LANCZOS)
        return _hash_from_image(im)
    except Exception:
        return None


def _phash_original(path, hash_size=HASH_SIZE, highfreq=HIGHFREQ):
    """老老实实读原图算 pHash（缩略图没命中时走这条）。单独拆出来是为了能被回归直接对比。"""
    try:
        with Image.open(path) as im:
            # draft 必须在任何其他操作之前 —— 放在 convert/transpose 之后会完全失效
            try:
                im.draft("RGB", (64, 64))
            except Exception:
                pass
            im = im.convert("L").resize((highfreq * hash_size,) * 2, Image.LANCZOS)
        return _hash_from_image(im)
    except Exception:
        return None


def phash(path, hash_size=HASH_SIZE, highfreq=HIGHFREQ):
    """64bit 感知哈希。返回 8 字节，失败返回 None。

    命中缩略图缓存就走小图（快 5.7x），没命中才去读原图 —— 机械盘上
    IO+解码是死瓶颈，这是零依赖能拿到的最大提速。
    """
    tf = thumb_cache_file(path)
    if tf:
        h = phash_from_thumb(tf, hash_size, highfreq)
        if h is not None:
            return h
    return _phash_original(path, hash_size, highfreq)


def scan_images(root):
    out = []
    for r, _dirs, files in os.walk(root):
        # 跳过工具自己的目录和缓存
        if os.path.normcase(os.path.abspath(r)) == os.path.normcase(TOOL_DIR):
            _dirs.clear()
            continue
        for f in files:
            if os.path.splitext(f)[1].lower() in IMG_EXT:
                out.append(os.path.join(r, f))
    return sorted(out)


def split_group(path):
    """拆出 (顶层组名, 图包名)。

    实现在 pkgpath.py —— 前端(album_of)、索引(pkg 列)、分析(判定单元) 共用同一份。
    三处各写一遍的代价已经付过一次了（v5.10：28 个待删图包一个标记都画不出来）。
    """
    return pkgpath.pkg_of(path, ROOT)


def migrate_pkg(db=None, log_path=None):
    """把历史行的 pkg 重算成新规则（v5.10 之前是完整相对路径 / "(根)" / "(扁平)"）。

    幂等，随时可重跑。path 是绝对路径，直接重算即可，不需要重解码图片。
    """
    own = db is None
    db = db or open_db()
    rows = db.execute("SELECT path, pkg FROM phash").fetchall()
    upd = []
    for path, old in rows:
        try:
            _, new = split_group(path)
        except ValueError:  # 不在 ROOT 下（盘符不同等），跳过
            continue
        if new != old:
            upd.append((new, path))
    if upd:
        db.executemany("UPDATE phash SET pkg=? WHERE path=?", upd)
        db.commit()
    log(f"pkg 规则迁移：{len(rows)} 行检查，{len(upd)} 行改写", log_path)
    if own:
        db.close()
    return len(upd)


def open_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.execute("""CREATE TABLE IF NOT EXISTS phash(
        path   TEXT PRIMARY KEY,
        folder TEXT,
        pkg    TEXT,
        h      BLOB,
        size   INTEGER,
        mtime  INTEGER,
        ts     INTEGER)""")
    db.execute("CREATE INDEX IF NOT EXISTS ix_ph_folder ON phash(folder)")
    db.execute("CREATE INDEX IF NOT EXISTS ix_ph_pkg ON phash(pkg)")
    db.commit()
    return db


class _InstanceLock:
    """单实例锁：保证同一时刻只有一个索引进程在写 dedup.db。

    为什么要它：2026-10-16 实测踩到 —— 计划任务一次拉起会看到【两个】进程
    （不同 svchost 父进程），两个实例扫同样的组、抢同一个 SQLite 写锁，
    结果进度卡在 40/66 一动不动（20 秒内新增 0 条）。与其去追"为什么起了两个"，
    不如让第二个实例自己体面退出。

    用独占的 lock 文件而不是数据库行锁，因为后者在进程被强杀后不会自动释放。
    Windows 上进程退出（含被强杀）会由 OS 关闭句柄，锁随之释放。
    """

    PATH = os.path.join(CACHE, "dedup_build.lock")

    def __init__(self):
        self.fh = None

    def __enter__(self):
        try:
            import msvcrt
        except ImportError:
            return self  # 非 Windows：不加锁，退化为无保护
        try:
            self.fh = open(self.PATH, "w")
            # 【关键】msvcrt.locking 锁的是"当前文件指针起的 nbytes"，不是从 0 开始。
            # 探锁的一方（gallery_server._dedup_build_running）用 "a+b" 打开，
            # 指针停在 EOF；两边必须都显式 seek(0)，否则锁的不是一个区间、
            # 互斥形同虚设（实测：探针会永远以为没人在跑）。
            self.fh.seek(0)
            msvcrt.locking(self.fh.fileno(), msvcrt.LK_NBLCK, 1)
            self.fh.write(f"pid={os.getpid()} started={time.strftime('%F %T')}\n")
            self.fh.flush()
        except OSError:
            if self.fh:
                self.fh.close()
                self.fh = None
            return None  # 已被别的实例持有
        return self

    def __exit__(self, *a):
        # 【解锁和加锁必须对准同一个区间】__enter__ 写完 pid 行之后文件指针停在
        # EOF（实测 39），这里不 seek(0) 解的就是另一个区间 —— Windows 会直接
        # 抛 Permission denied，于是下面的 close() 被跳过，句柄一直开着，
        # 锁到进程退出才释放。后果：同一个进程里只要拿过一次锁，
        # _dedup_build_running() 就永远返回 True，界面上"补索引"按钮被永久挡死。
        # 所以解锁失败也必须走 finally 关句柄 —— 关句柄本身就会释放这把锁。
        fh, self.fh = self.fh, None
        if not fh:
            return
        try:
            try:
                import msvcrt

                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            except (OSError, ImportError):
                pass
        finally:
            try:
                fh.close()
            except OSError:
                pass
            pass


def known_groups():
    """从 gallery.db 拿权威的顶层组列表（与服务端口径一致）。"""
    if not os.path.exists(GALLERY_DB):
        return None
    try:
        db = sqlite3.connect(GALLERY_DB)
        rows = db.execute("SELECT name FROM folders").fetchall()
        db.close()
        return {r[0] for r in rows}
    except sqlite3.Error:
        return None


def judged_groups():
    try:
        st = json.load(open(STATE_PATH, encoding="utf-8"))
        return {k for k, v in st.items() if v.get("state") in ("kept", "marked")}
    except Exception:
        return set()


def groups_by_gap(db, min_cov=0.98):
    """按「还缺多少张」从大到小列出索引不全的组，与"有没有判定过"无关。

    为什么必须按缺口而不是按判定状态选目标 —— 这是全库覆盖率只有 17.5% 的根因：
        scope=unreviewed 的选目标是 (known - judged)，
        即「还没被用户判定过(标记保留/标记删除)的组」。
    但 **"判定过"和"索引过"是两件完全不相干的事**：
        [非R18]黏黏团子兔 用户早就判定完了 → 被永久排除在扫描目标外
        → 8,506 张图只有 113 张进过索引 → 凭空产出 22 个 1.5GB 的假阳性。
    内容最多的那批组（已经整理过的）恰恰被这条规则跳过了。

    磁盘张数优先取 gallery.db 的 folders.media_count（服务端维护，实测与实walk一致），
    拿不到才退回 walk（只列目录不读内容）。
    """
    idx = collections.Counter()
    try:
        for (g,) in db.execute("SELECT folder FROM phash"):
            idx[g] += 1
    except sqlite3.Error:
        pass

    total = {}
    try:
        con = sqlite3.connect(GALLERY_DB)
        for g, n in con.execute("SELECT name, media_count FROM folders"):
            total[g] = n or 0
        con.close()
    except sqlite3.Error:
        total = {}
    if not total:
        for d in os.listdir(ROOT):
            p = os.path.join(ROOT, d)
            if not os.path.isdir(p) or d.startswith(("_", ".")):
                continue
            n = 0
            for r, _ds, fs in os.walk(p):
                n += sum(1 for f in fs if os.path.splitext(f)[1].lower() in IMG_EXT)
            total[d] = n

    out = []
    for g, t in total.items():
        if t <= 0:
            continue
        have = idx.get(g, 0)
        if have / t < min_cov:
            out.append((g, t - have))
    out.sort(key=lambda x: -x[1])
    return out


def build(scope="unreviewed", folder=None, workers=16, log_path=None, limit=0):
    db = open_db()
    known = known_groups()
    judged = judged_groups()

    if folder:
        targets = [folder]
    elif scope == "gap":
        # 目标是"没扫全的组"，按缺口从大到小。断点续跑时重跑同样会先补最大的洞。
        gaps = groups_by_gap(db)
        targets = [g for g, _ in gaps]
        if gaps:
            log("索引缺口前 5：%s" % ", ".join("%s 缺 %d 张" % (g[:26], m) for g, m in gaps[:5]), log_path)
    elif scope == "unreviewed":
        log(
            "!! scope=unreviewed 的选目标依据是【判定状态】，不是【索引覆盖率】："
            "已判定的组会被永久跳过，而它们往往内容最多、最需要索引。"
            "想补索引请用 --scope gap 或 --scope all。",
            log_path,
        )
        targets = sorted((known or set()) - judged) if known else []
        if not targets:
            log("!! 未判定组列表为空（gallery.db 不可用或全部已判定），回退为扫描顶层目录", log_path)
            targets = [
                d
                for d in os.listdir(ROOT)
                if os.path.isdir(os.path.join(ROOT, d)) and not d.startswith(("_", ".")) and d not in judged
            ]
    else:
        targets = (
            sorted(known)
            if known
            else [
                d
                for d in os.listdir(ROOT)
                if os.path.isdir(os.path.join(ROOT, d)) and not d.startswith(("_", "."))
            ]
        )

    log(f"目标 {len(targets)} 组 · workers={workers} · scope={scope or folder}", log_path)

    done = dict(db.execute("SELECT path, (size || '|' || mtime) FROM phash").fetchall())
    t_all = time.time()
    total_new = total_skip = total_fail = 0
    total_bytes = 0
    broken = []  # 算不出哈希的图（坏图），要落盘留档

    def _save_broken():
        if not broken:
            return
        p = os.path.join(CACHE, "dedup_broken.json")
        try:
            json.dump(
                {"count": len(broken), "files": broken},
                open(p, "w", encoding="utf-8"),
                ensure_ascii=False,
                indent=1,
            )
        except OSError:
            pass

    for gi, grp in enumerate(targets, 1):
        grp_path = os.path.join(ROOT, grp)
        if not os.path.isdir(grp_path):
            continue
        files = scan_images(grp_path)
        if limit:
            files = files[:limit]
        if not files:
            continue

        todo = []
        for p in files:
            try:
                st = os.stat(p)
            except OSError:
                continue
            key = f"{st.st_size}|{int(st.st_mtime)}"
            if done.get(p) == key:
                total_skip += 1
            else:
                todo.append((p, st.st_size, int(st.st_mtime)))
        if not todo:
            log(f"[{gi}/{len(targets)}] {grp}: 全部已索引，跳过", log_path)
            continue

        t0 = time.time()
        # 【分块提交】大组（实测最大 17,726 张）攒到最后一次性 commit 有两个代价：
        #   1) 日志只在整组结束时写一行 → 几十分钟看不到任何进度，像卡死了；
        #   2) 中途崩溃/被杀，整个组的活全丢 —— 断点续跑是按文件判跳过的，
        #      没落盘就等于没做过，几小时的活可能白干。
        # 每 CHUNK 张落一次盘，最坏只丢一个 chunk。
        rows, fail, saved = [], 0, 0
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for (p, sz, mt), h in zip(todo, ex.map(lambda x: phash(x[0]), todo)):
                if h is None:
                    fail += 1
                    # 算不出哈希的图对去重是**隐形**的，必须点名留档：
                    # 用户得知道哪些图坏了，而不是只看到"失败 23"这个数字
                    if len(broken) < 2000:
                        broken.append(p)
                    continue
                g, pk = split_group(p)
                rows.append((p, g, pk, h, sz, mt, int(time.time())))
                total_bytes += sz
                if len(rows) >= CHUNK:
                    db.executemany(
                        "INSERT OR REPLACE INTO phash(path,folder,pkg,h,size,mtime,ts) VALUES(?,?,?,?,?,?,?)",
                        rows,
                    )
                    db.commit()
                    saved += len(rows)
                    rows.clear()
                    dt = time.time() - t0
                    log(
                        f"    · {grp[:28]}: {saved}/{len(todo)}"
                        f" · {dt:.0f}s · {saved / max(dt, 0.1):.1f} 张/s",
                        log_path,
                    )
        if rows:
            db.executemany(
                "INSERT OR REPLACE INTO phash(path,folder,pkg,h,size,mtime,ts) VALUES(?,?,?,?,?,?,?)", rows
            )
            db.commit()
            saved += len(rows)
        dt = time.time() - t0
        total_new += saved
        total_fail += fail
        log(
            f"[{gi}/{len(targets)}] {grp}: +{saved} 张"
            f"（跳过 {len(files) - len(todo)}，失败 {fail}）"
            f" · {dt:.0f}s · {saved / max(dt, 0.1):.1f} 张/s",
            log_path,
        )

    _save_broken()
    dt_all = time.time() - t_all
    log(
        f"=== 完成 === 新增 {total_new} · 跳过 {total_skip} · 失败 {total_fail} · "
        f"用时 {dt_all / 60:.1f} 分钟 · 读取 {total_bytes / 1024**3:.1f} GB · "
        f"平均吞吐 {total_bytes / max(dt_all, 1) / 1024**2:.0f} MB/s",
        log_path,
    )
    if broken:
        log(f"!! 坏图 {len(broken)} 张（算不出哈希，对去重隐形）→ cache/dedup_broken.json", log_path)
    cnt = db.execute("SELECT COUNT(*) FROM phash").fetchone()[0]
    log(f"索引总量: {cnt:,} 张", log_path)
    db.close()
    return total_new


# ---------- 供服务内联调用：浏览即索引 ----------
# 单独扫全库在机械盘上要 90 分钟以上（IO 瓶颈，并行收益仅 30%）。
# 但用户浏览时服务端**已经在解码这张图了**，此时顺手算一次 pHash 的边际成本≈0。
# 所以真正的索引策略是：以"浏览即索引"为主，全量扫描只用来补没看过的组。
_db_local = threading.local()
_index_lock = threading.Lock()
_index_cache = {}  # path -> (size, mtime)，避免每次都查库


def get_db():
    if getattr(_db_local, "db", None) is None:
        db = open_db()
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=NORMAL")
        _db_local.db = db
    return _db_local.db


def index_one(path, thumb_bytes=None):
    """给单张图建/更新 pHash。

    thumb_bytes：已经读进内存的缩略图字节（400px 封面即可）。传了就零额外 IO。
    返回 True 表示新写入，False 表示跳过（已索引/失败）。
    绝不抛异常 —— 索引是搭车的，不能拖垮看图主流程。
    """
    try:
        st = os.stat(path)
    except OSError:
        return False
    key = (st.st_size, int(st.st_mtime))
    try:
        with _index_lock:
            if _index_cache.get(path) == key:
                return False
    except Exception:
        pass
    try:
        db = get_db()
        row = db.execute("SELECT size, mtime FROM phash WHERE path=?", (path,)).fetchone()
        if row and (row[0], row[1]) == key:
            with _index_lock:
                _index_cache[path] = key
            return False

        if thumb_bytes is not None:
            import io

            with Image.open(io.BytesIO(thumb_bytes)) as im:
                im = im.convert("L").resize((HIGHFREQ * HASH_SIZE,) * 2, Image.LANCZOS)
            h = _hash_from_image(im)
        else:
            h = phash(path)
        if h is None:
            return False

        folder, pkg = split_group(path)
        db.execute(
            "INSERT OR REPLACE INTO phash(path,folder,pkg,h,size,mtime,ts) VALUES(?,?,?,?,?,?,?)",
            (path, folder, pkg, h, st.st_size, key[1], int(time.time())),
        )
        db.commit()
        with _index_lock:
            _index_cache[path] = key
        return True
    except Exception:
        return False


def _hash_from_image(im):
    """从已打开的灰度图算 64bit pHash。"""
    px = np.asarray(im, dtype=np.float32)
    d = scipy_dct(scipy_dct(px, axis=0), axis=1)
    low = d[:HASH_SIZE, :HASH_SIZE]
    return np.packbits((low > np.median(low)).flatten()).tobytes()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--scope",
        default="gap",
        choices=["gap", "unreviewed", "all", "none"],
        help="gap=按索引缺口从大到小（默认，推荐）；all=全库；unreviewed=只看未判定组",
    )
    ap.add_argument("--folder", default=None)
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--log", default=None)
    ap.add_argument("--limit", type=int, default=0, help="每组只取前 N 张（调试用）")
    ap.add_argument(
        "--migrate", action="store_true", help="只把历史行的 pkg 重算成与前端 album 一致的规则，然后退出"
    )
    a = ap.parse_args()

    log_path = a.log
    if log_path:
        try:
            open(log_path, "w", encoding="utf-8").close()
        except OSError:
            pass
    if a.migrate:
        migrate_pkg(log_path=log_path)
        return
    with _InstanceLock() as lk:
        if lk is None:
            log("已有索引进程在跑（单实例锁未获取），本次退出", log_path)
            return
        build(scope=a.scope, folder=a.folder, workers=a.workers, log_path=log_path, limit=a.limit)


if __name__ == "__main__":
    main()
