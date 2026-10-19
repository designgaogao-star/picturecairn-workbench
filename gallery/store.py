# -*- coding: utf-8 -*-
"""数据层：SQLite 的建表、迁移与读写。

只有两张表，职责很清楚：
  · `folders` —— 每个顶层组一行：分类、体积、文件数、媒体数、**顶层指纹**、更新时间
  · `media`   —— 每个媒体文件一行：(folder, rel) 主键，带 album 归属

**为什么 fingerprint 存在 folders 表里**：它决定下次启动要不要重扫这个组。
存下来之后，DB 与磁盘一致时启动只要 0.23 秒；不存就得每次递归 21 万个文件（167 秒）。

**排序规则必须与 `_build_media_list` 完全一致**（Python 的 `(album.lower(), rel.lower())`）。
曾经这里写 `ORDER BY album, rel`（SQLite 的 BINARY 排序，大小写敏感），
导致同一组走"磁盘扫描"和"DB 缓存"两条路径得到不同顺序 ——
而前端把列表下标存进 review_state.index，顺序一变，"上次看到第几张"就落到另一张图上。
那条评论留在 `all_media()` 里，别删。
"""

import os
import sqlite3
import threading
import time

from gallery.config import IMG_EXT
from gallery.paths import DB_PATH, META_PATH

_db = None
_lock = threading.RLock()

#: 老库迁移时用；由 init_db 调用方保证已就绪
_SCHEMA = """
CREATE TABLE IF NOT EXISTS folders(
    name TEXT PRIMARY KEY, category TEXT, size INTEGER,
    file_count INTEGER, media_count INTEGER, fp TEXT, updated INTEGER);
CREATE TABLE IF NOT EXISTS media(
    folder TEXT, rel TEXT, album TEXT, kind TEXT, size INTEGER,
    PRIMARY KEY(folder, rel)) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_media_folder ON media(folder);
"""


def category_of(name):
    """从组名前缀判分类。纯函数，无 IO。"""
    if not isinstance(name, str):
        return "其他"
    if name.startswith("[R16]"):
        return "R16"
    if name.startswith("[R18]"):
        return "R18"
    if name.startswith("[非R18]"):
        return "非R18"
    return "其他"


def init(path=None):
    """打开连接并建表。幂等 —— 多次调用只会复用同一个连接。"""
    global _db
    if _db is not None:
        return _db
    db_path = path or DB_PATH
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    _db = sqlite3.connect(db_path, check_same_thread=False)
    _db.row_factory = sqlite3.Row
    _db.execute("PRAGMA journal_mode=WAL")
    _db.execute("PRAGMA synchronous=NORMAL")
    _db.execute("PRAGMA temp_store=MEMORY")
    _db.executescript(_SCHEMA)
    _db.commit()
    _migrate_legacy()
    return _db


def conn():
    """拿连接（未初始化则初始化）。"""
    return _db if _db is not None else init()


def close():
    global _db
    if _db is not None:
        try:
            _db.close()
        except sqlite3.Error:
            pass
        _db = None


def _migrate_legacy():
    """首次（folders 表空）时把旧 folders_meta.json 导入，并补算顶层指纹。

    实现无感升级：老版本只有 JSON，没有 DB 指纹；不补的话升级后第一次启动会重扫全库。
    """
    db = conn()
    with _lock:
        cnt = db.execute("SELECT COUNT(*) c FROM folders").fetchone()["c"]
    if cnt or not os.path.exists(META_PATH):
        return
    try:
        import json

        with open(META_PATH, "r", encoding="utf-8") as f:
            legacy = json.load(f)
    except (OSError, ValueError):
        return
    # 延迟导入：fingerprint 属于扫描层，而扫描层要用本模块 → 不能顶层互相 import
    try:
        from gallery.scan import folder_fingerprint
    except Exception:

        def folder_fingerprint(_n):
            return None

    rows = []
    now = int(time.time())
    for it in legacy:
        name = it.get("name")
        if not name:
            continue
        rows.append(
            (
                name,
                it.get("category") or category_of(name),
                int(it.get("size", 0)),
                int(it.get("file_count", 0)),
                int(it.get("media_count", 0)),
                folder_fingerprint(name),
                now,
            )
        )
    with _lock:
        db.executemany("INSERT OR REPLACE INTO folders VALUES(?,?,?,?,?,?,?)", rows)
        db.commit()


