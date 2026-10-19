# -*- coding: utf-8 -*-
"""
图库本地预览 / 审查服务器（标准库 + Pillow）

v5.3 安全与健壮性加固（对应 代码体检报告-20260911.md）：
  * 入口白名单  _valid_group_name/_is_known_group —— folder/names 一律先过白名单，
                堵掉「绝对路径让 os.path.join 丢弃 ROOT → 删除/读取图库之外的文件」
                以及「空 folder → base 变成 ROOT → 一次请求递归整库 28 万文件」
  * 媒体层      _serve_media 限定 MEDIA_EXT、独立 _parse_range（支持 RFC 7233 后缀范围）、
                发送阶段出错只关连接不重发响应头
  * 传输        HTTP/1.1 keep-alive（图包墙一屏几十上百张缩略图）+ backlog 64；
                所有响应补齐 Content-Length
  * 并发        list_media 单飞去重；扫描并发 12 → 4（HDD 友好）
  * 缓存        thumb_cache_stats 5s TTL；缩略图解码失败退灰块占位

分层：
  数据层  init_db / folders_* / media_* —— SQLite(WAL) 统一文件夹元数据与媒体清单，
          顶层指纹增量失效；首次启动自动从旧 folders_meta.json / cache/files 迁移；批量单事务写入
  扫描层  scan_root / scan_one            —— 顶层体积元数据，指纹未变直接走库，变化项并行重扫；
          结果带 SCAN_TTL 短缓存，高频接口不重复扫目录（HDD 友好）；公共遍历器 _walk_files
  白名单  _top_level_names/_is_known_group—— 所有 folder/names 入口的统一关卡（见上）
  状态层  load_state / save_state         —— 审查状态内存化 + 防抖落盘 review_state.json（量小、透明可手改）
  抽样层  survey_overview / survey_samples—— 未处理组概览 + 纯随机抽样（支持 exclude 避开已看）
  缩略层  get_thumb_bytes / Warmer        —— 缩略图磁盘缓存（多尺寸），后台低优先级预热；thumb_cache_gc 保守清理
  删除层  recycle_one / permanent_delete  —— 送系统回收站（可恢复，ctypes 零依赖）/ 永久删除（需 confirm_permanent 硬闸门）
  媒体层  _serve_media                    —— 原图 ETag/304 + Range
  传输：GalleryHTTPServer(HTTP/1.1) + 磁盘并发信号量（F: 为机械硬盘，限制并发寻道）+ 每请求异常兜底
"""

import os
import sys

