# -*- coding: utf-8 -*-
"""命令行入口：把散落的十几个脚本收成一组子命令。

    gallery serve             启动浏览器界面（默认）
    gallery scan              重建索引
    gallery dedup report      体检：覆盖率 / 冗余 / 空壳 / 坏图
    gallery dedup build       补 pHash 索引
    gallery dedup clean       清理索引里指向已删文件的孤儿行
    gallery info              显示当前路径配置

设计原则：**每个子命令都等价于原来那条 python xxx.py**，
不新增行为，只换入口。这样从旧用法迁移过来零学习成本。
"""

import argparse
import os
import subprocess
import sys

from gallery import paths as P


def _run(script, args=()):
    """在工具目录里跑一个脚本，把退出码传回去。"""
    cmd = [sys.executable, os.path.join(P.TOOL_DIR, script)] + list(args)
    return subprocess.call(cmd, cwd=P.TOOL_DIR)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="gallery",
        description="本地图库浏览与去重工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="根目录：%s\n可用 GALLERY_ROOT 环境变量覆盖" % P.ROOT,
    )
    ap.add_argument("--root", help="覆盖图库根目录（等价于设置 GALLERY_ROOT）")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("serve", help="启动浏览器界面")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--no-open", action="store_true", help="不自动打开浏览器")

    sub.add_parser("scan", help="重建组索引（gallery.db）")
    sub.add_parser("info", help="显示当前路径配置")

    d = sub.add_parser("dedup", help="去重相关")
    dsub = d.add_subparsers(dest="sub")
    dsub.add_parser("build", help="补 pHash 索引（默认按缺口）")
    dsub.add_parser("report", help="生成体检报告")
    dsub.add_parser("cover", help="只跑覆盖率体检")
    dsub.add_parser("clean", help="清理索引孤儿行")
    bs = dsub.add_parser("build-all", help="补齐全库索引")
    bs.add_argument("--scope", default="gap", choices=["gap", "all", "unreviewed"])

    a = ap.parse_args(argv)

    if a.root:
        os.environ["GALLERY_ROOT"] = a.root
        P.ROOT = os.path.abspath(a.root)

    if a.cmd == "info" or not a.cmd:
        print(P.describe())
        exists = os.path.isdir(P.ROOT)
        print("根目录存在：%s" % ("是" if exists else "否 —— 请用 --root 或 GALLERY_ROOT 指定"))
        return 0 if exists else 2

    if a.cmd == "serve":
        argv2 = []
        if a.no_open:
            argv2.append("--no-open")
        argv2 += ["--port", str(a.port)]
        return _run("gallery_server.py", argv2)

    if a.cmd == "scan":
        # gallery_server 没有单独的重扫入口，直接走 HTTP 不方便；
        # 这里复用 dedup_cover 的全量扫描（它本身就会重建组表）。
        return _run("dedup_cover.py")

    if a.cmd == "dedup":
        if a.sub == "build":
            return _run("dedup_build.py")
        if a.sub == "build-all":
            return _run("dedup_build.py", ["--scope", a.scope])
        if a.sub == "report":
            return _run("dedup_health.py")
        if a.sub == "cover":
            return _run("dedup_cover.py")
        if a.sub == "clean":
            return _run("dedup_clean.py")
        d.print_help()
        return 1

    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
