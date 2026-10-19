# -*- coding: utf-8 -*-
"""扫描层：体积统计、指纹校验、媒体清单构建。

两个核心问题在这里解决：

**1. 启动要不要重扫？** —— `folder_fingerprint()` 只 stat 组下的**直接子项**
（名字 / 是否目录 / mtime_ns）。内层套图增删会更新其目录的 mtime，所以 O(顶层项)
就能感知变化。指纹和上次一致就直接用 SQLite，不再递归 21 万个文件（167 秒 → 0）。

**2. 清单从哪来？** —— `list_media()` 先看内存 LRU，再看指纹是否匹配 SQLite，
最后才回落磁盘遍历。两条路径的**排序规则必须一致**（`(album.lower(), rel.lower())`），
否则前端存的浏览下标会落到另一张图上。

并发控制：同一个组的首次建清单用 `locks.key_lock("files:"+folder)` 串行化。
大组在机械盘上是秒级到分钟级的随机寻道，两个并发请求各跑一遍纯属浪费。
"""

import hashlib
import os
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor

import pkgpath
from gallery import guard
from gallery import store as _store
from gallery.config import FILES_CACHE_MAX, IMG_EXT, SCAN_TTL
from gallery.fileio import atomic_write_json
from gallery.locks import key_lock
from gallery.paths import META_PATH, ROOT
from gallery.store import category_of

# scan_root 的短 TTL 缓存（force/删除时主动失效）
_scan_cache = {"at": 0.0, "result": None}
_scan_cache_lock = threading.Lock()

# 热文件夹媒体清单的内存 LRU
_files_cache = OrderedDict()
_files_cache_lock = threading.Lock()


# ---------------------------------------------------------------- 遍历
def walk_files(base):
    """深度优先递归产出 base 下所有文件的 DirEntry，容错跳过不可访问项。

    单一遍历实现，供体积统计（scan_one）与媒体清单构建（build_media_list）复用，
    避免两处各写一份递归 os.scandir。调用方对顺序不敏感（统计累加 / 清单最后统一排序）。
    """
    stack = [base]
    while stack:
        path = stack.pop()
        try:
            with os.scandir(path) as it:
                entries = list(it)
        except OSError:
            continue
        for e in entries:
            try:
                if e.is_dir(follow_symlinks=False):
                    stack.append(e.path)
                elif e.is_file(follow_symlinks=False):
                    yield e
            except OSError:
                continue


def scan_one(entry_path, name):
    """统计一个组的体积 / 文件数 / 媒体数。"""
    total = file_count = media_count = 0
    for e in walk_files(entry_path):
        file_count += 1
        try:
            total += e.stat(follow_symlinks=False).st_size
        except OSError:
            pass
        if os.path.splitext(e.name)[1].lower() in IMG_EXT:
            media_count += 1
    return {
        "name": name,
        "size": total,
        "file_count": file_count,
        "media_count": media_count,
        "category": category_of(name),
    }