# 【打包成窗口程序后 stdout/stderr 是 None】
# PyInstaller 的 console=False 用 runw.exe 启动，此时 sys.stdout / sys.stderr 都是 None。
# CPython 的 print() 会静默跳过，但**任何直接写 sys.stderr 的代码都会崩**
# （最典型的是 http.server 的 log_message，以及 Pillow 的警告输出）。
# 这类崩溃发生在请求线程里，主线程毫无感觉，表现是"进程在跑但端口不响应"。
# 所以一进来就把它们接到日志文件上，绝不留给 None。
if getattr(sys, "frozen", False) and (sys.stdout is None or sys.stderr is None):
    _boot_dir = os.environ.get("GALLERY_DATA") or os.path.dirname(sys.executable)
    try:
        _boot_dir = os.path.join(_boot_dir, "cache")
        os.makedirs(_boot_dir, exist_ok=True)
        _boot = open(os.path.join(_boot_dir, "boot.log"), "a", encoding="utf-8", buffering=1)
    except OSError:
        _boot = open(os.devnull, "w", encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = _boot
    if sys.stderr is None:
        sys.stderr = _boot

import json
import mimetypes
import random
import sqlite3
import threading
import time
import traceback
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if __name__ == "__main__":
    sys.modules["gallery_server"] = sys.modules[__name__]

# 路径与常量都收在 gallery/ 包里 —— 原先这两样东西在 7 个脚本里各写了一遍，
# 而且扩展名白名单互相不一致（详见 gallery/config.py 顶部注释）。
from gallery import remove as _remove  # 删除链路（回收站 / 永久 / 落位校验）
from gallery import store as _store  # 数据层（SQLite）
from gallery.api import dedup as _dedup_api  # 去重接口业务逻辑
from gallery.api import maintain as _maint_api  # 维护接口业务逻辑
from gallery.api import remove as _remove_api  # 删除接口业务逻辑
from gallery.api import review as _review_api  # 接口业务逻辑（纯函数）
from gallery.config import (  # 常量唯一来源
    DEDUP_DEFAULT_TH,
    IMG_EXT,
    PORT,
    STATE_FLUSH_DELAY,
    THUMB_CACHE_LIMIT,
    THUMB_LONG_EDGE,
    THUMB_QUALITY,
    UI_CTYPE,
)
from gallery.fileio import atomic_write_json as _atomic_write_json
from gallery.guard import (
    _is_known_group,
    safe_media_path,
)
from gallery.locks import disk_sem as _disk_sem  # 并发闸门统一在 locks.py
from gallery.paths import (  # 路径唯一来源（支持 GALLERY_ROOT 覆盖）
    CACHE,
    DB_PATH,
    INDEX_PATH,
    LEGACY_MARKS,
    LOG_PATH,
    ROOT,
    STATE_PATH,
    SURVEY_PATH,
    THUMB_DIR,
    TOOL_DIR,
    UI_DIR,
)
from gallery.scan import (
    invalidate_file_caches,
    invalidate_scan_cache,
    list_media,
    scan_root,
)
from gallery.store import (
    delete_folder as db_delete_folder,
)
from gallery.store import (  # 保持旧名字，调用点零改动
    init as init_db,
)

# /api/dim 只需要读文件头拿宽高，用 thumbs 里同一份 PIL 句柄
from gallery.thumbs import (  # 保持旧名字，调用点零改动
    HAS_PIL,
    Image,
    get_thumb_bytes,
    get_warmer,
    invalidate_thumb_stats,
    prewarm_active,
    prewarm_stop,
    thumb_cache_gc,
    thumb_cache_stats,
)
from gallery.thumbs import (
    placeholder_jpeg as _placeholder_jpeg,
)

# 缩略图锁原先在这里（_thumb_locks / _thumb_locks_guard），已并入 gallery/locks.py


# ============================ 状态层（内存化 + 合并写） ============================
_state_mem = None
_state_dirty = False
_state_flush_timer = None
_state_lock = threading.RLock()


def _read_state_from_disk() -> dict:
    data = {}
    for p in (STATE_PATH, STATE_PATH + ".bak"):  # 主文件损坏/为空时回退到上一版备份
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data:
                    break
            except (OSError, ValueError):
                data = {}
    return migrate_legacy(data)


def migrate_legacy(state: dict) -> dict:
    if state or not os.path.exists(LEGACY_MARKS):
        return state
    try:
        with open(LEGACY_MARKS, "r", encoding="utf-8") as f:
            old = json.load(f)
        for name, flagged in old.items():
            if flagged:
                state[name] = {"state": "marked", "index": 0, "ts": int(time.time())}
    except (OSError, ValueError):
        pass
    return state


def load_state() -> dict:
    global _state_mem
    with _state_lock:
        if _state_mem is None:
            _state_mem = _read_state_from_disk()
        return _state_mem


def _flush_state_now():
    global _state_dirty, _state_flush_timer
    with _state_lock:
        if not _state_dirty:
            return
        snapshot = json.loads(json.dumps(_state_mem, ensure_ascii=False))
        _state_dirty = False
        _state_flush_timer = None
    try:
        _atomic_write_json(STATE_PATH, snapshot, keep_bak=True)
    except OSError:
        with _state_lock:
            _state_dirty = True


def _schedule_state_flush():
    global _state_flush_timer
    with _state_lock:
        if _state_flush_timer is not None:
            _state_flush_timer.cancel()
        t = threading.Timer(STATE_FLUSH_DELAY, _flush_state_now)
        t.daemon = True
        _state_flush_timer = t
        t.start()


def save_state(state: dict, immediate: bool = False):
    global _state_mem, _state_dirty, _state_flush_timer
    with _state_lock:
        _state_mem = state
        _state_dirty = True
        if immediate:
            if _state_flush_timer is not None:
                _state_flush_timer.cancel()
                _state_flush_timer = None
            _flush_state_now()
        else:
            _schedule_state_flush()


def flush_state_on_exit():
    try:
        _flush_state_now()
    except Exception:
        pass


# ============================ 索引层（媒体清单，SQLite + 内存热缓存） ============================
# ============================ 抽样层 ============================
def survey_overview(state: dict):
    """仅返回尚未处理（无 kept/marked）的文件夹概览，顺序沿用体积降序。"""
    out = []
    for f in scan_root():
        if state.get(f["name"], {}).get("state") in ("kept", "marked"):
            continue
        out.append(
            {"name": f["name"], "category": f["category"], "size": f["size"], "media_count": f["media_count"]}
        )
    return out


def survey_samples(folder: str, n: int = 20, seed: int = 0, exclude=None):
    """从某文件夹的全部图片中纯随机抽 n 张；exclude 内的 rel 不参与（重抽避开已看）。"""
    files = list_media(folder)
    all_imgs = [{"rel": x["rel"], "album": x.get("album", ""), "kind": x["kind"]} for x in files]
    ex = set(exclude or [])
    pool = [x for x in all_imgs if x["rel"] not in ex]
    reset_round = False
    if not pool:
        pool = all_imgs
        reset_round = True
    rnd = random.Random(f"{seed}|{folder}")
    k = min(n, len(pool))
    picks = rnd.sample(pool, k) if k else []
    picked_rel = {p["rel"] for p in picks}
    remaining = len([x for x in all_imgs if x["rel"] not in ex and x["rel"] not in picked_rel])
    return {
        "folder": folder,
        "seed": seed,
        "total_images": len(files),
        "total_media": len(files),
        "remaining": remaining,
        "reset_round": reset_round,
        "samples": picks,
    }


_dedup_ana_cache = {}  # folder -> (cache_key, result)，避免每次点开都重算 O(n²)
_dedup_pair_cache = {}  # folder -> (cache_key, pair_queue)
_dedup_husk_cache = {}  # folder -> (cache_key, 空壳/残缺/广告图)
_dedup_ad_cache = None  # (cache_key, ad_stems, ad_hashes) —— 全库共用一份


def _dedup_build_running():
    """索引器此刻是否在跑。直接探测它的**同一把锁**，不另造一套状态。

    dedup_build 用 cache/dedup_build.lock 的 1 字节独占区间做单实例保护
    （进程被强杀时 OS 会关句柄，锁自动释放）。这里拿同一把锁探一下就知道，
    比去 ps 里抓进程名可靠得多——抓名字的老问题是会把自己也匹配进去。
    """
    p = os.path.join(CACHE, "dedup_build.lock")
    try:
        import msvcrt
    except ImportError:
        return False
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        fh = open(p, "a+b")  # 绝不能用 "w"：会把锁文件截断
    except OSError:
        return True
    try:
        # 【关键】msvcrt.locking 锁的是"当前文件指针起的 nbytes"，不是从 0 开始。
        # "a+b" 打开后指针在 EOF，会锁到一个别人根本不碰的区间，探测永远返回"没人在跑"。
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        fh.close()
        return True  # 锁被持有 → 有实例在跑
    try:
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
    except OSError:
        pass
    finally:
        fh.close()
    return False


def dedup_status():
    """去重索引的覆盖情况。前端用它决定"查重"按钮是否可用 / 提示先建索引。"""
    indexed = groups = 0
    try:
        import dedup_build as m

        db = m.get_db()
        indexed = db.execute("SELECT COUNT(*) FROM phash").fetchone()[0]
        groups = db.execute("SELECT COUNT(DISTINCT folder) FROM phash").fetchone()[0]
    except Exception:
        pass
    total = 0
    try:
        con = sqlite3.connect(DB_PATH)
        total = con.execute("SELECT COALESCE(SUM(media_count),0) FROM folders").fetchone()[0]
        con.close()
    except sqlite3.Error:
        pass
    return {
        "indexed": indexed,
        "groups": groups,
        "total_media": total,
        "coverage": round(indexed / total, 4) if total else 0.0,
        "building": _dedup_build_running(),
    }


def dedup_analyze_group(folder, th=DEDUP_DEFAULT_TH):
    """组内重复分析（含图包级整包重复）。结果按"该组索引最后更新时间"缓存。"""
    try:
        import dedup_analyze as da
        import dedup_build as m

        db = m.get_db()
        row = db.execute(
            "SELECT COUNT(*), COALESCE(MAX(ts),0) FROM phash WHERE folder=?", (folder,)
        ).fetchone()
        ck = (row[0], row[1], th)
        hit = _dedup_ana_cache.get(folder)
        if hit and hit[0] == ck:
            return hit[1]
        r = da.analyze_folder(db, folder, th=th)
        _dedup_ana_cache[folder] = (ck, r)
        return r
    except Exception:
        return None


def dedup_pair_queue(folder, th=DEDUP_DEFAULT_TH, limit=0):
    """重复对裁决队列（B 级）。

    先拿 A 级的整包删除清单，把那些图包**排除在队列之外**：
    它们的内容会被整包带走，再让人逐张裁决一遍纯属浪费（实测重叠 1,215 条）。
    """
    try:
        import dedup_analyze as da
        import dedup_build as m

        db = m.get_db()
        row = db.execute(
            "SELECT COUNT(*), COALESCE(MAX(ts),0) FROM phash WHERE folder=?", (folder,)
        ).fetchone()
        ck = (row[0], row[1], th, limit)
        hit = _dedup_pair_cache.get(folder)
        if hit and hit[0] == ck:
            return hit[1]
        excl = [d["pkg"] for d in (dedup_analyze_group(folder, th) or {}).get("pkg_drops", [])]
        r = da.pair_queue(db, folder, th=th, exclude_pkgs=excl, limit=limit)
        _dedup_pair_cache[folder] = (ck, r)
        return r
    except Exception:
        return None


def _dedup_ad_sets():
    """广告图的 (文件名集合, 哈希集合)。全库只算一次，按索引规模缓存。

    【为什么哈希集合必须一起传下去】只按文件名匹配会出大事：
    `222.jpg` 被自动识别成水印图之后，`[222P+10V]` 这种包里的
    **第 222 张真照片**（12MB）会因为同名被一起判成广告图。
    名字只是线索，哈希才是证据 —— 所以两个集合必须成对使用。
    """
    global _dedup_ad_cache
    try:
        import dedup_build as m
        import dedup_husk as dh

        db = m.get_db()
        row = db.execute("SELECT COUNT(*), COALESCE(MAX(ts),0) FROM phash").fetchone()
        ck = (row[0], row[1])
        if _dedup_ad_cache and _dedup_ad_cache[0] == ck:
            return _dedup_ad_cache[1], _dedup_ad_cache[2]
        stems, hashes = set(dh.KNOWN_AD_STEMS), set()
        for x in dh.find_spam(db):
            stems.add(dh._stem(x["sample"]))
            hashes.add(bytes.fromhex(x["h"]))
        _dedup_ad_cache = (ck, stems, hashes)
        return stems, hashes
    except Exception:
        return set(), set()


def dedup_pkg_pair(folder, drop_pkg):
    """图包对比数据（A 级删除前的"肉眼复核"界面用）。

    为什么必须有这一步：A 级建议是**概率性**结论，以前在点一下就删的确认框里
    只有一行「与「X」重复 97%」的文字。用户真正要看的不是这个百分比，而是
    「删掉会损失什么」——所以这里把两侧的清单、代表图、独有文件都摆出来，
    让人先用眼睛比一遍再按键。
    """
    try:
        import dedup_verify as dv

        hit = None
        for d in (dedup_analyze_group(folder) or {}).get("pkg_drops", []):
            if d.get("pkg") == drop_pkg:
                hit = d
                break
        if not hit or not hit.get("peer"):
            return None
        r = dv.compare_pkgs(folder, drop_pkg, hit["peer"])
        if "error" in r:
            return r
        r["kind"] = hit.get("kind", "")
        r["rate"] = hit.get("rate", 0)
        return r
    except Exception:
        return None


def dedup_husk_groups(folder):
    """空壳包 / 残缺包 / 包内广告图（C 级）。

    与前两级的关系：A 级整包删的是"别处的副本"，B 级逐张裁的是"重复对"，
    这一级找的是**压根没有内容**的东西——同一个 pHash 撒在 ≥6 个包里的
    水印广告图，以及被它们（或其他原因）掏空的包。
    这类东西 A/B 都看不见：它们字节太小，算不进"重复体积"，
    却正是 A 级假阳性的来源（黏黏团子兔 22 个 1.5GB 大包被判互为副本，
    就是各包里那张 51KB 水印图被当成了共同内容）。
    """
    global _dedup_ad_cache
    try:
        import dedup_build as m
        import dedup_husk as dh

        db = m.get_db()
        row = db.execute(
            "SELECT COUNT(*), COALESCE(MAX(ts),0) FROM phash WHERE folder=?", (folder,)
        ).fetchone()
        ck = (row[0], row[1])
        hit = _dedup_husk_cache.get(folder)
        if hit and hit[0] == ck:
            return hit[1]
        stems, hashes = _dedup_ad_sets()
        husks, ads, shrunk = dh.find_husks(stems, [folder], db=db, hashes=hashes)
        r = {"husks": husks, "shrunk": shrunk, "ad_in_pkg": ads, "ad_stems": sorted(stems)}
        _dedup_husk_cache[folder] = (ck, r)
        return r
    except Exception:
        return None


_dim_cache = OrderedDict()
_dim_lock = threading.Lock()
_DIM_CACHE_MAX = 4096


def _image_dims(target):
    """原图宽高。`Image.open` 只读文件头、不解码像素（JPEG 上约 1–3ms），带 LRU 缓存。

    用途：预览已经够屏幕大时，前端就不必再拉原图，但"真实分辨率"仍然要显示得出来 ——
    所以单独开一个极轻的接口给尺寸，而不是为了两个数字去解码一张 91MB 的位图。
    """
    try:
        st = os.stat(target)
        key = (target, st.st_mtime_ns, st.st_size)
    except OSError:
        return None
    with _dim_lock:
        v = _dim_cache.get(key)
        if v is not None:
            _dim_cache.move_to_end(key)
            return v
    if not HAS_PIL:
        return None
    try:
        with Image.open(target) as im:
            v = (im.width, im.height)
    except Exception:
        return None
    with _dim_lock:
        _dim_cache[key] = v
        while len(_dim_cache) > _DIM_CACHE_MAX:
            _dim_cache.popitem(last=False)
    return v


def _clear_dedup_caches(folder):
    """删除后让该组的去重缓存失效。"""
    global _dedup_ad_cache
    _dedup_ana_cache.pop(folder, None)
    _dedup_pair_cache.pop(folder, None)
    _dedup_husk_cache.pop(folder, None)
    # 广告图名单是全库统计出来的，删掉一份就可能让它不再"撒在 >=6 个包"，
    # 留着旧名单会走到"降级信名字"那条路，宁可重算（0.6s）
    _dedup_ad_cache = None


def _purge_name(name: str):
    """删除某文件夹后清理所有缓存/状态。"""
    invalidate_file_caches(name)
    invalidate_scan_cache()
    db_delete_folder(name)
    st = load_state()
    if name in st:
        st.pop(name, None)
        save_state(st, immediate=True)


# 【钩子注册】gallery.remove 不 import 这两个函数（会形成循环），
# 由这里把实现注入过去。注册必须在模块初始化阶段完成，
# 否则 remove_folders 删完组不会清理 state —— 下次启动又会从 DB 里把已删的组读回来。
_remove.set_purge_hook(_purge_name)
_remove.set_dedup_clear_hook(_clear_dedup_caches)


# ============================ HTTP ============================
def _parse_range(header: str, fsize: int):
    """解析单段 Range，返回闭区间 (start, end)；非法或不可满足返回 None（调用方回 416）。

    支持 RFC 7233 的两种形式：
      * bytes=start-end / bytes=start-   从 start 开始
      * bytes=-suffix                    最后 suffix 个字节（历史上被误当成 bytes=0-suffix，
                                         实测返回的是开头而不是结尾，见 代码体检报告 B6）
    多段 Range（逗号分隔）只取第一段：浏览器对图片/视频不会发多段，近似足够。
    """
    if fsize <= 0:
        return None
    try:
        spec = header[6:].split(",", 1)[0].strip()
        if not spec:
            return None
        first, _, last = spec.partition("-")
        first, last = first.strip(), last.strip()
        if not first and not last:
            return None
        if not first:  # 后缀范围：bytes=-N → 最后 N 字节
            n = int(last)
            if n <= 0:
                return None
            n = min(n, fsize)
            return fsize - n, fsize - 1
        start = int(first)
        if start < 0 or start >= fsize:  # 起点越界 → 不可满足
            return None
        end = int(last) if last else fsize - 1
        if end < start:
            return None
        return start, min(end, fsize - 1)
    except (ValueError, AttributeError):
        return None


def log_line(msg):
    """把服务端异常落到文件。pythonw 是无窗口进程，不写文件就等于没有日志——
    "界面一直说断开"这种事发生后无从查证，只能靠猜。"""
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        if os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) > 4 * 1024**2:
            os.replace(LOG_PATH, LOG_PATH + ".1")  # 留一份上一代，不会无限涨
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write("[%s] %s\n" % (time.strftime("%F %T"), msg))
    except OSError:
        pass