# ---------------------------------------------------------------- folders
def folder_row(name):
    with _lock:
        r = conn().execute("SELECT * FROM folders WHERE name=?", (name,)).fetchone()
    return dict(r) if r else None


def upsert_folder(rec):
    with _lock:
        conn().execute(
            "INSERT OR REPLACE INTO folders VALUES(?,?,?,?,?,?,?)",
            (
                rec["name"],
                rec["category"],
                rec["size"],
                rec["file_count"],
                rec["media_count"],
                rec.get("fp"),
                int(time.time()),
            ),
        )
        conn().commit()


def bulk_upsert_folders(recs):
    """单事务批量写入，避免逐条 commit 的写入放大（WAL 下批量可快一到两个数量级）。"""
    if not recs:
        return
    now = int(time.time())
    rows = [
        (r["name"], r["category"], r["size"], r["file_count"], r["media_count"], r.get("fp"), now)
        for r in recs
    ]
    with _lock:
        conn().executemany("INSERT OR REPLACE INTO folders VALUES(?,?,?,?,?,?,?)", rows)
        conn().commit()


def delete_folder(name):
    with _lock:
        conn().execute("DELETE FROM folders WHERE name=?", (name,))
        conn().execute("DELETE FROM media WHERE folder=?", (name,))
        conn().commit()


def all_folders():
    with _lock:
        return [dict(r) for r in conn().execute("SELECT * FROM folders")]


# ---------------------------------------------------------------- media
def replace_media(folder, files, fp, media_count):
    with _lock:
        c = conn()
        c.execute("DELETE FROM media WHERE folder=?", (folder,))
        c.executemany(
            "INSERT OR REPLACE INTO media(folder,rel,album,kind,size) VALUES(?,?,?,?,?)",
            ((folder, x["rel"], x.get("album", ""), x["kind"], x["size"]) for x in files),
        )
        c.execute("UPDATE folders SET fp=?, media_count=? WHERE name=?", (fp, media_count, folder))
        c.commit()


def clear_media(folders=None):
    """清掉 media 表（或指定的几个组）。

    为什么删除后必须清：批量删除是脚本直接删文件的，**顶层组目录的 mtime 往往不变**
    （删的是子目录里的东西），于是 `list_media` 的指纹判定"没变化"直接复用旧清单 ——
    结果 /api/files 里全是幽灵文件，点开就是 404。
    """
    with _lock:
        c = conn()
        if folders is None:
            c.execute("DELETE FROM media")
        else:
            for f in folders:
                c.execute("DELETE FROM media WHERE folder=?", (f,))
        c.commit()


def media_count(folder):
    with _lock:
        return (
            conn()
            .execute("SELECT COUNT(*) c FROM media WHERE folder=? AND kind='image'", (folder,))
            .fetchone()["c"]
        )


def all_media(folder):
    """取某组全部媒体，**用 Python 排序**，与 `_build_media_list` 保持一致。

    别改成 ORDER BY：SQLite 的 BINARY 排序大小写敏感，
    两条路径顺序不同会让"上次看到第几张"落到别的图上。
    """
    with _lock:
        rows = (
            conn()
            .execute("SELECT rel,album,kind,size FROM media WHERE folder=? AND kind='image'", (folder,))
            .fetchall()
        )
    rows = sorted(rows, key=lambda r: (str(r["album"]).lower(), str(r["rel"]).lower()))
    return [
        {"rel": r["rel"], "album": r["album"], "kind": r["kind"], "size": r["size"]}
        for r in rows
        if os.path.splitext(r["rel"])[1].lower() in IMG_EXT
    ]
