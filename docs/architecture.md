# 架构说明

## 入口和边界

`gallery_server.py` 提供回环 HTTP 服务及状态、抽样和去重编排。`gallery_cli.py` 提供本地命令入口。Electron 负责窗口、托盘及 Python 子进程；前端只通过 HTTP 访问图片和数据，不直接访问文件系统。

| 模块 | 职责 |
|---|---|
| `gallery/paths.py` | 代码、资源、图库和可写数据目录 |
| `gallery/config.py` | 唯一图片扩展名集合和运行参数 |
| `gallery/guard.py` | 组白名单、路径归属和图包边界 |
| `gallery/store.py` | SQLite 文件夹元数据和图片清单 |
| `gallery/scan.py` | 指纹、增量扫描和有界清单缓存 |
| `gallery/thumbs.py` | 缩略图、预热队列及缓存回收 |
| `gallery/remove.py` | 文件、图包和组的删除链路 |
| `gallery/journal.py` | 删除日志 |
| `gallery/locks.py`、`fileio.py` | 键锁、磁盘限流、原子写入 |
| `gallery/api/` | 审查、清理和维护接口，返回 payload/status |
| `dedup_build.py` | pHash 索引及断点续跑 |
| `dedup_analyze.py` | 整包关系和重复图片队列 |
| `dedup_verify.py` | 整包内容确证及对比数据 |
| `dedup_husk.py` | 空壳、残缺、广告图分析 |
| `dedup_cover.py`、`dedup_health.py`、`dedup_clean.py` | 覆盖率、报告和索引维护 |
| `pkgpath.py` | 各层共用的图包归属规则 |

`index.html` 加载 `ui/` 下的 CSS 和七个原生 JS 文件，按数字前缀顺序共享词法作用域。`survey.html` 为抽样页面。当前没有前端构建链。

## 数据兼容

SQLite 中 `media`、`media_count` 和接口 `/media` 沿用既有命名，避免对用户数据库和调用协议做无收益的迁移；其中用于浏览的清单只返回图片。旧数据库中其他类型的记录会被过滤，不删除原始文件。

浏览位置仍存为排序后图片清单的下标。磁盘和数据库两条读取路径必须使用相同的 `(album.lower(), rel.lower())` 排序。

开发数据默认写项目目录，打包版由 Electron 设置 `GALLERY_DATA` 到用户目录。去重数据库、锁和日志也必须使用这个目录，不能拼接安装目录。

## 必须保留的保护

组名先过白名单，文件路径必须位于所属组内。永久删除的三个粒度都要求 `confirm_permanent: true`。默认删除经过回收站操作、事后落位检测和日志记录，检测结果不能等同于可恢复性的绝对保证。

pHash 只作为相似度证据；整包核验遍历所有文件，非图片文件也必须找到对应内容。包内存在其他类型时，不因忽略它们而建议按空壳或残缺整包清理。

缩略图的 `draft()` 必须在任何完整解码之前调用。队列、DOM、清单与预载对象必须有界，继续照顾机械盘的寻道成本。

HTTP/1.1 响应必须有准确的 `Content-Length`，连接有超时，发送响应头前先打开图片文件。

## 构建

唯一入口为 `scripts/build.ps1`，使用 `scripts/gallery.spec` 打包当前后端，并与 Electron 组装为绿色版。运行数据不纳入构建。后台补索引使用后端 exe 的 `--build-index` 入口或源码脚本，继承当前数据目录。
