# GalleryTool 图片工作台设计需求包实施计划

**Goal:** 选择适合本地大图库的设计，并交付能直接指导正式前端的文档、语义令牌、交互样机和验收依据。

**Architecture:** 独立设计包放在 `docs/design/image-workbench/`，不接后端、不改变运行入口。根目录 `PRODUCT.md`、`DESIGN.md` 记录共同背景；现有规范只增加设计包入口。

**Tech Stack:** Markdown、CSS 自定义属性、原生 HTML/JS、仓库现有 Lucide、Playwright/Edge；正式前端仍是 Preact/Signals/TypeScript。

## 1. 核实问题与边界

- [x] 阅读当前界面规范、交接、样式、页面和 API 契约。
- [x] 检查安全合成截图，区分现有事实与下一版目标。
- [x] 决定 Fluent 2 操作语义与图片工作台布局，不引入框架迁移。
- [x] 写出 `audit.md`，每个问题给出现有代码依据、影响和替代规则。

## 2. 固化产品与设计依据

- [x] 完成根 `PRODUCT.md`、`DESIGN.md`，明确浏览优先与非目标。
- [x] 完成 `tokens.css` 的浅/深主题、焦点、字体、间距和动效令牌。
- [x] 完成 `requirements.md`，给出桌面/窄屏尺寸、页面流程、选择、恢复、整理与删除状态。

## 3. 制作独立样机

- [x] 在 `preview/` 创建 `index.html`、`styles.css`、`app.js`、`data.js`。
- [x] 使用非敏感的公开摄影素材，保存本地并在 `assets/README.md` 记录出处和许可。
- [x] 使用已有 Lucide；供应文件保持许可证，不把 `node_modules` 放入交付包。
- [x] 接通文件夹、图包、图片墙、查看器、主题、任务、信息、选择、删除模拟与状态场景。
- [x] 原型所有写操作只改变样机内存；不连接真实 API，不读写真实图库。

## 4. 形成前端交接

- [x] `README.md` 给出阅读顺序、已定方案、参考规范、样机范围和启动方法。
- [x] `delivery.md` 映射现有文件和 API，按工作阶段列验收条件，不为未支持的功能画假入口。
- [x] `frontend-prompt.md` 提供可以直接交给 Claude 的开工提示词，说明共享分支、约束和禁止照搬的原型代码。
- [x] `docs/frontend-ui.md` 只增加“待实施设计”链接，不改写当前运行事实。

## 5. 验证与自审

- [x] JS 运行 `node --check`；样机在 Edge 中直接通过本地文件打开。
- [x] Playwright 验证 1440 × 1000、1280 × 800、1920 × 1080、390 × 844，无横向溢出，图片实际加载。
- [x] 验证图片打开/关闭恢复、包边界、键盘、主题、任务暂停/取消、模拟删除逐项结果和离线/坏图。
- [x] 保存桌面、查看器、整理、窄屏截图，检查文字、图像比例和浮层遮挡。
- [x] 按仓库约定执行 pytest、Ruff，记录结果；设计样机不要求生产打包。
- [x] 完成 `verification.md`，写明实际通过的检查、模拟范围和遗留限制，复查 Git 只包含本轮文件。

后续正式前端实施按 `docs/design/image-workbench/delivery.md` 执行。当前计划在本轮直接完成，不需要额外技能或代理才能读取交付物。
