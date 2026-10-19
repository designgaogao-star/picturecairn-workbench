# -*- coding: utf-8 -*-
"""维护接口：缩略图预热、索引构建、缓存失效。

这些操作共同点是**都很重**（扫目录、读原图、跑 pHash），所以一律异步：
接口只负责把任务塞进队列/线程，立刻返回，进度另开接口查。
"""

from gallery.config import SURVEY_EDGE, THUMB_EDGE_MAX, THUMB_LONG_EDGE
from gallery.guard import _is_known_group
from gallery.scan import scan_root
from gallery.thumbs import get_warmer, prewarm_start


def warm(data):
    """小批量预热（抽样页预热下一组）。幂等、可随时穿插。"""
    folder = data.get("folder", "")
    rels = data.get("rels", []) or []
    try:
        edge = int(data.get("edge", SURVEY_EDGE))
    except (TypeError, ValueError):
        edge = SURVEY_EDGE
    if not _is_known_group(folder) or not isinstance(rels, list):
        return {"error": "bad warm"}, 400
    added = get_warmer().enqueue(folder, rels[:200], edge=edge)
    return {"ok": True, "queued": added}, 200


def prewarm(data):
    """批量预热缩略图。

    默认生成 400px 封面（图包墙切换时会等的那个）。若带了 view_edge，则同一张原图
    再额外产出一份「单张看图用的预览尺寸」——只读一次原图，主要代价是多一次 JPEG 编码。
    只有 scope=group（量小）才允许带 view_edge：全量预热生成大预览要 8 小时以上，不值。
    """
    scope = data.get("scope", "group")
    try:
        edge = int(data.get("edge", THUMB_LONG_EDGE))
    except (TypeError, ValueError):
        edge = THUMB_LONG_EDGE
    edge = max(160, min(edge, THUMB_EDGE_MAX))
    try:
        view_edge = int(data.get("view_edge", 0) or 0)
    except (TypeError, ValueError):
        view_edge = 0
    if view_edge:
        view_edge = max(160, min(view_edge, THUMB_EDGE_MAX))

    if scope == "group":
        folder = data.get("folder", "")
        if not _is_known_group(folder):
            return {"error": "unknown folder"}, 400
        folders = [folder]
    elif scope == "unreviewed":
        view_edge = 0  # 全量预热不生成大预览
        from gallery_server import load_state

        st = load_state()
        folders = [
            f["name"] for f in scan_root() if st.get(f["name"], {}).get("state") not in ("kept", "marked")
        ]
    else:
        return {"error": "bad scope"}, 400

    if not folders:
        return {"error": "nothing to prewarm"}, 400
    n = prewarm_start(folders, scope, edge=edge, view_edge=view_edge)
    return {"ok": True, "groups": n, "scope": scope, "edge": edge, "view_edge": view_edge}, 200


def stop_prewarm():
    """取消正在跑的批量预热（连同队列一起清掉）。"""
    from gallery.thumbs import prewarm_stop as _ps

    _ps()
    return {"ok": True}, 200
