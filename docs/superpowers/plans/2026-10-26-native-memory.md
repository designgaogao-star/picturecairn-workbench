# 发布后原生图片内存调查

**目标：** 用已公开的同一实际 Electron 包，判断超过一小时后的资源增长是否趋于平台，并保留可复核的图片资源、DOM、内存与进程退出证据。

**边界：** 不改产品运行代码、不强制 GC、不注入内存压力、不清系统缓存；继续使用临时合成图库和独立数据目录。保留原六阶段负载、20 秒最短间隔、任务控制和增长门槛。代码与长测在当前共享分支执行。

## 假设与判别

1. 闲置图片缓存累积：Blink 图片 size／count 应与私有内存同步增长；若图片资源有界但私有内存继续上升，单一图片缓存解释不足。
2. 分配器保留高水位：DOM、JS 堆、图片资源有界，第二小时私有内存应趋于平台；若第二小时仍持续增长，不认为已经稳定。
3. 界面引用累积：DOM 节点、文档、监听器或 JS 堆应出现持续增长；这些指标平稳时，继续查原生角色和资源类别。
4. 自动化网络观测保留响应：已核对锁定的 Playwright 1.64.1，Chromium 会话调用 Network.enable，未显式指定响应缓冲上限。若后续单变量限制观测缓冲使增长消失，才支持此解释；当前没有测到该缓冲的实际占用或默认上限，不能把它认定为根因。原两小时负载保持原设置，避免中途改变基线。

## 实施与证据

- [x] 为 `scripts/ui-qa/soak.mjs` 增加 `--image-stats`。使用已有 `resource-stats.cjs` 的只读 getter；主进程以原始 getAppMetrics 读取数据，并单独计数产品路径的查询次数。观察器不增加回收、伪造内存值或改变图片请求。
- [x] 每轮 `renderer.jsonl` 加可选 imageResources：原生私有内存／工作集、产品查询次数、Blink 各资源类别、当前有 src 的图片数和采集耗时。run.json 和 result.json 明确标记该观测开关；默认检查不启用。
- [x] JS 语法、实际包六阶段预检与 `verify.ps1 -SkipUi` 通过；后者包含契约、严格类型、品牌／UI 构建、113 项 Python、Ruff、全部维护 JS 语法和图片预算策略。没有把跳过的完整 UI 场景当作本轮执行。预检六条样本已逐份复核，生产查询次数为 1／2／3／3／3／3，单次观测 1–4ms，所属进程均退出；此结果不作为长期通过证据。

```powershell
node --check scripts/ui-qa/soak.mjs
node scripts/ui-qa/soak.mjs --desktop build-out/20261025-164104/GalleryTool/GalleryTool.exe --minutes 120 --preflight --image-stats
pwsh -NoProfile -File scripts/verify.ps1 -SkipUi
```

- [ ] 工程检查通过后，串行启动同一实际包的两小时负载，不同时运行性能对照或其他压力测试。保留本地 run.json、数据库和服务日志，完成后执行完整独立审计。

```powershell
node scripts/ui-qa/soak.mjs --desktop build-out/20261025-164104/GalleryTool/GalleryTool.exe --minutes 120 --image-stats
```

- [ ] 按前／后小时和最后半小时拆分各进程角色、Blink 图片、DOM、堆与查询次数；使用原始样本计算趋势，不用总进程趋势代替渲染器结论。结论明确区分通过、仍增长、未复现与证据缺失。
- [ ] 只有证据支持运行代码缺陷时再构造对应失败回归并修改产品；届时另行构建和验收新包，不修改已经公开的 ZIP。

## 当前证据

- 已发布包的一小时原始时序重新按角色计算：后半小时渲染器 +1.06349 MiB/分钟，后端 −0.02097，GPU +0.00044，主进程 +0.00718。渲染器 JS 堆、节点、监听器、文档和资源数量没有同步持续增长；这削弱了常规界面引用累积的解释，尚不能证明具体原生根因。记录为 `output/quality/native-memory-baseline-review-20261026.json`。
- 观测预检为 `output/quality/soak-1792959538474`，六阶段 11.4 秒、全部退出；逐条复核另存 `output/quality/native-memory-preflight-review-20261026.json`。工程检查日志为 `output/quality/native-memory-source-checks-20261026.log`。
- 两小时正式负载已启动，输出 `output/quality/soak-1792959707007`，日志 `output/quality/native-memory-120min-20261026.log`。当前只确认进程存活和已完成的首批样本；未取得终态，不能宣称两小时通过。接续状态与实际 PID／创建时间保存在忽略的 `output/quality/native-memory-active-20261026.json`。
- 当前执行脚本已另存 `observed-soak-source.mjs`，SHA-256 为 `8980f0df4c35aac65a50e696d5ad9aa3425a496ca585d8dacd3730a1468ff57c`；原文件修改时间早于本轮启动，副本与现有脚本逐字节一致。观察报告单独保存，不改写原始 renderer.jsonl／processes.jsonl；读取运行中的文件时只排除未写完的末行，并明确记录是否排除。