def folder_fingerprint(folder):
    """只统计顶层直接子项（名字 / 是否目录 / mtime_ns）。

    内层套图增删会更新其目录 mtime，故 O(顶层项) 即可感知 —— 这是启动 0.23 秒的关键。
    返回 None 表示读不到（目录不存在/无权限），调用方会当作"必须重扫"。
    """
    base = os.path.join(ROOT, folder)
    items = []
    try:
        with os.scandir(base) as it:
            for e in it:
                if e.name.startswith("."):
                    continue
                try:
                    st = e.stat(follow_symlinks=False)
                    items.append((e.name, e.is_dir(follow_symlinks=False), st.st_mtime_ns))
                except OSError:
                    continue
    except OSError:
        return None
    items.sort()
    return hashlib.md5(repr(items).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- 清单
def build_media_list(folder):
    """从磁盘遍历出某组的媒体清单。慢，但只有指纹不匹配时才会走到。"""
    base = os.path.join(ROOT, folder)
    out = []
    if not os.path.isdir(base):
        return out
    for e in walk_files(base):
        ext = os.path.splitext(e.name)[1].lower()
        if ext not in IMG_EXT:
            continue
        try:
            size = e.stat(follow_symlinks=False).st_size
        except OSError:
            size = 0
        rel = os.path.relpath(e.path, base).replace("\\", "/")
        # 图包名的唯一定义在 pkgpath.py：索引(pkg 列) / 分析(判定单元) / 前端(标记键)
        # 三处共用同一份。粒度一不一致，待删标记就画不出来（v5.10 的教训）。
        album = pkgpath.album_of(rel)
        out.append({"rel": rel, "album": album, "kind": "image", "size": size})
    out.sort(key=lambda x: (x.get("album", "").lower(), x["rel"].lower()))
    return out


def list_media(folder, force=False):
    """取某组全部媒体。内存 LRU → 指纹匹配则走 SQLite → 否则磁盘遍历。"""
    with _files_cache_lock:
        if not force and folder in _files_cache:
            _files_cache.move_to_end(folder)
            return _files_cache[folder]

    with key_lock("files:" + folder):
        with _files_cache_lock:
            if not force and folder in _files_cache:
                _files_cache.move_to_end(folder)
                return _files_cache[folder]

        fp = folder_fingerprint(folder)
        out = None
        row = _store.folder_row(folder)
        # 必须 media 表里确实建过该 folder（行数>0）才算缓存命中；
        # 迁移来的元数据行 media 表为空，需首建
        if not force and row and row.get("fp") == fp and _store.media_count(folder) > 0:
            out = _store.all_media(folder)
        if out is None:
            out = build_media_list(folder)
            if row is None:  # 确保 folders 行存在再写 media
                _store.upsert_folder(
                    {
                        "name": folder,
                        "category": category_of(folder),
                        "size": 0,
                        "file_count": 0,
                        "media_count": len(out),
                        "fp": fp,
                    }
                )
            _store.replace_media(folder, out, fp, len(out))

        with _files_cache_lock:
            _files_cache[folder] = out
            _files_cache.move_to_end(folder)
            while len(_files_cache) > FILES_CACHE_MAX:
                _files_cache.popitem(last=False)
        return out


def invalidate_file_caches(folder=None):
    with _files_cache_lock:
        if folder:
            _files_cache.pop(folder, None)
        else:
            _files_cache.clear()


# ---------------------------------------------------------------- 顶层扫描
def invalidate_scan_cache():
    with _scan_cache_lock:
        _scan_cache["at"] = 0.0
        _scan_cache["result"] = None
    guard.invalidate_names()  # 组名缓存由 gallery.guard 持有


def scan_root(force=False):
    """增量扫描：顶层指纹未变直接用 SQLite 缓存；新增/变化项并行重扫；已消失项删库。

    结果带 SCAN_TTL 秒短缓存：/api/state、/api/survey/list 等高频接口在窗口内直接复用，
    不再每次都对全部顶层文件夹各 scandir 取指纹（机械盘上是数百次随机寻道）。
    force=True（手动重扫）绕过缓存；删除文件夹后由 _purge_name 主动失效。
    """
    now = time.time()
    if not force:
        with _scan_cache_lock:
            if _scan_cache["result"] is not None and now - _scan_cache["at"] < SCAN_TTL:
                return _scan_cache["result"]

    entries = guard._top_level_entries()
    actual = {n for _, n in entries}
    cached = {r["name"]: r for r in _store.all_folders()}
    # 库中已不存在于磁盘的文件夹（外部删除）
    for name in list(cached.keys()):
        if name not in actual:
            _store.delete_folder(name)
            cached.pop(name, None)

    todo, result, changed = [], [], []
    for path, name in entries:
        row = cached.get(name)
        fp = folder_fingerprint(name)
        if not force and row and row.get("fp") == fp and row.get("size"):
            result.append(
                {
                    "name": name,
                    "size": row["size"],
                    "file_count": row["file_count"],
                    "media_count": row["media_count"],
                    "category": row["category"],
                }
            )
        else:
            todo.append((path, name, fp))

    if todo:
        # 并发数刻意压到 4：F 盘是机械盘，12 路并发递归 scandir 会把随机寻道放大到极致。
        # 只读目录元数据，4 路已足够打满顺序带宽。
        with ThreadPoolExecutor(max_workers=4) as ex:
            futs = {ex.submit(scan_one, p, n): (n, fp) for p, n, fp in todo}
            for fu, (n, fp) in futs.items():
                try:
                    rec = fu.result()
                except Exception:
                    old = cached.get(n)
                    if old:  # 重扫失败则沿用旧值，避免丢数据
                        rec = {
                            "name": n,
                            "size": old["size"],
                            "file_count": old["file_count"],
                            "media_count": old["media_count"],
                            "category": old["category"],
                        }
                    else:
                        continue
                rec["fp"] = fp
                changed.append(rec)
                result.append(rec)
        _store.bulk_upsert_folders(changed)  # 单事务批量落库

    result.sort(key=lambda x: x["size"], reverse=True)
    # 同步一份人类可读 JSON 快照（便于排查/降级，不作为权威源）
    try:
        atomic_write_json(META_PATH, result)
    except OSError:
        pass
    with _scan_cache_lock:
        _scan_cache["at"] = time.time()
        _scan_cache["result"] = result
    return result
