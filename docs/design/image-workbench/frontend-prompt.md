# 给前端负责人的开工提示词

你接手 PictureCairn 影标图片工作台前端的改版。当前是开发预览（未发布），不使用正式版本号。全程中文，项目在本机工作区，与后端共享当前开发分支，不要切换分支或覆盖别人修改。

设计方向已由用户授权确定，不需要重新让用户挑配色：**Fluent 2 操作习惯 + 专业图片工作台**。浅色中性工作区、可切换深色、青绿选择色、完整图片墙、深色沉浸查看器。目标是减少操作歧义与信息竞争，不是只换颜色。

先读：

1. `AGENTS.md`、`README.md`、`PRODUCT.md`、`DESIGN.md`。
2. `docs/design/image-workbench/README.md`、`audit.md`、`requirements.md`。
3. 直接打开 `docs/design/image-workbench/preview/index.html`，走通图包→图片墙→查看器→返回，整理核验、任务和删除模拟，查看窄屏与深色。
4. `docs/design/image-workbench/tokens.css`、`delivery.md`、`verification.md`。
5. 当前运行事实与数据契约：`docs/frontend-ui.md`、`docs/frontend-handoff.md`、`docs/frontend-gaps.md`、`contracts/client.ts`。

按 `delivery.md` 的 A–E 阶段实施到 `ui/`，保留 Preact 10、Signals、Vite、严格 TypeScript 和现有 Lucide。不引入 React Fluent UI，不把独立样机的整页 innerHTML 重绘、8 张图数组、模拟删除结果或示例路径搬进生产。

优先交付：清晰的工作区框架和主题，图包主入口先进入图片墙，文件名常驻，默认完整图片，查看器和位置恢复，然后整理/任务/删除。行为以 requirements 为准，不能为追求视觉照抄样机而削弱既有功能。

所有资源通过 `/api/v1`、持久 ID 和现有客户端访问。分页、虚拟 DOM、预载、Blob 生命周期和机械硬盘 IO 预算继续有上限。主题、侧栏、信息面板切换不能重启图片加载链路。当前 API 没有任意目录内容过滤、全局搜索和任意排序，不做假的入口，不把新后端功能当作设计前提。

保持包内导航、静态封面、查看器动图、散图限制与位置恢复。文件夹状态不是图片标签。相似度只能筛候选，整包核验包含非图片文件且过期后撤掉核验快捷删除依据。默认回收站，永久删除必须显式确认，返回任务不等于已完成，失败项必须保留和可核查。

测试一律临时图库和临时数据目录。不要写真实数据库，不做真实删除探针，不动回收站、不结束他人进程。真实数据副本仍指向真实图片，只能按现有只读联调约定短时查看；敏感图像不进入截图或提交。

每阶段同步当前 UI 文档并运行相关检查。最终运行 ui:check、ui:build、check、pytest、Ruff、改过 JS 的 node --check，完成桌面/窄屏/双主题浏览器检查。构建只用 `scripts/build.ps1`，验证实际 Electron 产物后再切换入口。不要提交生成资源、依赖、输出、用户数据或真实截图；不要删除旧 prototype。

完成每阶段后用中文说明已实现行为、验证结果与仍未接入的部分。发现 API 差异先核对生成契约，再按原格式写入 frontend-gaps；不要自造字段或用本地全量数组掩盖契约问题。
