# 参与开发

工作台面向 Windows 本地图片浏览。先阅读 AGENTS.md、PRODUCT.md、DESIGN.md 和 docs/frontend-ui.md；接口以 contracts/client.ts 与生成的 schema 为准。改 API 后运行 npm run contract 和 npm run check。

## 环境与验证

需要 PowerShell 7、Node.js 24、uv 和 Python 3.14：

```powershell
uv sync --frozen --extra dev --extra desktop
npm ci
pwsh -NoProfile -File scripts/verify.ps1
```

本地前端通过 npm run ui:dev 启动，GALLERY_BACKEND 指向自己的临时后端。pytest 默认排除 native_recycle 测试；日常检查不操作 Windows 回收站。全部测试使用生成的临时图库与数据目录，只结束自己启动的进程。

构建统一使用 scripts/build.ps1。验证实际产物时，运行 scripts/verify.ps1 -Desktop <exe路径>；长测另加 -SoakMinutes 60，并保留完整一小时的原始记录。CI 的构建工作流默认包含长测；关闭该选项后得到的只是通过短测的候选包。

## 提交与评审

- 变更应说明触发条件、结果、验证方式，以及影响到的数据或行为。
- 保留分页、持久 ID、图包边界、离线索引、有限的 IO/解码预算。快速切换要取消或忽略过期请求。
- 删除默认回收；永久删除必须显式确认。完整核验包括非图片文件，相似度不能直接触发删除。
- UI 变更遵守既定工作台规范，复核浅/深主题及 1440×1000、390×844 的真实界面。
- 不提交依赖、构建输出、运行数据、数据库、缓存、个人配置或真实图库截图。对演示材料使用合成图片，并记录生成方法。
- 共享分支协作时先确认工作区改动归属，不重置、覆盖或顺带提交他人的修改。

发现问题时使用缺陷模板，功能建议使用需求模板。模板关注本地浏览与整理；产品暂不扩展视频、云同步、标签评分、网络图库或修图。

## 许可

提交的项目代码使用 MIT License。引入依赖或第三方素材时保留其许可证和来源，并更新 THIRD_PARTY_NOTICES.md 与打包许可收集。不要把开发工具的授权自动当作运行时授权。
