# GitHub 首次公开发布清单

Stillmark 当前是 Windows 本地开发预览。产品名称为 **Stillmark 影迹图片工作台**；本次包保留构建时的“开发预览（未发布）”元数据，以日期和源码摘要标识，Release 使用日期标签。稳定版本号、签名和自动更新另行验证。

## 当前已经具备

- [x] README、MIT LICENSE、第三方许可、贡献指南和安全说明。
- [x] Windows CI 与手工构建 workflow，均固定 Action 引用并使用临时图库。
- [x] 缺陷与功能建议模板，要求提供构建日期或源码摘要，不上传真实图库数据。
- [x] `scripts/build.ps1` 生成便携 ZIP、SHA-256、逐文件来源清单和许可清单。
- [x] 公开文件扫描器：`python scripts/public_release_check.py --json`。
- [x] 当前工作区没有发现个人路径、生成目录或依赖目录进入公开文件集合。
- [x] 当前开发包已完成实际 Electron 流程、图库管理、品牌和退出验证。
- [x] 本机候选包 `20261025-180752` 的 438 个产物和 ZIP 校验通过；GitHub 候选包改为 `20261025-115847`，来源与范围单列于 [Windows 包验收](github-preview-verification-20261025.md)，不混用两个包的摘要和运行记录。

## 发布前必须完成

- [x] 已创建公开仓库 [designgaogao-star/stillmark-workbench](https://github.com/designgaogao-star/stillmark-workbench)，origin 指向该仓库，main 为默认分支。
- [x] 已推送源码与文档，main 与 feat/backend-v2 内容一致；runtime.local.json、output/、build-out/、ui/dist/、依赖和用户数据不在提交中。API 上传造成的提交分叉已通过保留双方历史的合并消除，没有 force push。
- [x] 历史接手、Review、性能报告和设计阶段保留为历史证据；[文档导航](README.md) 区分当前使用指南与历史记录。本地输出和归档不随源码分发。
- [x] 提交 d3fb940 的 [main Windows 检查](https://github.com/designgaogao-star/stillmark-workbench/actions/runs/40197273329) 与 [开发分支检查](https://github.com/designgaogao-star/stillmark-workbench/actions/runs/40197271124) 均已通过。
- [x] ffadf60 的 [完整 Windows 包验收](https://github.com/designgaogao-star/stillmark-workbench/actions/runs/40191052297) 已成功；3600 秒、180 轮完成，原始进程和 renderer 时序复核通过。后续测试与文档更新未改变产品或构建运行代码。
- [x] GitHub 全新 Windows runner 验证实际便携包；本机在新目录解压同一 ZIP，440 个文件与原包完全匹配，首次启动、添加图库、GIF/WebP、删除确认、重启恢复与退出通过。两次未完成尝试及后续隔离验证记录见验收文档，不把复测通过描述为超时原因已解决。
- [x] 本机完整统一验证再次通过：111 项 Python、两项原生回收测试排除，126 项工作台及其余类型、构建、语法、品牌、退出、只读联调门槛均通过。日志为 output/quality/github-preview-final-20261025.log。
- [x] 当前开发预览包保持未签名，README 和随包说明已写明未知发布者提示、升级备份与回退方式；这不代表已发布二进制 Release。
- [x] 已将最终候选包的合成图片墙、深色查看器和窄屏截图加入 `docs/screenshots/`，附 SHA-256 来源记录并接入 README；截图不来自真实图库。
- [ ] 发布按日期标识的 GitHub 开发预览 Release，附件包含便携 ZIP、SHA-256、来源清单及去除本机路径的验收证据。

## 后续发行验证

- 稳定版版本号、签名、自动更新与更多 Windows 机器验证不在本次开发预览的已完成承诺中。
- 继续复现本机截图和重启等待的偶发超时，已有失败日志与页面状态采集；不把未确定原因的现象记为已修复。

## 品牌与外部事项

已保留 Stillmark 全称及同名风险记录。正式商标检索尚未开展；商业发行前应结合发行地区复核名称与权利范围，现有网页与竞品对照不能代替正式检索。这项外部工作不由本地自动检查器认证。

## 文件与历史检查范围

公开检查器检查当前文件集，不能认证整个 Git 历史。对 ffadf60 之前远程历史的 447 个文本 blob 补充扫描，未发现匹配的访问令牌或私钥；19 个旧 blob 含已从当前文件移除的本机路径。没有上传用户数据库或图片，不把“未发现凭据”写成全面安全保证，也未通过强制重写公开历史掩盖旧提交。

## 当前技术观察项

本机 040954 行为包与 GitHub 115847 候选包均完成 60 分钟负载；GitHub 原始时序中渲染器私有内存仍约 +1.122 MiB/分钟，JS 堆与句柄保持平稳。既有 90 轮 GIF/WebP 差分短测显示活跃图片资源有界；不能据此认定长期原生内存已经恒定。公开预览保留这一限制，并继续进行跨机器验证。

## 执行入口

```powershell
.venv/Scripts/python.exe scripts/public_release_check.py --json
pwsh -NoProfile -File scripts/build.ps1
pwsh -NoProfile -File scripts/verify.ps1 -Desktop <GalleryTool.exe绝对路径>
```

当前检查器的 `LOCAL_CHECK_PASS` 只表示工作区公开卫生通过；没有 Git remote 时会同时输出 `PUBLISH_BLOCKED_EXTERNAL_SETUP`，已有 remote 时输出 `EXTERNAL_CHECKS_REQUIRED`。脚本不联网，所以仓库是否存在、CI、签名和发布状态均为 null（未核实）；publish_ready 不能因配置 remote 就变为 true。它不会创建仓库、推送代码、创建 Release 或上传文件。
