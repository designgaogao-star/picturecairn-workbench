# 前端集成验证

使用新建的临时图库与临时数据库，不依赖本机图库 ID，不连接既有服务，不操作回收站。截图及日志放在 `output/ui-qa/integration-<时间>/`；测试数据保留在输出提示的临时路径，便于失败后排查。

```powershell
# Windows 上使用已安装的 Microsoft Edge，不下载浏览器
npm run ui:qa

# 只验证只读请求入口，不启动浏览器
npm run ui:qa -- --api-only

# 对实际打包后端验证正式前端、只读开发模式和浏览流程
npm run ui:qa -- --backend <gallery_server.exe绝对路径>

# 启动实际桌面包，验证预载脚本、目录选择 IPC、正式前端和后端退出
npm run ui:qa -- --desktop <GalleryTool.exe绝对路径>

# 仅重跑图库管理与桌面重启场景（仍使用临时图库）
npm run ui:qa -- --libraries-only
npm run ui:qa -- --libraries-only --desktop <GalleryTool.exe绝对路径>

# 使用当前源码 Electron 主进程，仍启动独立临时后端和图库
npm run ui:qa -- --source-desktop
npm run ui:qa -- --source-desktop --libraries-only
```

需要项目依赖和已构建的 `ui/dist`；构建桌面只能用 `scripts/build.ps1`。`--backend` 和 `--desktop` 二选一。每轮自动挑选空闲端口，只结束本轮创建的进程。

源码桌面还需要先执行 `npm run brand:build`，生成 output/brand/runtime 的位图与 ICO；`--source-desktop` 不与 `--backend` 或 `--desktop` 同用。它用于 review 变更，不替代实际打包产物验收。

覆盖：开发只读模式全部非 GET 请求被拒绝、普通开发模式允许写请求、普通浏览器手工添加、目录选择成功/取消/异常、添加与扫描、图包和图片浏览、图包边界、浏览位置保存与刷新恢复、GIF/WebP 像素变化、后台任务、临时图片的逐项删除结果，以及 1440×1000 和 390×844 截图。

`libraries.mjs` 在同一隔离环境中检查图库改名、真实暂停任务阻止重连、取消后恢复输入、无效路径、根目录搬迁后的离线/重连、移出/重新添加及 ID/位置/标记/文件保留。图库管理阶段不请求文件删除端点，只移动本轮系统临时目录内的测试图库；桌面仍经过实际预载/IPC，系统目录对话框返回值受控。结果写入同轮 `library-lifecycle.json`。

Windows runner 的临时目录可能包含 `RUNNER~1` 这类短路径，或通过 junction 访问。图库管理测试在比对后端登记路径和检查临时目录范围前先用 `realpath()` 解析两端，避免将同一图库误判成尚未添加。使用 junction 作为 TEMP/TMP 执行完整 `run.mjs` 已复现并验证该场景。

`branding.mjs` 在同轮检查网页完整标题、应用内主题优先、朱色与转曲字标、真实 favicon、深浅启动页、390px 品牌区。Electron 另检查应用名／AppUserModelID、黑白 100/125/150/200% NativeImage 的真实像素与主题更新刷新托盘，共 17 项，浏览器为 13 项。系统对比度和 DPI 没有被全局修改；这些断言不声称在多台物理显示器上人工验收。结果为 `brand-verification.json`。

品牌截图使用 Playwright 的 animations: disabled，完成有限 CSS 过渡后再截取，避免把深浅主题切换中的灰色中间帧当作最终视觉。产品里的主题过渡保持原样。

截图阶段临时禁用 CSS 动画和过渡，再等待实际可见的列表骨架和缩略图就绪、图片透明度接近 1。可见性按 IntersectionObserver 判断，包含滚动容器裁剪；屏外懒加载项不作为等待条件。固定桌面场景额外断言图包八张图片全部解码并可见，动图仍单独检查真实像素变化。

主题无重取场景先等从窄屏返回桌面的六个封面全部就绪，再同时检查无缩略图请求和 Blob 地址不变，避免把窗口调整后尚未发出的懒加载请求误判为主题重取。

目录选择测试将 `dialog.showOpenDialog` 的返回值替换为受控结果，桌面模式仍经过正式预载脚本及 IPC；不声称自动点击过 Windows 原生对话框。浏览器模式使用同形状的 bridge 测试替身。

桌面流程另断言真实沙箱的 galleryImageResources.release 接口在首次启动和重启后均存在，观察完整业务流程中的内存预算 IPC 警告，并提交一次释放提示；记录在 image-memory-verification.json。提示只表示请求检查，不把固定等待时间视为异步回收已经完成的证明。原生内存是否稳定仍由实际桌面一小时进程采样验收。

image-lifecycle.mjs 在浏览器与桌面流程中阻塞本轮临时 GIF 的原图，保留静态占位层和待加载层的 DOM 引用，然后关闭查看器，断言两者的 src 均立即移除。它不强制 GC、不清原生缓存，验证解除引用的真实 UI 路径；失败及成功的 before／after 都写入 image-lifecycle-verification.json。旧实际包曾保留占位图地址，改用 ImageElement 后相同回归通过。

