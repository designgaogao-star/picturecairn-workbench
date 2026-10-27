# PictureCairn 影标图片工作台 · 开发预览 2026-10-27

这是 PictureCairn 的首次公开 Windows x64 开发预览。它使用日期型预览标签，不代表稳定版或正式语义版本；程序内部仍保留 `0.0.0-dev` 和“开发预览（未发布）”构建元数据。

## 下载

- [PictureCairn-dev-win-x64.zip](https://github.com/designgaogao-star/picturecairn-workbench/releases/download/preview-20261027/PictureCairn-dev-win-x64.zip)
- [SHA-256 校验文件](https://github.com/designgaogao-star/picturecairn-workbench/releases/download/preview-20261027/PictureCairn-dev-win-x64.zip.sha256)

下载后先核对 `.sha256` 文件，再将整个 ZIP 解压到可写目录，运行 `GalleryTool.exe`。程序文件和数据目录保留 GalleryTool 兼容名；窗口、托盘和正式界面使用 PictureCairn 品牌。

## 这次预览包含

- 多个本地图库，按真实文件夹和图包浏览。
- 大图库分页、虚拟滚动、键盘导航和位置恢复。
- JPEG、PNG、GIF、WebP、BMP；GIF/WebP 在单张查看器中播放。
- 相似图包线索、双图包完整文件核验，以及非图片文件核验。
- 默认移入 Windows 回收站；永久删除要求二次确认并显示逐项结果。
- 图库改名、搬迁后重新连接、移出管理和重新添加恢复。
- 浅色/深色主题、Windows 托盘、动态端口和退出时状态保存。

## 验证范围

候选由 `scripts/build.ps1` 生成，包含 438 个产物、来源清单、第三方许可证和同名 SHA-256 文件。源码检查、契约生成、严格 TypeScript、Python 测试、Ruff、品牌资产转换、JS 语法和公开仓库卫生检查均通过。

实际 Windows Electron 回归使用临时图库和临时数据目录，覆盖目录选择、图片墙、查看器、GIF/WebP、图包边界、位置恢复、任务、临时删除、图库生命周期、资源释放、品牌、动态端口重启和退出。八小时临时图库长测覆盖 480 分钟和 1440 轮，独立审计通过；记录见 [长测报告](long-run-verification-20261027.md)。

## 已知限制

- 这是未签名的 Windows 开发预览，SmartScreen 可能显示未知发布者。
- 安装器目前提供视觉与交互样机，正式构建仍是便携 ZIP。
- 当前只支持本地图片，不支持视频、云同步、网络图库、标签、评分、收藏、RAW、HEIC 或 AVIF。
- 首次冷读和大图解码受硬盘、图片尺寸和系统负载影响。
- 本轮没有操作真实图库、真实数据库或 Windows 回收站；删除验证只使用临时图库。

反馈时请提供构建日期或 `release-manifest.json` 的源码摘要、Windows 版本、显示缩放、临时图库复现步骤和脱敏日志。不要上传真实图库数据库、原图、缓存、浏览记录或删除日志全文。
