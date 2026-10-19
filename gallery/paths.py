# -*- coding: utf-8 -*-
"""全项目唯一的路径来源。零依赖，可以被任何模块安全地提前 import。

优先级（后者覆盖前者）：
    1. 默认：本文件所在目录的父目录的父目录当作「图库根」
    2. 环境变量 GALLERY_ROOT
    3. 命令行参数（由 cli 传入，最终也落到环境变量）

"""

import os
import sys

# 【打包后必须区分代码、资源和数据】
#   APP_DIR = 可执行程序目录
#   RES_DIR = 只读资源（ui/ 静态文件）→ PyInstaller 解压到 sys._MEIPASS
#   DATA_DIR = 可写数据（db / thumbs / 状态），可由 GALLERY_DATA 覆盖
# 如果把数据也放进 _MEIPASS，每次启动都是一个全新的临时目录：
# 索引、缩略图、审查进度全部丢失 —— 这是打包最容易犯的错。
_FROZEN = getattr(sys, "frozen", False)

if _FROZEN:
    APP_DIR = os.path.dirname(os.path.abspath(sys.executable))
    RES_DIR = getattr(sys, "_MEIPASS", APP_DIR)
else:
    # gallery/paths.py → 工具目录是它的父目录
    APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    RES_DIR = APP_DIR

# 历史名字，全项目都在用
TOOL_DIR = APP_DIR


def _default_root():
    """默认把「工具目录的父目录」当图库根。

    三种部署都成立：
      · F:\\图库\\_gallery_tool\\  → 根 = F:\\图库
      · ~/gallery/tool/           → 根 = ~/gallery
      · 打包分发后：exe 在 GalleryTool\\，根 = 它的父目录（用户自己挪到图库旁边即可）
    首选还是 `GALLERY_ROOT` 环境变量或首次启动时选的目录。
    """
    return os.path.dirname(APP_DIR)


ROOT = os.path.abspath(os.environ.get("GALLERY_ROOT") or _default_root())

# 【数据目录可以和代码目录分开】
# 装到 C:\Program Files\ 之后，exe 所在目录**没有写权限** ——
# 数据库、缩略图、审查状态全都写不进去，表现为"能打开但什么都记不住"。
# 所以打包版由 Electron 通过 GALLERY_DATA 把数据指到 %APPDATA%\GalleryTool。
# 开发态不设这个变量，仍然写在工具目录下（和以前一致）。
DATA_DIR = os.path.abspath(os.environ.get("GALLERY_DATA") or APP_DIR)

CACHE = os.path.join(DATA_DIR, "cache")
THUMB_DIR = os.path.join(DATA_DIR, "thumbs")
FILECACHE_DIR = os.path.join(CACHE, "files")
# ui/ 是**只读资源**：开发态和工具目录同级；打包后在 _MEIPASS 里
UI_DIR = os.path.join(RES_DIR, "ui")
# 页面模板同理（index.html / survey.html）
PAGE_DIR = RES_DIR

# 数据文件
GALLERY_DB = os.path.join(CACHE, "gallery.db")
DEDUP_DB = os.path.join(CACHE, "dedup.db")
DB_PATH = GALLERY_DB  # 旧名，gallery_server 里用这个
META_PATH = os.path.join(DATA_DIR, "folders_meta.json")
STATE_PATH = os.path.join(DATA_DIR, "review_state.json")
LEGACY_MARKS = os.path.join(DATA_DIR, "marks.json")
JOURNAL_PATH = os.path.join(CACHE, "delete_journal.jsonl")
LOG_PATH = os.path.join(CACHE, "server.log")

# 静态页面
INDEX_PATH = os.path.join(PAGE_DIR, "index.html")
SURVEY_PATH = os.path.join(PAGE_DIR, "survey.html")


def describe():
    return "root=%s\ntool=%s\ncache=%s" % (ROOT, TOOL_DIR, CACHE)


if __name__ == "__main__":
    print(describe())
