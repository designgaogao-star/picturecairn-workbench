"""gallery-tool 的模块包。

拆包原则：**先抽无依赖的底层（paths / config），再抽上层（guard / delete / thumbs）。**
每一刀都必须能独立回滚 —— `gallery_server.py` 始终是可运行入口，
`python gallery_server.py` 在任何一步之后都还能起服务。

为什么不一次拆完 2,300 行：那等于重写，回归面从 0 放大到全量。
分步拆的好处是每一步都有明确的可验证边界（编译 + 141 条回归）。
"""

__version__ = "0.2.0"
