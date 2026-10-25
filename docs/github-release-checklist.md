# GitHub 首次公开发布清单

Stillmark 当前是 Windows 本地开发预览。首次公开发布前，产品名称保持为 **Stillmark 影迹图片工作台**，包保持“开发预览（未发布）”文案；正式版本号、Release 标签和签名在仓库公开后再决定。

## 当前已经具备

- [x] README、MIT LICENSE、第三方许可、贡献指南和安全说明。
- [x] Windows CI 与手工构建 workflow，均固定 Action 引用并使用临时图库。
- [x] 缺陷与功能建议模板，要求提供构建日期或源码摘要，不上传真实图库数据。
- [x] `scripts/build.ps1` 生成便携 ZIP、SHA-256、逐文件来源清单和许可清单。
- [x] 公开文件扫描器：`python scripts/public_release_check.py --json`。
- [x] 当前工作区没有发现个人路径、生成目录或依赖目录进入公开文件集合。
- [x] 当前开发包已完成实际 Electron 流程、图库管理、品牌和退出验证。
- [x] 当前开发候选包为 `build-out/20261025-180752/GalleryTool/GalleryTool.exe`；438 个产物和 ZIP 校验通过，公开卫生检查输出 `LOCAL_CHECK_PASS`。

## 发布前必须完成

- [x] 已创建公开仓库 [designgaogao-star/stillmark-workbench](https://github.com/designgaogao-star/stillmark-workbench)，origin 指向该仓库，main 为默认分支。
- [x] 已推送源码与文档，main 与 feat/backend-v2 内容一致；runtime.local.json、output/、build-out/、ui/dist/、依赖和用户数据不在提交中。API 上传造成的提交分叉已通过保留双方历史的合并消除，没有 force push。
- [x] 历史接手、Review、性能报告和设计阶段保留为历史证据；[文档导航](README.md) 区分当前使用指南与历史记录。本地输出和归档不随源码分发。
- [x] 提交 ffadf60 的 [main Windows 检查](https://github.com/designgaogao-star/stillmark-workbench/actions/runs/40191040399) 与 [开发分支检查](https://github.com/designgaogao-star/stillmark-workbench/actions/runs/40191040416) 均已通过。
- [ ] 同提交的 [完整 Windows 包验收](https://github.com/designgaogao-star/stillmark-workbench/actions/runs/40191052297) 正在执行；完成后核对结论与产物。
- [ ] 在干净 Windows 环境解压 ZIP，验证首次启动、添加图库、GIF/WebP、删除确认、重启恢复和退出。
- [x] 在 CPU 和内存正常的当前机器上重跑统一验证；`verify.ps1 -Desktop <最新包> -SkipUi` 通过，Python 为 104 passed、2 deselected，后端握手门槛通过。
- [x] 当前开发预览包保持未签名，README 和随包说明已写明未知发布者提示、升级备份与回退方式；这不代表已发布二进制 Release。
- [x] 已将最终候选包的合成图片墙、深色查看器和窄屏截图加入 `docs/screenshots/`，附 SHA-256 来源记录并接入 README；截图不来自真实图库。
- [ ] 发布后再创建正式版本号、GitHub Release、签名证书和后续自动更新策略。

## 品牌与外部事项

已保留 Stillmark 全称及同名风险记录。正式商标检索尚未开展；商业发行前应结合发行地区复核名称与权利范围，现有网页与竞品对照不能代替正式检索。这项外部工作不由本地自动检查器认证。

## 文件与历史检查范围

公开检查器检查当前文件集，不能认证整个 Git 历史。对 ffadf60 之前远程历史的 447 个文本 blob 补充扫描，未发现匹配的访问令牌或私钥；19 个旧 blob 含已从当前文件移除的本机路径。没有上传用户数据库或图片，不把“未发现凭据”写成全面安全保证，也未通过强制重写公开历史掩盖旧提交。

## 当前技术观察项

040954 行为验收包完成过 60 分钟负载和独立审计；后半小时总量门槛通过，但渲染器角色仍有正增长。90 轮 GIF/WebP 差分短测显示活跃图片资源稳定，剩余现象更接近 Windows 原生分配器或混合墙面负载保留。公开预览可以继续做隔离验证，但在签名和跨机器承诺前应保留这项限制说明。

## 执行入口

```powershell
.venv/Scripts/python.exe scripts/public_release_check.py --json
pwsh -NoProfile -File scripts/build.ps1
pwsh -NoProfile -File scripts/verify.ps1 -Desktop <GalleryTool.exe绝对路径>
```

当前检查器的 `LOCAL_CHECK_PASS` 只表示工作区公开卫生通过；没有 Git remote 时会同时输出 `PUBLISH_BLOCKED_EXTERNAL_SETUP`，已有 remote 时输出 `EXTERNAL_CHECKS_REQUIRED`。脚本不联网，所以仓库是否存在、CI、签名和发布状态均为 null（未核实）；publish_ready 不能因配置 remote 就变为 true。它不会创建仓库、推送代码、创建 Release 或上传文件。
