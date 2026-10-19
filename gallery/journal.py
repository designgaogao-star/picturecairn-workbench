# -*- coding: utf-8 -*-
"""删除日志：append-only 的 JSONL，记录"删了什么、什么时候、多大、走回收站还是永久"。

★ 为什么必须有：2026-10-17 那次误删 5,747 张，事后**没有任何记录**能回答
  "删了哪些、什么时候删的、走的是 API 还是脚本"。回收站一旦被清空就彻底无从追溯。

设计要点：
  · append-only 单行 JSON —— 崩在半路也只是最后一行残缺，前面的都还在
  · 保持长开的句柄 + 行缓冲，避免每写一条都 open/close（批量删除时是几千次系统调用）
  · permanent=True 时额外 fsync —— 不可恢复的那种删除，宁可慢也不能丢
  · **日志写失败绝不阻断删除**：日志是证据，不是前置条件。写失败转投 server.log 留痕。
"""

import json
import os
import threading
import time

from gallery.paths import JOURNAL_PATH

_f = None
_lock = threading.Lock()


def _log(msg):
    """延迟导入，避免和 gallery_server 形成循环依赖。"""
    try:
        from gallery_server import log_line

        log_line(msg)
    except Exception:
        pass


def write(op, permanent=False, **kw):
    """记录一次删除。op: file / pkg / group / husk-clear"""
    global _f
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "op": op, "permanent": bool(permanent)}
    rec.update(kw)
    try:
        line = json.dumps(rec, ensure_ascii=False)
    except (TypeError, ValueError):
        line = json.dumps(
            {"ts": rec["ts"], "op": op, "permanent": rec["permanent"], "note": "无法序列化的参数"},
            ensure_ascii=False,
        )
    try:
        with _lock:
            if _f is None:
                os.makedirs(os.path.dirname(JOURNAL_PATH), exist_ok=True)
                _f = open(JOURNAL_PATH, "a", encoding="utf-8", buffering=1)
            _f.write(line + "\n")
            if permanent:
                _f.flush()
                os.fsync(_f.fileno())
    except OSError as e:
        _log("删除日志写入失败：%s | 原始记录：%s" % (e, line[:300]))


def read(limit=500, tail=True):
    """读最近 N 条，给"删除记录"查看器用。返回 list[dict]，坏行跳过。"""
    out = []
    try:
        with open(JOURNAL_PATH, "r", encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    out.append(json.loads(ln))
                except ValueError:
                    continue  # 崩溃时留下的半行，跳过就好
    except OSError:
        return []
    return out[-limit:] if tail else out[:limit]


def stats():
    """给界面用的汇总：总条数、永久删除条数、总字节。"""
    rows = read(limit=10**9, tail=False)
    perm = [r for r in rows if r.get("permanent")]
    return {
        "total": len(rows),
        "permanent": len(perm),
        "bytes": sum(int(r.get("bytes") or 0) for r in rows),
        "last": rows[-1]["ts"] if rows else None,
    }
