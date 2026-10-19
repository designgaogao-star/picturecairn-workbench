# -*- coding: utf-8 -*-
"""路径校验：所有接受 folder / names / pkg / rel 的入口都必须先过这里。

为什么单独成模块：这是**删除前的最后一道闸门**。历史上踩过两次：
  · `os.path.join(ROOT, "C:\\\\x")` 在 Windows 上会丢弃 ROOT 前缀，
    于是 remove_folders 会对图库之外的目录执行删除；
  · `_pkg_dir` 用 `abspath`（字符串归一化）而不是 `realpath`，
    `pkg="..."` 被解析成"组目录本身"，一个"删图包"的请求能把整个组删掉。

这两条都有对应的单元测试（tests/test_guard.py），改这里请先跑 pytest。

**ROOT 动态读取**：本模块所有函数都用 `paths.ROOT`，不是 import 时的快照。
否则测试里 monkeypatch 换根之后，这里还在对着旧目录校验 —— 症状是"校验通过了但删错地方"。
"""

import os
import threading
import time

from gallery import paths

# ---- 顶层组名白名单：所有接受 folder / names 的入口都必须先过这里 ----
_TOP_NAMES_TTL = 0.5
_top_names_cache = {"at": 0.0, "names": frozenset()}
_top_names_lock = threading.Lock()


def _top_level_entries(root=None):
    root = root or paths.ROOT
    out = []
    try:
        with os.scandir(root) as it:
            for e in it:
                try:
                    # 跳过 "_" 与 "." 开头的条目：前者是工具目录自身，后者是工作区元数据目录
                    # （如 .workbuddy/.git/.venv），都不属于图库审查对象。
                    if e.is_dir(follow_symlinks=False) and not e.name.startswith(("_", ".")):
                        out.append((e.path, e.name))
                except OSError:
                    continue
    except OSError:
        return []
    return out


def invalidate_names():
    """清组名缓存。删除/新建顶层目录之后必须调，否则 0.5 秒内还会读到旧名单。"""
    with _top_names_lock:
        _top_names_cache["at"] = 0.0
        _top_names_cache["names"] = frozenset()


def _top_level_names(force=False, root=None):
    """当前 ROOT 下合法顶层组名的集合，带 0.5s 短缓存（避免每个缩略图请求都 scandir 一次）。"""
    now = time.time()
    if not force:
        with _top_names_lock:
            if _top_names_cache["names"] and now - _top_names_cache["at"] < _TOP_NAMES_TTL:
                return _top_names_cache["names"]
    names = frozenset(n for _, n in _top_level_entries(root))
    with _top_names_lock:
        _top_names_cache["at"] = time.time()
        _top_names_cache["names"] = names
    return names


def _is_known_group(name):
    """name 是否是当前 ROOT 下的真实顶层组。缓存未命中时强制刷新一次，避免 TTL 窗口内误拒新建的组。"""
    if not isinstance(name, str) or not name:
        return False
    if name in _top_level_names():
        return True
    return name in _top_level_names(force=True)


def _valid_group_name(name):
    """名字形态校验（与磁盘状态无关），用于给出更精确的拒绝原因。"""
    if not isinstance(name, str) or not name or name in (".", ".."):
        return False
    if any(c in name for c in '\\/:*?"<>|'):  # 含分隔符/盘符/保留字符 → 拒绝
        return False
    if name != name.strip() or name.endswith((".", " ")):  # Windows 目录名不允许以点或空格结尾
        return False
    return True


def safe_media_path(folder, rel, root=None):
    """把 (组名, 相对路径) 解析成磁盘上真实可读的文件路径；任何越界一律返回 None。

    三层校验，缺一不可：
      1) folder 必须是当前 ROOT 下的真实顶层组名（挡绝对路径 / ".." / 内部目录旁路）；
      2) base 必须仍在 ROOT 之内（双保险，防 realpath 意外解析到别处）；
      3) target 必须仍在 base 之内且是真实文件（挡 rel 里的 ".." 穿越）。
    """
    if not _is_known_group(folder):
        return None
    root_real = os.path.realpath(root or paths.ROOT)
    base = os.path.realpath(os.path.join(root_real, folder))
    if not base.startswith(root_real + os.sep):
        return None
    if not os.path.isdir(base):
        return None
    target = os.path.realpath(os.path.join(base, str(rel).replace("/", os.sep)))
    if target != base and not target.startswith(base + os.sep):
        return None
    if not os.path.isfile(target):
        return None
    return target


def _pkg_dir(folder, pkg, root=None):
    """把 (顶层组, 组内相对子目录) 解析成安全的绝对路径，任何可疑输入返回 None。

    图包级去重要删的是"组内的一个子目录"，比删顶层组更容易被路径穿越利用
    （pkg 来自前端，可以传 ../../..），所以每一段都单独校验，最后再用 commonpath 兜底。
    """
    if not (_valid_group_name(folder) and _is_known_group(folder)):
        return None
    if not isinstance(pkg, str) or not pkg:
        return None
    parts = pkg.replace("/", os.sep).split(os.sep)
    # 【点开头的段一律拒绝】只挡 "." 和 ".." 是不够的：Windows 的路径规范化
    # 把 "..." 也当成"上上级目录"。实测 pkg="..." 会解析到**组目录本身**，
    # 于是一个"删图包"的请求把整个组删掉了。凡是点开头就拒，不留例外。
    if any((not p) or p in (".", "..") or p.startswith(".") for p in parts):
        return None
    # 用 realpath 而不是 abspath：junction / 符号链接也要还原到真实位置再比
    base = os.path.realpath(os.path.join(root or paths.ROOT, folder))
    target = os.path.realpath(os.path.join(base, *parts))
    if target == base:
        return None
    try:
        if os.path.commonpath([base, target]) != base:
            return None
    except ValueError:  # 不同盘符（C: vs F:）会抛这个
        return None
    return target if os.path.isdir(target) else None
