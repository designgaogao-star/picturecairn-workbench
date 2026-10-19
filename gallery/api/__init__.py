# -*- coding: utf-8 -*-
"""HTTP 接口的业务逻辑层。

**约定**：每个函数收 `data`（已解析的 JSON），返回 `(payload, status)`。
不碰 `self`、不写响应、不读 body —— 这样可以直接单元测试，也为将来换 HTTP 框架留了余地。

handler 层（`gallery_server.Handler`）只负责：
读 body → 调这里 → 把 `(payload, status)` 写回响应。
"""
