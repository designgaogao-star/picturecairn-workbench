# GitHub 首次公开发布清单

Stillmark 当前是 Windows 本地开发预览。产品名称为 **Stillmark 影迹图片工作台**；本次包保留构建时的“开发预览（未发布）”元数据，以日期和源码摘要标识，Release 使用日期标签。稳定版本号、签名和自动更新另行验证。

## 当前已经具备

- [x] README、MIT LICENSE、第三方许可、贡献指南和安全说明。
- [x] Windows CI 与手工构建 workflow，均固定 Action 引用并使用临时图库。
- [x] 缺陷与功能建议模板，要求提供构建日期或源码摘要，不上传真实图库数据。
- [x] `scripts/build.ps1` 生成便携 ZIP、SHA-256、逐文件来源清单和许可清单。
- [x] 公开文件扫描器：`python scripts/public_release_check.py --json`。
- [x] 当前工作区没有发现个人路径、生成目录或依赖目录进入公开文件集合。
- [x] 历史候选完成实际 Electron 流程、图库管理、品牌和退出验证；旧包的来源与运行范围保留于 [2026-10-25 记录](github-preview-verification-20261025.md)。
- [x] 本机历史候选 `20261025-180752` 的 438 个产物和 ZIP、GitHub 旧候选 `20261025-115847` 的 440 个产物已核验。当前候选改为含运行代码修复的 `28faca1`，来源与未完成事项单列于 [本次验收](github-preview-verification-20261026.md)。

## 发布前必须完成

当前发布保持草稿。历史 main 检查 40202393252 在重新添加图库后读取活动任务返回 HTTP 500，缺少异常堆栈；后续另已复现并修复 WAL 连接生命周期竞争，但尚未证明同根。缩略图状态竞争和在途分页失效也已确定性复现并修复，`28faca1` 的 main 与共享分支完整检查均通过。

