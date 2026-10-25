# 文档导航

Stillmark 是 Windows 本地图片工作台。当前源码已在 GitHub 公开，二进制包仍按开发预览验收。使用入口见 [项目 README](../README.md)。

## 当前使用与开发

- [界面与交互](frontend-ui.md)：图片墙、查看器、位置恢复、整理与任务的当前行为；开头的最新记录优先于下方历史阶段。
- [产品范围](../PRODUCT.md) 与 [设计规则](../DESIGN.md)：以浏览为主，不扩展视频、云同步或标签评分。
- [架构](architecture.md) 与 [前端接口交接](frontend-handoff.md)：模块边界、持久 ID、资源预算及类型契约。
- [图库管理](library-management-20261024.md)：改名、搬迁重连、移出与恢复的数据语义。
- [公开演示材料](screenshots.md)：合成图片截图、生成方法和摘要。
- [品牌资产](brand/stillmark/README.md) 与 [工程接入](brand-integration-20261024.md)：D「压角印」设计源和实际接入。

## 发布与验收

- [GitHub 发布清单](github-release-checklist.md)：当前通过、未完成事项及远程 Actions 链接。
- [当前 GitHub Windows 候选验收](github-preview-verification-20261026.md)：本次修复、源码检查、实际包与剩余发布门槛；[旧候选记录](github-preview-verification-20261025.md) 保留历史构建与长测证据。
- [Windows 开发预览收尾](release-readiness-20261024.md)：每个本机构建的来源与验收范围。旧构建通过不能代替新构建的验收。
- [便携包说明](portable-readme.md) 与 [发布说明草稿](github-release-draft.md)：数据目录、升级备份、回退及限制。
- [测试工具说明](../scripts/ui-qa/README.md)：源码、实际 Electron、性能和长测入口。测试只用临时图库，不操作回收站。

## 历史记录

`review-*.md`、`reference/`、`superpowers/`、`cleanup-plan.md`、`backend-v2-plan.md` 和设计交接中的阶段记录保留用于追溯迁移、性能与失败修复。它们描述当时的实现，不是当前使用指南，也不表示存在面向用户的 V2 产品版本。

历史记录引用的 `output/`、`build-out/` 和本机归档不随源码分发。正式界面以 `ui/` 为准，`prototype/` 与设计样机只作历史参考。公开 Git 历史的旧提交仍有已从当前文件中移除的本机路径；当前文件检查不代表历史已重写。不要将真实图片、数据库、浏览状态或删除日志补入这些记录。
