# GalleryTool V2

Windows 本地纯图片图库。支持多个本地目录、目录与图包浏览、GIF/WebP 动图、浏览位置恢复、筛选标记、抽样、去重候选、内容核验和回收站删除。

后端为 Python 3.14、FastAPI、SQLite WAL、Pillow、NumPy、SciPy。Electron 提供窗口和目录选择；`prototype/` 是可运行的接口原型，正式前端可独立替换。

## 开发

安装 uv、Node.js 22.12+、PowerShell 7 后执行：

```powershell
uv sync --frozen --extra dev --extra desktop
npm ci
uv run python -m gallery --port 8765
```

打开 `http://127.0.0.1:8765` 添加本地目录。现有后台服务可通过 `启动图库预览.bat` 打开，通过 `停止图库服务.bat` 正常停止。

默认数据位于 `%LOCALAPPDATA%\GalleryTool`。`GALLERY_DATA` 可指定其他本地数据目录；原图留在注册的图库根目录中。

```powershell
# 独立临时数据，避免与已经运行的桌面程序争用同一数据库
uv run python -m gallery --data C:\Temp\gallery-dev --port 8766
npm start
```

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

开发前端独立运行时，后端进程可设置 `GALLERY_FRONTEND_ORIGIN=http://localhost:5173`；默认仅允许同源请求。

## 验证与构建

```powershell
uv run python -m pytest
uv run python -m ruff check .
node --check prototype/app.js
node --check electron/main.js
npm run check
pwsh -NoProfile -File scripts/build.ps1
```

测试使用临时图库。`GALLERY_TEST_BACKEND` 指定打包后端路径后，`tests/test_v2_http.py` 对实际 exe 执行相同的 HTTP、图片、SSE、退出与临时图片回收检查。

构建输出为 `build-out/<时间>/GalleryTool/GalleryTool.exe`。运行不需要另外安装 Python，不下载运行资源。

本机迁移核对、性能实测与桌面验收见 [V2 Review 与验收](docs/review-v2-20261020.md)。

## 数据迁移

```powershell
uv run python -m gallery --root F:\图库 --legacy F:\图库\_gallery_tool --data C:\Temp\gallery-migrated
```

迁移在后台执行，先使用 SQLite backup 获取一致快照，并保留原始浏览记录与删除日志。旧下标转换为图片 ID，旧哈希注明算法来源，不与新规范的哈希混用；兼容的旧 JPEG 缩略图按需复制复用。重复迁移同一来源返回原报告，不覆盖已有用户状态。

目录离线不清空索引；任务中断保留已提交的数据。永久删除必须明确传入 `confirm_permanent: true`。相似度与空壳报告是判断证据，完全重复结论需要 SHA-256 遍历图包内所有文件，包括隐藏文件和非图片文件。
