# 实施交接

2026-10-22。设计与任务拆解已定，剩余实现交给执行方。行为以 [requirements.md](requirements.md) 为准；**下面的设计修订优先于 requirements、样机和 tokens.css**。规则仍按根目录 `AGENTS.md` 与 [delivery.md](delivery.md)。

**执行状态更新**：A1–E 已接入并通过临时图库及实际 Electron 产物验收，见 [实施记录](../../frontend-ui.md) 和 [生产验收记录](implementation-verification.md)。下面“进度”保留的是交接时的中间态，不能据此回退当前组件；设计修订继续有效。

## 设计修订

| 项目 | 修订后 | 原方案 | 理由 |
| --- | --- | --- | --- |
| 外观 | 默认跟随系统，可固定浅色或深色；偏好键 `gt.theme`，跟随系统时不存 | 浅色为初始 | Windows 用户已在系统里选过；首帧由 `index.html` 内联脚本设定，不闪烁 |
| 强调色 | Fluent 蓝：浅色 `#0f6cbd`；深色填充 `#115ea3`，文字和描边 `#62abf5` | 青绿 | 青绿和“保留/成功”的绿色太近，选中与已保留容易混淆；蓝色在 Windows 上就是选中和主操作 |
| 框架 | 52px 位置栏 + 44px 上下文工具栏（窄屏 48px） | 位置栏 + 约 132px 标题/模式区 + 工具栏 + 28px 状态栏 | 图片区多出约 110px，每条栏只承担一种职责 |
| 位置栏 | 面包屑最后一项是不可点的页面标题（16px/600），分类徽标跟在其后；右侧依次为连接状态、信息（阶段 B）、外观菜单、任务 | 标题在标题区 | 当前位置就是标题，不重复 |
| 工具栏 | 左：浏览/整理下划线页签、继续浏览或返回、名称与计数；右：缩略图大小、文件夹状态、选择、更多 | 分散在标题区与状态栏 | 命令就近，顺序固定 |
| 收起规则 | 按内容区宽度（容器查询）：≤1099 文件夹状态只留图标；≤899 整理子工具只留图标，隐藏“第 N 张”；≤719 文件夹状态和尺寸移入“更多”，隐藏计数；≤599 收紧间距，隐藏按钮次要文字（`.label-wide`）和模式页签图标 | 按视口 | 侧栏开合时也能正确收起 |
| 菜单 | 无遮罩；在外部按下、Tab、Escape 关闭；Escape 只关菜单，不会同时退出选择；方向键、Home、End 移动焦点 | 遮罩层 | 桌面菜单不锁住背景 |
| 图包封面 | 3:4 竖幅，文字区 52px 两行 | 4:3，66px | 图包封面以竖图为主，裁切更少 |
| 图片格 | 1:1 完整显示（contain），下方常驻 56px 说明区：文件名 / 宽×高 · 大小 | 文字区 66px | 两行信息够用，同屏多放图片 |
| 卡片状态 | 无边框，悬停换底色；选中为 14% 强调色底 + 2px 强调描边 + 勾选圈；刚看过为 2px 外框；键盘焦点为 2px 黑/白焦点环 | 青绿边框 | 选中、最近和焦点三种状态互不混淆 |
| 抽样 | 并入“整理 → 抽样”；旧 `…/samples` 深链改写为 `…/organize/t/samples`；整理记住上次子工具（sessionStorage `gt.organizeTab`） | 独立视图 | 浏览只保留一个入口，抽样属于整理工具 |
| 命名 | “文件夹状态”（原“整理状态”），只在文件夹层级出现 | — | 与图片标签区分 |
| 查看器顶栏 | 52px，与位置栏同高 | 56px | 统一节奏 |

生产令牌以 `ui/src/styles/base.css` 为准。`tokens.css` 与样机保留作参考，不改。

## 进度

已完成，未提交：

- `ui/index.html`：`color-scheme` 改为 `light dark`；内联脚本读取 `gt.theme`。
- `ui/src/styles/base.css`：新语义令牌（`light-dark()`），旧令牌已全部替换。
- `ui/src/styles/shell.css`、`walls.css`、`viewer.css`、`organize.css`：按新令牌与框架重写。
  - 已删除：`.page-head`、`.group-head`、`.wall-bar`、`.menu-scrim`、`.org-tabs`、`.btn.resume`。
  - 已新增：`.toolbar*`、`.menu*`、`.at-wide`/`.at-narrow`、`.tool-tabs`、`.sample-controls` 和容器查询。
