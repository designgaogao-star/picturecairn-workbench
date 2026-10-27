# PictureCairn 品牌标识与 SVG 资产

> PictureCairn 影标图片工作台 · 品牌提案 v1.0 · 2026-10-24
> 设计交付阶段只制作品牌和矢量资产。2026-10-24 用户已确认 D「压角印」，工程侧按规范接入正式界面和桌面；以下四方案比较保留为设计依据，工程验收另附记录。

![品牌速览](picturecairn-brand-sheet.png)

## 1. 四个 Logo 方向对比

![四个 Logo 方向](exploration/picturecairn-directions.png)

每个方向在对比页中都包含以下内容：

- 图形、字标、中文副标题的排法
- 16 / 24 / 32 / 64px 缩小测试
- 浅色和深色背景
- Windows 托盘（深浅任务栏）
- GitHub 头像（圆形、圆角）

字标探索比较了 `PictureCairn`、`picturecairn` 和定制字标：

![字标探索](exploration/picturecairn-wordmarks.png)

## 2. 各方向设计说明

| 方向 | 构形逻辑 | 怎样表达图片 / 位置 / 续看 / 核验 | 用户印象 | 可能的误解 |
|---|---|---|---|---|
| **A 档案 / 索引 · 索引印相** | 矩阵：3×3 等距方格，右中一格换成朱色，像索引印相上被标出的一帧 | 图片、检阅较强；位置一般 | 档案室、索引卡、整齐 | 九宫格是“全部应用 / 缩略图视图”的通用图标；黑白时标记消失；16px 每格只有 4px，容易糊 |
| **B 路径 / 续看 · 续看径** | 单线：等粗路径逐行折返，停在左下朱印上，整体是 S | 位置、续看最强；图片感弱 | 流畅、有方向感 | S 字母标、贪吃蛇、管线；路线感接近需求里要避开的“地图” |
| **C 检阅 / 核验 · 对照线** | 对称并置：两幅竖画面，中间一条朱色对照线 | 检阅、核验最强；不表达位置和续看 | 严谨、对称、工具感 | 容易被看成“暂停键 ‖”；也像分栏视图、diff；16px 下朱线只有 1px 宽，还落在半像素上，会发虚变淡 |
| **D 纯抽象 · 压角印** | 压叠切口：方形画面的左下角压一枚朱印，画面让出等宽切缝，内角与印同心 | 图片（画面）、位置 / 书签（印）、核验（钤印）、长期使用（方正少细节） | 安静、可靠，有档案与钤印的东方气质 | 可能联想到“复制”“还原窗口”图标；靠 2:1 尺度差、朱印、等宽切缝和同心内角区分 |

各方向配的字标：

| 方向 | 字体 | 副标题排法 |
|---|---|---|
| A | IBM Plex Sans 500 | 宽字距，像索引标签 |
| B | Hanken Grotesk 560，全小写 | 在字标下方 |
| C | Source Sans 3 600，字距 +20 | 与字标同一基线 |
| D | Instrument Sans 560 定制 | 在字标下方，与图形上下对齐 |

## 3. 推荐方向与放弃理由

**推荐 D · 压角印。**

1. **小尺寸最稳**。16px 下仍是“大方块＋小方块＋一道缝”三个清楚的元素，直边都落在整像素上；托盘单色照样成立。
2. **概念最完整**。一个图形里同时有 Still（画面）和 Mark（印记、位置、核验）。
3. **不靠颜色**。黑白、反白都能认出来；朱色是加分项，不是前提，也不依赖蓝色。
4. **和通用图形拉开距离**。它不是九宫格、不是 S 字母、也不是暂停键。
5. **规则简单**。边长都是 4 的倍数；印是画面的 1/2，缝是印的 1/6，圆角是边长的 1/8。工程好复刻，长期看不累。

放弃其他方向的原因：

- **A**：本质是通用网格图标，独特性最弱；黑白时失去标记；16px 发糊。
- **B**：图片属性弱；S 字母和路线感容易被看成导航或地图类产品。
- **C**：被看成暂停键的风险高；1px 朱线在小尺寸失效；不表达位置和续看。

## 4. 推荐方向的各个版本

