# -*- coding: utf-8 -*-
"""原子写文件：先写 .tmp 再 os.replace。

为什么必须原子：审查状态（review_state.json）和体积快照（folders_meta.json）
都是"整份覆盖"写的。直接 open(path, "w") 写到一半断电/崩溃，文件就是半截 JSON，
下次启动解析失败 —— 表现为"进度全没了"。os.replace 在同一分区上是原子的。

keep_bak=True 时额外把上一版留成 .bak，读取端在主文件损坏时可以回退。
"""

import json
import os
import shutil


def atomic_write_json(path, obj, keep_bak=False):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    if keep_bak and os.path.exists(path):
        try:
            shutil.copy2(path, path + ".bak")
        except OSError:
            pass
    os.replace(tmp, path)
