# 前端交接

正式前端负责布局、视觉、交互细节和前端状态管理；后端负责索引、文件访问、图片派生、用户记录、任务和整理判据。现有原型仅用于验证这些接口。

## 联调

后端 `http://127.0.0.1:8765`，OpenAPI 在 `/openapi.json`，所有业务接口在 `/api/v1`。重新生成契约用 `npm run contract`；不要手动编辑生成的 schema.d.ts。

`contracts/client.ts` 使用生成的路径、参数、请求体和成功响应类型，支持 AbortSignal。图片 URL 由客户端的 thumbnail/original 方法构造。所有图片请求都走后端，前端不读取文件系统、不拼接原图绝对路径。

## 浏览流程

1. GET libraries 获取分页的图库清单；POST libraries 注册用户选中的目录，随后后台扫描。目录名称可重复，始终使用 ID。
2. GET libraries/{id}/groups，支持 state/category 筛选；GET groups/{id}/packages。
3. GET packages/{id}/images 获取当前页；GET images/{id}/context 获取包内前后 ID、所在下标和图片信息。
4. PATCH groups/{id}/review 保存整理状态；PUT groups/{id}/position 保存 image_id。重新打开组时读取 review，再通过 context 定位。

所有 Page 响应使用 items、total、offset、limit、revision。默认 100、最多 500 条。revision 改变时重新读取受影响的可见页；不要预先下载整组清单。根目录散图使用 loose 图包，不允许按图包删除它。

revision 表示关联图库的索引版本；跨图库的图库列表、任务和操作日志返回 0，按 SSE 通知重新读取快照。每条 Library 自身仍提供对应索引版本。抽样接口按 count 返回至多 100 张图片，不使用分页。

width、height、animated 首次可能为 null；封面生成后补齐。图片墙请求 400/800，查看器选满足视口的最小预览档位，原图供细看和动图播放。mtime_ns 是后端版本信息，不要在 JavaScript 中对其做精确整数计算或用它自行生成缓存键。

上下文 previous_id/next_id 为 null 即图包边界，不允许自行跳到另一图包。图片被删除时上下文返回 404；回到图包或读取仍存在的相邻 ID。维护有界 DOM、分页缓存、胶片条与预载，快速切换时取消或忽略旧请求。

## 任务与事件

POST tasks 接收带 kind 的联合类型：scan、prewarm、build、analyze、compare、audit、collect。DELETE 操作通过 POST operations/delete 创建任务；成功受理返回 202 和任务对象，不能当成文件已操作成功。

queued → running → completed/failed；pause/resume 在 paused 和 running 间切换；cancel 导致 cancelled，可能先显示 cancelling。删除任务不可暂停，可在项目之间取消。任务中已完成的文件操作不因取消而回滚，逐项结果及 operations 日志是判断依据。重启后的未完成任务为 interrupted，可重新提交。

SSE events 发送 snapshot、task、catalog、review、reset。事件是失效通知，收到后读取相应快照；重连收到 snapshot 时重新读取当前图库与任务。事件缓冲最多 256 项，落后太远发送 reset，不能把它当可靠消息队列。

413/422 表示请求或图片无法处理，404 表示资源消失，409 表示状态冲突或文件发生变化，503 表示队列已满或正在停止。图像失败在 UI 上显示错误状态，并允许查看原图；不要把解码失败伪装为成功的灰色图片。

## 整理与证据

GET groups/{id}/samples 提供带 seed 的可重复抽样。build 补齐该组新规范的 pHash；analyze 返回相似度与覆盖率，逐图片候选通过 tasks/{id}/pairs 分页读取。

compare 接收同组的 left_id/right_id 图包，刷新目录后对所有文件做 SHA-256。exact_equal 与 left_contained/right_contained 具有不同含义；左右 unique 各提供前 100 项和 total，剩余通过 tasks/{id}/findings?kind=left_unique/right_unique 分页获取。revision 表示证据生成时版本，执行整理前应关注后续内容变化。

audit 检查空壳、残缺与广告图，result 中各类只预览前 100 项；完整列表通过 findings 的 shell/advertisement/incomplete 类型分页获取。verified 代表哈希来源验证，不代表“可以放心整包删除”；非图片文件仍可能是独有内容。

默认回收站删除。永久删除必须明确设置 permanent 与 confirm_permanent 为 JSON true。删除后检查任务 result.failed、逐项 state 和 error；无法回收不会永久删除，也不能把任务受理或 completed 状态单独当成所有项目成功。取消或中断后可通过 operations?task_id={id} 查询已执行项目。

原型没有完整呈现去重证据与所有整理操作；正式前端可直接使用这些已实现的类型化接口。前端选用框架可独立决定，无需更改后端文件系统和数据库逻辑。
