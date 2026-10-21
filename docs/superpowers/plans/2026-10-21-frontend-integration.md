# 正式前端集成实施计划

**目标：** 将已提交的正式前端接入 Windows 桌面包，并使开发用只读模式拦截全部写请求。

**依据：** 用户本轮交接及 `docs/frontend-ui.md` 第 8 节。沿用已确定的布局、hash 路由和 Preact 状态管理，在当前会话逐项执行。

**架构：** 后端继续服务 `/api/v1`，同源托管 `ui/dist`；Electron 通过现有目录选择 IPC 提供系统能力。类型客户端增加可注入的 HTTP transport，前端在此统一拒绝只读模式的非 GET 请求，组件保留必要的只读交互提示。

**技术栈：** Preact、Signals、Vite、TypeScript、FastAPI、PyInstaller、Electron；验证使用 pytest、Playwright 的 Electron 驱动及已安装的 Microsoft Edge，无需下载额外浏览器。

## 1. 回归与测试环境

涉及 `scripts/ui-qa/`、`package.json`、`package-lock.json`、`scripts/demo_ui_library.py`、`tests/test_v2_http.py`。

- [x] 保存可复用的隔离 QA：创建新的临时图库、数据库和桌面 userData，动态选择端口，退出只结束本次启动的进程。
- [x] 用真实客户端复现只读漏写：拦截所有非 GET 网络请求，依次调用添加图库、各类任务、任务控制、标记、位置和删除；断言 `writes.length === 0`，错误含“只读联调模式”。拦截层保证修复前也不会实际执行写操作。
- [x] HTTP 回归解析首页脚本及样式引用，断言正式前端入口和构建资源均可取得，替换旧原型专属的 lucide.js 断言。
- [x] 回收站相关原生测试不执行；临时图片删除验证使用显式确认的永久删除，保留默认回收方式的界面断言。

执行：`npm run ui:qa -- --api-only`，修复前复现了 15 个非 GET 请求到达网络层。

## 2. 只读模式与目录选择

涉及 `contracts/client.ts`、`ui/src/api.ts`、`ui/src/components/AddLibraryDialog.tsx`。

- [x] 将客户端内部 `fetch` 改为构造时注入的 transport，保留默认 fetch 和既有类型签名。
- [x] 在 `api.ts` 的 transport 中按 DEV 与查询参数判断只读，并在网络发送之前拒绝所有非 GET；生产构建不启用此开关。
- [x] 目录选择使用已有 bridge；按钮显示“选择文件夹…”，选择期间禁止重复操作，取消保留输入，失败显示表单错误，始终恢复可操作状态。
- [x] QA 验证普通浏览器没有目录按钮、可手工输入，桌面 IPC 选择结果填入输入框。

执行：`npm run ui:qa`，漏写回归与实际页面通过；`npm run ui:check` 与 `npm run check` 通过。

## 3. 桌面构建与托管

涉及 `scripts/build.ps1`、`scripts/gallery.spec`、`gallery/app.py`、`README.md`、`docs/architecture.md`、`docs/frontend-ui.md`、`docs/frontend-gaps.md`。

- [x] 统一构建在 PyInstaller 前运行 `npm run ui:build` 并检查退出码。
- [x] PyInstaller 资源由 `prototype` 改为 `ui/dist`，后端根路径挂载同一资源目录，不需要 hash 路由回退。
- [x] 文档标记缺口 28 已解决，保留 `prototype/`；缺口 9、12、13、22 等待后端字段，不提前移除兼容实现。
- [x] 执行 `npm run ui:check`、`npm run ui:build`、`npm run check`、`.venv/Scripts/python.exe -m pytest -k "not windows_recycles_only_temporary_file and not process_recycles_temporary_image"`、`.venv/Scripts/python.exe -m ruff check .` 和改动 JS 的 `node --check`。
- [x] 仅通过 `pwsh -NoProfile -File scripts/build.ps1` 生成实际产物。

## 4. 实际产物与交付

- [x] 对最终 exe 运行 HTTP 与资源回归（排除实际回收站操作）。
- [x] 实际 Electron 包从空临时数据启动，验证首页为正式前端、目录选择 IPC、添加图库、目录与图包浏览、动图、图包边界、位置保存及刷新恢复、逐项删除结果、后台任务与退出。
- [x] 系统目录选择返回值使用受控测试替身；记录这项验证范围，不声称自动操作过 Windows 原生对话框。
- [x] 桌面和 390×844 浏览器视口截图，仅使用生成的几何图片；检查无横向溢出及图片正常加载。
- [x] 更新 UI 文档和本计划中的状态，review 差异，只提交本次修改及已检查的合成图库生成脚本，不推送、不切分支。

最终产物 `build-out/20261021-232934/GalleryTool/GalleryTool.exe`。源码回归 42 项、打包 HTTP 5 项与实际桌面/浏览器流程通过；两个原生回收测试按用户约束排除。Review 额外发现并修正原生 fetch 的接收者绑定问题，浏览器默认客户端调用已加入回归。

## 安全边界

本轮不读取真实数据库或真实图片，不使用 8765/8766，不操作回收站。图库、应用数据和截图输出均隔离，截图、依赖和构建产物不提交 Git。