当前实际包验收 [40212772400](https://github.com/designgaogao-star/stillmark-workbench/actions/runs/40212772400) 已成功；同一 ZIP 的来源、440 个产物、原始一小时采样与本机实际运行均已复核。默认启动十轮复验 [40220316275](https://github.com/designgaogao-star/stillmark-workbench/actions/runs/40220316275) 与本机十轮成功，全部远程服务日志和 358 次请求已复核。历史单次超时与 500 缺少根因证据，继续记录。当前还需确认退出专项修正的重复检查、统一验证与远程检查，并整体替换旧草稿附件。

- [x] 已创建公开仓库 [designgaogao-star/stillmark-workbench](https://github.com/designgaogao-star/stillmark-workbench)，origin 指向该仓库，main 为默认分支。
- [x] 已推送源码与文档，main 与 feat/backend-v2 内容一致；runtime.local.json、output/、build-out/、ui/dist/、依赖和用户数据不在提交中。API 上传造成的提交分叉已通过保留双方历史的合并消除，没有 force push。
- [x] 历史接手、Review、性能报告和设计阶段保留为历史证据；[文档导航](README.md) 区分当前使用指南与历史记录。本地输出和归档不随源码分发。
- [x] 提交 d3fb940 的 [main Windows 检查](https://github.com/designgaogao-star/stillmark-workbench/actions/runs/40197273329) 与 [开发分支检查](https://github.com/designgaogao-star/stillmark-workbench/actions/runs/40197271124) 均已通过。
- [x] 历史 ffadf60 的 [完整 Windows 包验收](https://github.com/designgaogao-star/stillmark-workbench/actions/runs/40191052297) 已成功；3600 秒、180 轮完成，原始进程和 renderer 时序复核通过。该结果不证明后续运行代码修复已通过实际包验收。
- [x] GitHub 全新 Windows runner 验证实际便携包；本机在新目录解压同一 ZIP，440 个文件与原包完全匹配，首次启动、添加图库、GIF/WebP、删除确认、重启恢复与退出通过。两次未完成尝试及后续隔离验证记录见验收文档，不把复测通过描述为超时原因已解决。
- [x] 本机完整统一验证再次通过：111 项 Python、两项原生回收测试排除，126 项工作台及其余类型、构建、语法、品牌、退出、只读联调门槛均通过。日志为 output/quality/github-preview-final-20261025.log。
- [x] 当前开发预览包保持未签名，README 和随包说明已写明未知发布者提示、升级备份与回退方式；这不代表已发布二进制 Release。
- [x] 已将最终候选包的合成图片墙、深色查看器和窄屏截图加入 `docs/screenshots/`，附 SHA-256 来源记录并接入 README；截图不来自真实图库。
- [x] `28faca1` 的 [main 完整检查](https://github.com/designgaogao-star/stillmark-workbench/actions/runs/40212760133) 与 [共享分支检查](https://github.com/designgaogao-star/stillmark-workbench/actions/runs/40212760158) 通过，保留原失败提示与重试断言；本机统一验证为 113 项 Python、14 项交互和 126 项工作台通过。
- [x] QA 测量修正提交 773b542 的 [main 检查](https://github.com/designgaogao-star/stillmark-workbench/actions/runs/40218184742) 与 [共享分支检查](https://github.com/designgaogao-star/stillmark-workbench/actions/runs/40218184013) 完整通过，运行代码与候选包保持一致。
- [x] 复核相同运行代码的默认启动十轮隔离业务及全部临时服务日志；本机与远程均通过，没有把未复现写成已查明历史 500 的根因。
- [x] 本次实际桌面包、完整一小时负载、原始采样与退出记录已核验；复核范围和未上传资料的边界见当前候选记录。
- [x] 下载本次包，核对 artifact 摘要、ZIP SHA-256、295 个来源与 440 个产物。本机隔离解压运行、重启和四项退出专项通过；阻塞退出约 2595ms，记录 shutdown-1792951749883。
- [ ] 偏好保存改为真实界面操作后，确认源码／实际包重复退出、完整统一验证和远程检查。总第九次的单次退出超时保留，失败阶段通过新增生命周期记录继续区分。
- [ ] 使用本次包整体替换草稿附件、构建来源及验收摘要；发布说明记录验证范围和剩余观察项。
- [ ] 发布按日期标识的 GitHub 开发预览 Release，附件包含便携 ZIP、SHA-256、来源清单及去除本机路径的验收证据。

## 后续发行验证

- 稳定版版本号、签名、自动更新与更多 Windows 机器验证不在本次开发预览的已完成承诺中。
- 继续复现本机截图和重启等待的偶发超时，已有失败日志与页面状态采集；不把未确定原因的现象记为已修复。

## 品牌与外部事项

已保留 Stillmark 全称及同名风险记录。正式商标检索尚未开展；商业发行前应结合发行地区复核名称与权利范围，现有网页与竞品对照不能代替正式检索。这项外部工作不由本地自动检查器认证。

## 文件与历史检查范围

公开检查器检查当前文件集，不能认证整个 Git 历史。对 ffadf60 之前远程历史的 447 个文本 blob 补充扫描，未发现匹配的访问令牌或私钥；19 个旧 blob 含已从当前文件移除的本机路径。没有上传用户数据库或图片，不把“未发现凭据”写成全面安全保证，也未通过强制重写公开历史掩盖旧提交。

## 当前技术观察项

当前 GitHub 164104 候选包完成 60 分钟、180 轮负载，原始时序中总私有内存后半小时仍约 +1.058 MiB/分钟，JS 堆与句柄没有持续增长。既有 90 轮 GIF/WebP 差分短测显示活跃图片资源有界；不能据此认定长期原生内存已经恒定。公开预览保留这一限制，并继续进行跨机器验证。旧 040954 与 115847 包只作为历史对照。

## 执行入口

```powershell
.venv/Scripts/python.exe scripts/public_release_check.py --json
pwsh -NoProfile -File scripts/build.ps1
pwsh -NoProfile -File scripts/verify.ps1 -Desktop <GalleryTool.exe绝对路径>
```

当前检查器的 `LOCAL_CHECK_PASS` 只表示工作区公开卫生通过；没有 Git remote 时会同时输出 `PUBLISH_BLOCKED_EXTERNAL_SETUP`，已有 remote 时输出 `EXTERNAL_CHECKS_REQUIRED`。脚本不联网，所以仓库是否存在、CI、签名和发布状态均为 null（未核实）；publish_ready 不能因配置 remote 就变为 true。它不会创建仓库、推送代码、创建 Release 或上传文件。