- `ui/src/lib/icons.tsx`：新增 Ellipsis、Monitor、Moon、PanelRight、Sun；线宽改为 1.65。
- `ui/src/lib/router.ts`：
  - `GroupView` 只剩 `packages | organize`，`OrganizeTab` 增加 `samples`，新增 `lastOrganizeTab()`；
  - 旧 samples 深链会被改写；
  - 从整理页关闭查看器时去掉 package。
- `ui/src/state/app.ts`：新增 `theme` 信号（`system | light | dark`）。
- `ui/src/components/Menu.tsx`（新）：通用菜单按钮，行为见上表“菜单”一行。

**当前是迁移中间态。** 组件还没接上新样式和路由，`npm run ui:check` 报 6 处与 `samples` 相关的类型错误：App.tsx:73、GroupHeader.tsx:35、Topbar.tsx:15、Samples.tsx:72、Viewer.tsx:112、Viewer.tsx:328。页面上旧的标题区、工具条和菜单遮罩已经没有样式。完成 A1 之前不要构建，也不要切换入口。`npm run check` 只检查契约，不受影响。

## A1. 接上框架

先做这一步；做完后 ui:check 与 ui:build 应通过。

### 1. `components/Topbar.tsx`

- 去掉缩略图尺寸分段，它移到工具栏。
- 面包屑为 图库 › 文件夹 › 图包：
  - 图包项只在 `r.package && r.view === 'packages'` 时出现，散图包显示“散图”。
  - 最后一项渲染为 `<span class="crumb" aria-current="page" title=完整名称>`，其余项为 `button.crumb`。
  - `narrow` 且已进入文件夹时，不显示图库项。
  - 分隔符为 `ChevronRight` 14 `.crumb-sep`。
- 面包屑之后：分类徽标 `badge category`，category 为“其他”时不显示。然后是 spacer。
- 右侧依次为：
  - 连接状态 `.conn`，只在非 online 时显示。
  - `<Menu label="外观">`：
    - 触发图标随当前值变化：跟随系统为 Monitor，浅色为 Sun，深色为 Moon。
    - 菜单内是 `.menu-label`“外观”和三个 `menuitemradio`（跟随系统、浅色、深色）。
    - 每项都有 `aria-checked`，尾部带 `Check` 图标 `.menu-check`，点击时写 `theme.value`。
  - 任务按钮 `btn subtle tasks-btn`：
    - 内容为 `ListChecks` 16、`<span class="tasks-label">任务</span>`，活动数用 `.count-badge`。
    - `aria-label` 为“后台任务”，带 `aria-expanded`。

### 2. `components/GroupHeader.tsx`

删除 `GroupHeader` 组件和 `VIEWS`。保留 `Resume`、`useResume`、`prewarm`、`groupOf`。新增以下导出：

- `ModeTabs()`：`nav.tabs[aria-label=模式]`。
  - 浏览（LayoutGrid）导航到 `{library, group}`。
  - 整理（ScanSearch）导航到 `{library, group, view: 'organize', tab: lastOrganizeTab()}`。
  - 当前项加 `active` 与 `aria-current="page"`，点击当前项不导航。
- `ResumeButton({resume})`：`btn subtle small`。
  - 内容为 History 14、`<span class="label-wide">继续浏览</span>`、`<span class="muted resume-pos">第 N 张</span>`。
  - title 为“上次看到：图包 · 文件名”，图包名经 `cachedPackage` 取得。
- `SizeSegment({class})`：`div.segment.tile-size`，`role=radiogroup`，`aria-label` 为“缩略图大小”。
  - 三个 radio：小、中、大，title 为“X缩略图”。
- `NarrowMarks({group})` 和 `NarrowSizes()`：`div.at-narrow[role=group]`。
  - 内含 `.menu-label`（aria-hidden）、若干 `menuitemradio`（尾部 `.menu-check`），最后一个元素是 `div.menu-sep[role=separator]`。
  - 状态项调用 `applyMark`。
  - 宽屏时整组隐藏，Menu 会跳过不可见项。