| 版本 | 文件 |
|---|---|
| 彩色（自动深浅） | [picturecairn-mark.svg](picturecairn-mark.svg) |
| 浅色背景 | [picturecairn-mark-light.svg](picturecairn-mark-light.svg) |
| 深色背景 | [picturecairn-mark-dark.svg](picturecairn-mark-dark.svg) |
| 单色（currentColor） | [picturecairn-mark-monochrome.svg](picturecairn-mark-monochrome.svg) |
| 纯黑 / 纯白 | [extra/picturecairn-mark-black.svg](extra/picturecairn-mark-black.svg) / [extra/picturecairn-mark-white.svg](extra/picturecairn-mark-white.svg) |
| 单色反白（镂空） | [extra/picturecairn-mark-reverse.svg](extra/picturecairn-mark-reverse.svg) |
| 小尺寸（像素对齐） | [extra/picturecairn-mark-16.svg](extra/picturecairn-mark-16.svg)、[extra/picturecairn-mark-24.svg](extra/picturecairn-mark-24.svg)、托盘 16 / 20 / 24、favicon 16、应用图标 24 |

![小尺寸检查](previews/picturecairn-small-sizes.png)

## 5. SVG 源文件

主交付：

| 文件 | viewBox |
|---|---|
| `picturecairn-mark.svg` | 64 × 64 |
| `picturecairn-mark-monochrome.svg` | 64 × 64 |
| `picturecairn-mark-light.svg` | 64 × 64 |
| `picturecairn-mark-dark.svg` | 64 × 64 |
| `picturecairn-wordmark.svg` | 420 × 96 |
| `picturecairn-lockup.svg` | 560 × 128 |
| `picturecairn-favicon.svg` | 16 × 16 |
| `picturecairn-tray.svg` | 16 × 16 |
| `picturecairn-app-icon.svg` | 256 × 256 |

