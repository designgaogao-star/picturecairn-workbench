# PictureCairn D「压角印」工程接入

用户于 2026-10-24 确认 D「压角印」。沿用设计负责人交付的路径、比例与墨／纸／朱色，不重新设计图形或工作台布局。

## 名称与兼容

当前源码和未发布候选对外统一使用 **PictureCairn 影标图片工作台**，英文描述为 PictureCairn Image Workbench。源码仓库仍为 [designgaogao-star/picturecairn-workbench](https://github.com/designgaogao-star/picturecairn-workbench)。公开的 [Windows 开发预览](https://github.com/designgaogao-star/picturecairn-workbench/releases/tag/preview-20261026-28faca1) 是品牌迁移前的 Stillmark 历史包，不能作为 PictureCairn 已随包发布的证据；当前品牌候选以本文件的候选记录和源码验证为准。

Windows AppUserModelID 为 `GalleryTool.PictureCairnWorkbench`，应用名、窗口标题、托盘提示、PE 产品信息均使用完整名称。`GalleryTool.exe`、`GalleryTool.local.json`、`GALLERY_DATA`、原数据目录和 API 保持兼容，不因品牌更名迁移用户数据。未来公开发布的包管理器 ID 应带实际发布者前缀，本轮不抢占无前缀的 npm、winget 或文件扩展名。

## 界面

- 侧栏使用交付的 24px 图形与已转曲的紧凑字标，中文副标题为辅助信息。
- 启动态采用交付的深浅竖版组合，背景和图形跟随应用内主题。
- 查看器顶部为 16px 纯白标，固定深色画布，窄屏让出操作空间。
- favicon 使用交付的 16px 像素对齐版。README 使用固定深浅的横版组合。
- 朱色只用于标志，选择、焦点、按钮和进度仍沿用工作台的交互色。界面继续使用系统字体和 Lucide。

SVG 在构建时以可信常量接入，不引入用户或服务端提供的 SVG 文本。32 个 SVG 经过结构校验：有 viewBox、不含位图、外链、字体依赖或不必要滤镜。字标已经转曲，运行和打包不需要下载字体。

## Windows 图标与构建

`scripts/build-brand.mjs` 使用本机 Edge 无头渲染交付 SVG，`scripts/brand_assets.py` 用现有 Pillow 生成 ICO。生成物在忽略目录 `output/brand/runtime/`，不提交。这里不依赖 ImageMagick，也不改写原始设计稿。

- ICO 包含 16、24、32、48、64、128、256 七个尺寸；16/24 使用专门像素对齐稿，校验每档解码像素与输入 PNG 完全一致。
- 托盘单色黑白各提供 16/20/24/32px，Electron `NativeImage` 显式注册 100%、125%、150%、200% 四档。
- 托盘依据 Windows 系统集成 UI 的深浅模式选黑白，监听主题更新；不会将应用内主题误当作任务栏主题。
- `scripts/stamp-desktop.mjs` 从原始 Electron 生成新的可执行文件，用锁定的 resedit/pe-library 写入七档图标和版本信息，不原位修改依赖。
- `scripts/build.ps1` 是唯一打包入口；实际包中的窗口 ICO、托盘位图和可执行文件资源均已生成。Windows 原生 `ExtractIconEx` 已成功提取大／小图标；开发预览的 PE 数值版本槽位为 0.0.0.0，Windows 属性文字显示“开发预览（未发布）”。

当前是未签名的 Windows 预览包；资源写入不等于代码签名。未改变机器全局主题或 DPI，四档验证针对实际 NativeImage representation 和像素，不声称在四套物理屏幕上人工测试。

## 实际产物验证

公开的 Stillmark 历史包为 `build-out/20261025-164104/GalleryTool/GalleryTool.exe`，产品源码为 `28faca1`；它包含 WAL 生命周期、缩略图迟到事件和在途分页刷新修复，但不包含 PictureCairn 品牌迁移。首个品牌候选为 `20261024-232328`，中间命名整理包 `20261025-161637`、040954 的图片内存与占位图验收保留于 [历史收尾记录](release-readiness-20261024.md)。

PictureCairn 当前候选为 `build-out/20261027-023425/GalleryTool/GalleryTool.exe`，对应便携包 `GalleryTool-dev-win-x64.zip`，ZIP SHA-256 为 `5c4fcd5c08f831e5aaf0223e9102d0e9a592a239e755d0b27284f1c5d0e67004`，共 438 个产物。该候选已完成品牌、实际 Electron 流程、退出和工程检查，但尚未提交、推送或替换公开 Release；它是开发候选，不是新的公开版本。

公开包的运行证据和历史内存观察见 [本次验收](github-preview-verification-20261026.md)；限定扫描候选 `20261026-105024` 的来源、限制与性能见 [候选验收与交付](candidate-verification-20261026.md)，品牌候选 `20261027-023425` 的运行验证见本节记录和对应的 `output/ui-qa/` 证据。三者的结果不能混用。

- 源码浏览器品牌检查 13 项通过，实际 Electron 品牌检查 17 项通过。
- 检查包括应用内主题优先、朱色、转曲字标、启动深浅、favicon、390px 侧栏、应用名／ID、黑白四档原生位图及主题更新刷新托盘。
- 完整实际桌面流程还覆盖目录选择 IPC、图片墙、GIF/WebP、位置恢复、整理、逐项结果、图库管理 22 项、动态端口重启和所属后端退出。
- PictureCairn 候选的本机品牌证据为 `output/ui-qa/integration-1793039783447/brand-verification.json`，四项退出证据为 `output/ui-qa/shutdown-1793039826551/result.json`；这两份记录对应 `build-out/20261027-023425`，不是公开 Release。公开历史包的品牌证据为 `output/ui-qa/integration-1792951374652/brand-verification.json`，历史 161637 的证据为 `output/ui-qa/integration-1792916370612/brand-verification.json`。主题截图均等待有限 CSS 过渡完成，避免截取中间色；完整退出与长期内存的范围单列于各自验收记录。

截图全部来自生成的几何图片。设计提案中的场景预览仍属于样机，不能替代实际产品截图。截图、位图、ICO、输出与用户数据均不暂存或提交。

## 竞品构形复核

`node scripts/compare-brand.mjs` 生成本机对照页、PNG 和来源／SHA-256 清单：`output/brand/comparison/`。第三方图标只用于本机设计复核，不提交，不进入产品包。

| 对照对象 | 来源与限制 |
| --- | --- |
| ImageGlass | 官方 GitHub `ImageGlass.Win32/icon256.ico`，通过 Contents API 取得原文件 |
| digiKam | 官网 32px favicon，大图展示会放大 |
| XnView | 官网 144px Apple touch 图标 |
| FastStone | 官网本轮不可达；使用 Ninite 标为 FastStone Image Viewer 8.5 的 16px 缓存，页上明确标注放大 |
| Adobe Bridge | Adobe 官方 Bridge SVG |
| Eagle | 官网 PNG favicon |

并排查看浅色、深色与 16/24/32px 后，D 的方形画面、左下角印与切缝轮廓仍清晰；与 ImageGlass 的字形、digiKam/XnView/FastStone 的镜头或眼睛、Bridge 的 Br 和 Eagle 的动物轮廓有明显区别。小尺寸的两块及间隙可以辨认，但“图片／位置／核验”的具体含义仍需要名称和产品使用建立，不能把设计解释当作用户研究结论。

同名检索风险沿用 [原始提案](brand/picturecairn/README.md) 第 10 节，尤其是相邻品类的 Windows 截图工具。此轮决定保留全称并做命名空间区分；图标对照和工程接入均不构成正式商标检索或注册结论。
