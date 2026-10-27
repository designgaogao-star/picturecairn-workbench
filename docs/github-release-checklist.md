# GitHub 首次公开发布清单

PictureCairn 当前是 Windows 本地开发预览。产品名称为 **PictureCairn 影标图片工作台**；源码和公开包使用这个名称。旧的 `preview-20261026-28faca1` 是品牌迁移前的 Stillmark 历史包。本次公开预览使用 `preview-20261027` 和源码摘要标识；稳定版本号、签名和自动更新另行验证。

## PictureCairn 开发预览 · 2026-10-27

- [x] 仓库改名为 `designgaogao-star/picturecairn-workbench`，旧地址保留重定向。
- [x] PictureCairn 品牌、正式前端和 Electron 桌面入口已接入。
- [x] `scripts/build.ps1` 生成的 438 个产物、来源清单、许可证和 SHA-256 已核对。
- [x] 实际 Electron 回归和 480 分钟临时图库长测通过，结果见 [开发预览说明](github-release-20261027.md) 和 [长测报告](long-run-verification-20261027.md)。
- [x] 日期型 GitHub Release：`preview-20261027`。

## 当前已经具备

- [x] README、MIT LICENSE、第三方许可、贡献指南和安全说明。
- [x] Windows CI 与手工构建 workflow，均固定 Action 引用并使用临时图库。
- [x] 缺陷与功能建议模板，要求提供构建日期或源码摘要，不上传真实图库数据。
- [x] `scripts/build.ps1` 生成便携 ZIP、SHA-256、逐文件来源清单和许可清单。
- [x] 公开文件扫描器：`python scripts/public_release_check.py --json`。
- [x] 当前工作区没有发现个人路径、生成目录或依赖目录进入公开文件集合。
- [x] 历史候选完成实际 Electron 流程、图库管理、品牌和退出验证；旧包的来源与运行范围保留于 [2026-10-25 记录](github-preview-verification-20261025.md)。
- [x] 本机历史候选 `20261025-180752` 的 438 个产物和 ZIP、GitHub 旧候选 `20261025-115847` 的 440 个产物已核验。公开包 `28faca1` 是 Stillmark 品牌下的历史包；其来源与观察项单列于 [本次验收](github-preview-verification-20261026.md)。PictureCairn 品牌候选单列于 [品牌接入记录](brand-integration-20261024.md)。

## 本次发布门槛（已完成）

