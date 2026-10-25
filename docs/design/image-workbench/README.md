# GalleryTool 图片工作台设计需求包

2026-10-22。**图片工作台已实现并通过实际桌面产物验收。** A1–E 的实施记录见 [frontend-ui.md](../../frontend-ui.md)，结果与性能范围见 [生产验收记录](implementation-verification.md)。设计修订仍以 [handoff.md](handoff.md) 为准；后端图片 API 未改变，旧 prototype 保留。

## 设计结论

采用 **Fluent 2 操作语义 + 专业图片工作台布局**：浅色中性工作区、可切换深色、蓝色选择色（原为青绿，见 handoff.md 设计修订）、完整图片墙、深色全屏查看器。目录、当前位置和图片优先，整理与任务退到明确的工作区域。

这不是控件换肤。主要改变是：图包先进入图片墙，文件名常驻，浏览/整理分模式，文件夹标记不再和视图切换争位置，删除结论与任务受理分开表达。

| 参考方向 | 采用的部分 | 取舍理由 |
| --- | --- | --- |
| Windows Fluent 2 | 控件语义、焦点、层级、菜单与对话框、主题 | 面向 Windows 本地长期使用，学习成本低；沿用现有 Preact，不引入 React 专用控件库 |
| Adobe Bridge | 位置导航、内容网格、可折叠信息面板 | 符合大图库查找和比较；去掉评分、标签、修图等超出范围的工具 |
| Lightroom Classic | 深色查看、包内胶片条、紧凑工具 | 适合沉浸看图；保留真实目录，不引入导入目录和修图流程 |
| Material / Apple 式整体换装 | 本轮不采用 | Web 管理台或触摸设备的视觉习惯不是本项目的首要依据；不为外观重写技术栈 |

## 阅读顺序

实施方先读 **[handoff.md](handoff.md)**：其中的设计修订优先于下列文档，另有当前进度和按文件拆好的任务。

1. 根目录 [PRODUCT.md](../../../PRODUCT.md)、[DESIGN.md](../../../DESIGN.md)：使用场景与已定方向。
2. [audit.md](audit.md)：当前问题、代码依据和改动优先级。
3. **[requirements.md](requirements.md)**：布局、行为、组件、状态、无障碍和性能要求。
4. **[preview/index.html](preview/index.html)**：可操作的高保真样机，直接打开，无需服务器或网络。
5. [tokens.css](tokens.css)：可移植的浅/深主题语义令牌。
6. [delivery.md](delivery.md)：现有 API 映射、文件改动范围、实施顺序与验收。
7. [frontend-prompt.md](frontend-prompt.md)：最初的开工提示词；进度与修订以 handoff.md 为准。
8. [verification.md](verification.md)：设计样机验证与模拟限制；[implementation-verification.md](implementation-verification.md) 记录生产前端验收。

行为以需求文档为准，视觉以令牌和样机为参考；与 handoff.md 的设计修订冲突时，以修订为准。样机不能代替生成的契约，也不能作为生产数据层实现。

## 样机范围

可以操作：图库切换、文件夹筛选、图包、图片墙、完整/填充、缩略图尺寸、选择、全屏查看与缩放、包内导航、位置恢复、主题、整理四个页签、核验模拟、任务暂停/继续/取消、删除确认与逐项报告。

素材保存在本地，来源见 [assets/README.md](preview/assets/README.md)。全是非敏感公开摄影，没有真实图库图片、文件名、ID 或数据库。

添加图库表单、任务和删除只演示界面状态。**不会调用 API，不会枚举输入的路径，不会执行回收或永久删除。** 动画、SSE、虚拟列表和大图库性能仍需在正式前端联调，样机的小数据数组不证明这些能力。

通过查询参数检查特殊状态；先清除地址中的旧 hash，再进入对应链接：

| 场景 | 链接 |
| --- | --- |
| 正常图包墙 | [浏览](preview/index.html) |
| 图片墙 / 查看器 | [图片墙](preview/index.html?view=images) / [查看器](preview/index.html?view=viewer) |
| 整理 / 任务 | [整包核验](preview/index.html?view=organize) / [后台任务](preview/index.html?view=tasks) |
| 离线 / 封面失败 / 空目录 | [离线](preview/index.html?scene=offline) / [失败](preview/index.html?scene=error) / [空目录](preview/index.html?scene=empty) |
| 过期核验 / 各有独有内容 | [过期](preview/index.html?scene=stale&view=organize) / [独有](preview/index.html?scene=unique&view=organize) |
| 删除部分失败 | [先选择至少两项，再删除](preview/index.html?scene=mixed&view=images) |

键盘：Tab/Enter 操作控件，查看器左右方向键切图、Escape 返回、0 适应窗口、1 原始尺寸。选择状态下 Delete 打开确认，Escape 退出选择。样机位置与主题只写到独立的 `gallery-workbench-design-v1` 本地存储项。

## 复验

仓库已安装依赖并有 Microsoft Edge 时，在项目根目录运行：

```powershell
node docs/design/image-workbench/verify.cjs
```

截图和机器可读结果生成在 `output/playwright/workbench-design/`，不进 Git。样机本体、令牌、素材与许可证均在设计包中，可离线查看。

## 规范来源

- [Fluent 2](https://fluent2.microsoft.design/)：[布局](https://fluent2.microsoft.design/layout)、[色彩](https://fluent2.microsoft.design/color)、[字体](https://fluent2.microsoft.design/typography)、[无障碍](https://fluent2.microsoft.design/accessibility)。本包尺寸与颜色是针对 GalleryTool 的选择，不声称是 Fluent 官方令牌。
- [Adobe Bridge 工作区](https://helpx.adobe.com/bridge/using/workspace.html)。只参考导航、内容与检查器的关系。
- [Lightroom Classic 工作区](https://helpx.adobe.com/lightroom-classic/help/workspace-basics.html)。只参考查看画布与胶片条。
- WCAG 2.2：[文字对比](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html)、[非文字对比](https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html)、[目标尺寸](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html)。
