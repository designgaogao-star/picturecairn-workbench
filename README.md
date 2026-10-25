<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/brand/stillmark/extra/stillmark-lockup-dark.svg">
    <img src="docs/brand/stillmark/extra/stillmark-lockup-light.svg" alt="Stillmark 影迹图片工作台" width="420">
  </picture>
</p>

# Stillmark 影迹图片工作台

**原目录浏览，随时续看，核实再整理。**

面向大量成套图片的 Windows 本地工作台。图片留在原有文件夹中：按目录和图包浏览，关掉再打开时继续上次的位置；两套图包看起来相似时，先检查差异和完整文件内容，再决定怎样整理。

## Windows 预览版

当前是 **开发预览（未发布）**，主要在 Windows 11 x64 验收。便携包自带 Electron、Python 后端与依赖，使用时无需安装开发环境。目前尚未发布 GitHub Release；本地候选包由下文的统一构建入口生成。

GitHub 首次公开发布前不使用正式版本号。开发包以构建日期和 `release-manifest.json` 的源码摘要区分；依赖工具要求的版本字段只使用开发占位值。

1. 取得 `GalleryTool-dev-win-x64.zip` 和同名 `.sha256`，核对 SHA-256。
2. 将整个 ZIP 解压到可写目录，保留 `resources/` 等文件。
3. 双击 **GalleryTool.exe**，选择存放图片的本地目录。索引在后台建立，已扫描部分可以直接浏览。

为兼容既有启动脚本，开发预览继续使用 GalleryTool.exe 和 GalleryTool.local.json 文件名；窗口、托盘和界面显示完整的 Stillmark 品牌。当前包未做代码签名，Windows 可能显示“未知发布者”。

```powershell
# 哈希应与 .sha256 第一列一致
Get-FileHash .\GalleryTool-dev-win-x64.zip -Algorithm SHA256
```

关闭窗口会收至系统托盘。托盘“退出”会停止桌面自己启动的后端；复用的外部后台服务由它的启动者单独管理。既有本机启动脚本仍可使用，动态端口由脚本读取。

## 能做什么

- 管理多个本地图库；改显示名称、移出管理，或在目录搬迁后重新连接，保留相对路径对应的 ID、位置与标记。
- 真实目录和图包浏览；分页、虚拟滚动、按 ID 定位与恢复，单张导航止于当前图包。
- 图片墙使用静态封面；查看器支持 GIF/WebP 动画、缩放、旋转和胶片条。
- 按文件夹标记状态，筛选和抽样；旧目录名前缀的分类规则继续兼容，不是图片标签系统。
- 查看相似图包的覆盖与独有内容。完整核验逐文件读取 SHA-256，包括隐藏文件和非图片文件。
- 默认删除移至 Windows 回收站，失败不会自动改成永久删除；永久删除必须明确确认，结果逐项显示并记录。
- 暂停、继续和取消后台任务；离线目录保留已建索引，坏图和失败任务显示原因。

支持 **JPEG、PNG、GIF、WebP、BMP**。当前范围是 Windows 本地纯图片；暂不支持 RAW、HEIC、AVIF、压缩包、视频、网络图库、云同步或修图。

大图库进入持久索引后，图片仍按需读取和生成预览。首次加载大图需要磁盘读取与解码时间；实际表现取决于硬盘、素材和缓存状态。测量和测试范围见 [最新交付](docs/release-readiness-20261024.md) 与 [质量验收](docs/review-quality-20261023.md)，不把单台机器的结果当作跨机器保证。实际桌面演示只用合成图片，生成方式见 [演示材料](docs/screenshots.md)。

## 数据、升级与恢复

原图始终留在添加的图库目录中。默认数据库、缩略图、浏览状态与操作日志位于 `%LOCALAPPDATA%\GalleryTool`，建议放在本机 SSD。`GALLERY_DATA` 可指定其他本地数据目录；便携程序也支持相邻 `GalleryTool.local.json` 的 `dataDirectory` 字段。

升级前退出旧版并备份数据目录；将新包解压到另一目录，使用相同数据目录启动。数据库可能执行向前迁移，回退旧版时使用升级前备份。不要用旧程序直接打开已经升级的数据。

“移出管理”保留磁盘文件、索引、缩略图、位置、标记和日志；重新添加原目录可以恢复。目录离线不会清空索引。有未结束的关联任务时，重新连接或移出会提示先处理任务。

