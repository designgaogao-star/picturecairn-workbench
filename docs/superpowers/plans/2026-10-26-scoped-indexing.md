# 限定目录扫描 Implementation Plan

> **For agentic workers:** 按下面步骤在当前共享分支内执行并逐项 review。用户已授权直接推进；不创建子 agent、不切换分支、不覆盖并行改动。

**Goal:** 对已有分组和深层空目录的扫描只枚举目标子树，并沿用正确图包上下文，避免相似分析意外扫描整个图库。

**Architecture:** `Indexer._scan` 从目录及其祖先对应的持久图包确定起始 package ID。图库根扫描继续使用根散图图包；限定目录扫描不因目标本身没有直接图片而扩大范围。Dedup、Watcher 和 HTTP 使用同一索引入口，无需改契约或迁移数据。

**Tech Stack:** 现有 Python 3.14、SQLite 递归查询、pytest、Ruff；实际桌面继续通过唯一 PowerShell 构建入口。

**交付收口优先：** 用户随后要求停止扩项。本轮于北京时间 2026-10-26 14:15 前交付，按 [收口清单](../../delivery-cutoff-20261026.md) 执行；只收完正在运行的默认长测，不再启动原生等长对照或历史异常压力复现。

## 现场与边界

- 已公开包 `20261025-164104` 的原生观测对照在第 47 轮分析任务超过原有 120 秒门槛；主机曾出现 CPU 100%、可用内存约 884 MiB，不能据此认定唯一耗时根因。
- `Dedup.build` 请求限定 group_id 的强制扫描，`Indexer._scan` 却只寻找该目录的非散图图包或直接文件；普通分组没有直接图片时 start_pkg 为空，随后退回整个图库。深层空目录也有同类分支。
- 原始失败保留于 `output/quality/soak-1792978454466`；所有所属进程已退出。修复不得将该次失败改判为成功。
- 仅用新建临时图库，不写真实数据库、不操作回收站，不覆盖公开 ZIP。产品代码变动后另建候选包，原公开包继续作为前后对照。

## Task 1: 固定限定扫描回归

**Files:** Create `tests/test_indexer_scope.py`。

- [x] 建立不启动后台线程的真实 Catalog、Indexer、Resources 和 Context；生成 `library/group/package/image.png` 与 `library/unrelated/package/old.png`。初始完整扫描后才在无关分组加入 `later.png`。
- [x] 参数化目标为 `group` 与 `group/package/empty/deep`。深层空目录在初始扫描前建立，扫描后在目标目录加入 `new.png`。调用真实 `Indexer.scan`，断言目标文件沿用分组／图包，新增无关文件未进入索引。
- [x] 另用两套临时图包走 `Dedup.build`，验证真实相似分析准备链路不会枚举无关分组。
- [x] 运行旧实现并保留失败日志：

```powershell
.venv/Scripts/python.exe -X utf8 -m pytest tests/test_indexer_scope.py
```

预期旧实现因无关分组 `later.png` 被索引而失败，而不是由于计时或模拟服务失败。

实际三条均因访问无关目录的枚举断言失败；日志为 `output/quality/scoped-indexing-red-20261026.log`。修复后三条通过，日志为 `scoped-indexing-green-20261026.log`；测试完整代码位于 `tests/test_indexer_scope.py`，不以测试替身替代真实目录和数据库。

## Task 2: 保留起始图包和扫描边界

**Files:** Modify `gallery/indexer.py` 的 `_scan` 起始目录选择。

- [x] 将“直接文件／非散图图包，否则全库”分支替换为最近祖先图包查询：

```python
if directory and directory['rel']:
    package = self.catalog.one(
        'WITH RECURSIVE parents(id,parent_id,depth) AS ('
        'SELECT id,parent_id,0 FROM directories WHERE id=? UNION ALL '
        'SELECT d.id,d.parent_id,p.depth+1 FROM directories d JOIN parents p ON d.id=p.parent_id) '
        'SELECT packages.id FROM parents JOIN packages ON packages.directory_id=parents.id '
        'WHERE packages.group_id=? ORDER BY parents.depth LIMIT 1', (subtree, directory['group_id']))
    stack = [(directory['rel'], directory['id'], directory['group_id'], package['id'])]
else:
    stack = [('', root_id, root_id, root_pkg)]
```