- `GroupMenu({group, lib, children})`：`<Menu label="更多操作">`。项目顺序：
  1. children（窄屏折叠项）。
  2. 重新扫描此文件夹（RefreshCw）。
  3. 预先生成缩略图（Sparkles）。
  4. 有 `group.rel` 时：分隔线，然后危险项“删除整个文件夹…”。`requestDelete` 参数照搬原实现，完成后回到图库。

### 3. `components/Selection.tsx`

- `SelectionBar` 改为渲染 `.toolbar`，并新增 `before`、`after` 插槽。
- 非选择状态：依次为 children、spacer、before、选择按钮、after。
  - 选择按钮为 `btn subtle small`，图标改用 `SquareCheck`（加入 icons.tsx），文字放在 `.label-wide` 里。
  - `ListChecks` 只留给后台任务，避免一个图标两种含义。
- 选择状态：`.toolbar.selecting[role=toolbar]`，依次为已选 N、清空（subtle）、spacer、删除…（danger）、完成。

### 4. `components/Marks.tsx` 与 `components/Sidebar.tsx`

- `MarkSegment` 接受 `class`，`aria-label` 改为“文件夹状态”。
- `MarkSegment` 新增 `shortcuts` 开关，只有查看器传入。按钮 title 里的（K）（M）（U）只在查看器显示，因为这三个键只在查看器生效；图片墙上只显示“保留”等名称。
- `Sidebar.tsx` 中状态筛选 select 的 `aria-label` 同样改为“文件夹状态”。

### 5. `App.tsx`

- 去掉 GroupHeader 和 Samples 分支，`Content` 只渲染 `GroupBody`。
- 骨架屏在 `.wall-hold` 之前放一个空的 `.toolbar`。

### 6. `views/LibraryHome.tsx`

`page-head` 换成 `.toolbar.wrap`，依次放：

- 扫描状态；
- `.at-wide` 上次扫描时间；
- `.toolbar-count` 文件夹数，有筛选时注明；
- spacer、FilterBar、SizeSegment；
- 重新扫描按钮（subtle small，文字在 `.label-wide` 里）。

### 7. `views/PackageWall.tsx`

`SelectionBar` 的三个插槽：

- children：ModeTabs、`.toolbar-sep`、ResumeButton。
- before：图包数，`.toolbar-text.toolbar-count`。
- after：`SizeSegment.at-wide`、`MarkSegment.at-wide`、`GroupMenu`（children 为 NarrowMarks 与 NarrowSizes）。

### 8. `views/ImageWall.tsx`

左侧先放 ModeTabs 和分隔线，之后按模式分开：

| | `inline`（文件夹只有一个包） | 非 `inline` |
| --- | --- | --- |
| 左侧其余部分 | ResumeButton | “← 图包”返回按钮、`.toolbar-title` 图包名（title=rel）、`.at-wide` 父路径、计数 |
| after | `SizeSegment.at-wide`、`MarkSegment.at-wide`、GroupMenu | `SizeSegment.at-wide`、`<Menu label="更多操作">` |

非 `inline` 的“更多操作”菜单包含“删除此图包…”（非散图时）和 NarrowSizes。

删除 `wall-title`、`wall-sub` 和删除图标按钮。

### 9. `views/Organize.tsx`

- TABS 依次为：抽样（Dices）、相似图包（Images）、整包核验（GitCompare）、清理检查（ShieldAlert）。
- `tab = route.tab ?? lastOrganizeTab()`，变化时写入 sessionStorage `gt.organizeTab`。
- 工具栏依次为：
  - ModeTabs、分隔线；
  - `nav.segment.tool-tabs`：用 replace 导航，当前项 `active` + `aria-current`，带 title；按钮文字包在 `<span>` 里，≤899 时容器查询靠它收成图标；
  - spacer、`MarkSegment.at-wide`、GroupMenu（children 为 NarrowMarks）。
- 抽样页渲染 `<Samples>`，放在 `.org-scroll` 之外，它自带滚动。

### 10. `views/Samples.tsx`

- 点样张进入 `{view: 'organize', tab: 'samples', package, image}`。
- `.wall-bar` 改为 `.sample-controls`。
- 保持 20/40/100 选项；seed 仍按文件夹存在 sessionStorage，关闭查看器后回到同一批。
- 卡片须注明所属图包（requirements 第 105 行）。

### 11. `views/Viewer.tsx`

删除 samplesMode 分支，然后：

