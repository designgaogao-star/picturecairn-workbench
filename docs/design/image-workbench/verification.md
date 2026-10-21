# 设计包验证记录

日期：2026-10-22。检查对象是本目录的独立设计样机及交接文档，**不代表正式前端已经完成改版**。

## 本轮结果

| 检查 | 结果 |
| --- | --- |
| Edge 155.0.4283.62，Playwright 本地文件打开 | 111 项断言通过 |
| 浏览器异常、控制台错误/图标缺失警告 | 0 |
| 样机发出的 HTTP 请求 | 0；全部资源从设计包本地加载 |
| 设计包内部相对链接 | 34 个目标均存在 |
| 1440×1000、1280×800、1920×1080、390×844 | 页面、主内容、控件无横向溢出，卡片文字不溢出 |
| 390px 超长中文＋连续英文名称 | 核验与相似页均通过，不撑宽工作区 |
| 浅/深主题语义对比 | 22 项组合通过；正文最低门槛 4.5:1，关键边界/焦点 3:1 |
| 新增 app.js、data.js、verify.cjs 的 node --check | 通过 |
| npm run ui:check、npm run check | 通过 |
| .venv/Scripts/python.exe -m pytest | 70 passed，44.03s |
| .venv/Scripts/python.exe -m ruff check . | All checks passed |

测试入口：

```powershell
node docs/design/image-workbench/verify.cjs
```

机器记录：[verification.json](../../../output/playwright/workbench-design/verification.json)。输出目录被 Git 忽略；换机器后重新运行即可生成。

## 已验证的交互

- 图包主入口进入图片墙，图片墙默认完整显示；可见照片实际解码，图标实际渲染。
- 查看器方向键、包末停止、关闭后的焦点与最近图片标记、继续浏览、刷新恢复同一图片。
- 浅/深主题切换和 22 个令牌对比组合。
- 任务暂停有待确认与最终状态，继续与取消保留最后处理数量。
- 尚未核验、核验完成、包含非图片文件、各有独有内容、结果过期的不同表达；相似候选不带删除捷径。
- 抽样数量有界，清理检查保留文本文件详情。
- 删除默认回收、永久删除显式二次确认、逐项完成/失败、失败项继续保留选择、只重试失败项。
- 离线索引保留，封面局部失败和局部重试、空目录。
- 窄屏两列、模态导航与任务抽屉、竖图完整显示、窄屏核验布局。

## 对比结果

| 主题 | 正文/表面 | 辅助文字/画布 | 弱文字/画布 | 主按钮 | 控件边界 |
| --- | --- | --- | --- | --- | --- |
| 浅色 | 14.89:1 | 5.81:1 | 4.65:1 | 6.40:1 | 3.03:1 |
| 深色 | 12.88:1 | 9.34:1 | 7.43:1 | 8.04:1 | 4.34:1 |

这些是基于当前 CSS 令牌的 WCAG 相对亮度计算，不等同于对整套正式界面的完整 WCAG 认证。生产中还需验证焦点顺序、屏幕阅读器和动态状态播报。

## 本机截图

- [桌面图包墙](../../../output/playwright/workbench-design/browse-desktop.png)
- [桌面图片墙](../../../output/playwright/workbench-design/images-desktop.png) / [深色图片墙](../../../output/playwright/workbench-design/images-dark.png)
- [桌面查看器](../../../output/playwright/workbench-design/viewer-desktop.png)
- [桌面整包核验](../../../output/playwright/workbench-design/organize-desktop.png)
- [桌面任务](../../../output/playwright/workbench-design/tasks-desktop.png) / [删除部分失败](../../../output/playwright/workbench-design/delete-result.png)
- [窄屏图包墙](../../../output/playwright/workbench-design/browse-mobile.png) / [窄屏图片墙](../../../output/playwright/workbench-design/images-mobile.png)
- [窄屏竖图查看](../../../output/playwright/workbench-design/viewer-mobile.png)
- [窄屏任务](../../../output/playwright/workbench-design/tasks-mobile.png) / [窄屏核验](../../../output/playwright/workbench-design/organize-mobile.png)

所有图片来自本包记录的公开摄影素材，没有真实图库截图。

## 自审与修正

1. 初次窄屏出现 2px 横向溢出，定位到最右工具按钮的提示气泡，已改为向内对齐。
2. 超长连续英文路径令核验说明撑宽主内容，定位到 method-line，已增加按任意边界换行，并对核验和相似页补充回归。
3. 删除部分失败后原型保留选中项却退出选择模式，已统一保留失败项与工具栏状态，重试完成再退出。
4. 文档逐项对照 OpenAPI，修正 Library 字段、位置读取/写入方法和定位方式；没有新增不存在的 anchor_id 查询或 GET position。
5. 侧栏计数改为图片数，分类沿用真实枚举，状态与分类允许组合，不引入新标签。

## 交付边界

样机使用 12 张本地摄影素材、合成图包和少量内存数据，整页重绘仅适用于评审。生产必须继续使用现有虚拟列表、客户端、分页、资源调度和 Blob 释放逻辑。

添加图库只演示表单和受理反馈，不访问输入路径；图库切换使用固定夹具。任务、内容核验、回收和永久删除都是内存模拟，任何成功或失败都不是实际磁盘结果。刷新会恢复模拟清单，主题与最近位置仅写到独立的样机存储键。

动图播放、透明棋盘、临时旋转、系统全屏、触摸手势、真实 SSE、实际回收与大图库性能需在正式改版中验收。样机未完整实现这些行为，不能据此删掉正式前端的已有能力。

本轮未修改 `ui/` 生产代码、后端、数据目录和桌面入口，未重建或替换当前运行包。正式实施与实际产物的验收见 `delivery.md`。Fluent 官方参考可访问；Adobe 和 Unsplash 的正文自动抓取受站点限制，保留官方出处，文档不引用未取得的正文。