删除的依据是用户自己的选择或完整文件核验的结论。相似度、空壳包和其他整理提示都是检查线索；任务受理不等于操作成功，请查看逐项结果。

## 反馈与参与

发现问题时使用仓库的缺陷模板，提供构建日期或源码摘要、Windows 环境、复现步骤及已脱敏的日志片段。用合成目录说明问题，不上传真实图库数据库、原图、缓存或删除日志全文。

[版本记录](CHANGELOG.md) · [贡献指南](CONTRIBUTING.md) · [漏洞报告](SECURITY.md) · [当前界面说明](docs/frontend-ui.md) · [产品背景](PRODUCT.md) · [品牌与同名项目记录](docs/brand/stillmark/README.md)

对外名称统一为 Stillmark 影迹图片工作台；公开仓库建议使用 `stillmark-workbench`。当前仓库尚无远程地址，CI 与手工构建工作流已准备好，远程执行结果会在创建仓库后产生。

## 开发

技术栈：Python 3.14、FastAPI、SQLite WAL、Pillow、NumPy、SciPy、watchfiles；Preact 10、Signals、严格 TypeScript、Vite；Electron 桌面壳。

安装 PowerShell 7、Node.js 24 和 uv：

```powershell
uv sync --frozen --extra dev --extra desktop
npm ci
npm run ui:build

# 为开发创建独立数据目录，动态端口写入 ready.json
uv run python -m gallery --data C:\Temp\stillmark-dev --port 0 --ready-file C:\Temp\stillmark-dev\ready.json
```

前端联调时将 `GALLERY_BACKEND` 指向这个临时后端，再运行 `npm run ui:dev`；`GALLERY_UI_PORT` 可指定前端端口。源码桌面使用 `npm start`，启动前会生成已确认的品牌位图和 ICO。

开发服务器的 `?readonly` 会在前端请求入口拒绝全部非 GET；生产构建不启用该开关。它不是后端只读模式：图片 GET 仍可能写缓存，后台维护独立运行，真实数据排查应使用隔离副本。`--no-scan --no-watch` 同时禁止启动/维护扫描与监听。

接口统一在 `/api/v1`，运行时契约为 `/openapi.json`。修改接口后执行 `npm run contract` 和 `npm run check`，不手改生成的 TypeScript schema。前端交接见 [接口说明](docs/frontend-handoff.md)，模块边界见 [架构](docs/architecture.md)。

## 验证与构建

```powershell
pwsh -NoProfile -File scripts/verify.ps1
pwsh -NoProfile -File scripts/build.ps1
pwsh -NoProfile -File scripts/verify.ps1 -Desktop <GalleryTool.exe绝对路径> -SoakMinutes 60
```

测试只使用临时图库与独立数据目录，默认排除原生回收站探针。统一验证包括 Python、Ruff、契约、严格 TS、UI 构建、品牌转换、JS/CJS 语法、工作台回归与桌面退出；实际产物和一小时负载另外核验。

构建生成便携 ZIP、SHA-256、逐文件构建来源清单及许可证清单。`build-out/`、`ui/dist`、依赖和用户数据不进 Git。GitHub 的 Windows 检查与手工构建工作流复用相同入口；手工构建默认运行完整长测，关闭长测时产物仍标为候选包。`prototype/` 保留作历史参考。

## 旧版数据迁移

```powershell
uv run python -m gallery --root D:\Pictures --legacy D:\OldGalleryTool --data C:\Temp\stillmark-migrated
```

迁移先用 SQLite backup 获取一致快照，保留旧数据库、原图、缩略图、浏览记录与删除日志。旧下标转换为图片 ID；旧哈希注明来源，不与新规范混用。相同来源的重复迁移返回原报告。

已有 GalleryTool 数据可用 `python scripts/prepare_live_data.py <旧数据目录> <新目录>` 建立独立副本。`python -m scripts.verify_library --data <新目录> --report output/verification.json` 可独立只读核对原图目录与索引。不要把程序迁移、截图和用户数据清理混在一起。

## 许可

项目代码使用 [MIT License](LICENSE)。第三方声明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)；便携包保留 Electron 许可，并附带 Python 解释器、运行依赖、前端库和相关构建工具的许可原文及版本索引。
