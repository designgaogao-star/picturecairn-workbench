# 图片加载流水线实施计划

**目标：** 缩短同卷预览的串行等待，让前台看图优先获得解码资源，并交付可复查的同素材性能对照。

**依据：** 用户已授权持续优化并要求继续。本会话顺序实施；设计见 ../specs/2026-10-22-loading-pipeline-design.md。

**架构：** 在现有 Images / Resources 边界拆分磁盘读取与编码阶段。资源预算不放大，HTTP 契约和缓存内容保持兼容。沿用 Python、Pillow、SQLite、pytest 和现有 Electron 验证入口。

## 1. 建立可复现基线

- [x] 新增 scripts/benchmark_pipeline.py：自行创建临时混合图库、动态端口和后端，采集冷派生缓存、并发、预热竞争、热缓存、RSS 与进程 IO；保存输出指纹。
- [x] 运行 `.venv/Scripts/python.exe -m scripts.benchmark_pipeline --source-parent output --output output/pipeline-before-fixed.json`，记录原实现；固定 ICC 日期以保证素材完全相同。
- [x] 新增 tests/test_loading.py：用线程事件复现编码占用源卷、等待解码占卷以及前后台资源顺序；原实现两个占卷测试失败，新版十项回归通过。

## 2. 拆分阶段并明确资源优先级

- [x] gallery/jobs.py 的 Resources.decode 增加 foreground 参数，登记前台等待者，在 finally 中归还等待计数和预算；保持原有默认后台调用兼容。
- [x] gallery/images.py 用 ExitStack 确保图像和预算按依赖顺序释放；图片头和首帧读取分别占用源卷，缩放编码在卷名额外执行。
- [x] gallery/dedup.py 在源卷名额外等待解码预算，再重新校验文件并按原规范计算 pHash。
- [x] 运行定向回归并核查异常、取消、透明度、方向与首帧；四轮测试 72 个输出完全相同，不变更 PIPELINE。

## 3. 对照与 Review

- [x] 运行相同基准，比较 source_manifest 和 output_sha256，记录延迟、吞吐与内存变化，不将派生缓存未命中称为绝对冷盘。交错顺序对照包含 git archive 导出的旧提交，未切换共享分支。
- [x] Review 资源获取顺序、退出清理、数据库与缓存兼容性；补齐编码失败和等待时文件变化回归，复现并修正暂停扣留预算与锁等待不可取消。
- [x] 更新 docs/architecture.md、docs/review-loading-20261022.md 及前端交接说明；按实际结果说明收益和限制。

## 4. 交付

- [x] pytest 68 项通过，两个真实回收站测试排除；Ruff、ui:check、ui:build、check 通过。契约内容未变。
- [x] 使用 `pwsh -NoProfile -File scripts/build.ps1` 构建；最终包 HTTP 五项通过，Electron 覆盖完整浏览、任务与重启；实际包同素材基准和索引副本启动复核完成。
- [x] 本轮修改提交到共享分支，未推送；本机启动入口切到 20261022-025843 包，正式索引 ready、无活动任务，原包和用户数据保留。
