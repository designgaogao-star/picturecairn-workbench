# GalleryTool

本地图片浏览器，面向机械硬盘上的大型图片库。目录即图库，不联网、不上传。支持图包墙、单张查看、缩放、旋转、全屏和胶片条；筛选、抽样、去重及清理是辅助功能。

2026-10-19 确定产品只做图片，视频播放及相关计划已移除。支持 JPG、JPEG、PNG、GIF、WebP、BMP。

## 开发运行

需要 Python 3.9+、Node.js 和 Windows。后端依赖 Pillow、NumPy、SciPy，数据库使用 SQLite。前端为原生 HTML/CSS/JS，无前端构建步骤或 CDN。

```powershell
Set-Location F:\图库\_gallery_tool
python -m pip install -e ".[dev,desktop]"
npm ci
python gallery_cli.py info
python gallery_server.py --no-open
```

浏览器访问 http://127.0.0.1:8765。现有服务会复用端口；后端改动需要重启，前端改动刷新即可。

本机已验证的解释器是 `%LOCALAPPDATA%\Programs\Python\Python312\python.exe`。PATH 中可能有其他 Python，运行前确认已安装依赖。

启动 Electron：

```powershell
$env:GALLERY_PYTHON = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
npm start
```

也可使用根目录的 `启动图库预览.bat`、`后台启动图库.vbs`、`停止图库服务.bat`。窗口关闭后收进托盘，从托盘菜单退出应用。

## 数据位置

| 配置 | 默认值 | 用途 |
|---|---|---|
| `GALLERY_ROOT` | 项目目录的父目录 | 原始图片库 |
| `GALLERY_DATA` | 项目目录 | 可写数据目录 |
| 打包版数据目录 | `%APPDATA%\GalleryTool` | 由 Electron 设置 |

开发数据：`cache/gallery.db`、`cache/dedup.db`、`thumbs/`、`review_state.json`、`folders_meta.json`。删除日志是 `cache/delete_journal.jsonl`。这些都不是源码，不纳入 Git，也不随安装包分发。

打包版从 `%APPDATA%\GalleryTool\config.json` 读取根目录：

```json
{"root": "F:\\图库"}
```

## 构建桌面版

使用 PowerShell 7，所有构建统一走一个入口：

```powershell
npm run build
# 只生成可运行目录，不压缩：
& .\scripts\build.ps1 -NoZip
```

产物在 `build-out/<时间戳>/GalleryTool/GalleryTool.exe`，默认附带 zip。构建会同时打包当前 Python 后端与 Electron 壳，遇到失败查看同目录的 `build.log`。不再保留 electron-builder 或只输出前端的构建路径。

## 验证

```powershell
python -m pytest
python -m ruff check .
python -m ruff format --check .
```

自动测试使用合成图片和临时数据库，覆盖图片清单、旧库过滤、pHash、路径校验、HTTP 字节与缩略图、删除确认闸门和非图片内容保护。

`tests/api_regression.py`、`hardening_check.py`、`browser_probe.py`、`dedup_ui_probe.py` 和 `delete_path_check.py` 是既有人工集成探针，部分依赖本机图库，可能写浏览状态或操作测试组。日常回归优先使用 pytest；运行旧探针前先阅读各文件说明。

## 维护入口

```powershell
python gallery_cli.py dedup build-all --scope gap
python gallery_cli.py dedup report
python gallery_cli.py dedup clean
python dedup_analyze.py --help
python dedup_verify.py --help
```

所有图片格式判断来自 `gallery/config.py`，路径来自 `gallery/paths.py`。pHash 是相似度线索；整包对比还会核验其他文件，不能忽略包内独有内容。

项目结构见 [架构说明](docs/architecture.md)，产品方向见 [UX/UI 需求](UX-UI需求.md)，本轮进展见 [接手报告](接手报告.md) 和 [清理计划](docs/cleanup-plan.md)。历史性能测量保存在 `docs/reference/`。
