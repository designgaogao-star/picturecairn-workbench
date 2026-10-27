# PictureCairn 长时间运行验证 · 2026-10-27

本轮目标是用临时图库和临时数据目录完成至少 8 小时的真实桌面混合浏览。测试不连接真实图库、不写真实数据库、不执行删除探针、不操作回收站；当前运行结束后只保留脱敏结果和失败现场路径。

## 运行配置

- 长测候选：`build-out/20261027-031047/GalleryTool/GalleryTool.exe`
- 当前最终候选：`build-out/20261027-062443/GalleryTool/GalleryTool.exe`
- 目标时长：480 分钟
- 负载：大目录分页滚动、普通图片查看、GIF/WebP 动画、抽样、相似分析、整包核验、扫描、缩略图预热、暂停/继续/取消
- 采样：所属 Electron/后端进程私有内存、RSS、句柄、线程和 IO；渲染器 JS 堆、DOM、请求数量、任务数量、缓存预算
- 通过线：沿用 `scripts/ui-qa/soak.mjs` 和 `scripts/ui-qa/audit_soak.py` 的既有阈值，不降低门槛，不把 preflight 当作长测通过

## 结果

长测目录为 `output/quality/soak-1793042145230/`。负载覆盖 `28800.02` 秒（480 分钟）和 1440 轮，页面错误为空，暂停／继续／取消控制均实际执行；`result.json` 的趋势检查为 `passed: true`。独立 `audit_soak.py` 复核通过：运行时长、连续阶段、首尾采样、任务终态、缓存预算和所有所属进程退出均满足门槛。尾段总私有内存斜率为 `0.698 MiB/分钟`，中位数变化 `13.66 MiB`；句柄斜率 `-0.159/分钟`，渲染器 JS 堆斜率 `-0.0038 MiB/分钟`。峰值采样总 RSS `1533.37 MiB`、总私有内存 `1589.78 MiB`，最大 DOM `616`，最大并发请求 `3`，缓存末值约 `37.6 MiB / 12 GiB`；最终任务为 `697 completed`、`80 cancelled`，没有失败任务。

自动化在完成运行断言后采集最终截图时超时，保留于 `failure.txt` 和 `failure.png`；审计按候选清单中的脚本哈希确认这是截图采集失败，不改变长测运行结论。审计器已修复为按代码顺序寻找时长断言，覆盖中间存在注释的实际脚本结构；对应 `tests/test_soak_audit.py` 回归通过。

## 关联回归

- 正式候选构建：`build-out/20261027-062443/`
- ZIP SHA-256：`5523018d8dba400dd00e45afa3bb09e24df8f554de9c9a6704d98fd2c08d10dc`
- Electron 集成回归：`output/ui-qa/integration-1793072129854/`
- 安装器视觉样机：[docs/design/installer/picturecairn-installer.html](design/installer/picturecairn-installer.html)
