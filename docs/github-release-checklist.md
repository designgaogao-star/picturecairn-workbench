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
- [x] 当前开发候选包为 `build-out/20261025-175349/GalleryTool/GalleryTool.exe`；438 个产物和 ZIP 校验通过，公开卫生检查输出 `LOCAL_CHECK_PASS`。

## 发布前必须完成

- [ ] 在 GitHub 创建仓库并配置唯一 remote；仓库名建议 `stillmark-workbench`。
- [ ] 推送经过 review 的提交；发布前不得把 `runtime.local.json`、`output/`、`build-out/`、`ui/dist/`、依赖或用户数据带入提交。
- [ ] 最终审阅历史接手记录、旧性能报告和设计交接文档；决定哪些作为公开历史保留，哪些移入仓库外，不把内部对话或工作区操作记录当作产品文档。
- [ ] 在 GitHub Actions 实际执行一次 CI 和 Windows 手工构建，保存 workflow 结果和构建产物。
- [ ] 在干净 Windows 环境解压 ZIP，验证首次启动、添加图库、GIF/WebP、删除确认、重启恢复和退出。
- [x] 在 CPU 和内存正常的当前机器上重跑统一验证；`verify.ps1 -Desktop <最新包> -SkipUi` 通过，Python 为 104 passed、2 deselected，后端握手门槛通过。
- [ ] 在干净 Windows 环境解压 ZIP，验证首次启动、添加图库、GIF/WebP、删除确认、重启恢复和退出。
- [ ] 决定是否发布未签名开发预览；若发布，明确写出 SmartScreen 未签名提示和回退方式。
- [ ] 公开发布前完成 Stillmark 的 CNIPA 第 9/42 类以及 USPTO、EUIPO、WIPO 的正式检索。
- [ ] 重新生成公开 README 使用的截图并确认所有素材许可可追溯；截图不得来自真实图库。
- [ ] 发布后再创建正式版本号、GitHub Release、签名证书和后续自动更新策略。

## 当前技术观察项

040954 行为验收包完成过 60 分钟负载和独立审计；后半小时总量门槛通过，但渲染器角色仍有正增长。90 轮 GIF/WebP 差分短测显示活跃图片资源稳定，剩余现象更接近 Windows 原生分配器或混合墙面负载保留。公开预览可以继续做隔离验证，但在签名和跨机器承诺前应保留这项限制说明。

## 执行入口

```powershell
.venv/Scripts/python.exe scripts/public_release_check.py --json
pwsh -NoProfile -File scripts/build.ps1
pwsh -NoProfile -File scripts/verify.ps1 -Desktop <GalleryTool.exe绝对路径>
```

当前检查器的 `LOCAL_CHECK_PASS` 只表示工作区公开卫生通过；没有 Git remote 时会同时输出 `PUBLISH_BLOCKED_EXTERNAL_SETUP`。它不会创建仓库、推送代码、创建 Release 或上传文件。