删除先验证默认回收方式与永久删除确认约束，随后仅显式永久删除本轮生成的临时图片。不能传入真实图库路径，也不支持复用真实数据库。

旧的 `%TEMP%/gallery-ui-qa/shoot/` 全量 QA 场景未整体迁入；本目录保存本轮工程收尾所需的独立回归，未携带旧 ID、数据副本或 `real.js`。

## 图片工作台回归

```powershell
node scripts/ui-qa/review-regressions.mjs
node scripts/ui-qa/desktop-shutdown.mjs
node scripts/ui-qa/desktop-shutdown.mjs --desktop <GalleryTool.exe绝对路径>
node scripts/ui-qa/workbench.mjs
node scripts/ui-qa/workbench.mjs --stage B --only
node scripts/ui-qa/workbench.mjs --stage C --only
node scripts/ui-qa/workbench.mjs --stage D --only
node scripts/ui-qa/workbench.mjs --stage E --only
```

`review-regressions.mjs` 不启动后端，所有图片 API 均由 Playwright 拦截。独立浏览器上下文覆盖桌面偏好迁移一次、刷新与首帧主题、Escape 层级、8120 张清单的墙面锚点与深链返回、无锚点时的继续位置，以及 1440/390 宽度的键盘跨页、末页、快速连按、选择和返回焦点；不访问任何用户数据。实际桌面偏好与 IPC 另用 `run.mjs --desktop` 验证。

列表修订回归额外模拟前置插入、删除和重排，验证焦点 ID 保持不变、方向键使用新索引、改变列数后仍能继续导航；另有缩略图迟到事件与在途分页失效的四个回归，共十四个独立场景。`desktop-shutdown.mjs` 使用全新空数据目录，不注册图库：正常保存偏好、模拟渲染线程阻塞四秒后检查超时结果未覆盖旧文件、恢复后正常保存，再阻塞八秒验证桌面及所属后端能提前退出。默认测试源码，`--desktop` 测试实际包；没有图片删除或回收请求。

图库生命周期的 `library-lifecycle.json` 保留最近 256 次请求的方法、路由、响应头与完整读取耗时。失败时通过独立 HTTP 客户端做一次一秒健康探测，然后仍抛出原请求失败；不替代请求、不增加重试、不放宽十秒门槛。`node scripts/ui-qa/run.mjs --trace-backend` 另在临时源码后端每两秒记录 Python 线程栈到 `backend-threads.log`，便于区分后端阻塞与客户端连接问题；只允许诊断源码后端，不影响实际桌面包和生产入口。手动多轮 CI 的追加业务流程启用该记录。

默认新建 8120 张大图包及格式、长名、同名图片、全部文件核验等夹具，动态启动隔离后端和 Vite，再用本机 Edge 无头验证。`--stage` 截止到指定阶段，`--only` 仅运行该阶段。C/E 单独运行时只生成 620 张大图包；B 仍验证 8120 张深页恢复。输出为 `output/ui-qa/workbench-<时间>/`，包括结果 JSON、截图以及失败现场。

桌面信息面板缩至窄屏时，媒体查询事件与前端渲染异步完成。QA 等待 `.inspector:modal`，不能把原本已经可见的桌面面板当成模式切换已完成；随后仍断言原生模态并检查 Escape。延迟媒体查询通知的隔离复现确认，旧即时读取会失败，实际模态最终正常。

部分删除失败通过 `lock_file.py` 持有生成的临时图片、不共享删除权限来验证，只显式永久删除临时文件。默认回收失败使用 HTTP 模拟，所有回收请求都由测试拦截。没有调用 Windows 回收站，也不清理既有数据。

```powershell
node scripts/ui-qa/performance.mjs <旧gallery_server.exe> <新gallery_server.exe>
```

性能对照使用同一份生成素材、相同视口、独立空数据与缓存目录以及新的浏览器上下文。记录已有索引就绪、实际图片墙和查看器可见时间 P50/P95、100 条图片清单、热缩略图、渲染器 GC 后 JS 堆。浏览器资源首取不等于物理磁盘冷读，脚本不清系统缓存，不以 JS 堆代替进程 RSS。后端负载、RSS 和进程 IO 另用 `python -m scripts.benchmark_pipeline` 测量。

```powershell
node scripts/ui-qa/desktop-performance.mjs <旧GalleryTool.exe> <新GalleryTool.exe>
```

该对照直接启动两个实际 Electron 包，串行使用同一份生成素材、1440×1000 视口与独立临时数据。先测 16 张图片的资源首取／热切换，再自然进出 GIF/WebP 各 90 次，测动画后首次重访及立即再次重热，保留逐图时间和原生内存。独立沙箱预载只读取 Blink 统计；主进程观测内存 API 的真实调用次数，返回值来自原始 API。只使用产品自身的资源策略，不额外强制 GC、注入压力或手工清缓存；确认所属后端随桌面退出。它不替代完整一小时长测，也不能与 Edge 脚本的绝对数值直接混合。不要与 soak 或其他性能负载同时运行。

