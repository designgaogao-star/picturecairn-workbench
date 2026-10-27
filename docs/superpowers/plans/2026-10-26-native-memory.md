# 发布后原生图片内存调查

**当前执行边界：** 用户于后续回合要求停止无限扩展，本轮最晚北京时间 2026-10-26 14:15 交付，见 [收口清单](../../delivery-cutoff-20261026.md)。收完当前候选的默认两小时运行后，只做最终审计、review 和交付整理；下文未执行的原生等长控制与历史复现保留为后续调查，不再自动启动。

**目标：** 用已公开的同一实际 Electron 包，判断超过一小时后的资源增长是否趋于平台，并保留可复核的图片资源、DOM、内存与进程退出证据。

**边界：** 不改产品运行代码、不强制 GC、不注入内存压力、不清系统缓存；继续使用临时合成图库和独立数据目录。保留原六阶段负载、20 秒最短间隔、任务控制和增长门槛。代码与长测在当前共享分支执行。

## 假设与判别

1. 闲置图片缓存累积：Blink 图片 size／count 应与私有内存同步增长；若图片资源有界但私有内存继续上升，单一图片缓存解释不足。
2. 分配器保留高水位：DOM、JS 堆、图片资源有界，第二小时私有内存应趋于平台；若第二小时仍持续增长，不认为已经稳定。
3. 界面引用累积：DOM 节点、文档、监听器或 JS 堆应出现持续增长；这些指标平稳时，继续查原生角色和资源类别。
4. 自动化网络观测保留响应：已核对锁定的 Playwright 1.64.1，Chromium 会话调用 Network.enable，未显式指定响应缓冲上限。Electron 44.9.0 的 DEPS 指向 Chromium 152.0.7977.167，对应桌面实现默认总响应缓冲 200,000,000 bytes、单资源 20,000,000 bytes；重复 enable 会更新限制并回收超额响应。默认上限不代表本轮实际占用，根因仍须单变量控制验证。原两小时负载保持原设置。
5. 自动化请求元数据累积：同版本 `NetworkResourcesData::ResourceCreated` 按请求 ID 向 map 写入 ResourceData；`EvictContent` 与 `SetResourcesDataSizeLimits` 只回收正文，不删除请求元数据。`Clear` 在 Network.disable 或文档导航时清理该 map，而本负载使用同文档 hash 导航。故 1 MiB 正文上限不是整个网络观测器的内存上限，不能仅凭其结果排除所有观测开销；本轮没有直接测得 map 的项数或实际字节数。

## 实施与证据

- [x] 为 `scripts/ui-qa/soak.mjs` 增加 `--image-stats`。使用已有 `resource-stats.cjs` 的只读 getter；主进程以原始 getAppMetrics 读取数据，并单独计数产品路径的查询次数。观察器不增加回收、伪造内存值或改变图片请求。
- [x] 每轮 `renderer.jsonl` 加可选 imageResources：原生私有内存／工作集、产品查询次数、Blink 各资源类别、当前有 src 的图片数和采集耗时。run.json 和 result.json 明确标记该观测开关；默认检查不启用。
- [x] JS 语法、实际包六阶段预检与 `verify.ps1 -SkipUi` 通过；后者包含契约、严格类型、品牌／UI 构建、113 项 Python、Ruff、全部维护 JS 语法和图片预算策略。没有把跳过的完整 UI 场景当作本轮执行。预检六条样本已逐份复核，生产查询次数为 1／2／3／3／3／3，单次观测 1–4ms，所属进程均退出；此结果不作为长期通过证据。

```powershell
node --check scripts/ui-qa/soak.mjs
node scripts/ui-qa/soak.mjs --desktop build-out/20261025-164104/GalleryTool/GalleryTool.exe --minutes 120 --preflight --image-stats
pwsh -NoProfile -File scripts/verify.ps1 -SkipUi
```

- [x] 工程检查通过后，串行执行同一实际包的两小时负载，未同时运行性能对照或其他压力测试。完整运行 7200.012 秒、360 轮，原始退出码 1、passed=false：最后半小时总私有内存斜率 +2.31305 MiB/分钟，超过既定 2 MiB/分钟门槛。保留原始失败；完成本地失败现场核对，不把它标为通过的 runtime-audit。

