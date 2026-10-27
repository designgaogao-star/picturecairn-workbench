# 前端交接

正式前端位于 `ui/`，沿用 Preact 10、Signals、Vite、严格 TypeScript 和现有 Lucide；负责布局、视觉、交互细节和前端状态管理。后端负责索引、文件访问、图片派生、用户记录、任务和整理判据。界面行为见 [当前 UI 说明](frontend-ui.md)，设计修订以 [图片工作台交接](design/image-workbench/handoff.md) 为准；`prototype/` 保留为历史参考。

## 联调

首份 [Windows 开发预览](https://github.com/designgaogao-star/picturecairn-workbench/releases/tag/preview-20261026-28faca1) 已公开，但它是品牌迁移前的 Stillmark 历史包；当前源码和未发布候选使用 PictureCairn。API 的产品版本字段仍使用构建时的开发占位值；`api_version: "1"` 与 `/api/v1` 表示接口契约编号。

联调使用独立临时数据目录，以 `--port 0 --ready-file <临时就绪文件>` 启动后端，从该文件读取实际回环地址，并通过 `GALLERY_BACKEND` 传给 Vite。Vite 未设置该变量时默认代理到 `http://127.0.0.1:8765`；联调时用本轮临时后端的实际地址覆盖。OpenAPI 在 `/openapi.json`，所有业务接口在 `/api/v1`。重新生成契约用 `npm run contract`；不要手动编辑生成的 schema.d.ts。

`contracts/client.ts` 使用生成的路径、参数、请求体和成功响应类型，支持 AbortSignal。图片 URL 由客户端的 thumbnail/original 方法构造。所有图片请求都走后端，前端不读取文件系统、不拼接原图绝对路径。

正式桌面前端位于 `ui/`，后端托管 `ui/dist`，统一构建脚本会先执行 `npm run ui:build`。客户端构造函数的第二个可选参数是 HTTP transport；正式前端在这里统一拦截开发模式 `?readonly` 的所有非 GET 请求，生产构建不启用此开关。

## 浏览流程

1. GET libraries 获取分页的图库清单；POST libraries 注册用户选中的目录，随后后台扫描。目录名称可重复，始终使用 ID。
2. GET libraries/{id}/groups，支持 state/category 筛选；GET groups/{id}/packages。
3. GET packages/{id}/images 获取当前页；GET images/{id}/context 获取包内前后 ID、所在下标和图片信息。
4. PATCH groups/{id}/review 保存整理状态；PUT groups/{id}/position 保存 image_id。重新打开组时读取 review，再通过 context 定位。

所有 Page 响应使用 items、total、offset、limit、revision。默认 100、最多 500 条。revision 改变时重新读取受影响的可见页；不要预先下载整组清单。根目录散图使用 loose 图包，不允许按图包删除它。

GET groups/{id} 和 GET packages/{id} 可直接恢复深链，不再需要分页查找。Group 和 Package 都携带 cover_id、cover_version；Group 同时提供 resume_image_id。不存在的资源返回 404；离线图库保留索引供浏览。

revision 表示关联图库的索引版本；跨图库的图库列表、任务和操作日志返回 0，按 SSE 通知重新读取快照。每条 Library 自身仍提供对应索引版本。抽样接口按 count 返回至多 100 张图片，不使用分页。

width、height、animated 首次可能为 null；封面生成后补齐。图片墙请求 400/800，查看器选满足视口的最小预览档位，原图供细看和动图播放。mtime_ns 是后端版本信息，不要在 JavaScript 中对其做精确整数计算或用它自行生成缓存键。

ImageItem.version 是后端生成的不透明字符串。thumbnail(id, edge, version) 使用长缓存 immutable，版本不符返回 409；未带 version 的 URL 保留条件请求。封面用 cover_version。缩略图由有界 fetch 直接读取 HTTP 失败原因，Blob URL 在卸载时释放；大原图仍使用 img，避免先把整文件读入 Blob 才显示。

上下文 previous_id/next_id 为 null 即图包边界，不允许自行跳到另一图包。图片被删除时上下文返回 404；回到图包或读取仍存在的相邻 ID。维护有界 DOM、分页缓存、胶片条与预载，快速切换时取消或忽略旧请求。

## 图库管理

- `GET libraries/{library_id}` 获取单个受管理图库。
- `PATCH libraries/{library_id}` 接受 `{name}`，去除首尾空白，长度 1–120；只修改显示名，不改磁盘目录、不扫描。
- `POST libraries/{library_id}/reconnect` 接受 `{path}`，验证本地、存在、与其他管理中图库不重叠；返回 `202 Task`，随后对账。迁移前后的相对路径一致时沿用目录、图包和图片 ID，保留位置与标记；revision 递增会使旧核验失效。
- `DELETE libraries/{library_id}` 返回 204，只移出工作台。原图、索引、缓存、位置、标记和操作日志保留，重新 POST 原路径恢复原 ID。移出后资源、标记和新任务入口返回 404，历史任务与操作日志仍可查询。

重连、移出时如有关联任务处于 queued/running/paused/cancelling，返回 `409`，结构化错误 code 为 `library_busy`。前端提示处理后台任务后重试；不能悄悄取消文件操作。其他 409 仍表示路径重叠或占用，不应一律引导到任务抽屉。队列满或停止中的注册/重连返回 503，根路径不会半更新。路径被另一个历史图库占用时不能合并 ID，应重新添加对应原目录。

入口位于图库首页工具栏和侧栏文件夹标题旁的“管理图库”菜单；离线横幅提供“重新定位目录…”。桌面重连复用目录选择 IPC，普通浏览器允许手工输入。移出最后一库回到添加表单并清除旧路由；只读开发模式仍由统一 transport 拦截三个写入口。

## 任务与事件

POST tasks 接收带 kind 的联合类型：scan、prewarm、build、analyze、compare、audit、collect。DELETE 操作通过 POST operations/delete 创建任务；成功受理返回 202 和任务对象，不能当成文件已操作成功。

Task.targets 附带 kind/id/label/rel/library_id/group_id，scope 提供任务所属图库和分组；trigger 为 user/startup/watcher/maintenance/legacy。GET tasks 支持 kind、state、library_id、active、offset、limit，历史不能只保留最近 50 条。完成后 progress/total/current 继续保留。

queued → running → completed/failed；pause/resume 在 paused 和 running 间切换；cancel 导致 cancelled，可能先显示 cancelling。删除任务不可暂停，可在项目之间取消。任务中已完成的文件操作不因取消而回滚，逐项结果及 operations 日志是判断依据。重启后的未完成任务为 interrupted，可重新提交。

预热的暂停在图片边界生效，当前图片会先完成并释放解码预算和生成锁，避免暂停任务挡住前台浏览。paused 表示已接受暂停，不能据此认定正在进行的原生解码或编码被立即抢断。取消会在资源等待和处理检查点响应；已生成的缓存保留。

SSE events 发送 snapshot、task、catalog、review、reset 和 ping（15 秒无其他事件时，附 Unix 时间戳）。catalog 带 library_id、group_ids、package_ids，按范围使列表失效；范围缺失时全库刷新。事件是失效通知，收到后读取相应快照；重连收到 snapshot 时重新读取当前图库与任务。事件缓冲最多 256 项，落后太远发送 reset，不能把它当可靠消息队列。前端 45 秒没有任何事件时主动重连。

413/422 表示请求或图片无法处理，404 表示资源消失，409 表示状态冲突或文件发生变化，503 表示队列已满或正在停止。图像失败在 UI 上显示错误状态，并允许查看原图；不要把解码失败伪装为成功的灰色图片。

HTTP 错误使用 {error:{code,message,path}}；path 可以为 null，UI 显示 message。CacheStats 有 count/bytes/limit。任务控制的非法状态统一返回 409。

## 整理与证据

GET groups/{id}/samples 提供带 seed 的可重复抽样。build 补齐该组新规范的 pHash；analyze 返回相似度与覆盖率，逐图片候选通过 tasks/{id}/pairs 分页读取。

Pair 带 left_package_id/right_package_id。相似图包结果内嵌前 500 条，完整结果通过 findings?kind=package_pair 分页；旧任务未存储的超出部分需重新分析。

compare 接收同组的 left_id/right_id 图包，刷新目录后对所有文件做 SHA-256。exact_equal 与 left_contained/right_contained 具有不同含义；左右 unique 各提供前 100 项和 total，剩余通过 tasks/{id}/findings?kind=left_unique/right_unique 分页获取。revision 表示证据生成时版本，执行整理前应关注后续内容变化。

audit 检查空壳、残缺与广告图，使用独立 AuditJob 输入，不接受 threshold。证据图片有 name/package_id；result 中各类只预览前 100 项，完整列表通过 findings 的 shell/advertisement/incomplete 类型分页获取。verified 代表哈希来源验证，不代表“可以放心整包删除”；非图片文件仍可能是独有内容。

默认回收站删除。永久删除必须明确设置 permanent 与 confirm_permanent 为 JSON true。删除后检查任务 result.failed、逐项 state 和 error；无法回收不会永久删除，也不能把任务受理或 completed 状态单独当成所有项目成功。取消或中断后可通过 operations?task_id={id} 查询已执行项目。

正式前端已使用这些类型化接口呈现相似候选、完整核验、清理证据、逐项删除和任务控制；后续修改继续遵守当前图片工作台布局、现有技术栈和有界资源规则。新增接口需求先核对 `contracts/client.ts`，再按 [接口缺口](frontend-gaps.md) 的现有格式记录。
