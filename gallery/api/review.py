# -*- coding: utf-8 -*-
"""审查状态接口：标记 kept / marked、保存浏览位置。

**这一层不碰 HTTP**：每个函数收 `data`（已解析的 JSON），返回 `(payload, status)`。
handler 只负责读 body、调这里、把结果写回响应。
好处是这些逻辑可以脱离服务直接单元测试，也不用为了测一个校验去起 HTTP。

状态本身存在 review_state.json（`load_state` / `save_state` 在 server 的状态层），
这里用延迟导入拿它们 —— 状态层依赖 store，本模块依赖状态层，顶层 import 会绕成环。
"""

import time

from gallery.guard import _is_known_group

VALID_STATES = ("marked", "kept", "none")


def _state_api():
    """延迟导入状态层（避免循环）。"""
    from gallery_server import load_state, save_state

    return load_state, save_state


def counts(st):
    """统计各状态数量。"""
    marked = sum(1 for v in st.values() if isinstance(v, dict) and v.get("state") == "marked")
    kept = sum(1 for v in st.values() if isinstance(v, dict) and v.get("state") == "kept")
    return {"marked": marked, "kept": kept}


def set_state(data):
    """设置某组的审查状态。返回 (payload, status)。"""
    name = data.get("name", "")
    new_state = data.get("state", "")
    if new_state not in VALID_STATES:
        return {"error": "bad state"}, 400
    load_state, save_state = _state_api()
    st = load_state()

    if new_state == "none":
        # 取消标记不产生新数据：即使组已不在磁盘上也允许，
        # 顺带清掉历史残留键（含 None 幽灵键）
        if isinstance(name, str) or name is None:
            st.pop(name, None)
            save_state(st)
        return {"ok": True, "counts": counts(st)}, 200

    # 打标记必须落在当前 ROOT 的真实顶层组上。少了这道，前端在"未选文件夹"时
    # 点按钮会传 name=null，落盘成 review_state.json 里的 "null" 假键并虚增计数。
    if not _is_known_group(name):
        return {"error": "unknown folder"}, 400

    rec = st.get(name, {"index": 0})
    rec["state"] = new_state
    rec["ts"] = int(time.time())
    st[name] = rec
    save_state(st)
    return {"ok": True, "counts": counts(st)}, 200


def set_progress(data):
    """保存浏览位置（当前看到第几张）。返回 (payload, status)。"""
    name = data.get("name", "")
    if not _is_known_group(name):
        return {"error": "unknown folder"}, 400
    try:
        idx = int(data.get("index", 0) or 0)
    except (TypeError, ValueError):
        idx = 0
    load_state, save_state = _state_api()
    st = load_state()
    rec = st.get(name, {})
    rec["index"] = max(0, idx)
    rec["ts"] = int(time.time())
    st[name] = rec
    save_state(st)
    return {"ok": True}, 200
