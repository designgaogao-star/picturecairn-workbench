# -*- coding: utf-8 -*-
"""缩略图：多尺寸磁盘缓存 + 后台预热 + 缓存回收。

**缓存键 = md5(realpath | mtime_ns | size | edge | quality)**。
mtime 变（文件被替换）或尺寸变，都会生成全新 key —— 旧的靠 GC 回收。
这保证了"永远不会显示过期的缩略图"，代价是窗口尺寸频繁变化时会积很多缓存。

**为什么一张 400px 缩略图要 146ms**：机械盘随机读 7MB 原图 + 解码。
`draft()` 让 JPEG 解码器直接按 1/2^n 降采样，再 LANCZOS 精缩 —— 实测省 36%。
⚠️ **draft 必须在 Image.open 之后、任何其他操作之前调用**。
放在 exif_transpose 之后完全失效（实测只省 3%）：transpose/copy 会触发完整解码。

**浏览即索引**：缩略图字节已经在内存里，顺手算 pHash 几乎不要钱（零额外 IO）。
全量扫一遍 pHash 在机械盘上要 90 分钟，靠这个搭车能省掉大部分。
熔断策略是**连续失败 20 张**才关，不是一碰就炸 —— 库里有 7 张已知坏图，
原先一碰就炸等于这个功能随时被它们弄哑。
"""

import hashlib
import os
import threading
import time
from collections import deque

from gallery import guard
from gallery.config import (
    DEDUP_MAX_FAIL,
    PREVIEW_QUALITY,
    SURVEY_EDGE,
    THUMB_CACHE_LIMIT,
    THUMB_EDGE_MAX,
    THUMB_LONG_EDGE,
    THUMB_QUALITY,
)
from gallery.locks import disk_sem, key_lock
from gallery.paths import THUMB_DIR
from gallery.scan import list_media

try:
    from PIL import Image, ImageOps

    HAS_PIL = True
except Exception:  # pragma: no cover
    Image = ImageOps = None
    HAS_PIL = False

_placeholder_cache = {"v": None}


# ---------------------------------------------------------------- 缓存
def thumb_cache_path(target, edge, quality):
    """(缓存文件路径, stat)。目标读不到时返回 (None, None)。"""
    try:
        st = os.stat(target)
    except OSError:
        return None, None
    key = hashlib.md5(f"{target}|{st.st_mtime_ns}|{st.st_size}|{edge}|{quality}".encode("utf-8")).hexdigest()
    return os.path.join(THUMB_DIR, key + ".jpg"), st


def placeholder_jpeg():
    """8×8 深灰 JPEG，用作「这张图解不开」的占位。

    图库有 21 万张图，个别损坏/截断的文件能把单个缩略图请求打成 500，
    让整面封面墙出现破图；退成灰块后页面始终是干净的。
    """
    if _placeholder_cache["v"] is None:
        data = b""
        if HAS_PIL:
            try:
                from io import BytesIO

                buf = BytesIO()
                Image.new("RGB", (8, 8), (32, 34, 40)).save(buf, "JPEG", quality=60)
                data = buf.getvalue()
            except Exception:
                data = b""
        _placeholder_cache["v"] = data
    return _placeholder_cache["v"]


def get_thumb_bytes(target, edge=THUMB_LONG_EDGE, quality=THUMB_QUALITY):
    """优先磁盘缓存，否则用 Pillow 生成并缓存。返回 (bytes, mime)。"""
    edge = max(160, min(int(edge), THUMB_EDGE_MAX))
    quality = max(40, min(int(quality), 92))
    cache, _ = thumb_cache_path(target, edge, quality)
    if cache and os.path.exists(cache):
        with disk_sem:
            with open(cache, "rb") as f:
                body = f.read()
        dedup_index(target, body if edge <= 512 else None)
        return body, "image/jpeg"
    if not HAS_PIL:
        return None, None
    with key_lock(cache or target):
        if cache and os.path.exists(cache):
            with disk_sem:
                with open(cache, "rb") as f:
                    body = f.read()
            dedup_index(target, body if edge <= 512 else None)
            return body, "image/jpeg"
        os.makedirs(THUMB_DIR, exist_ok=True)
        with disk_sem:
            with Image.open(target) as im:
                # draft 必须在 open 之后、任何其它操作之前（见模块注释）
                try:
                    im.draft("RGB", (edge, edge))
                except Exception:
                    pass
                im = ImageOps.exif_transpose(im)
                if im.mode not in ("RGB", "L"):
                    im = im.convert("RGB")
                im.thumbnail((edge, edge), Image.LANCZOS)
                tmp = cache + ".tmp"
                im.save(tmp, "JPEG", quality=quality, optimize=False)
            os.replace(tmp, cache)
            with open(cache, "rb") as f:
                body = f.read()
        dedup_index(target, body if edge <= 512 else None)
        return body, "image/jpeg"


# ---------------------------------------------------------------- 去重搭车
_dedup_mod = None
_dedup_broken = False
_dedup_fail = 0  # 连续失败次数（成功一次就清零）
_dedup_lock = threading.Lock()


