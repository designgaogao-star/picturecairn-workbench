# -*- coding: utf-8 -*-
"""删除接口：组 / 图包 / 单文件，回收站与永久两档。

**永久删除的硬闸门**：必须显式带 `confirm_permanent: true`（前端二次确认后才会带）。
缺失或非布尔 True 一律拒绝 —— 防的是脚本 / 自动化 / 误调直接永久删数据。
这条纪律在三个粒度上完全一致，少一个都是漏洞。
"""

from gallery import remove as _remove
from gallery.guard import _is_known_group


def _need_confirm(data, permanent):
    """永久删除必须二次确认。返回错误响应或 None。"""
    if permanent and data.get("confirm_permanent") is not True:
        return ({"error": "permanent delete requires confirm_permanent=true after double-confirm"}, 400)
    return None


def remove_folders_api(data, permanent):
    """删顶层组（可批量）。"""
    bad = _need_confirm(data, permanent)
    if bad:
        return bad
    names = data.get("names", []) or []
    if not isinstance(names, list):
        return {"error": "bad names"}, 400
    names = [n for n in names if isinstance(n, str) and n]
    if not names:
        return {"error": "no names"}, 400
    names = names[:500]  # 单次批量上限，避免脚本一次塞进上万条
    results, freed = _remove.remove_folders(names, permanent)

    # 计数用 review.counts（和 /api/review/state 同一份统计口径）
    from gallery.api import review as _review
    from gallery_server import load_state

    return {
        "ok": True,
        "permanent": permanent,
        "freed": freed,
        "results": results,
        "counts": _review.counts(load_state()),
    }, 200


def remove_pkg_api(data, permanent):
    """删组内的一个图包子目录。"""
    bad = _need_confirm(data, permanent)
    if bad:
        return bad
    folder = data.get("folder", "")
    pkg = data.get("pkg", "")
    if not _is_known_group(folder):
        return {"error": "unknown folder"}, 400
    r = _remove.remove_pkg(folder, pkg, permanent)
    if not r.get("ok"):
        return {"error": r.get("error", "failed")}, 400
    return {"ok": True, "permanent": permanent, "path": r.get("path", "")}, 200


def remove_file_api(data, permanent):
    """删组内的单张图（重复对裁决用）。"""
    bad = _need_confirm(data, permanent)
    if bad:
        return bad
    folder = data.get("folder", "")
    rel = data.get("rel", "")
    if not isinstance(rel, str) or not rel:
        return {"error": "no rel"}, 400
    if not _is_known_group(folder):
        return {"error": "unknown folder"}, 400
    r = _remove.remove_media_file(folder, rel, permanent)
    if not r.get("ok"):
        return {"error": r.get("error", "failed")}, 400
    return {"ok": True, "permanent": permanent, "freed": r.get("freed", 0), "path": r.get("path", "")}, 200