## 统一检查与长期运行

```powershell
pwsh -NoProfile -File scripts/verify.ps1
pwsh -NoProfile -File scripts/verify.ps1 -Desktop <GalleryTool.exe绝对路径>
node scripts/ui-qa/soak.mjs --desktop <GalleryTool.exe绝对路径> --minutes 60
```

verify 默认执行 Python、Ruff、契约、UI 类型/构建、品牌转换、全部维护的 JS/MJS/CJS 语法检查、三个浏览器回归入口及桌面退出回归。`-SkipUi` 跳过这些源码 UI/桌面场景；`-Desktop` 另测实际产物与包内退出；加 `-SoakMinutes 60` 运行长测。两个原生回收站探针始终排除；临时文件的显式永久删除只在已有隔离回归中执行。

image-memory-policy.mjs 在 Node VM 中验证预算策略的合并、低占用保留缓存、超预算回收、冷却期和活跃大图余量；verify 已包含该检查。它不模拟真实浏览器的内存数值，也不能替代长测。诊断中手工 GC／压力通知只用于定位，不进入生产策略或正式 soak。

pytest 配置默认排除 `native_recycle` 标记，因此直接运行 `.venv/Scripts/python.exe -m pytest` 也不会触发这两项原生回收测试。只有显式选择该标记才会运行，不得在“不碰回收站”的任务中启用。

soak 只接受不少于 60 分钟的实际桌面测试。它在系统临时目录生成 8120 张大图包及混合格式图库、数据库和缓存，证据写入 output/quality；循环跨页滚动、快切、普通图片、GIF/WebP、抽样、分析、整包核验、扫描及预热任务控制。每轮即时写入渲染器 JS 堆、DOM、未完成请求、任务、缓存数据；process_metrics.py 每 30 秒采集所属 Electron/后端进程的 RSS、私有内存、句柄、线程及进程 IO。没有强制 GC，也不把进程 IO 等同于物理磁盘 IO。

后半小时通过线性斜率和前后半段中位数检查持续增长，阈值为全部所属进程私有内存 <2 MiB/分钟且中位数增量 <96 MiB、句柄 <2/分钟且增量 <100、JS 堆 <1 MiB/分钟且增量 <32 MiB。阈值是回归告警线，不替代时序数据 review。退出后按 PID 与创建时间核对所有采样进程均已结束；只结束本轮启动的进程。失败保留现场，修复运行时代码后需要重新计满 60 分钟。

`--preflight` 只快速执行六种负载场景，检查测试脚本与进程采集/退出能否正常运行，结果会明确标为 preflight，不能作为长期稳定性验收。

`python scripts/ui-qa/audit_soak.py <本轮输出目录>` 可只读复核完整采样、后半小时趋势、临时数据库最终任务状态、后端日志及所属进程退出，输出 runtime-audit.json。运行结论和截图采集结论分别保留；2026-10-23 一轮已满一小时的末尾截图超时，审计通过与构建清单匹配的执行脚本及失败位置确认所有运行断言已完成，不把原自动化退出码改成成功。后续脚本先写完整数据结果，再做最终截图，避免截图失败丢失已完成的运行证据。

20 秒是循环的最短间隔，不是每轮的最长允许时间；分析与核验等操作可能更长。审计核对至少一小时的完成检查点、连续轮次、六阶段顺序、递增时间和尾段覆盖，不要求理想情况下的固定 180 轮，并报告 `max_cycle_gap_seconds` 供人工复核。测试用一份含 200 秒额外等待、实际 171 轮的完整小时记录确认不会误报，同时拒绝缺轮、阶段错位、未满一小时和失败检查点。较长的间隔仍需结合进程／页面记录说明，不能据此宣称操作延迟良好。

## 远程偶发错误复现

Windows checks 的手动运行可选择 `integration_runs` 为 1、5 或 10。完整统一检查已含一轮业务流程，其余轮次继续执行现有 `run.mjs`；每轮独立创建临时图库和数据，首次失败停止，普通 push/PR 不重复运行。`run.mjs` 无论通过或失败都会保留临时服务日志；失败另外保存页面状态，所有记录进入 `isolated-ui-evidence` artifact，不上传真实数据。

例如在共享开发分支运行十轮：

```powershell
gh workflow run ci.yml --ref feat/backend-v2 -f integration_runs=10
```

重复通过只记录未复现，不能据此把原 HTTP 500 或未定位的超时标为已修复。

## 真实图库只读检查

`node scripts/ui-qa/inspect-live.mjs <后端地址> <非R18图包ID> [输出目录]` 只允许明确标记为非R18的分组，拦截全部非 GET，检查大图包顶部、中部、末页、刷新与窄屏锚点。默认输出为 output/playwright/live；截图会先禁用过渡、验证图片的 blur(32px)，再保存。不要把此入口用于 R18 内容，也不要提交输出数据。
