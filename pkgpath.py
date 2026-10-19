# -*- coding: utf-8 -*-
"""图包名的唯一权威定义。零依赖（只 import os），谁都能安全地 import 它。

为什么要有这个文件
------------------
"这张图属于哪个图包"这个问题，曾经在三个文件里各写了一遍：
    gallery_server.py   → 前端 dedupMap 的键，用来画待删标记
    dedup_build.py      → 索引里存的 pkg 列
    dedup_analyze.py    → 图包级包含的判定单元
三处各自演化，v5.10 时终于对不上：索引存的是"完整相对路径 + 根散图叫 (根)"，
前端要的是"首段 + 空串"。后果是后端算出 28 个待删图包、前端一个标记都画不出来。

现在的规则（三处共用这一份）：
    图包名 = 组内相对路径的**首段**；组内根目录的散图 → ""（空串，不是"(根)"）
    例：Pure/Vol.264 [236P]/001.jpg  → ("Pure", "Vol.264 [236P]")
        Pure/001.jpg                 → ("Pure", "")     ← 根散图，删它等于动组根目录
"""

import os

ROOT = os.path.dirname(os.path.abspath(__file__))  # F:\图库\_gallery_tool
LIB_ROOT = os.path.dirname(ROOT)  # F:\图库


def pkg_of(abs_path, root=LIB_ROOT):
    """绝对路径 → (组名, 图包名)。"""
    rel = os.path.relpath(abs_path, root)
    parts = rel.replace("/", os.sep).split(os.sep)
    if len(parts) < 2:
        return parts[0], ""
    folder, rest = parts[0], parts[1:]
    # rest = ["子目录", "x.jpg"] → 图包名 = "子目录"
    # rest = ["x.jpg"]          → 组内根散图 → ""
    return folder, (rest[0] if len(rest) > 1 else "")


def album_of(rel_in_group):
    """组内相对路径 → 图包名。给已经拿到 rel 的调用方（服务端）用。"""
    rel = rel_in_group.replace("\\", "/")
    return rel.split("/", 1)[0] if "/" in rel else ""