```powershell
node scripts/ui-qa/soak.mjs --desktop build-out/20261025-164104/GalleryTool/GalleryTool.exe --minutes 120 --image-stats
```

- [x] 按前／后小时和最后半小时拆分各进程角色、Blink 图片、DOM、堆与查询次数；原始样本的最终重算存为 `window-observation-final.json`。渲染器在第二小时仍增长，见下表；默认观测两小时未通过，不以其他资源平稳代替此结论。
- [x] 默认两小时完成并核对后，对 `output/quality/soak-network-buffer-control.mjs` 做六阶段预检，随后完成一小时同负载对照和独立审计。唯一参数变化是原 Playwright 页面会话的 Network.maxTotalBufferSize 设为 1 MiB，单资源上限和产品代码不变；原负载、请求／任务检查及增长门槛保留。该脚本使用锁定 1.64.1 的私有会话定位，只用于忽略目录中的诊断，不进入产品或默认 CI。结果明确标为观测对照，不能替代原始默认运行。
- [ ] 只有证据支持运行代码缺陷时再构造对应失败回归并修改产品；届时另行构建和验收新包，不修改已经公开的 ZIP。

若正文上限对照结束后渲染器仍明显增长，下一步单独隔离整个 Network 观测代理：在同一页面会话停用 Network，以 Electron session.webRequest 的真实开始／完成／失败事件保留请求数量与超时检查。此项须另做六阶段预检，确认真实事件被记录、全部原门槛仍执行、页面操作与进程退出有效后，才可开展长测；不能让 CDP 停用后空的 page.on(request) 充当零并发证据。它是另一种观测方法的诊断对照，不改写当前默认运行或 1 MiB 正文控制的结果，暂不引入产品或默认 CI。

该条件对照为 `output/quality/soak-native-network-control.mjs`，六阶段预检已通过：10.967 秒，224 次真实开始、215 次完成、9 次失败／取消事件，全部阶段的 Inspector Network 请求事件为零；五个所属进程退出。复核为 `output/quality/native-memory-native-network-preflight-review-20261026.json`。随后请求两小时等长运行，输出 `output/quality/soak-1792978454466`；第 47 轮分析任务超过原有 120 秒门槛，退出码 1，没有完整两小时结果，详见下节。脚本要求原生记录必须出现真实开始与完成事件，同时监测原页面的 Network.requestWillBeSent，若代理意外重新启用则失败。请求仍执行原来的 16 项与 30 秒门槛，后台、缓存、时长、六阶段及内存／句柄门槛不变。

## 当前证据

- 已发布包的一小时原始时序重新按角色计算：后半小时渲染器 +1.06349 MiB/分钟，后端 −0.02097，GPU +0.00044，主进程 +0.00718。渲染器 JS 堆、节点、监听器、文档和资源数量没有同步持续增长；这削弱了常规界面引用累积的解释，尚不能证明具体原生根因。记录为 `output/quality/native-memory-baseline-review-20261026.json`。
- 观测预检为 `output/quality/soak-1792959538474`，六阶段 11.4 秒、全部退出；逐条复核另存 `output/quality/native-memory-preflight-review-20261026.json`。工程检查日志为 `output/quality/native-memory-source-checks-20261026.log`。
- 两小时正式负载已结束，输出 `output/quality/soak-1792959707007`，日志 `output/quality/native-memory-120min-20261026.log`。360 轮页面错误为零，临时数据库最终为 175 个完成、20 个取消任务，服务日志没有 ERROR；五个采样进程以及 Node 驱动、cmd 启动层均已按 PID／创建时间核对退出。`result.json` 和 `failure.txt` 保留内存门槛失败，独立现场核对为 `failure-forensic-audit.json`。
- 当前执行脚本已另存 `observed-soak-source.mjs`，SHA-256 为 `8980f0df4c35aac65a50e696d5ad9aa3425a496ca585d8dacd3730a1468ff57c`；原文件修改时间早于本轮启动，副本与现有脚本逐字节一致。观察报告单独保存，不改写原始 renderer.jsonl／processes.jsonl；读取运行中的文件时只排除未写完的末行，并明确记录是否排除。
- Chromium 版本、默认值与重复 enable 的实现均已对照对应版本源码，URL 和文件摘要存于 `output/quality/native-memory-observer-source-proof-20261026.json`。1 MiB 总缓冲的控制预检已通过：六阶段 10.897 秒，暂停／继续／取消覆盖完整，真实采样单次最长 3ms，五个所属进程退出；复核为 `native-memory-network-control-preflight-review-20261026.json`。一小时正式控制已完整结束，输出 `output/quality/soak-1792967057249`；run.json、结果、完整数据库与日志均由 audit_soak.py 独立复核通过，详见下节。

