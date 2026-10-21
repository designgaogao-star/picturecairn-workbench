# 正式前端实施与验收

## 契约对应

所有请求通过 `contracts/client.ts` 和现有 `api.ts`。`contracts/schema.d.ts` 不手改。下表是核对当前 OpenAPI 后可直接实施的范围。

| 设计对象 | 当前 API / 字段 | 实施注意 |
| --- | --- | --- |
| 图库与添加 | `GET/POST /libraries`，Library 的 name/path/online/scan_status | 桌面沿用 `window.galleryApp.chooseDirectory()`，取消不清空手输内容 |
| 文件夹列表与组合筛选 | `GET /libraries/{id}/groups?offset&limit&state&category` | 侧栏计数取 image_count；category 是 R16/R18/非R18/其他，不新增风景、建筑标签 |
| 文件夹详情、封面 | `GET /groups/{id}`，cover_id/cover_version | 深链按 ID 读取，不遍历全库寻找名字，不逐项查询封面 |
| 图包墙 | `GET /groups/{id}/packages`，Package.rel/loose/cover_id | 缩略图主入口改为图片墙；保留散图限制 |
| 图片墙与附近定位 | `GET /images/{id}/context` 的 index，再 `GET /packages/{id}/images?offset&limit` | 以 index 计算目标页 offset，配合 Page.total/revision 恢复，不新增 anchor_id 参数 |
| 查看器 | `GET /images/{id}/context`，previous_id/next_id/index | 方向与边界由上下文决定，不按文件名猜下一个 |
| 图片资源 | `GET /images/{id}/thumbnail?edge&version`、`/original` | 静态封面与原图动画分开，保留内容版本缓存与请求预算 |
| 继续位置与文件夹状态 | `GET/PATCH /groups/{id}/review`、`PUT /groups/{id}/position` | review 读取状态和 image_id，PATCH 改状态，PUT position 写位置，没有 GET position |
| 抽样 | `GET /groups/{id}/samples?count&seed` | 固定本批 seed，返回本批不能重新随机 |
| 相似候选 | `POST /tasks` kind=analyze；task findings/pairs | 分别展示左右匹配率、覆盖率，不推导内容重复 |
| 内容核验 | `POST /tasks` kind=compare；CompareResult | 全部文件、独有文件分页、revision 过期检查继续保留 |
| 清理检查 | `POST /tasks` kind=audit | 只读检查不等于自动删除 |
| 任务与控制 | `/tasks`、`/tasks/{id}`、`/control` | targets.label/rel 可直接显示；状态/类型/图库筛选和历史分页不能丢失 |
| 删除与操作历史 | `POST /operations/delete`、`GET /operations` | 返回任务，不是完成；逐项结果、回收失败、永久确认必须保留 |
| 缓存与事件 | `GET /cache`、task kind=collect、`GET /events` | SSE 重连读取快照；缓存预算继续 12 GiB 默认 |

上表路径省略统一 `/api/v1` 前缀，路径参数名字按生成类型填写，不照抄简写 `{id}`。

### 没有承诺的能力

`GET /libraries/{id}/directories?parent_id=...` 可以列目录，但当前图包清单没有 directory_id 筛选参数，目录项本身也没有“进入后应列哪些图片”的完整 UI 契约。因此本轮不画任意层级目录树、不自行在前端全量过滤图包。

没有全局搜索或日期/大小排序接口。只显示现有顺序，不放一个实际只筛当前页的搜索框。样机中的名称、范围和数量是固定夹具，不能用它补造服务端能力。

## 分阶段实施

共享分支仍为 `feat/backend-v2`。每阶段保持能运行，只提交本人修改。实现文档变更同步到 `docs/frontend-ui.md`；正式完成前不要把新设计写成当前已上线行为。

### A. 主题与框架

涉及 `ui/src/styles/base.css`、`shell.css`、`App.tsx`、`Topbar.tsx`、`Sidebar.tsx`、`GroupHeader.tsx`、`state/app.ts`。

- 引入语义变量，映射现有 --bg/--text 等变量，逐步替换，禁止两套令牌长期并行。
- 增加浅/深/系统外观偏好，使用独立的设置键；保留路由、图库与位置记录。
- 明确位置栏、标题/模式区与上下文工具栏职责；抽样入口移到整理子页，保留旧 samples 深链的有效跳转。
- 侧栏保留图库选择、状态与分类的组合筛选；信息与任务入口有名称和当前打开状态。
- 验收：四种尺寸无溢出，两种主题无旧蓝灰硬编码残留，桌面目录选择和浏览器手输都能使用。

