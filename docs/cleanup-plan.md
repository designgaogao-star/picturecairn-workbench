# 纯图片项目清理执行计划

日期：2026-10-19。

目标：按用户要求完成接手、清理、review，再开始使用 Git。产品只处理图片，日常浏览优先，筛选和去重保留为辅助功能。

技术：Python 3.12、Pillow、NumPy、SciPy、SQLite，原生 HTML/CSS/JS，Electron。保留现有接口和数据库结构，减少兼容改动。

## 执行清单

- [x] 阅读当前源码、交接记录、接口和计划任务；确认服务在 127.0.0.1:8765 正常运行。
- [x] 运行原有单元测试：33 项通过。
- [x] 将清理前的源码、脚本、文档和配置压缩到项目外的本地备份目录。
- [x] 删除视频浏览和播放分支；图片扫描、SQLite 缓存读取、抽样、图包墙统一为图片。整包去重仍核验其他文件，防止忽略独有内容。
- [x] 删除无人调用的一次性整理、还原、批量删除和报告脚本，统一使用 gallery.paths，删除转发兼容文件和明确无用的代码。
- [x] 统一打包入口到 scripts/build.ps1；保留 scripts/gallery.spec，移除 electron-builder；补齐 Python 依赖和包发现配置，删除跳过后端构建的残缺路径。
- [x] 合并现行文档，记录纯图片范围、架构、开发和验证方法；历史性能测量保留为参考。
- [x] 用临时图片库验证文件扫描、已有数据库过滤、缩略图、图片读取、去重和删除闸门；57 项 pytest、静态检查及浏览器检查通过。
- [x] 构建并验证新的桌面产物，清理源码备份；旧构建因批量删除被策略拒绝，已移出项目归档。保留原图、cache、thumbs、review_state.json、folders_meta.json 和删除日志。
- [x] Review 清理后的代码和打包产物，修复发现的问题，记录验证结果和剩余限制。
- [x] 在 _gallery_tool 内初始化 Git，完善忽略规则，确认无用户数据和构建产物入库，提交首个基线版本。

## 验证命令

使用 C:\Users\79974\AppData\Local\Programs\Python\Python312\python.exe，避免 PATH 上其他 Python 环境。

```powershell
python -m pytest -q
python -m ruff check .
Get-ChildItem ui,electron -Filter *.js | ForEach-Object { node --check $_.FullName }
& .\scripts\build.ps1 -NoZip
```

集成测试使用临时图库和临时数据目录，不对真实图片执行删除。现有浏览器探针中依赖真实库、会改审查状态的步骤需先核对，不能把历史的 209 项通过记录当成本轮验证。

## 清理边界

不改操作系统计划任务，不导入外部图库，不重写界面，不替换 pHash 算法。删除前保留本地源码快照；Git 在清理和 review 完成后初始化。