另有 `extra/` 下的补充文件，完整用途见[品牌规范第 2 节](picturecairn-brand-guidelines.md#2-文件)。

技术情况：

- 全部是纯路径（`path` + `fill`）：没有位图、滤镜、渐变、外部字体或外部 CSS，也没有编辑器元数据。
- 字标和副标题已转曲。
- 每个文件 0.4–10.5 KB。
- 已用 XML 解析检查过全部文件，并用 Edge（Electron 同内核）渲染了所有尺寸。
- 设计交付时没有实际跑过 .ico 转换。工程接入后已用 Edge＋Pillow 完成七档 ICO 和四档黑白托盘位图、Windows 原生图标提取与实际 Electron 验证，见 [品牌集成记录](../../brand-integration-20261024.md)。自动深浅版在转换工具忽略内部样式时仍会回退为浅色稿；实际工程使用明确版本。

生成脚本在 [source/](source/README.md)，可重复生成：

- `build_assets.py`：生成全部 SVG
- `pages.py`：生成预览页
- `render.cjs`：把预览页渲染成 PNG

## 6. PNG 预览图

| 文件 | 内容 |
|---|---|
| [picturecairn-brand-sheet.png](picturecairn-brand-sheet.png) | 品牌速览：组合、各版本、图标、小尺寸、颜色、字体、构造、留白、错误用法、界面共存 |
| [exploration/picturecairn-directions.png](exploration/picturecairn-directions.png) | 四个方向对比 |
| [exploration/picturecairn-wordmarks.png](exploration/picturecairn-wordmarks.png) | 字标探索 |
| [previews/picturecairn-windows.png](previews/picturecairn-windows.png) | Windows 应用图标、标题栏、任务栏、托盘（100% 缩放） |
| [previews/picturecairn-workbench-light.png](previews/picturecairn-workbench-light.png) / [picturecairn-workbench-dark.png](previews/picturecairn-workbench-dark.png) | 浅色、深色工作台和侧栏品牌区 |
| [previews/picturecairn-splash.png](previews/picturecairn-splash.png) | 启动页 |
| [previews/picturecairn-viewer.png](previews/picturecairn-viewer.png) | 图片查看器顶部 |
| [previews/picturecairn-github.png](previews/picturecairn-github.png) | GitHub 仓库头像和 README 标题 |
| [previews/picturecairn-small-sizes.png](previews/picturecairn-small-sizes.png) | 16 / 20 / 24 / 32px 实际像素与放大 |

预览里的缩略图都是占位色块，没有使用任何真实图库内容。

## 7. 应用图标、托盘和 GitHub 头像

![Windows 场景](previews/picturecairn-windows.png)

![GitHub 场景](previews/picturecairn-github.png)

## 8. 品牌使用规范

完整内容见 [picturecairn-brand-guidelines.md](picturecairn-brand-guidelines.md)，包括：

- 颜色与对比度
- 构造比例
- 留白和最小尺寸
- 版本选用
- 小尺寸规则
- 字体与授权
- 错误用法
- 工程接入清单

## 9. 与现有界面配色共存

![浅色工作台](previews/picturecairn-workbench-light.png)

![深色工作台](previews/picturecairn-workbench-dark.png)

- **朱色只用在标志里**，不做按钮、链接、选中、进度或提醒。界面的删除色 `#b33835` 与朱色同属红橙色系，混用会让“删除”和“品牌”难以区分。
- **选择、焦点、链接继续用蓝色 accent**；标志不需要蓝色。
- **侧栏**：画面块跟随正文色（`--text`），印保持朱色。现在给图标套 `--accent-text` 的写法要去掉。
- **查看器**：顶部只放纯白单色标（不透明度 70–80%），见[查看器预览](previews/picturecairn-viewer.png)。
- **启动页**：用纸色或墨色底，进度条用石色，见[启动页预览](previews/picturecairn-splash.png)。
- **界面图标**继续用 Lucide，不改成朱色。
- 品牌没有引入新的界面字体，界面仍用 Segoe UI Variable / Microsoft YaHei UI。

## 10. 商标、GitHub 仓库名与同名产品

以下结果来自 2026-10-27 的 GitHub、npm 和网页初步检查，**不是正式的商标检索**。

| 名称 / 项目 | 初步结果 | 结论 |
|---|---|---|
| `PictureCairn` | 未发现精确同名 GitHub 用户、组织、仓库或 npm 包 | 可作为当前候选；仍需正式检索 |
| `PhotoCairn` | 已有两个低活跃照片工具仓库，其中一个是浏览器图片编辑器 | 不使用 PhotoCairn，避免近名混淆 |
| `PhotoTrail` | 有 38 star 的 macOS 照片地理标注工具 | 不使用，品类相邻 |
| `PhotoBench` | 有 19 star 的照片工具项目 | 不使用，容易被理解为基准测试 |
| `ImageTrace` | `imagetracerjs` 约 1,548 star，主打位图转 SVG | 不使用，语义和搜索结果都被占用 |
| 旧名 `Stillmark` | GitHub 上有多个同名项目，其中包含 Windows 截图工具和同名 workbench；最高星数不高但品类相邻 | 仅作为迁移历史保留，不再作为产品名 |
| 中文名“影标” | 未发现阻断性的同品类冲突；正式中文商标检索尚未开展 | 发布前检查 CNIPA 第 9、42 类 |

建议：

1. **对外统一写全称**：`PictureCairn 影标图片工作台`；英文描述使用 `PictureCairn Image Workbench`。
2. **仓库名使用 `picturecairn-workbench`**；GitHub 已保留旧仓库地址的重定向。
3. **标识符使用发布者命名空间**：Windows AppUserModelID 使用 `GalleryTool.PictureCairnWorkbench`；程序文件和数据目录继续使用 GalleryTool 兼容名。
4. **正式发布前**检查 CNIPA、USPTO、EUIPO、WIPO，以及目标域名和包管理器名称。
## 验收自查

| 验收项 | 结果 |
|---|---|
| 去掉文字后，图形仍有辨识度 | 通过。图形单独成立，见对比页 D 行 |
| 16px 下不会糊成方框或圆点 | 通过。像素对齐版的直边都在整像素上，见小尺寸检查 |
| 黑白打印能识别 | 通过。有纯黑稿、反白稿和单色稿 |
| 深浅主题都清楚 | 通过。有浅色版、深色版和自动版 |
| 不依赖蓝色 | 通过。只用墨和朱 |
| 能感受到图片、位置、检阅、长期使用中至少两项 | 四项都有对应（见第 2 节） |
| 不会被误认为相机、云盘、地图或安全产品 | 图形里没有镜头、云、图钉、盾牌元素 |
| 与 ImageGlass、digiKam、XnView、FastStone、Adobe Bridge、Eagle 明显区分 | 设计交付时只按构形判断；工程接入后已补浅／深底及 16/24/32px 并排对照，结论和真实来源限制见 [品牌集成记录](../../brand-integration-20261024.md)。第三方图标只留在忽略的本机输出目录，不分发 |
| 不靠渐变、阴影或材质 | 通过。全部是平面纯色 |
