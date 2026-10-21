# 前端集成验证

使用新建的临时图库与临时数据库，不依赖本机图库 ID，不连接既有服务，不操作回收站。截图及日志放在 `output/ui-qa/integration-<时间>/`；测试数据保留在输出提示的临时路径，便于失败后排查。

```powershell
# Windows 上使用已安装的 Microsoft Edge，不下载浏览器
npm run ui:qa

# 只验证只读请求入口，不启动浏览器
npm run ui:qa -- --api-only

# 对实际打包后端验证正式前端、只读开发模式和浏览流程
npm run ui:qa -- --backend <gallery_server.exe绝对路径>

# 启动实际桌面包，验证预载脚本、目录选择 IPC、正式前端和后端退出
npm run ui:qa -- --desktop <GalleryTool.exe绝对路径>
```

需要项目依赖和已构建的 `ui/dist`；构建桌面只能用 `scripts/build.ps1`。`--backend` 和 `--desktop` 二选一。每轮自动挑选空闲端口，只结束本轮创建的进程。

覆盖：开发只读模式全部非 GET 请求被拒绝、普通开发模式允许写请求、普通浏览器手工添加、目录选择成功/取消/异常、添加与扫描、图包和图片浏览、图包边界、浏览位置保存与刷新恢复、GIF/WebP 像素变化、后台任务、临时图片的逐项删除结果，以及 1440×1000 和 390×844 截图。

目录选择测试将 `dialog.showOpenDialog` 的返回值替换为受控结果，桌面模式仍经过正式预载脚本及 IPC；不声称自动点击过 Windows 原生对话框。浏览器模式使用同形状的 bridge 测试替身。

删除先验证默认回收方式与永久删除确认约束，随后仅显式永久删除本轮生成的临时图片。不能传入真实图库路径，也不支持复用真实数据库。

旧的 `%TEMP%/gallery-ui-qa/shoot/` 全量 QA 场景未整体迁入；本目录保存本轮工程收尾所需的独立回归，未携带旧 ID、数据副本或 `real.js`。
