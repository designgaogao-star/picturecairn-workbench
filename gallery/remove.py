# -*- coding: utf-8 -*-
"""删除链路：回收站 / 永久删除，带落位校验和记账。

这是全项目**唯一**会真正删东西的模块。三条护栏缺一不可：

1. **路径校验**（`gallery.guard`）—— 每一层都过，越界一律拒绝
2. **落位校验**（`recycle_one_verified`）—— SHFileOperation 返回 0 **不代表进了回收站**
3. **记账**（`gallery.journal`）—— 删了什么、多大、走哪条路，事后可追

关于第 2 点：Windows 在回收站配额不足（默认只有卷容量的 5%）或回收站被组策略关闭时，
`FOF_NOCONFIRMATION` 会把"文件太大，无法放入回收站"那个对话框**按"是"处理且不显示** ——
SHFileOperation 照样返回 0，调用方以为成功了，实际已经永久删除。
2026-10-17 丢掉的 5,747 张就是这么没的。

关于只读位：图库里大量文件是从 zip/rar 解压出来的，带只读属性。
Windows 上 `os.unlink` 删只读文件会抛 WinError 5，默认 rmtree 直接中断，
留下"删了一半"的目录（2026-09-23 永久删 42 组时有一组卡在根目录 25 个只读文件上）。
所以永久删除必须挂 `_rmtree_retry_writable` 回调，并且**删完复核目录是否真的消失**。

**依赖注入**：删完之后要清各类缓存，但那些缓存住在 server 里（状态、去重）。
这里不 import 它们（会循环），改用 `set_purge_hook()` 由 server 在启动时注册。
"""

import ctypes
import os
import shutil
import stat
import sys

from gallery import guard, journal
from gallery.config import IMG_EXT
from gallery.paths import ROOT
from gallery.scan import invalidate_file_caches, invalidate_scan_cache

#: 由 server 注入：删完一个顶层组后清理状态/去重缓存
_purge_hook = None
#: 由 server 注入：让某个组的去重缓存失效


def set_purge_hook(fn):
    global _purge_hook
    _purge_hook = fn


def set_dedup_clear_hook(fn):
    fn_holder[0] = fn


# 用列表持有，避免全局声明到处漏
fn_holder = [None]


def _clear_dedup(folder):
    fn = fn_holder[0]
    if fn:
        try:
            fn(folder)
        except Exception:
            pass


def _log(msg):
    try:
        from gallery_server import log_line

        log_line(msg)
    except Exception:
        pass


# ============================ 回收站 ============================
class _SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.c_void_p),
        ("wFunc", ctypes.c_uint),
        ("pFrom", ctypes.c_wchar_p),
        ("pTo", ctypes.c_wchar_p),
        ("fFlags", ctypes.c_ushort),
        ("fAnyOperationsAborted", ctypes.c_int),
        ("hNameMappings", ctypes.c_void_p),
        ("lpszProgressTitle", ctypes.c_wchar_p),
    ]


_FO_DELETE = 0x0003
_FOF_SILENT = 0x0004
_FOF_ALLOWUNDO = 0x0040  # 送入回收站而非直接删除
_FOF_NOCONFIRMATION = 0x0010
_FOF_NOERRORUI = 0x0400


def recycle_one(path):
    """送系统回收站（可恢复）。返回 0 表示成功。零第三方依赖，走 shell32 宽字符接口。"""
    abspath = os.path.abspath(path)
    buf = abspath + "\0\0"  # pFrom 需双 NUL 结尾
    op = _SHFILEOPSTRUCTW()
    op.hwnd = None
    op.wFunc = _FO_DELETE
    op.pFrom = buf
    op.pTo = None
    op.fFlags = _FOF_SILENT | _FOF_ALLOWUNDO | _FOF_NOCONFIRMATION | _FOF_NOERRORUI
    op.fAnyOperationsAborted = 0
    return ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))


class _SHQUERYRBINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("i64Size", ctypes.c_longlong),
        ("i64NumItems", ctypes.c_longlong),
    ]