### 已完成的首小时观察窗口

这只是上述两小时运行中的完整首小时，不是两小时终态验收：180 轮、六阶段各 30 轮，页面错误为零。按 Electron 原生计数，渲染器私有内存斜率为 +1.8683 MiB/分钟；按阶段分别计算为 +1.7511～+2.0067 MiB/分钟，增长并非只来自某个页面占比变化。同期 JS 堆斜率 +0.00624 MiB/分钟，Blink 图片 −0.00958 MiB/分钟，中位数图片资源约 7.01 MiB。这些数据削弱了常规 JS 引用或单一图片缓存累积的解释，尚不能确认原生增长的根因。

原始首小时复核为 `output/quality/soak-1792959707007/first-hour-observation-review.json`。后续窗口分析用独立只读脚本 `output/quality/analyze-native-memory-windows.py`，按 run.json 的 started 与进程 UTC 对齐时间，逐项报告完整窗口、阶段、角色及末行是否完整；不修改原始记录或原有验收门槛。第二小时已在下节按终态重算，中间观察快照不代替最终结果。

### 默认两小时终态分项

| 完整窗口 | Electron 渲染器私有内存斜率 | 渲染器 JS 堆斜率 | Blink 图片资源斜率 |
| --- | ---: | ---: | ---: |
| 首小时 | +1.86829 MiB/分钟 | +0.00624 MiB/分钟 | −0.00958 MiB/分钟 |
| 第二小时 | +2.20236 MiB/分钟 | +0.00430 MiB/分钟 | −0.01659 MiB/分钟 |
| 最后半小时 | +2.12954 MiB/分钟 | +0.00302 MiB/分钟 | +0.00104 MiB/分钟 |

最后半小时独立进程计数的渲染器为 +2.18020 MiB/分钟，后端 −0.00464、GPU +0.10677、主进程 +0.03456、utility −0.00384，总量 +2.31305。两种原生读取均显示渲染器增长，第二小时没有证明平台。JS 堆和图片资源平稳只缩小调查范围，不能将默认观测失败改判为通过，也不能凭上游缓冲默认值断言具体占用。

### 1 MiB 正文缓冲控制终态

完整执行 3600.014 秒、180 轮，原门槛通过；独立审计覆盖 121 次进程采样、临时数据库、服务日志及五个所属进程退出，最终任务为 88 个完成、10 个取消。页面错误为零，最大实际 DOM 616、采样未完成请求最多一项。`runtime-audit.json` 记录 `runtime_passed=true`；此结果只属于标明诊断参数的控制。

| 相同第 30～60 分钟窗口 | 默认观测 | 1 MiB 正文控制 |
| --- | ---: | ---: |
| Electron 渲染器私有内存斜率 | +2.08579 MiB/分钟 | +1.04112 MiB/分钟 |
| 独立进程计数的渲染器斜率 | +2.12451 MiB/分钟 | +0.93136 MiB/分钟 |
| 总私有内存斜率 | +1.59674 MiB/分钟 | +0.39969 MiB/分钟 |
| 渲染器 JS 堆斜率 | +0.01087 MiB/分钟 | +0.00429 MiB/分钟 |

单次控制的增长明显减少，但渲染器仍持续上升，未证明平台；不能因此宣布产品无泄漏或根因唯一为正文缓冲。完整对照为 `output/quality/native-memory-buffer-control-comparison-final-20261026.json`，后续停用整个 Network 代理的等长控制继续调查元数据等观测开销。

### 独立审计时间覆盖修订