[2026-10-26 Stillmark 开发预览](https://github.com/designgaogao-star/picturecairn-workbench/releases/tag/preview-20261026-28faca1) 已公开。它是品牌迁移前的历史包。历史 main 检查 40202393252 在重新添加图库后读取活动任务返回 HTTP 500，缺少异常堆栈；后续另已复现并修复 WAL 连接生命周期竞争，但尚未证明同根。缩略图状态竞争和在途分页失效也已确定性复现并修复，`28faca1` 的 main 与共享分支完整检查均通过。历史观察不因本次公开预览而关闭；当前 PictureCairn 预览见上方 2026-10-27 条目。

当前实际包验收 [40212772400](https://github.com/designgaogao-star/picturecairn-workbench/actions/runs/40212772400) 已成功；同一 ZIP 的来源、440 个产物、原始一小时采样与本机实际运行均已复核。默认启动十轮复验 [40220316275](https://github.com/designgaogao-star/picturecairn-workbench/actions/runs/40220316275) 与本机十轮成功，全部远程服务日志和 358 次请求已复核。QA 修正 `dd6d644` 的两路远程检查成功，旧草稿附件已替换；发布后匿名 API、校验文件、验收摘要与 ZIP 范围下载均通过。

- [x] 已创建公开仓库 [designgaogao-star/picturecairn-workbench](https://github.com/designgaogao-star/picturecairn-workbench)，origin 指向该仓库，main 为默认分支。
- [x] 已推送源码与文档，main 与 feat/backend-v2 内容一致；runtime.local.json、output/、build-out/、ui/dist/、依赖和用户数据不在提交中。API 上传造成的提交分叉已通过保留双方历史的合并消除，没有 force push。
- [x] 历史接手、Review、性能报告和设计阶段保留为历史证据；[文档导航](README.md) 区分当前使用指南与历史记录。本地输出和归档不随源码分发。
- [x] 提交 d3fb940 的 [main Windows 检查](https://github.com/designgaogao-star/picturecairn-workbench/actions/runs/40197273329) 与 [开发分支检查](https://github.com/designgaogao-star/picturecairn-workbench/actions/runs/40197271124) 均已通过。
- [x] 历史 ffadf60 的 [完整 Windows 包验收](https://github.com/designgaogao-star/picturecairn-workbench/actions/runs/40191052297) 已成功；3600 秒、180 轮完成，原始进程和 renderer 时序复核通过。该结果不证明后续运行代码修复已通过实际包验收。
- [x] GitHub 全新 Windows runner 验证实际便携包；本机在新目录解压同一 ZIP，440 个文件与原包完全匹配，首次启动、添加图库、GIF/WebP、删除确认、重启恢复与退出通过。两次未完成尝试及后续隔离验证记录见验收文档，不把复测通过描述为超时原因已解决。
- [x] 历史本机完整统一验证通过：111 项 Python、两项原生回收测试排除，126 项工作台及其余类型、构建、语法、品牌、退出、只读联调门槛均通过。日志为 output/quality/github-preview-final-20261025.log；当前 113 项验证另列于下方。
- [x] 当前开发预览包保持未签名，README 和随包说明已写明未知发布者提示、升级备份与回退方式；实际发布状态通过下方的匿名下载单独复核。
- [x] 已将最终候选包的合成图片墙、深色查看器和窄屏截图加入 `docs/screenshots/`，附 SHA-256 来源记录并接入 README；截图不来自真实图库。
- [x] `28faca1` 的 [main 完整检查](https://github.com/designgaogao-star/picturecairn-workbench/actions/runs/40212760133) 与 [共享分支检查](https://github.com/designgaogao-star/picturecairn-workbench/actions/runs/40212760158) 通过，保留原失败提示与重试断言；本机统一验证为 113 项 Python、14 项交互和 126 项工作台通过。
- [x] QA 测量修正提交 773b542 的 [main 检查](https://github.com/designgaogao-star/picturecairn-workbench/actions/runs/40218184742) 与 [共享分支检查](https://github.com/designgaogao-star/picturecairn-workbench/actions/runs/40218184013) 完整通过，运行代码与候选包保持一致。
- [x] 复核相同运行代码的默认启动十轮隔离业务及全部临时服务日志；本机与远程均通过，没有把未复现写成已查明历史 500 的根因。
- [x] 本次实际桌面包、完整一小时负载、原始采样与退出记录已核验；复核范围和未上传资料的边界见当前候选记录。
- [x] 下载本次包，核对 artifact 摘要、ZIP SHA-256、295 个来源与 440 个产物。本机隔离解压运行、重启和四项退出专项通过；阻塞退出约 2595ms，记录 shutdown-1792951749883。
- [x] 偏好保存改为真实界面操作后，源码五次／实际包五次重复退出与完整统一验证通过；`dd6d644` 的 main 40227232701 与共享分支 40227231836 成功。总第九次的历史退出超时保留，未查明根因。
- [x] 使用构建 20261025-164104 整体替换草稿附件、构建来源及脱敏验收摘要；四个附件的大小和 GitHub digest 与本地逐项一致，发布说明保留范围与观察项。
- [x] 公开按日期标识的开发预览 `preview-20261026-28faca1`，标签指向完整 `28faca1` 源码；未登录访问 API、校验文件与验收摘要成功，ZIP 范围请求返回 206 和正确文件签名。
- [x] 同一包复制到本机固定构建目录后，440 个产物校验和实际 Electron 全流程／重启通过，再更新本机桌面与后台启动路径；数据目录保持原值，没有启动真实数据或停止旧进程。

## 后续发行验证

- 稳定版版本号、签名、自动更新与更多 Windows 机器验证不在本次开发预览的已完成承诺中。
- 继续复现本机截图和重启等待的偶发超时，已有失败日志与页面状态采集；不把未确定原因的现象记为已修复。

## 品牌与外部事项

已保留 PictureCairn 全称及同名风险记录。公开 Release 的旧 Stillmark 名称只作为迁移历史保留，不再作为当前产品名。正式商标检索尚未开展；商业发行前应结合发行地区复核名称与权利范围，现有网页与竞品对照不能代替正式检索。这项外部工作不由本地自动检查器认证。

## 文件与历史检查范围

公开检查器检查当前文件集，不能认证整个 Git 历史。对 ffadf60 之前远程历史的 447 个文本 blob 补充扫描，未发现匹配的访问令牌或私钥；19 个旧 blob 含已从当前文件移除的本机路径。没有上传用户数据库或图片，不把“未发现凭据”写成全面安全保证，也未通过强制重写公开历史掩盖旧提交。

## 当前技术观察项

当前 GitHub 164104 候选包完成 60 分钟、180 轮负载，原始时序中总私有内存后半小时仍约 +1.058 MiB/分钟，JS 堆与句柄没有持续增长。既有 90 轮 GIF/WebP 差分短测显示活跃图片资源有界；不能据此认定长期原生内存已经恒定。公开预览保留这一限制，并继续进行跨机器验证。旧 040954 与 115847 包只作为历史对照。

发布后的本机默认观测已完整执行两小时／360 轮，末半小时总私有内存 +2.31305 MiB/分钟，超过原定门槛，结果保留为失败。1 MiB 自动化响应正文缓冲控制完成一小时／180 轮并通过独立审计，但渲染器仍增长；停用整个 Network 代理、以真实原生请求事件保留检查的控制在高负载期间因分析任务超时失败，未完成两小时。这些结果不改变公开 ZIP，长期稳定性仍待根因和终态证据，详见 [调查计划](superpowers/plans/2026-10-26-native-memory.md) 与 [原始交付核对](delivery-audit-20261026.md)。

限定目录扫描退回全库的独立缺陷已在源码修复，新增三条回归通过；新候选 105024 已通过完整统一检查、实际 Electron、8120 张无关图片的扫描边界及加载性能，公开预览未包含此项。首次 117 项通过与一次启动门槛失败保留；资源恢复后的完整重跑为 118 项 Python／126 项工作台通过。最终 review 已完成；候选两小时／360 轮的总私有内存末半小时 +2.39308 MiB/分钟，超原定 2 的门槛，审计没有将失败改成通过。本轮交付源码与开发候选，不替换公开 ZIP 或入口，远程检查未执行，详见 [候选验收与交付](candidate-verification-20261026.md)。

## 本轮源码同步准备 · 2026-10-26

在线核对时，公开仓库和首个开发预览均已存在；远程 `main` 与 `feat/backend-v2` 均指向 `20637e2`。本节准备同步此后的本地修复，不创建新产品版本、不替换公开二进制。

- [x] 本轮扫描修复、审计时钟修复与回归已完成 review，完整本机源码／实际包验证及长测失败结论见 [候选交付](candidate-verification-20261026.md)。
- [x] `git diff --check` 和工作区公开卫生检查通过，未包含用户数据、依赖、生成资源或构建包；本机候选文件以路径说明，避免在 GitHub 上产生缺失的下载链接。
- [ ] 将本轮源码、测试和必要文档提交到共享分支；当前仍为未提交改动，尚未推送。
- [ ] 推送后核对对应提交的 Windows CI；未执行前不得引用旧提交绿灯认证本轮。

两小时内存门槛未达标及历史异常根因未明的记录随源码公开。现有下载和本机入口保持原样；本次准备不启动新功能、长测或重构。

## 执行入口

```powershell
.venv/Scripts/python.exe scripts/public_release_check.py --json
pwsh -NoProfile -File scripts/build.ps1
pwsh -NoProfile -File scripts/verify.ps1 -Desktop <GalleryTool.exe绝对路径>
```

当前检查器的 `LOCAL_CHECK_PASS` 只表示工作区公开卫生通过；没有 Git remote 时会同时输出 `PUBLISH_BLOCKED_EXTERNAL_SETUP`，已有 remote 时输出 `EXTERNAL_CHECKS_REQUIRED`。脚本不联网，所以仓库是否存在、CI、签名和发布状态均为 null（未核实）；publish_ready 不能因配置 remote 就变为 true。它不会创建仓库、推送代码、创建 Release 或上传文件。