def recycle_used(path):
    """该盘回收站当前占用字节。拿不到返回 None —— 检测失败绝不能反过来阻断删除。"""
    try:
        drive = ctypes.c_wchar_p(os.path.splitdrive(os.path.abspath(path))[0] + "\\")
        info = _SHQUERYRBINFO()
        info.cbSize = ctypes.sizeof(_SHQUERYRBINFO)
        if ctypes.windll.shell32.SHQueryRecycleBinW(drive, ctypes.byref(info)) == 0:
            return int(info.i64Size)
    except Exception:
        pass
    return None


def recycle_one_verified(path, expected_bytes=0):
    """送回收站，并**校验它真的进去了**。返回 (rc, not_recycled)。

    判据：删完之后回收站的增量，至少要有文件体积的一半。
    达不到就说明它没进回收站（增量可能是别的进程顺手删的东西）。
    """
    if expected_bytes <= 0:
        return recycle_one(path), False
    before = recycle_used(path)
    rc = recycle_one(path)
    if rc != 0 or before is None:
        return rc, False
    after = recycle_used(path)
    if after is None:
        return rc, False
    if (after - before) < expected_bytes * 0.5:
        return rc, True
    return rc, False


# ============================ 永久删除 ============================
def rmtree_retry_writable(func, path, exc):
    """shutil.rmtree 的出错回调：清掉只读位后重试一次。

    回调里不抛异常（rmtree 会继续处理剩余项），最终由调用方复核目录是否真的消失。
    """
    try:
        st = os.stat(path)
        if not (st.st_mode & stat.S_IWRITE):
            os.chmod(path, st.st_mode | stat.S_IWRITE)
    except OSError:
        pass
    try:
        func(path)
    except OSError:
        pass


# Python 3.12 起 rmtree 的出错回调参数改名 onexc（推荐），旧版是 onerror；两者签名一致
RMTREE_ERRKW = "onexc" if sys.version_info >= (3, 12) else "onerror"


# ============================ 三个粒度 ============================
def remove_media_file(folder, rel, permanent):
    """删组内的一张图（重复对裁决的主要操作）。默认回收站（可恢复）。

    校验口径与 /media 完全一致（safe_media_path 三层 + IMG_EXT 白名单），
    绝不因为"只是删一个文件"就放松任何一道。
    """
    p = guard.safe_media_path(folder, rel)
    if not p:
        return {"ok": False, "error": "invalid file"}
    if os.path.splitext(p)[1].lower() not in IMG_EXT:
        return {"ok": False, "error": "not a media file"}
    try:
        size = os.path.getsize(p)
    except OSError:
        size = 0
    if permanent:
        try:
            # 只读位必须先清：压缩包解压出来的文件带只读属性，直接 unlink 会抛 WinError 5
            os.chmod(p, stat.S_IWRITE)
            os.remove(p)
            if os.path.exists(p):
                return {"ok": False, "error": "删除后文件仍存在"}
        except OSError as e:
            return {"ok": False, "error": str(e)}
    else:
        rc = recycle_one(p)
        if rc != 0:
            return {"ok": False, "error": "SHFileOperation rc=%d" % rc}
    journal.write("file", permanent=permanent, folder=folder, rel=rel, bytes=size)
    try:  # 索引里这一条作废，下次会重建
        import dedup_build as m

        db = m.get_db()
        db.execute("DELETE FROM phash WHERE path=?", (p,))
        db.commit()
    except Exception:
        pass
    invalidate_file_caches(folder)
    invalidate_scan_cache()
    _clear_dedup(folder)
    return {"ok": True, "path": p, "freed": size}