# ---------- 删除日志 ----------
# ★ 为什么必须有：2026-10-17 那次误删 5,747 张，事后没有任何记录能回答
#   "删了哪些、什么时候删的、走的是 API 还是脚本"。回收站一旦被清空就彻底无从追溯。
# 设计要点：
#   · append-only 的单行 JSON —— 写成一行，崩在半路也只是最后一行残缺，前面的都还在
#   · 保持长开的句柄 + 行缓冲，避免每写一条都 open/close（批量删除时这是几千次系统调用）
#   · permanent=True 时额外 fsync —— 不可恢复的那种删除，宁可慢也不能丢


def _route_guard(fn):
    """把单个请求处理包起来：客户端断开静默；其余异常统一回 500 JSON，不刷堆栈、不重置连接。"""

    def wrapped(self, *a, **k):
        try:
            return fn(self, *a, **k)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return
        except Exception as e:  # noqa: BLE001 — 边界兜底，保证单请求异常不影响服务器与其它连接
            # 【必须记全堆栈】这里是全服务唯一的异常出口。只回 500 不落盘的话，
            # 前端看到的是"某个请求失败"，而真正的原因（哪一行、什么错）无从追查。
            log_line(
                "500 %s %s\n%s"
                % (getattr(self, "command", "?"), getattr(self, "path", "?"), traceback.format_exc())
            )
            try:
                self._send_json({"error": "internal", "detail": type(e).__name__}, 500)
            except Exception:
                pass

    return wrapped


