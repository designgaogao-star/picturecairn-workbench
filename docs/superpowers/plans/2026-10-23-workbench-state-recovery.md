# 工作台状态恢复修复计划

**目标：** 修复 review 确认的三处回归，保留既定布局、接口和图片请求预算。

**方案：** 桌面启动会话负责一次性的偏好迁移，刷新使用当前来源的存储。非模态面板声明 Escape 所有权，由现有键盘守卫统一识别。查看历史与返回墙面的定位请求分开；已有墙面锚点优先于继续位置，明确退出查看器时定位一次并消费请求。

**技术栈：** 现有 Electron、Preact、Signals、严格 TypeScript 和 Playwright。沿用共享分支，不提交代码，不操作真实数据库或回收站。

## 1. 建立回归

- [x] 新增 `scripts/ui-qa/review-regressions.mjs`，使用 Vite、模拟图片 API 和临时浏览器上下文。
- [x] 运行 `node scripts/ui-qa/review-regressions.mjs`，分别确认刷新偏好、Escape、深页锚点失败。
- [x] 覆盖同来源新桌面会话、跟随系统、菜单/面板/确认框层级、深链返回和改变列数。

## 2. 修复

- [x] `electron/main.js` 为本次桌面启动生成独立的 `uiSession`；`preload.js` 暴露非敏感会话 ID。
- [x] `ui/index.html` 与 `bootstrap.ts` 根据 `sessionStorage` 的 `gt.desktopSession` 判断是否迁移；同会话刷新读取当前偏好。
- [x] `SidePanel.tsx` 声明 `data-escape-panel`；`lib/keys.ts` 为 Escape 识别活动面板；`Selection.tsx`、`Viewer.tsx` 使用共同守卫。
- [x] `state/app.ts` 保留 `lastViewed` 历史，增加单次 `wallReturn` 意图；离开对应范围即失效。
- [x] `VirtualGrid.tsx` 完成有效定位后调用 `onReveal`；`ImageWall.tsx`、`PackageWall.tsx` 消费返回意图，无已有锚点时才使用继续位置。
- [x] 重跑回归直至所有断言通过，同步 `docs/frontend-ui.md`。

## 3. 验证和交付

- [x] `npm run ui:check`、`npm run ui:build`、`npm run check`；修改的 JS/MJS 逐个 `node --check`。
- [x] `.venv/Scripts/python.exe -m pytest -k "not test_windows_recycles_only_temporary_file and not test_process_recycles_temporary_image"`：68 passed，两个原生回收测试按用户约束排除。
- [x] `.venv/Scripts/python.exe -m ruff check .`。
- [x] 工作台全量浏览器回归：125 项通过，包含桌面与 390×844 截图。
- [x] 仅用 `scripts/build.ps1 -NoZip` 构建，实际 Electron 产物验证刷新和跨进程重启；通过后更新本地入口至 `20261023-012543`。
- [x] 自检 diff，记录验证结果和限制，不提交生成资源或用户数据。