def dedup_index(path, thumb_bytes=None):
    """把这张图的 pHash 写进 dedup 索引。

    thumb_bytes 非空时用内存里的缩略图算（零 IO）；为 None 时会自己读原图（较慢，
    所以只在生成 400px 封面时传值，大预览不传）。
    """
    global _dedup_mod, _dedup_broken, _dedup_fail
    if _dedup_broken:
        return
    try:
        with _dedup_lock:
            if _dedup_mod is None and not _dedup_broken:
                try:
                    import dedup_build as _m

                    _dedup_mod = _m
                except Exception:
                    _dedup_broken = True
                    return
        if _dedup_mod is None:
            return
        _dedup_mod.index_one(path, thumb_bytes)
        _dedup_fail = 0
    except Exception:
        _dedup_fail += 1
        if _dedup_fail >= DEDUP_MAX_FAIL:
            _dedup_broken = True  # 连续 20 张都失败，才认定是系统性问题


# ---------------------------------------------------------------- 预热
class Warmer:
    """后台低优先级预热缩略图：队列 + 单 worker，小步让出机械盘 IO。

    两种用法：
      * enqueue()      —— 小批量（抽样页预热下一组），幂等、可随时穿插
      * begin_batch()  —— 大批量预热（用户点「预热」），带进度、可取消

    为什么必须单 worker + sleep：F 盘是机械盘，缩略图是随机读，并发只会把寻道放大。
    而且生成缩略图要把整张原图读进来解码（实测中位 163ms / 张），必须给前台浏览让位。
    """

    def __init__(self):
        self.q = deque()
        self.seen = set()
        self.lock = threading.Lock()
        self.done = 0
        self.total = 0
        self.current = ""
        self._stop = False
        self.batch = None
        self.worker = threading.Thread(target=self._loop, daemon=True)
        self.worker.start()

    def _add(self, target, edge, quality):
        """入队一张（调用方已持锁）。已生成过/已在队列里的跳过。"""
        cache, _ = thumb_cache_path(target, edge, quality)
        if not cache or cache in self.seen or os.path.exists(cache):
            return 0
        self.seen.add(cache)
        self.q.append((target, edge, quality))
        self.total += 1
        return 1

    def enqueue(self, folder, rels, edge=SURVEY_EDGE, quality=84):
        added = 0
        with self.lock:
            for rel in rels:
                target = guard.safe_media_path(folder, rel)
                if not target:
                    continue
                added += self._add(target, edge, quality)
                if len(self.q) > 4000:  # 小批量队列上限，超了丢最旧
                    self.q.popleft()
        return added

    # ---------------- 批量预热（用户点「预热」触发） ----------------
    def begin_batch(self, scope="", folders=0):
        with self.lock:
            self.q.clear()
            self.seen.clear()
            self.batch = {
                "scope": scope,
                "total": 0,
                "folders": folders,
                "folders_done": 0,
                "current_folder": "",
            }

    def add_batch(self, jobs, folder=""):
        """追加一批 job 并推进批量进度。返回实际入队数量。"""
        added = 0
        with self.lock:
            if self.batch is None:
                return 0
            for target, edge, quality in jobs:
                added += self._add(target, edge, quality)
            self.batch["total"] += added
            self.batch["folders_done"] += 1
            self.batch["current_folder"] = folder
        return added

    def stop_batch(self):
        """用户主动停止：连同队列一起清掉（已经排队的也不做了）。"""
        with self.lock:
            self.q.clear()
            b = self.batch
            self.batch = None
        return b

    def end_batch(self):
        """任务自然跑完：只标记结束，**队列留着继续排空**。

        千万别在这里清队列，否则刚入队的任务会被自己清掉，
        表现就是"启动了但一张都没生成"。
        """
        with self.lock:
            if self.batch is not None:
                self.batch["finished"] = True
                self.batch["queued"] = len(self.q)

    def _loop(self):
        while not self._stop:
            job = None
            with self.lock:
                if self.q:
                    job = self.q.popleft()
            if not job:
                time.sleep(0.15)
                continue
            target, edge, quality = job
            self.current = os.path.basename(target)
            try:
                get_thumb_bytes(target, edge, quality)
            except Exception:
                pass
            with self.lock:
                self.done += 1
            time.sleep(0.03)  # 给前台浏览让出 IO

    def progress(self):
        with self.lock:
            b = None
            if self.batch is not None:
                b = dict(self.batch)
                b["done"] = max(0, b["total"] - len(self.q))  # 队列剩余 = 未完成
                b["queued"] = len(self.q)
            return {
                "queued": len(self.q),
                "done": self.done,
                "total": self.total,
                "current": self.current,
                "remaining": max(0, self.total - self.done),
                "batch": b,
            }


