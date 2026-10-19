# -*- coding: utf-8 -*-
"""去重接口：批量清空壳/广告图、补建索引。

这两条的共同点是**判据是概率性的**（pHash 近重复、文件名像广告），
所以：
  · 清空壳只走回收站，不提供永久删除 —— 量大且可能误判，必须可恢复
  · 不信任客户端传的文件清单，只认服务端当场算出来的结果
  · 补索引复用当前运行时和数据目录，不修改系统计划任务
"""

import os
import subprocess
import sys

from gallery.guard import _is_known_group
from gallery.paths import CACHE, ROOT, TOOL_DIR
from gallery.remove import remove_media_file


def _dedup_mod():
    """延迟导入 server 里的去重编排（有循环依赖）。"""
    import gallery_server as gs

    return gs


def husk_clear(data):
    """把若干个图包里的广告图一次性送进回收站（包本身留着）。

    【不信任客户端传的文件清单】只认服务端**当场算出来**的广告图列表：
    前端传什么路径都不作数，避免一个被改过的请求把任意文件删掉。
    只走回收站，不提供永久删 —— 这类操作量大、判据是概率性的，必须可恢复。
    """
    folder = data.get("folder", "")
    if not _is_known_group(folder):
        return {"error": "unknown folder"}, 400
    raw = data.get("pkgs", [])
    if not isinstance(raw, list):
        return {"error": "bad pkgs"}, 400
    # 先切后建集合：集合没有切片，写成 {..}[:500] 会直接抛 TypeError
    want = {p for p in raw[:500] if isinstance(p, str) and p}

    gs = _dedup_mod()
    r = gs.dedup_husk_groups(folder)
    if r is None:
        return {"error": "husk scan failed"}, 500

    done, freed, errs, emptied = 0, 0, [], []
    for a in r.get("ad_in_pkg", []):
        if want and a["pkg"] not in want:
            continue
        for rel in a["drop"]:
            out = remove_media_file(folder, rel, False)
            if out.get("ok"):
                done += 1
                freed += out.get("freed", 0)
            else:
                errs.append({"rel": rel, "error": out.get("error", "failed")})
        # 广告图删完这个包还剩什么？什么都不剩的话告诉前端一句
        base = os.path.join(ROOT, folder, a["pkg"])
        try:
            left = sum(len(fs) for _r, _d, fs in os.walk(base))
        except OSError:
            left = -1
        if left == 0:
            emptied.append(a["pkg"])
    return {"ok": True, "deleted": done, "freed": freed, "errors": errs[:20], "emptied": emptied}, 200


def build_index(data):
    """后台补建 pHash 索引：整库、或指定一组。

    **为什么这个接口必须存在**：
      去重结论全部算在 pHash 索引上。索引没扫全，结论就是残缺的 ——
      实测全库 231,149 张只扫了 40,398 张（17.5%），而"黏黏团子兔"一组
      8,506 张只扫了 109 张，凭空报出 22 个 1.5GB 大包"互为副本"。
      工具必须**自己知道自己扫了多少**，并且能一键补上。

    子进程继承 GALLERY_ROOT/GALLERY_DATA。打包时复用后端 exe 的索引入口，
    不依赖安装目录中不存在的 Python 源文件。中断后可按指纹继续补索引。
    """
    folder = data.get("folder", "")
    if folder and not _is_known_group(folder):
        return {"error": "unknown folder"}, 400

    gs = _dedup_mod()
    if gs._dedup_build_running():
        return {"ok": False, "error": "已有索引任务在跑，等它跑完再开"}, 409

    log = os.path.join(CACHE, "dedup_full.log")
    # 整库用 gap（按缺口从大到小，且可安全重跑），单组用 --folder
    scope = ["--folder", folder] if folder else ["--scope", "gap"]
    command = [sys.executable]
    if getattr(sys, "frozen", False):
        command.append("--build-index")
    else:
        command.append(os.path.join(TOOL_DIR, "dedup_build.py"))
    command += scope + ["--workers", "16", "--log", log]
    try:
        os.makedirs(CACHE, exist_ok=True)
        flags = (subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP) if os.name == "nt" else 0
        with open(log, "ab") as output:
            subprocess.Popen(
                command,
                cwd=TOOL_DIR,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
                creationflags=flags,
                start_new_session=os.name != "nt",
            )
    except Exception as e:
        return {"error": "启动失败：%s" % e}, 500
    return {
        "ok": True,
        "folder": folder or "(全部)",
        "note": "后台补索引已启动，进度见 cache/dedup_full.log",
    }, 200
