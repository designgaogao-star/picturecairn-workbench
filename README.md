# GalleryTool V2

Windows 本地纯图片图库。支持多个本地目录、目录与图包浏览、GIF/WebP 动图、浏览位置恢复、筛选标记、抽样、去重候选、内容核验和回收站删除。

后端为 Python 3.14、FastAPI、SQLite WAL、Pillow、NumPy、SciPy。正式前端在 `ui/`，使用 Preact、Signals、Vite 和严格 TypeScript；Electron 提供窗口和目录选择。后端和桌面包同源托管 `ui/dist`，`prototype/` 保留作历史参考。

## 开发

安装 uv、Node.js 22.12+、PowerShell 7 后执行：

```powershell
uv sync --frozen --extra dev --extra desktop
npm ci
npm run ui:build
uv run python -m gallery --port 8765
```

打开 `http://127.0.0.1:8765` 添加本地目录。现有后台服务可通过 `启动图库预览.bat` 打开，通过 `停止图库服务.bat` 正常停止。

默认数据位于 `%LOCALAPPDATA%\GalleryTool`。`GALLERY_DATA` 可指定其他本地数据目录；原图留在注册的图库根目录中。

本机正式运行通过被 Git 忽略的 runtime.local.json 指定独立数据目录和已验证的桌面包。`启动图库.bat` 打开桌面，`启动图库预览.bat` 打开同一后台服务的浏览器页面，`停止图库服务.bat` 正常停止后台。动态端口会由脚本读取和展示，不能假定为 8765。桌面保存上次路由，重启后跨端口恢复。

runtime.local.json 支持 dataDirectory、backendPath、desktopPath；启动脚本显式参数优先于配置，GALLERY_DATA 优先于 dataDirectory。便携 exe 可从相邻的 GalleryTool.local.json 读取 dataDirectory；本机配置不进入 ZIP 或 Git。自行启动的桌面后端随桌面退出；复用脚本启动的后台服务时，用停止脚本结束它。

```powershell
# 独立临时数据，避免与已经运行的桌面程序争用同一数据库
# 动态端口在 GALLERY_READY 输出和 ready.json 中，不占用其他程序的端口
uv run python -m gallery --data C:\Temp\gallery-dev --port 0 --ready-file C:\Temp\gallery-dev\ready.json
```

也可让桌面自行启动后端：在一个未被其他实例使用的临时目录设置 `$env:GALLERY_DATA='C:\Temp\gallery-desktop-dev'`，再运行 `npm start`。

桌面启动使用动态端口和实例握手；已有受匹配的后台服务时复用它。关闭窗口收至托盘，托盘“退出”或 `GalleryTool.exe --quit` 退出应用，并停止应用自己启动的后端。

## 前端交接

接口前缀 `/api/v1`，运行时 OpenAPI 为 `/openapi.json`。

- `contracts/openapi.json`：生成的 API 契约。
- `contracts/schema.d.ts`：从 OpenAPI 生成的 TypeScript 类型。
- `contracts/client.ts`：使用生成类型的 HTTP 客户端与图片 URL 工具。
- `contracts/mock.json`：不包含真实图库信息的示例响应。
- `docs/frontend-handoff.md`：分页、位置恢复、任务和事件约定。

```powershell
npm run contract
npm run check
```

开发前端推荐通过 Vite 同源代理联调：`GALLERY_BACKEND` 指向上述临时后端，运行 `npm run ui:dev`。PowerShell 用 `$env:GALLERY_BACKEND='http://127.0.0.1:<端口>'` 设置，前端默认端口 5173，可用 `GALLERY_UI_PORT` 修改。也可在后端配置 `GALLERY_FRONTEND_ORIGIN` 明确允许独立来源。

开发服务器地址加 `?readonly` 会在前端请求入口拒绝全部非 GET 请求，包括添加图库、后台任务和任务控制，并显示“只读联调模式”；生产构建不启用这个开关。这不是后端只读模式，GET 图片仍可补齐派生缓存，后台维护也独立运行。只读排查必须使用隔离副本，不能直接打开真实数据目录。

## 验证与构建

```powershell
uv run python -m pytest
uv run python -m ruff check .
node --check prototype/app.js
node --check electron/main.js
npm run check
npm run ui:check
npm run ui:build
pwsh -NoProfile -File scripts/build.ps1
```

测试使用临时图库。`GALLERY_TEST_BACKEND` 指定打包后端路径后，`tests/test_v2_http.py` 对实际 exe 执行相同的 HTTP、图片、SSE、退出与临时图片回收检查。

构建输出为 `build-out/<时间>/GalleryTool/GalleryTool.exe`。运行不需要另外安装 Python，不下载运行资源。

`scripts/build.ps1` 先生成契约并构建正式前端，再将 `ui/dist` 与后端一起打包。前端集成回归入口为 `npm run ui:qa`，实际桌面验证为 `npm run ui:qa -- --desktop <GalleryTool.exe绝对路径>`，详见 `scripts/ui-qa/README.md`。测试自行生成临时图库、动态端口和临时数据目录，不依赖真实图库或操作回收站。

本机迁移核对、性能实测与桌面验收见 [V2 Review 与验收](docs/review-v2-20261020.md)。

正式前端接入、全库 215,243 张图片核对与当前运行入口见 [正式图库落地与验收](docs/review-live-20261022.md)。

## 数据迁移

```powershell
uv run python -m gallery --root F:\图库 --legacy F:\图库\_gallery_tool --data C:\Temp\gallery-migrated
```

迁移在后台执行，先使用 SQLite backup 获取一致快照，并保留原始浏览记录与删除日志。旧下标转换为图片 ID，旧哈希注明算法来源，不与新规范的哈希混用；兼容的旧 JPEG 缩略图按需复制复用。重复迁移同一来源返回原报告，不覆盖已有用户状态。

目录离线不清空索引；任务中断保留已提交的数据。永久删除必须明确传入 `confirm_permanent: true`。相似度与空壳报告是判断证据，完全重复结论需要 SHA-256 遍历图包内所有文件，包括隐藏文件和非图片文件。

已运行 V2 的数据可用 `python scripts/prepare_live_data.py <旧数据目录> <新目录>` 建立独立副本：SQLite backup 获取一致索引，复制并改写缓存路径，保留位置和日志，不修改来源。`python -m scripts.verify_library --data <新目录> --report output/verification.json` 独立只读遍历原图目录，检查索引是否完整。全量加载指全部图片进入持久索引，预览按需生成，不会一次解码全部图片。

`--no-scan` 同时禁止启动和定期扫描，`--no-watch` 禁止监听；维护间隔可用 `--maintenance-interval <秒>` 配置。只读排查仍应使用独立数据副本。