SERVER_VERSION = "5.14"  # 模块级：ping 与静态页面注入都要用，不能只挂在 Handler 上


class Handler(BaseHTTPRequestHandler):
    server_version = "GalleryTool/" + SERVER_VERSION
    # HTTP/1.1 启用 keep-alive：图包墙/胶片一屏就是几十上百个缩略图，逐个新建 TCP 连接的
    # 开销在这个场景里很可观。代价是【每个响应都必须有正确的 Content-Length，或本身是无 body
    # 的 204/304】——下面的 send_response 分支已逐条核对过，漏一个客户端就会挂着等 body。
    protocol_version = "HTTP/1.1"
    # keep-alive 下每条连接会独占一个处理线程，线程在等"下一个请求"时是没有超时的
    # （StreamRequestHandler.timeout 默认 None → rfile.readline() 可无限阻塞）。
    # 于是浏览器崩溃/半开的连接会一直钉着线程不放。加超时让服务端主动回收：
    # 实测 8 条空闲连接 = +8 线程且只有客户端关闭才释放；设 timeout 后到点即被服务端断开。
    timeout = 60

    def log_message(self, fmt, *args):
        pass

    def _send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _etag_of(self, fsize, mtime_ns):
        return f'"{mtime_ns:x}-{fsize:x}"'

    def _not_modified(self, etag):
        self.send_response(304)
        self.send_header("ETag", etag)
        self.send_header("Cache-Control", "private, max-age=86400")
        self.end_headers()

    def _read_body(self, limit=8 * 1024 * 1024):
        """读 JSON 请求体。超限时不但不解析，还要标记连接不可复用 —— 否则 rfile 里
        残留的未读字节会被当成下一个请求，在 keep-alive 下污染整条连接。"""
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
        except (TypeError, ValueError):
            length = 0
        if length <= 0:
            return {}
        if length > limit:
            self.close_connection = True
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    # ---------- GET ----------
    @_route_guard
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)
        if path == "/api/ping":  # 极轻量在线探测，供前端断线检测轮询，不触发任何业务逻辑/锁
            # 版本号放**响应头**而不是 body：body 是探测用的 payload，
            # 不该被附加语义污染（前端有一处断言就是认 body 的）。
            # 用途：服务重启/升级后，还开着的旧页面跑的是旧 JS，
            # 用户点了新按钮只会"没反应"。靠这个版本号前端能自己发现并提示刷新。
            body = b"pong"
            self.send_response(200)
            # 【顺序】send_response 会重置 header 缓冲区，自定义头必须排在它**之后**，
            # 写在前头会被静默丢掉（发了但收不到，最难受的那种 bug）。
            self.send_header("X-Version", SERVER_VERSION)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            # 【一次性连接】ping 的唯一职责是回答"你还活着吗"。
            # 如果走 keep-alive，浏览器会从连接池里捞一条**已经失效**的空闲连接来复用
            # （服务重启时被 RST 的那些）——请求失败，但服务其实是好的，界面就永远
            # 显示"本地服务已断开"。而且刷新也救不回来：F5 复用同一个连接池。
            # 每次 ping 强制新建连接，才真实反映连通性，也让"重连"这件事真的能自愈。
            self.send_header("Connection", "close")
            self.close_connection = True
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/favicon.ico":  # 无图标，直接 204，避免浏览器反复报 404
            self.send_response(204)
            self.end_headers()
            return
        if path in ("/", "/index.html"):
            return self._serve_file(INDEX_PATH)
        if path in ("/survey", "/survey.html"):
            return self._serve_file(SURVEY_PATH)
        # 前端拆出来的 css/js。必须走独立路由：_serve_file 把 Content-Type
        # 写死成 text/html，还会对整份内容做版本号替换 —— 拿它发 .js 会 MIME 错、
        # 注释里若有 FE_VER_MARK 还会被静默改写。
        if path.startswith("/ui/"):
            return self._serve_static(path[4:])
        if path == "/api/survey/list":
            return self._send_json({"items": survey_overview(load_state())})
        if path == "/api/survey/samples":
            return self._handle_samples(qs)
        if path == "/api/warm/progress":
            return self._send_json(get_warmer().progress())
        if path == "/api/prewarm/progress":
            p = get_warmer().progress()
            # 建清单的线程可能已经结束，但 Warmer 队列还在排空 —— 这两种都算"还在忙"
            p["active"] = prewarm_active() or (p.get("queued") or 0) > 0
            return self._send_json(p)
        if path == "/api/thumb/stats":
            return self._send_json(thumb_cache_stats())
        if path == "/api/state":
            return self._send_json(
                {
                    "root": ROOT,
                    "folders": scan_root(),
                    "review": load_state(),
                    "thumb": HAS_PIL,
                    "version": "5.14",
                }
            )
        if path == "/api/files":
            folder = qs.get("folder", [""])[0]
            # 白名单先行：既挡越界读取，也挡"空 folder → base 变成 ROOT → 递归整库"这种
            # 一次请求就把机械盘占满几分钟的调用（体检报告 B2）。
            if not _is_known_group(folder):
                return self._send_json({"error": "unknown folder"}, 400)
            force = qs.get("refresh", ["0"])[0] in ("1", "true")
            files = list_media(folder, force=force)
            return self._send_json({"folder": folder, "total": len(files), "files": files})
        if path == "/api/dim":
            folder = qs.get("folder", [""])[0]
            if not _is_known_group(folder):
                return self._send_json({"error": "unknown folder"}, 400)
            target = safe_media_path(folder, qs.get("file", [""])[0])
            if not target:
                return self._send_json({"error": "not found"}, 404)
            d = _image_dims(target)
            if not d:
                return self._send_json({"error": "no dims"}, 404)
            return self._send_json({"folder": folder, "file": qs.get("file", [""])[0], "w": d[0], "h": d[1]})
        if path == "/api/dedup/status":
            return self._send_json(dedup_status())
        if path == "/api/dedup/group":
            folder = qs.get("folder", [""])[0]
            if not _is_known_group(folder):
                return self._send_json({"error": "unknown folder"}, 400)
            try:
                th = int(qs.get("th", [str(DEDUP_DEFAULT_TH)])[0])
            except ValueError:
                th = DEDUP_DEFAULT_TH
            th = max(0, min(th, 32))
            r = dedup_analyze_group(folder, th)
            if r is None:
                return self._send_json({"error": "no index for this folder"}, 404)
            return self._send_json(r)
        if path == "/api/dedup/pairs":
            folder = qs.get("folder", [""])[0]
            if not _is_known_group(folder):
                return self._send_json({"error": "unknown folder"}, 400)
            try:
                th = int(qs.get("th", [str(DEDUP_DEFAULT_TH)])[0])
            except ValueError:
                th = DEDUP_DEFAULT_TH
            th = max(0, min(th, 32))
            try:
                limit = max(0, int(qs.get("limit", ["0"])[0]))
            except ValueError:
                limit = 0
            r = dedup_pair_queue(folder, th, limit)
            if r is None:
                return self._send_json({"error": "no index for this folder"}, 404)
            return self._send_json(r)
        if path == "/api/dedup/pkgpair":
            folder = qs.get("folder", [""])[0]
            pkg = qs.get("pkg", [""])[0]
            if not _is_known_group(folder):
                return self._send_json({"error": "unknown folder"}, 400)
            if not isinstance(pkg, str) or not pkg:
                return self._send_json({"error": "no pkg"}, 400)
            r = dedup_pkg_pair(folder, pkg)
            if r is None:
                return self._send_json({"error": "这个图包没有对应的整包去重建议"}, 404)
            if "error" in r:
                return self._send_json(r, 400)
            return self._send_json(r)
        if path == "/api/dedup/husk":
            folder = qs.get("folder", [""])[0]
            if not _is_known_group(folder):
                return self._send_json({"error": "unknown folder"}, 400)
            r = dedup_husk_groups(folder)
            if r is None:
                return self._send_json({"error": "husk scan failed"}, 500)
            return self._send_json(r)
        if path == "/media":
            return self._serve_media(qs.get("folder", [""])[0], qs.get("file", [""])[0])
        if path == "/thumb":
            try:
                edge = int(qs.get("edge", [str(THUMB_LONG_EDGE)])[0])
            except ValueError:
                edge = THUMB_LONG_EDGE
            try:
                tq = int(qs.get("q", [str(THUMB_QUALITY)])[0])
            except ValueError:
                tq = THUMB_QUALITY
            return self._serve_thumb(qs.get("folder", [""])[0], qs.get("file", [""])[0], edge, tq)
        return self._send_json({"error": "not found"}, 404)

    def _handle_samples(self, qs):
        folder = qs.get("folder", [""])[0]
        if not _is_known_group(folder):
            return self._send_json({"error": "unknown folder"}, 400)
        try:
            n = int(qs.get("n", ["20"])[0])
        except ValueError:
            n = 20
        try:
            seed = int(qs.get("seed", ["0"])[0])
        except ValueError:
            seed = 0
        n = max(1, min(n, 200))
        exclude = [x for x in qs.get("exclude", [""])[0].split(",") if x][:600]
        return self._send_json(survey_samples(folder, n, seed, exclude))

    @_route_guard
    def do_HEAD(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        if parsed.path == "/media":
            return self._serve_media(qs.get("folder", [""])[0], qs.get("file", [""])[0], head=True)
        # 无 body 也必须显式声明 Content-Length: 0，否则 HTTP/1.1 keep-alive 下客户端会挂着等 body
        self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()

    # ---------- POST ----------
    # 只认本机访问。任何其它 Host 一律 403 —— 这一条同时挡住 DNS rebinding：
    # 攻击者域名先解析到 127.0.0.1 就能绕过同源，从而读走整个图库、再挨个删组。
    _ALLOWED_HOSTS = ("127.0.0.1", "localhost", "[::1]", "::1")

    def _reject(self, msg, code):
        body = json.dumps({"error": msg}).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    @_route_guard
    def do_POST(self):
        parsed = urlparse(self.path)
        # 【先读完 body 再校验】不读就发响应会让 keep-alive 连接错位，
        # 表现是"第一次报错、之后整个页面假死"。
        data = self._read_body()
        host = (self.headers.get("Host") or "").split(":")[0].strip().lower()
        if host not in self._ALLOWED_HOSTS:
            return self._reject("bad host", 403)
        # 跨站的简单请求只能发 text/plain 这类"安全列表"内的类型；
        # 强制 application/json 会让它们必须先预检，而本服务从不回 CORS 头 → 预检必失败。
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype != "application/json":
            return self._reject("content-type must be application/json", 415)
        if parsed.path == "/api/review/state":
            return self._post_state(data)
        if parsed.path == "/api/review/progress":
            return self._post_progress(data)
        if parsed.path == "/api/review/clear":
            save_state({}, immediate=True)
            return self._send_json({"ok": True})
        if parsed.path == "/api/rescan":
            invalidate_file_caches()
            folders = scan_root(force=True)
            return self._send_json({"ok": True, "folders": len(folders)})
        if parsed.path == "/api/warm":
            return self._post_warm(data)
        if parsed.path == "/api/prewarm":
            return self._post_prewarm(data)
        if parsed.path == "/api/prewarm/stop":
            prewarm_stop()
            return self._send_json({"ok": True})
        if parsed.path == "/api/thumb/gc":
            try:
                limit = int(data.get("limit", THUMB_CACHE_LIMIT))
            except (TypeError, ValueError):
                limit = THUMB_CACHE_LIMIT
            limit = max(256 * 1024**2, limit)  # 不允许把上限设到 256MB 以下
            res = thumb_cache_gc(limit)
            invalidate_thumb_stats()  # 文件数变了，统计缓存必须失效
            return self._send_json({"ok": True, **res})
        if parsed.path == "/api/dedup/build":
            return self._post_dedup_build(data)
        if parsed.path == "/api/trash":
            return self._post_remove(data, permanent=False)
        if parsed.path == "/api/delete":
            return self._post_remove(data, permanent=True)
        if parsed.path in ("/api/trash/pkg", "/api/delete/pkg"):
            return self._post_remove_pkg(data, parsed.path == "/api/delete/pkg")
        if parsed.path in ("/api/trash/file", "/api/delete/file"):
            return self._post_remove_file(data, parsed.path == "/api/delete/file")
        if parsed.path == "/api/dedup/husk/clear":
            return self._post_husk_clear(data)
        if parsed.path == "/api/dedup/invalidate":
            return self._post_dedup_invalidate(data)
        return self._send_json({"error": "not found"}, 404)

    def _post_dedup_invalidate(self, data):
        """批量删完文件后，让服务端忘掉所有基于旧文件的结论。

        为什么需要：批量裁决是脚本直接调 shell32 删的（8 千个文件走 HTTP
        太慢），服务端的内存缓存和 media 表都不知道这事。不失效的话，
        界面还会显示"这里有个副本"，点进去 404。
        """
        global _dedup_ad_cache
        folders = data.get("folders")
        if not isinstance(folders, list) or not folders:
            folders = None
        n = 0
        for c in (_dedup_ana_cache, _dedup_pair_cache, _dedup_husk_cache):
            if folders is None:
                n += len(c)
                c.clear()
            else:
                for f in folders:
                    if c.pop(f, None) is not None:
                        n += 1
        _dedup_ad_cache = None  # 广告图名单全库统计，一律重算
        # 【必须连 media 表一起清】批量删除是脚本直接删文件的，顶层组目录的
        # mtime 往往不变（删的是子目录里的东西），于是 `list_media` 的指纹
        # 判定"没变化"直接复用旧清单 —— 结果 /api/files 里全是幽灵文件，
        # 点开就是 404。实测回归里 HEAD /media 就是被这个打成 404 的。
        try:
            # media 表在 gallery.db，不是 dedup.db ——
            # 用 dedup_build.get_db() 会清错库，删了个寂寞。
            # 锁由 gallery.store 统一持有（单连接 + RLock），这里不用再管。
            _store.clear_media(folders)
        except Exception as e:
            log_line("invalidate 清 media 失败：%s" % e)
        for f in folders or []:
            try:
                invalidate_file_caches(f)
            except Exception:
                pass
        if folders is None:
            try:
                invalidate_file_caches()
            except Exception:
                pass
        try:
            invalidate_scan_cache()
        except Exception:
            pass
        return self._send_json({"ok": True, "cleared": n})

    def _post_husk_clear(self, data):
        return self._send_json(*_dedup_api.husk_clear(data))

    def _post_dedup_build(self, data):
        return self._send_json(*_dedup_api.build_index(data))

    def _post_remove_file(self, data, permanent: bool):
        return self._send_json(*_remove_api.remove_file_api(data, permanent))

    def _post_state(self, data):
        # 业务逻辑在 gallery/api/review.py（纯函数，可脱离 HTTP 单测），这里只做包装
        return self._send_json(*_review_api.set_state(data))

    def _post_progress(self, data):
        return self._send_json(*_review_api.set_progress(data))

    def _post_warm(self, data):
        return self._send_json(*_maint_api.warm(data))

    def _post_prewarm(self, data):
        return self._send_json(*_maint_api.prewarm(data))

    def _post_remove_pkg(self, data, permanent: bool):
        return self._send_json(*_remove_api.remove_pkg_api(data, permanent))

    def _post_remove(self, data, permanent: bool):
        return self._send_json(*_remove_api.remove_folders_api(data, permanent))

    def _serve_static(self, rel):
        """服务 ui/ 下的 css/js。只读、只允许白名单扩展名、只允许 TOOL_DIR/ui 内。

        路径校验放在这里而不是上提到 Handler：业务路由不该拿到"读任意文件"的能力。
        realpath + 前缀比较是必须的 —— /ui/../../review_state.json 能直接读走审查状态。
        """
        rel = rel.replace("\\", "/").lstrip("/")
        parts = rel.split("/")
        if not rel or any(p in ("", ".", "..") for p in parts) or ":" in rel or rel.startswith("/"):
            return self._send_json({"error": "bad path"}, 400)
        ctype = UI_CTYPE.get(os.path.splitext(rel)[1].lower())
        if not ctype:
            return self._send_json({"error": "bad type"}, 404)
        root = os.path.realpath(UI_DIR) + os.sep
        full = os.path.realpath(os.path.join(UI_DIR, rel))
        if not full.startswith(root):
            return self._send_json({"error": "bad path"}, 400)
        try:
            with open(full, "rb") as f:
                body = f.read()
        except OSError:
            return self._send_json({"error": "asset missing"}, 404)
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        # 和 HTML 同策略：改完刷新即生效。否则会出现"HTML 是新的、JS 还是旧的"。
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, path):
        try:
            with open(path, "rb") as f:
                body = f.read()
            # 把版本号注进页面：这样"这份 HTML 对应的版本"就写在页面里，
            # 前端拿它和 ping 返回的当前版本一比，就知道自己是不是旧的。
            # 比在 JS 里写死常量可靠 —— 写死就得靠人记得每次都同步改。
            if b"FE_VER_MARK" in body:
                body = body.replace(b"FE_VER_MARK", SERVER_VERSION.encode())
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        except OSError:
            self._send_json({"error": "page missing"}, 500)

    def _serve_thumb(self, folder, rel, edge=THUMB_LONG_EDGE, quality=THUMB_QUALITY):
        target = safe_media_path(folder, rel)
        if not target:
            return self._send_json({"error": "not found"}, 404)
        if os.path.splitext(target)[1].lower() not in IMG_EXT:
            return self._send_json({"error": "image only"}, 415)
        try:
            body, ctype = get_thumb_bytes(target, edge, quality)
        except Exception:
            # 单张图损坏/截断不该把请求打成 500（会让封面墙出现破图），退回灰块占位
            body, ctype = _placeholder_jpeg(), "image/jpeg"
        if not body:
            return self._send_json({"error": "thumb failed"}, 500)
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "private, max-age=604800")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _serve_media(self, folder, rel, head=False):
        target = safe_media_path(folder, rel)
        if not target:
            return self._send_json({"error": "file not found"}, 404)
        ext = os.path.splitext(target)[1].lower()
        if ext not in IMG_EXT:
            # 与 _serve_thumb 策略对齐：不再把任意类型的文件当媒体吐出去
            return self._send_json({"error": "image only"}, 415)
        ctype, _ = mimetypes.guess_type(target)
        if not ctype:
            ctype = "image/jpeg"
        try:
            st = os.stat(target)
        except OSError:
            return self._send_json({"error": "stat failed"}, 404)
        fsize = st.st_size
        etag = self._etag_of(fsize, st.st_mtime_ns)
        if self.headers.get("If-None-Match") == etag:
            return self._not_modified(etag)

        start, status = 0, 200
        length = fsize
        range_header = self.headers.get("Range")
        if range_header and range_header.startswith("bytes="):
            parsed = _parse_range(range_header, fsize)
            if parsed is None:  # 语法非法或不可满足 → 416（必须带 Content-Length）
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{fsize}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            start, end = parsed
            status = 206
            length = end - start + 1

        # 先开好文件再发响应头：文件可能在 stat 与 open 之间被外部删除/改名（这个图库常被
        # 手工整理），早开一步就能干净地回 404，而不是先承诺 200 + Content-Length 再吐 0 字节。
        fh = None
        if not head:
            try:
                fh = open(target, "rb")
            except OSError:
                return self._send_json({"error": "file not found"}, 404)
        try:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Accept-Ranges", "bytes")
            if status == 206:
                self.send_header("Content-Range", f"bytes {start}-{start + length - 1}/{fsize}")
            self.send_header("Content-Length", str(length))
            self.send_header("ETag", etag)
            self.send_header("Cache-Control", "private, max-age=86400")
            self.end_headers()
            if head:
                return
            # 响应头此时已经发出去了，这一段再出错绝不能"回头重发一个 200"（旧实现会写出两套
            # 响应头，在 keep-alive 连接上直接把下一个请求搞坏）。正确做法：标记连接不可复用后收工。
            try:
                with _disk_sem:
                    if start:
                        fh.seek(start)
                    remain = length
                    while remain > 0:
                        chunk = fh.read(min(1024 * 1024, remain))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remain -= len(chunk)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                self.close_connection = True
        finally:
            if fh is not None:  # HEAD 请求不会 open，别在这里抛 AttributeError
                try:
                    fh.close()
                except OSError:
                    pass