审计原先用进程采样器自身的 elapsed_seconds 与负载时长比较，忽略两者起点不同，也可能拒绝结束前一采样间隔内的有效记录。新增两条回归先失败：有效采样在旧断言被拒绝；采样器自身超过一小时但缺少实际负载末段时反而被接受。现按 run.json 的 started 与逐条 UTC 对齐，要求头尾采样分别覆盖首／末 30 秒区间、时间递增，完成检查点仍证明完整时长；报告新增起止偏移和最大采样间隔。原有内存、句柄、堆、任务、请求、失败例外和退出条件不变，也不改变默认两小时的失败结论。

全部九项审计回归通过，随后 `scripts/verify.ps1 -SkipUi` 通过：115 项 Python、两项原生回收排除、Ruff、契约、严格类型、品牌／UI 构建、维护 JS 语法与图片内存策略，日志为 `output/quality/native-memory-audit-checks-20261026.log`。本轮未将跳过的完整 UI 场景当作已执行。

### 原生请求控制失败及扫描范围回归

`soak-1792978454466` 最后完成样本为第 46 轮、936.356 秒。随后分析任务 `3a9e470044a74126951052a89d9ff6cf` 在原 120 秒等待线失败，没有完成检查点；失败现场为 `failure-task-audit.json`，完整临时服务日志另存 `retained-server.log`。退出时任务取消，最终 21 个完成、4 个取消，服务日志没有 ERROR，五个所属进程及 Node／cmd 均已退出。此轮不能作为两小时稳定性或 Network 代理归因的通过证据。

失败前的主机快照为 CPU 100%、可用内存 883.86 MiB；记录为 `output/quality/native-memory-native-control-host-snapshots-20261026.jsonl`。监控汇总曾超过工具单次等待而返回运行 session，原负载未因此重启；后续监控正确等待汇总命令完成。主机压力影响因果对照，不能仅凭这一轮的内存曲线判别代理作用。

分析任务进度超过 8200 个文件后，对 `Dedup.build → Indexer._scan` 找到独立可复现的范围错误：分组没有直接图片时，代码找不到该目录的非散图图包，退回全库；深层空目录同样扩大。新增 `tests/test_indexer_scope.py` 的三个真实索引／准备链路回归在旧实现全部失败，均因枚举无关目录而失败；祖先图包查询修复后全部通过。红／绿日志为 `output/quality/scoped-indexing-red-20261026.log` 与 `scoped-indexing-green-20261026.log`。

该修复是产品运行代码变化，按 [限定目录计划](2026-10-26-scoped-indexing.md) 另建候选并验证，不覆盖公开 ZIP，不将此范围错误自动认定为原生内存或所有历史超时的根因。当前完整工程检查为 117 项 Python 通过、握手 14.32 秒超原 10 秒门槛失败；现场 CPU 100%、可用内存 1372 MiB，全仓 Ruff 单独通过。新独立候选正在构建，尚未切换入口或发布。

后续加载性能比较以旧公开包与新候选为前后对照。若继续隔离 Network 代理对内存的影响，默认观测与原生请求控制须使用同一份新候选和相同负载／时长，不能把旧默认包与新代码控制的差异都归因于观测器。性能及内存负载串行执行，并保留主机环境范围和所有旧失败。

### 本轮终态与停止条件

用户随后要求停止无限扩项。新候选 `20261026-105024` 已完成完整统一检查、实际 Electron、扫描边界和同素材加载性能，详见 [候选验收与交付](../../candidate-verification-20261026.md)。此前“正在构建／完整检查失败”的记录为历史阶段，原失败保留。

默认观测 `soak-1792986769470` 完整执行 7200.021 秒／360 轮；末半小时总私有内存 +2.39308 MiB/分钟超过原 2 的门槛，结果仍为失败。页面错误为空，任务最终 175 个完成／20 个取消，服务没有 ERROR，五个采样进程均退出。原始结果、失败文件、保留服务日志和只读复核均在该输出目录；`audit_soak.py` 按原规则拒绝失败，没有写入通过的 runtime-audit。

最终 review 已完成，范围修复不自动解决长期内存。按 [交付收口](../../delivery-cutoff-20261026.md) 交付源码和开发候选，保留现行入口与公开包；本轮调查在此结束。原定 14:15 交付未达到，如实记录，不追加原生等长对照、历史 500 压力复现或新的优化任务。未来若另行立项，继续保留这些已知限制和原始失败。