### B. 浏览与位置

涉及 `PackageWall.tsx`、`ImageWall.tsx`、`LibraryHome.tsx`、`Selection.tsx`、`VirtualGrid.tsx`、`walls.css`、`lib/router.ts`。

- 图包主入口打开图片墙，继续浏览保持直接进入原图片。
- 图片完整显示与常驻名称；图包 4:3、图片媒体格 1:1，更新虚拟网格的准确行高函数。
- 选中工具栏原位替换；保留 500 上限和散图规则，补齐清空、范围选择与可见项语义。
- 信息面板展示当前聚焦/选择资源；没有资源选择时展示当前文件夹，不默认谎称第一张为已选资源。
- 以持久 ID 恢复锚点，检查切换列数与关闭查看器后的位置；不重写已有分页调度。
- 验收：横图、竖图、长名、同名多路径、坏图、未知尺寸、8,000+ 图包分页和快速切换都正常。

### C. 查看器

涉及 `Viewer.tsx`、`Filmstrip.tsx`、`viewer.css`、`lib/preview.ts` 和必要的状态适配。

- 深色完整画布、透明棋盘、元数据、缩放和有界胶片条；沿用渐进加载、原图动画和请求预算。
- 焦点返回最近资源；Escape、左右键、适应/100% 和包边界一致。
- 验收：GIF/WebP 实际播放、透明 PNG、坏图、超大横/竖图、连续快切、包头包尾、刷新与桌面重启恢复。
- 不因原型只有 8 张图而去掉虚拟化，不在主题切换时重新下载原图。

### D. 整理、任务与决策

涉及 `Organize.tsx`、`Samples.tsx`、`Compare.tsx`、`Audit.tsx`、`organizeParts.tsx`、`TasksDrawer.tsx`、`DeleteDialog.tsx`、`Dialog.tsx` 和对应样式。

- 整理四个子工具按同一作用域呈现，保留原有参数与结果分页。
- 候选、核验、过期结果与各有独有文件有不同结论；只在适用时提供基于核验的回收入口。
- 桌面面板非模态，窄屏抽屉模态；任务关闭不取消，受理与最终结果分开。
- 删除默认回收站、永久二次确认、逐项报告、只重试失败项；不增加无协议支撑的撤销。
- 验收：读取失败/取消/中断/离线/部分删除失败可恢复，非图片文件不丢失，正常维护历史仍可查。

### E. 集成与交付

涉及 `scripts/ui-qa/` 与 `docs/frontend-ui.md`，如需构建只使用 `scripts/build.ps1`。

每阶段运行相关检查，最终执行仓库约定：

```powershell
npm run ui:check
npm run ui:build
npm run check
.venv/Scripts/python.exe -m pytest
.venv/Scripts/python.exe -m ruff check .
```

改过的原生 JS 另跑 `node --check <文件>`。只有 API 改变时才重新生成契约；本轮设计本身不需要修改 API。

实际桌面包用统一构建脚本生成，按 `scripts/ui-qa/README.md` 对临时图库验收。UI 切换不停止他人进程，不写真实数据目录，不清空用户缓存和位置。`prototype/` 是否删除仍由用户决定。

## 完成条件

- [ ] A–D 每阶段的交互已真实接入当前客户端，没有只改静态 CSS 的半成品。
- [ ] 1440×1000、1280×800、1920×1080、390×844 与浅/深主题截图完成，文字、按钮、图片和浮层无错位。
- [ ] 对比 `requirements.md` 的所有状态，有明确触发方式和可观察结果，不依赖几秒钟的 Toast 保存错误。
- [ ] 真实大图库只读副本验证：DOM/图片请求有界、快速滚动取消过期请求、重连读快照、定位和恢复稳定。
- [ ] 基于同素材/相同缓存状态比较改版前后首屏、查看器冷/热切图和内存；不把不同硬盘/缓存的数字直接比较。
- [ ] 既有性能门槛未退化：已有索引就绪目标 ≤2s，扫描时健康接口 P95 ≤50ms，100 条清单 P95 ≤100ms，热缩略图 P95 ≤50ms。记录 UI 可见首屏及 P50/P95，不用静态样机测量代替。
- [ ] 临时库完整验证添加、浏览、动画、位置恢复、任务、回收失败、永久确认和逐项删除结果。
- [ ] 完成实际包验证与 review 后再切换当前入口，Git 不提交 `ui/dist`、`node_modules`、输出、私密数据或真实截图。
