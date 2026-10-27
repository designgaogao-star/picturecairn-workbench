# PictureCairn Workbench Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 PictureCairn 工作台和首次设置流程收口为可长期使用的开发候选，并完成至少 8 小时临时图库运行验证。

**Architecture:** 保留现有 Preact/Signals 组件边界和后端契约。先在共享 shell、图库首页、图包墙、任务抽屉和首次设置页补齐状态与视觉层级，再以 CSS token 和少量局部组件实现响应式变化；桌面打包继续使用 `scripts/build.ps1`，安装器本轮以首次设置体验和静态安装器原型呈现，不增加新的安装打包依赖。

**Tech Stack:** Preact 10、Signals、严格 TypeScript、Vite、现有 Lucide、Electron、FastAPI、pytest、Ruff、PowerShell。

---

### Task 1: 建立可复现的 UI 审计基线

**Files:**
- Create: `docs/superpowers/specs/2026-10-27-picturecairn-workbench-polish-design.md`
- Create: `docs/superpowers/plans/2026-10-27-picturecairn-workbench-polish.md`
- Modify: `docs/frontend-ui.md`

- [x] 记录视觉方向、工程边界和验收条件。
- [x] 在真实临时图库上记录桌面、窄屏、扫描中、任务抽屉和查看器截图路径；输出为 `output/ui-qa/integration-1793041962937/`。
- [x] 将发现的实际缺陷按 P1/P2/P3 追加到交付记录，不把主观偏好写成缺陷；本轮实际检查未发现新的 P1/P2/P3，既有缺口仍以 `docs/frontend-gaps.md` 为准。

### Task 2: 首次设置与图库首页

**Files:**
- Modify: `ui/src/views/LibraryHome.tsx`
- Modify: `ui/src/components/AddLibraryDialog.tsx`
- Modify: `ui/src/styles/shell.css`
- Modify: `ui/src/styles/walls.css`
- Test: `scripts/ui-qa/workbench.mjs` or focused temporary-library flow

- [x] 添加紧凑的图库上下文头，显示名称、真实路径、索引状态、文件夹数量和上次扫描时间。
- [x] 将首次设置表单分成说明、路径、名称和索引反馈四个稳定区块；浏览器手输和 Electron 选择器继续共用同一提交逻辑。
- [x] 覆盖空图库、筛选无结果、扫描中、离线和部分失败的明确操作文案。
- [x] 在实际 Electron 集成的桌面与 390px 场景验证不溢出、不跳动。

### Task 3: 图包墙与任务抽屉的完成度

**Files:**
- Modify: `ui/src/views/PackageWall.tsx`
- Modify: `ui/src/components/TasksDrawer.tsx`
- Modify: `ui/src/styles/walls.css`
- Modify: `ui/src/styles/shell.css`

- [x] 让图包卡片的封面、数量、路径、最近位置和选择状态在默认/悬停/键盘/窄屏下都有稳定呈现。
- [x] 让任务抽屉的进行中、已结束、自动维护、错误和缓存状态更易扫描，保留分页和取消/暂停语义。
- [x] 检查任务抽屉和信息面板同时打开时的层级、焦点返回和窄屏关闭路径；现有 `scripts/ui-qa/review-regressions.mjs` 的 escape-layers 场景及实际桌面回归覆盖桌面非模态、窄屏模态、关闭后选择焦点保留和信息面板互斥。

### Task 4: 安装器/首次启动视觉交付

**Files:**
- Create: `docs/design/installer/picturecairn-installer.html`
- Create: `docs/design/installer/picturecairn-installer.css`
- Create: `docs/design/installer/README.md`
- Modify: `docs/portable-readme.md`

- [x] 制作可打开的高保真安装器原型，覆盖欢迎、安装位置、数据目录、安装进度、完成/启动和失败重试状态；状态可在样机内点击切换，并已用 Edge 在桌面和 390×844 窄屏走通。
- [x] 复用 PictureCairn mark、纸/墨/蓝/朱色 token 和现有字体，不将原型误当成实际安装程序。
- [x] 记录未来接入 NSIS/WiX 时必须保留的路径、数据迁移、回退和卸载语义。

### Task 5: 长时间运行与交付收口

**Files:**
- Create: `docs/long-run-verification-20261027.md`
- Modify: `docs/frontend-ui.md`
- Modify: `docs/github-release-checklist.md`

- [ ] 通过临时图库和临时数据目录启动候选，完成至少 8 小时混合浏览、扫描、任务和查看器运行。
- [ ] 记录页面错误、请求失败、任务积压、缓存上限、DOM 数量、RSS/私有内存、退出码和未达标项。
- [ ] 运行 `npm run ui:check`、`npm run ui:build`、`npm run check`、pytest、Ruff、维护 JS 的 `node --check` 和 `git diff --check`。
- [ ] 不提交构建产物、临时图库、用户数据或截图；不创建新的 GitHub Release。