def remove_pkg(folder, pkg, permanent):
    """删组内的一个图包子目录。默认回收站（可恢复）。"""
    p = guard._pkg_dir(folder, pkg)
    if not p:
        return {"ok": False, "error": "invalid pkg"}
    # 体积必须在删之前量 —— 删完目录就没了，量出来永远是 0，日志也就失去意义
    try:
        pkg_bytes = sum(
            os.path.getsize(os.path.join(r, f))
            for r, _d, fs in os.walk(p)
            for f in fs
            if os.path.exists(os.path.join(r, f))
        )
    except OSError:
        pkg_bytes = 0
    if permanent:
        try:
            shutil.rmtree(p, **{RMTREE_ERRKW: rmtree_retry_writable})
            if os.path.exists(p):  # 回调吞了单项错误，必须复核
                return {"ok": False, "error": "rmtree 后目录仍存在"}
        except OSError as e:
            return {"ok": False, "error": str(e)}
        not_recycled = False
    else:
        rc, not_recycled = recycle_one_verified(p, pkg_bytes)
        if rc != 0:
            return {"ok": False, "error": "SHFileOperation rc=%d" % rc}
        if not_recycled:
            _log("⚠ 图包可能未进回收站（已永久删除）：%s/%s %d 字节" % (folder, pkg, pkg_bytes))
    journal.write(
        "pkg", permanent=permanent, folder=folder, pkg=pkg, bytes=pkg_bytes, not_recycled=not_recycled
    )
    try:  # 索引里这棵子树的哈希作废，下次会重建
        import dedup_build as m

        db = m.get_db()
        db.execute(
            "DELETE FROM phash WHERE folder=? AND (pkg=? OR pkg LIKE ?)", (folder, pkg, pkg + os.sep + "%")
        )
        db.commit()
    except Exception:
        pass
    invalidate_file_caches(folder)
    invalidate_scan_cache()
    _clear_dedup(folder)
    return {"ok": True, "path": p}


def remove_folders(names, permanent):
    """names 为 ROOT 下的顶层文件夹名。返回 (每项结果, 释放字节)。

    纵深防御：即使上层漏了校验，这里也必须再挡一次 —— name 必须形态合法且确实是
    当前 ROOT 下的顶层组，否则绝不落到磁盘操作上。缺少这一道，name 传绝对路径会在
    Windows 上让 os.path.join 丢弃 ROOT，直接对图库之外的目录执行 rmtree。
    """
    results = []
    freed = 0
    mode = "permanent" if permanent else "recycle"
    for name in names:
        if not (guard._valid_group_name(name) and guard._is_known_group(name)):
            results.append(
                {
                    "name": name if isinstance(name, str) else repr(name),
                    "ok": False,
                    "mode": mode,
                    "size": 0,
                    "error": "invalid-group-name",
                }
            )
            continue
        path = os.path.join(ROOT, name)
        size = 0
        row = _folder_size(name)
        if row:
            size = int(row or 0)
        ok, err, not_recycled = False, "", False
        if not os.path.exists(path):
            ok, err = True, "already-missing"
        elif permanent:
            try:
                shutil.rmtree(path, **{RMTREE_ERRKW: rmtree_retry_writable})
                # 回调吞掉了单项错误，所以这里必须复核：目录还在就等于没删干净，
                # 绝不能报 ok=True（否则 state/db 会被清掉，磁盘上却留着残骸）。
                if os.path.exists(path):
                    ok, err = False, "rmtree 后目录仍存在（可能有文件被占用或权限受限）"
                else:
                    ok = True
            except OSError as e:
                err = str(e)
        else:
            rc, not_recycled = recycle_one_verified(path, size)
            ok = rc == 0
            if not ok:
                err = "SHFileOperation rc=%d" % rc
            elif not_recycled:
                _log("⚠ 组可能未进回收站（已永久删除）：%s %d 字节" % (name, size))
        if ok and not os.path.exists(path):
            freed += size
            if _purge_hook:
                try:
                    _purge_hook(name)
                except Exception:
                    pass
            if err != "already-missing":  # 本来就不在的话，没删任何东西，不该记账
                journal.write("group", permanent=permanent, name=name, bytes=size)
        results.append(
            {
                "name": name,
                "ok": ok,
                "mode": mode,
                "size": size,
                "error": err,
                "warning": "可能未进回收站（已永久删除），请检查回收站配额" if not_recycled else "",
            }
        )
    return results, freed


def _folder_size(name):
    """从 DB 拿组体积（删之前量，删完就没了）。"""
    try:
        from gallery import store

        row = store.folder_row(name)
        return int(row.get("size") or 0) if row else 0
    except Exception:
        return 0