# ---------------- 批量预热的驱动器 ----------------
# 建清单（list_media）本身要递归目录，138 组加起来要好几分钟，绝不能堵在 HTTP 请求里，
# 所以单独开一个线程边建清单边往 Warmer 里塞，边塞边生成。
_prewarm = {"thread": None, "stop": threading.Event(), "scope": ""}
_prewarm_lock = threading.Lock()

_warmer = None
_warmer_lock = threading.Lock()


def get_warmer():
    global _warmer
    with _warmer_lock:
        if _warmer is None:
            _warmer = Warmer()
        return _warmer


def _prewarm_worker(folders, scope, edge, quality, view_edge, view_quality, stop_ev):
    """逐组建清单并追加到 Warmer。

    view_edge > 0 时，同一张原图还会额外生成一份「单张看图用的预览尺寸」——
    只在预热当前组时开（一次打开原图、两种尺寸都产出）。全量预热不开，因为
    3840px 预览每张要重读一遍原图，138 组加起来要 8 小时以上，不值。
    """
    w = get_warmer()
    try:
        for folder in folders:
            if stop_ev.is_set():
                break
            try:
                files = list_media(folder)
            except Exception:
                files = []
            jobs = []
            for x in files:
                if x.get("kind") != "image":
                    continue
                target = guard.safe_media_path(folder, x["rel"])
                if not target:
                    continue
                jobs.append((target, edge, quality))
                if view_edge and view_edge != edge:
                    jobs.append((target, view_edge, view_quality))
            w.add_batch(jobs, folder=folder)
    finally:
        w.end_batch()


def prewarm_start(
    folders, scope, edge=THUMB_LONG_EDGE, quality=THUMB_QUALITY, view_edge=0, view_quality=PREVIEW_QUALITY
):
    """启动一次批量预热。已在跑就先停掉上一次。"""
    prewarm_stop()
    if not folders:
        return 0
    with _prewarm_lock:
        stop_ev = threading.Event()
        _prewarm["stop"] = stop_ev
        _prewarm["scope"] = scope
        get_warmer().begin_batch(scope=scope, folders=len(folders))
        t = threading.Thread(
            target=_prewarm_worker,
            args=(folders, scope, edge, quality, view_edge, view_quality, stop_ev),
            daemon=True,
        )
        _prewarm["thread"] = t
        t.start()
    return len(folders)


def prewarm_stop():
    with _prewarm_lock:
        _prewarm["stop"].set()
        _prewarm["scope"] = ""
    get_warmer().stop_batch()


def prewarm_active():
    with _prewarm_lock:
        t = _prewarm["thread"]
        return bool(t and t.is_alive())


# ---------------------------------------------------------------- 缓存统计 / 回收
_thumb_stats_cache = {"at": 0.0, "v": None}
_thumb_stats_lock = threading.Lock()
_THUMB_STATS_TTL = 5.0


def invalidate_thumb_stats():
    with _thumb_stats_lock:
        _thumb_stats_cache["at"] = 0.0
        _thumb_stats_cache["v"] = None


def thumb_cache_stats(force=False):
    now = time.time()
    if not force:
        with _thumb_stats_lock:
            if _thumb_stats_cache["v"] is not None and now - _thumb_stats_cache["at"] < _THUMB_STATS_TTL:
                return _thumb_stats_cache["v"]
    count = total = 0
    try:
        with os.scandir(THUMB_DIR) as it:
            for e in it:
                try:
                    st = e.stat(follow_symlinks=False)
                except OSError:
                    continue
                count += 1
                total += st.st_size
    except OSError:
        pass
    v = {"count": count, "bytes": total, "limit": THUMB_CACHE_LIMIT}
    with _thumb_stats_lock:
        _thumb_stats_cache["at"] = time.time()
        _thumb_stats_cache["v"] = v
    return v


def thumb_cache_gc(limit=THUMB_CACHE_LIMIT, target_ratio=0.85):
    """缓存超过 limit 时按 mtime 从旧到新删到 target_ratio。只删缓存，绝不碰原图。"""
    limit = int(limit) if limit else THUMB_CACHE_LIMIT
    st = thumb_cache_stats(force=True)
    if st["bytes"] <= limit:
        return {"removed": 0, "freed": 0, "before": st["bytes"], "after": st["bytes"], "limit": limit}
    target = int(limit * float(target_ratio))
    files = []
    try:
        with os.scandir(THUMB_DIR) as it:
            for e in it:
                try:
                    s = e.stat(follow_symlinks=False)
                except OSError:
                    continue
                files.append((s.st_mtime, s.st_size, e.path))
    except OSError:
        return {"removed": 0, "freed": 0, "before": st["bytes"], "after": st["bytes"], "limit": limit}
    files.sort()  # 最旧的先删
    freed = 0
    removed = 0
    now_bytes = st["bytes"]
    for _mt, sz, p in files:
        if now_bytes <= target:
            break
        try:
            os.remove(p)
        except OSError:
            continue
        now_bytes -= sz
        freed += sz
        removed += 1
    invalidate_thumb_stats()
    return {"removed": removed, "freed": freed, "before": st["bytes"], "after": now_bytes, "limit": limit}