- 前后图一律用 context 的 `previous_id`/`next_id`，只在包内。
- `go` 保留当前 view/tab，替换 package/image。
- 删除后取 `next_id ?? previous_id`。
- 只在 `view === 'organize' && tab === 'samples'` 时不写继续位置。
- 有 package 就显示胶片条。
- 删除“在图包中查看”。
- 边界提示只保留包内两句：“已是本图包第一张”和“已是本图包最后一张”。到边界后手动去下一个图包的功能保留。删去抽样批次的三句提示。

### 12. 可选：`electron/main.js`

按 `nativeTheme` 设置窗口背景（浅 `#f4f5f6`，深 `#1b1d1f`），改完运行 `node --check`。

### A1 验收

- ui:check、ui:build 通过。
- 下面的残留检查应无输出。令牌名后带 `\b`，所以 `--warning`、`--sidebar-width` 等新令牌不会误报。目前的命中都在 A1 要改的六个文件里。

  ```bash
  rg -n -e '--(bg|text-2|text-3|line-2|ok|warn|bad|accent-strong|radius-s|radius-l|bar-h|sidebar-w)\b' -e 'wall-bar|menu-scrim|page-head|group-head|org-tabs|samplesMode|view: .samples.' ui/src
  ```
- 用临时图库在 1440、1024、720、390 宽和浅/深主题下检查：
  - 工具栏不溢出；
  - 菜单可用键盘操作；
  - 选择模式中按 Escape 先关菜单，再按才退出选择；
  - 切换主题时 Network 中没有新的缩略图请求；
  - `#/l/<库>/g/<文件夹>/samples` 会跳到抽样页。
- 完成后把框架变化同步到 `docs/frontend-ui.md`。

## B–E 的修订要点

未列出的内容按 delivery.md 中 B–E 与 requirements.md 执行。

### B. 浏览与位置

- **图包入口**：点图包卡片进入该包的图片墙。角按钮改为“从封面开始查看”（Maximize），直接打开查看器。“第 N 张”芯片保持直接进入查看器。
- **网格列宽**：桌面目标列宽为小 180 / 中 230 / 大 310（`LibraryHome.tsx` 的 `TILE`）。窄屏的 `NARROW_TILE` 不变。
- **图片格**：
  - 1:1 媒体格，使用 `.thumb.fit-contain`。
  - 常驻 56px 说明区：
    - 第一行是 `name`，13px/500，单行省略，title 为完整名；
    - 第二行是 `width×height · size`，12px muted；尺寸为 null 时只显示大小。
  - 坏图在媒体格内报错，文件名照常显示。
  - 删除悬停渐显的 `.card-caption`。
  - 虚拟网格行高为“列宽 + 56 + 间距”，用准确的行高函数计算。
- **信息面板**：
  - 入口：位置栏“信息”按钮（PanelRight，`aria-pressed`），只在文件夹和图包页出现。放在外观菜单左侧，这样它在图库首页隐藏时，外观和任务按钮不会移位。
  - 形态：桌面为 280px 非模态右栏；860px 以下为模态抽屉。
  - 内容：选中一项或焦点在某项时，显示该图片的 name、rel（可选中复制）、尺寸、大小、动图、错误；多选时显示数量；什么都没选时显示当前文件夹或图包。
  - 开关状态存 localStorage。开关面板不重建图片请求。
- **选择**：
  - Shift+单击选择上次点击项到当前项之间已加载的连续项，不跨未加载页。
  - 工具栏增加“选中可见项”。
  - 超出 500 项时给出提示。

### C. 查看器

- 顶栏 52px：第一行文件名，第二行“图包 · 第 N / M 张”。
- 透明图下方垫棋盘格。
- 信息按钮用 PanelRight，与图片墙一致。
- 胶片条当前项为 2px 强调描边，并带 `aria-current`。
- 现有的渐进加载、动图和请求预算保持不变。

### D. 整理、任务、删除

`organize.css` 已按新令牌重写；行为照 requirements 执行。几处要点：

- 任务抽屉桌面宽 360px（`--task-width`），非模态。
- 删除默认进回收站；永久删除需要勾选确认，并使用红色主按钮。
- 结果逐项列出，失败项可以“只重试失败项”。

### E. 集成与交付

按 delivery.md 的 E 节执行：全量检查、`scripts/build.ps1`，验证实际 Electron 产物后再切换入口。
