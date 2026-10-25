# GitHub Windows 验收与发布准备

**目标：** 从公开仓库的干净 checkout 完成源码检查、实际桌面包构建和运行验证，修复远程环境暴露的问题。

**实施方式：** 在当前会话按步骤执行，不切换共享分支。所有图像、数据库和进程测试都使用隔离临时目录；不操作回收站，不改真实数据。

## 1. 复核远程状态与保存失败

- [ ] 读取 `Windows checks` 当前运行的状态、失败步骤和下载的 `result.json`，以具体 run ID 关联证据。
- [ ] 用实际 Electron、临时空数据目录复现 `desktop-shutdown.mjs` 的四个场景。分别记录窗口 close/show/hide 事件、renderer 请求耗时与 `gt.tileSize` 实际值。
- [ ] 检查 `ui/src/state/app.ts` 中偏好回写与测试直接设置 localStorage 的关系；同时验证隐藏窗口下主进程的 `executeJavaScript` 是否得到执行。
- [ ] 只针对证实的原因修改 `electron/main.js` 或 `scripts/ui-qa/desktop-shutdown.mjs`；保持 1.5 秒保存超时、迟到结果不得覆写和 6.5 秒退出断言。

## 2. 消除本地与远程 Git 分叉

- [ ] 获取远程 Git 对象，核对远程 tree 与本地 tree；保留已有历史，不使用 force push。
- [ ] 若网络 API 生成了不同的提交对象，将两条相同内容的历史合并到当前 `feat/backend-v2`，并检查结果树没有意外差异。
- [ ] 只推送审阅过的修复；确认 main 与 feature 分支指向同一已验证内容。

## 3. 远程源码与桌面验收

- [ ] 执行 `node --check scripts/ui-qa/desktop-shutdown.mjs`、实际退出专项和 `pwsh -NoProfile -File scripts/verify.ps1`。
- [ ] 等待修复后同一提交的 GitHub Windows checks 完成，检查 contract diff 与全部运行步骤。
- [ ] 运行 `Build Windows preview`；构建仅使用 `scripts/build.ps1`，检查产物清单、实际 Electron 流程与完整 60 分钟负载。
- [ ] 下载 CI 产物核对 ZIP 摘要，在本机临时解压目录验证运行；GitHub runner 的打包/运行证据与本机证据分开记录。

## 4. 文档与最终审查

- [ ] 更新 README、发布清单和构建草稿中的仓库状态；不把本地检查器的 `publish_ready` 当作远程验收结论。
- [ ] 审阅将公开的历史文档，不上传日志、用户数据、依赖或输出目录。
- [ ] 记录真实通过、失败、未完成事项及其证据链接；未通过不发布二进制 Release。