数据库目录树为每个分组创建散图图包，并为其直接子目录创建正常图包；已有目录的祖先链提供其原始图包上下文，无需扫描其他分组推断。

- [x] 原三条回归通过后，验证完整核验、目录消失、junction 拒绝、重连、稳定 ID 与前台 IO 优先：

```powershell
.venv/Scripts/python.exe -X utf8 -m pytest tests/test_indexer_scope.py tests/test_v2.py tests/test_library_lifecycle.py tests/test_loading.py
.venv/Scripts/python.exe -X utf8 -m ruff check .
```

- [x] Review 祖先查询是否保留分组边界、空目录中新文件的 package_id，以及全库扫描行为；不改变 pHash 规范和全文件核验。

上述回归已由完整 pytest 覆盖：117 项通过，唯一失败为实际进程握手 14.32 秒超过原定 10 秒，失败快照为 CPU 100%、可用内存 1372 MiB。全仓 Ruff 单独通过；没有因此放行完整验证，也不重复执行已经通过的同组用例。

## Task 3: 完整验证、实际包与交付

**Files:** Update `docs/architecture.md`、`docs/frontend-ui.md`、`docs/superpowers/plans/2026-10-26-native-memory.md` 和当前交付记录。

- [x] 通过真实相似准备回归验证新增第二个图包；另用实际前后两个后端包和 8120 张无关图片验证限定扫描。旧包扫描 8123 个文件、5 个目录并更新无关文件；新候选只扫描目标的 2 个文件、2 个目录，无关图库索引保留 8120 张，原图片 ID 保留。真实枚举断言另由单元回归覆盖，不只依据耗时变快。实际 API 证据为 `output/quality/scoped-indexing-packaged-api-20261026.json`。
- [x] 执行完整 `pwsh -NoProfile -File scripts/verify.ps1`；资源恢复后的第二轮全部通过：118 项 Python、两项原生回收排除、14 项交互、四项退出、126 项工作台、源码完整业务及其余契约／类型／品牌／构建／语法。日志为 `output/quality/scoped-indexing-full-verification-recovered-20261026.log`，第一轮启动失败原记录保留。
- [x] 只经 `scripts/build.ps1` 生成新候选 `20261026-105024`；438 个产物、来源和 ZIP 独立校验通过。实际 Electron 验证图包边界、恢复、相似分析、全部文件核验、22 项图库管理、17 项品牌、动态端口重启与所属后端退出，记录为 `output/ui-qa/integration-1792983836374`；实际四项退出另为 `output/ui-qa/shutdown-1792984873946`，阻塞退出 2655ms。公开包未覆盖，入口未切换，性能与长期内存仍待完成。
- [x] 当前主机恢复足够资源后，串行执行旧公开包／新候选的加载与后台竞争。API／Edge、实际 Electron 和混合大图均完成，另测完整 8301 文件扫描期间的健康 P95，见 [候选验收](../../candidate-verification-20261026.md)。两份包的 96 份派生文件 SHA-256 一致，来源、逐次耗时、RSS 与进程 IO 均保留。
- [x] 唯一默认两小时运行完整结束：7200.021 秒／360 轮，末半小时总私有内存 +2.39308 MiB/分钟超原 2 的门槛，结果为失败；没有重跑或降低门槛。页面错误零、最终任务 175 完成／20 取消、五个所属采样进程退出。独立审计按原规则拒绝失败记录；只读现场复核为输出目录中的 `final-evidence-review.json`，不能当作通过审计。
- [x] 最终 review 和交付记录完成，四个变更源码／测试文件及 ZIP 与候选清单一致。源码、候选包、启动方法和已知限制见 [交付文档](../../candidate-verification-20261026.md)。按 [收口决定](../../delivery-cutoff-20261026.md) 停止本轮开发，不切换入口、不替换公开二进制、不新增提交；原生等长对照和历史 500 压力复现不自动续开。