class GalleryHTTPServer(ThreadingHTTPServer):
    """本地单机服务：每请求一线程 + 足够的 accept backlog。
    浏览器会同时开 6~8 条 keep-alive 连接，默认 backlog 5 偏紧，容易出现连接排队。"""

    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 64


def _port_in_use(host="127.0.0.1", port=PORT):
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex((host, port)) == 0


def main():
    import argparse
    import webbrowser

    if "--build-index" in sys.argv[1:]:
        from dedup_build import main as build_index

        sys.argv.remove("--build-index")
        return build_index()

    # 【--port 必须真的被解析】原先只认 --no-open / --rescan，`gallery serve --port 9000`
    # 会静默无效 —— 用户以为换了端口，其实还是 8765，另一个服务却又起不来。
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("--rescan", action="store_true")
    a, _rest = ap.parse_known_args(sys.argv[1:])
    no_open = a.no_open
    force = a.rescan
    port = a.port
    url = f"http://127.0.0.1:{port}"
    # 注意签名的第一个参数是 host 不是 port，必须写关键字
    if _port_in_use(port=port):  # 已有实例在跑：不重复绑定、不报错，直接复用（可选帮打开浏览器）
        print(f"图库服务已在运行：{url}（跳过重复启动）")
        if not no_open:
            webbrowser.open(url)
        return
    os.makedirs(TOOL_DIR, exist_ok=True)
    if HAS_PIL:
        os.makedirs(THUMB_DIR, exist_ok=True)
    init_db()
    get_warmer()
    print("Scanning gallery folders (incremental via SQLite) ...")
    t0 = time.time()
    folders = scan_root(force=force)
    total = sum(f["size"] for f in folders)
    print(
        f"Done in {time.time() - t0:.2f}s: {len(folders)} folders, "
        f"total {total / 1024**3:.1f} GB | Pillow: {HAS_PIL}"
    )
    try:
        server = GalleryHTTPServer(("127.0.0.1", port), Handler)
    except OSError as e:
        print(f"端口 {PORT} 启动失败：{e}。若已有窗口在跑可直接访问 {url}，或结束旧进程后重试。")
        return
    print(f"Serving at {url}  (Ctrl+C to stop)")
    if not no_open:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        flush_state_on_exit()
        try:
            server.shutdown()
            server.server_close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
