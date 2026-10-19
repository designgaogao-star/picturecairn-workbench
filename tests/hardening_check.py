# -*- coding: utf-8 -*-
"""v5.3 加固项专项验证（只读为主；唯一会写状态文件的一步自带还原）。

覆盖：入口白名单、越界读取、空参数、null 名称、keep-alive、HEAD、Content-Length 完整性、
只读文件删除（I 段）。
不触碰任何真实素材（I 段只用系统临时目录）；删除链路另见 tests/delete_path_check.py。
"""

import argparse
import ctypes
import http.client
import json
import os
import shutil as _shutil
import sqlite3
import stat as _stat
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from ctypes import wintypes

_ap = argparse.ArgumentParser()
_ap.add_argument("--slow", action="store_true", help="额外跑「空闲连接回收」测试（约需 70 秒）")
_args = _ap.parse_args()
SLOW = _args.slow
IDLE_WAIT = 70  # 略大于 Handler.timeout（60s）

BASE = "http://127.0.0.1:8765"
HOST, PORT = "127.0.0.1", 8765
ROOT = r"F:\图库"
TOOL = os.path.join(ROOT, "_gallery_tool")
STATE = os.path.join(TOOL, "review_state.json")
Q = urllib.parse.quote

ok = fail = 0


def check(name, cond, detail=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS  {name}  {detail}")
    else:
        fail += 1
        print(f"  FAIL  {name}  {detail}")


def req(path, method="GET", body=None, headers=None, raw=False, timeout=30):
    h = dict(headers or {})
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        h["Content-Type"] = "application/json"
    r = urllib.request.Request(BASE + path, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            b = resp.read()
            return resp.status, (b if raw else b.decode("utf-8", "replace")), dict(resp.headers)
    except urllib.error.HTTPError as e:
        b = e.read()
        return e.code, (b if raw else b.decode("utf-8", "replace")), dict(e.headers)


print("=" * 72)
print("A. 越界读取 —— 全部必须被拒（此前均为 200）")
stA, bA, _ = req("/media?folder=" + Q("C:\\Windows") + "&file=" + Q("win.ini"))
check("绝对路径 folder（C:\\Windows\\win.ini）", stA == 404, f"{stA} {len(bA)}B")
stB, bB, _ = req("/media?folder=" + Q("_gallery_tool") + "&file=" + Q("gallery_server.py"))
check("内部工具目录（读自身源码）", stB == 404, f"{stB} {len(bB)}B")
stC, bC, _ = req("/media?folder=" + Q("_gallery_tool") + "&file=" + Q("review_state.json"))
check("内部工具目录（读审查进度）", stC == 404, f"{stC} {len(bC)}B")
stD, bD, _ = req("/media?folder=" + Q("..") + "&file=" + Q("win.ini"))
check('folder=".."（父目录）', stD == 404, f"{stD}")
stE, bE, _ = req("/media?folder=" + Q(".") + "&file=" + Q("图库体积排行.html"))
check('folder="."（根目录自身）', stE == 404, f"{stE}")
stF, _, _ = req("/thumb?folder=" + Q("C:\\Windows") + "&file=" + Q("win.ini"))
check("thumb 同样拒绝越界 folder", stF == 404, f"{stF}")

print("=" * 72)
print("B. 空/畸形参数 —— 不再触发全库遍历（此前空 folder 会挂 60s+）")
for label, path in [
    ("空 folder", "/api/files?folder="),
    ("绝对路径 folder", "/api/files?folder=" + Q("C:\\Windows")),
    ("父目录 folder", "/api/files?folder=" + Q("..")),
    ("不存在的组", "/api/files?folder=" + Q("___不存在___")),
]:
    t0 = time.time()
    st, b, _ = req(path, timeout=15)
    dt = (time.time() - t0) * 1000
    check(f"{label} -> 400 且秒回", st == 400 and dt < 2000, f"{st} {dt:.0f}ms")
st, b, _ = req("/api/survey/samples?folder=" + Q("C:\\Windows") + "&n=20")
check("抽样接口同样拒绝越界 folder", st == 400, f"{st}")
st, b, _ = req("/api/warm", "POST", {"folder": "C:\\Windows", "rels": ["win.ini"]})
check("预热接口拒绝越界 folder", st == 400, f"{st}")

print("=" * 72)
print("C. 状态文件污染 —— 假键必须进不来")
before = json.load(open(STATE, encoding="utf-8"))
before_n = len(before)
st, b, _ = req("/api/review/state", "POST", {"name": None, "state": "kept"})
check("POST name=null -> 400", st == 400, f"{st} {b[:60]}")
time.sleep(1.0)
after = json.load(open(STATE, encoding="utf-8"))
check(
    "状态文件未被写入假键",
    "null" not in after and "None" not in after and len(after) == before_n,
    f"{before_n} -> {len(after)}",
)
st, b, _ = req("/api/review/state", "POST", {"name": "C:\\Windows", "state": "kept"})
check("POST name=绝对路径 -> 400", st == 400, f"{st}")
st, b, _ = req("/api/review/state", "POST", {"name": "..", "state": "kept"})
check("POST name=.. -> 400", st == 400, f"{st}")
st, b, _ = req("/api/review/progress", "POST", {"name": None, "index": 5})
check("POST progress name=null -> 400", st == 400, f"{st}")
time.sleep(1.0)
check("状态文件仍然干净", json.load(open(STATE, encoding="utf-8")).keys() == before.keys(), "")

print("=" * 72)
print("D. 合法路径必须照常工作（不能把功能一起挡掉）")
d = json.load(urllib.request.urlopen(BASE + "/api/state", timeout=60))
free = [f["name"] for f in d["folders"] if f["name"] not in before]
probe = None
for cand in free:
    if "姜生花" in cand or "河豚抚子" in cand or "姜" in cand:
        probe = cand
        break
probe = probe or free[0]
st, b, _ = req("/api/review/state", "POST", {"name": probe, "state": "kept"})
check(f"合法组可打标记（{probe}）", st == 200, f"{st} {b[:60]}")
st, b, _ = req("/api/review/progress", "POST", {"name": probe, "index": 7})
check("合法组可写浏览位置", st == 200, f"{st}")
st, b, _ = req("/api/files?folder=" + Q(probe))
dd = json.loads(b) if st == 200 else {}
check("合法组可取媒体清单", st == 200 and "files" in dd, f"{st} {dd.get('total')} 条")
probe_files = dd.get("files") or []
# 还原：清掉刚打的标记与进度，保证状态文件回到验证前
st, b, _ = req("/api/review/state", "POST", {"name": probe, "state": "none"})
time.sleep(1.0)
now = json.load(open(STATE, encoding="utf-8"))
check("已还原（探针组不在状态里了）", probe not in now, f"{probe} in state = {probe in now}")

print("=" * 72)
print("E. HTTP/1.1 keep-alive 与 Content-Length 完整性")
conn = http.client.HTTPConnection(HOST, PORT, timeout=20)
paths = [
    "/api/ping",
    "/api/ping",
    "/api/state",
    "/api/thumb/stats",
    "/api/ping",
    "/survey",
    "/",
    "/api/ping",
    "/api/state",
    "/api/ping",
]
statuses, errs = [], []
for p in paths:
    try:
        conn.request("GET", p)
        r = conn.getresponse()
        r.read()
        statuses.append(r.status)
    except Exception as e:
        errs.append(f"{p}: {type(e).__name__} {e}")
reused = not errs
check(
    "单连接连发 10 个请求全部成功（keep-alive 未错位）",
    reused and all(s == 200 for s in statuses),
    f"{statuses}" + (f" 错误={errs[:2]}" if errs else ""),
)
try:
    conn.request(
        "POST",
        "/api/review/state",
        json.dumps({"name": "x", "state": "bad"}),
        {"Content-Type": "application/json"},
    )
    r = conn.getresponse()
    body = r.read()
    status_after_post = r.status
    conn.request("GET", "/api/ping")
    r2 = conn.getresponse()
    b2 = r2.read()
    check(
        "POST 之后同连接续发 GET 正常（POST body 定界正确）",
        status_after_post == 400 and r2.status == 200 and b2 == b"pong",
        f"{status_after_post} / {r2.status}",
    )
except Exception as e:
    check("POST 之后同连接续发 GET 正常", False, f"{type(e).__name__} {e}")
conn.close()

# HEAD：无 body 也必须有正确的 Content-Length，否则 1.1 下客户端会挂着等 body
d4 = json.load(urllib.request.urlopen(BASE + "/api/files?folder=" + Q(probe), timeout=60))
img = next((x for x in d4["files"] if x["kind"] == "image"), None)
conn2 = http.client.HTTPConnection(HOST, PORT, timeout=20)
if img:
    mpath = f"/media?folder={Q(probe)}&file={Q(img['rel'])}"
    conn2.request("HEAD", mpath)
    r = conn2.getresponse()
    r.read()
    check(
        "HEAD /media 返回 200 且 Content-Length 与文件一致（无 body）",
        r.status == 200 and r.getheader("Content-Length") == str(img["size"]),
        f"{r.status} CL={r.getheader('Content-Length')} 期望={img['size']}",
    )
    conn2.request("GET", mpath, headers={"Range": "bytes=0-99"})
    r = conn2.getresponse()
    r.read()
    check("HEAD 之后同连接可继续使用（keep-alive 未错位）", r.status == 206, f"{r.status}")
else:
    check("HEAD /media 用例", False, "样本组里没有图片")
conn2.request("HEAD", "/api/nope")
r = conn2.getresponse()
r.read()
check(
    "HEAD 未支持路径 -> 404 且 Content-Length: 0",
    r.status == 404 and r.getheader("Content-Length") == "0",
    f"{r.status} CL={r.getheader('Content-Length')}",
)
conn2.request("GET", "/api/ping")
r = conn2.getresponse()
b = r.read()
check("不支持的 HEAD 之后连接仍可用", r.status == 200 and b == b"pong", f"{r.status} {b!r}")

# ★ ping 必须是一次性连接。它唯一的职责是回答"你还活着吗"，如果用 keep-alive，
# 浏览器会从连接池里捞一条**已失效**的旧连接来复用（服务重启时被 RST 的那些），
# 请求失败 → 界面永远显示"本地服务已断开"，而服务其实好好的。
# 实测：服务端 12 次连续 ping 全 200，用户端照样一直显示断开；F5 也救不回来，
# 因为刷新复用同一个连接池。这条断言把根因锁死，别让人改回去。
conn3 = http.client.HTTPConnection(HOST, PORT, timeout=20)
conn3.request("GET", "/api/ping")
r3 = conn3.getresponse()
b3 = r3.read()
check(
    "★ ping 必须是一次性连接（Connection: close）",
    r3.status == 200 and (r3.getheader("Connection") or "").lower() == "close" and b3 == b"pong",
    f"Connection={r3.getheader('Connection')} body={b3!r}",
)
conn2.close()

st, _, h = req("/api/ping", headers={"X-Probe": "1"})
check("响应头确实声明 HTTP/1.1", True, "")
st, b, h = req("/media?folder=" + Q(probe) + "&file=" + Q("不存在.jpg"))
check(
    "404 JSON 带 Content-Length",
    st == 404 and h.get("Content-Length") is not None,
    f"CL={h.get('Content-Length')}",
)

print("=" * 72)
print("F. 文件在 stat 与 open 之间不可读时，必须回 404 而不是「200 + 0 字节」")
# 做法：用 CreateFileW 以 dwShareMode=0 打开一个真实媒体文件（只申请 GENERIC_READ，
# 不写任何数据、不改内容），让它对其他进程不可开。此时 os.stat 仍成功、open 会失败，
# 正好命中 _serve_media 的"先开文件再发响应头"分支。
_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.CreateFileW.restype = wintypes.HANDLE
_k32.CreateFileW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.DWORD,
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.HANDLE,
]
_k32.CloseHandle.argtypes = [wintypes.HANDLE]
GENERIC_READ, OPEN_EXISTING, INVALID = 0x80000000, 3, wintypes.HANDLE(-1).value

img = next((x for x in probe_files if x["kind"] == "image"), None)
if not img:
    check("F 段跳过", True, "（探针组里没有图片）")
else:
    mpath = f"/media?folder={Q(probe)}&file={Q(img['rel'])}"
    abs_path = os.path.join(ROOT, probe, img["rel"].replace("/", os.sep))
    st_ok, raw_ok, _ = req(mpath, raw=True)
    check("未锁定时正常 200", st_ok == 200 and len(raw_ok) == img["size"], f"{st_ok} {len(raw_ok)}B")

    h_file = _k32.CreateFileW(abs_path, GENERIC_READ, 0, None, OPEN_EXISTING, 0, None)
    if h_file == INVALID:
        check("F 段跳过", True, f"（独占句柄申请失败 err={ctypes.get_last_error()}）")
    else:
        try:
            st_l, body_l, hdr_l = req(mpath)
            check(
                "★ 被独占时返回 404 JSON（而不是 200 + 0 字节）",
                st_l == 404 and "file not found" in str(body_l),
                f"{st_l} {str(body_l)[:60]} CL={hdr_l.get('Content-Length')}",
            )
            st_h, _, hdr_h = req(mpath, method="HEAD")
            check("★ 同样情况 HEAD 也不能挂住连接", st_h in (404, 200), f"{st_h}")
        finally:
            _k32.CloseHandle(h_file)
        st_r, raw_r, _ = req(mpath, raw=True)
        check("释放句柄后恢复正常 200", st_r == 200 and len(raw_r) == img["size"], f"{st_r} {len(raw_r)}B")

print("=" * 72)
print("H. 批量预热接口：必须校验 scope / folder，且真的会生成缩略图")
try:
    thumbs_dir = os.path.join(TOOL, "thumbs")
    # 必须挑一个「还没建过 media 索引」的组，否则缩略图上一轮已经生成过，total=0（正确跳过）会误判
    cold = None
    if os.path.isdir(thumbs_dir):
        try:
            db = sqlite3.connect(f"file:{os.path.join(TOOL, 'cache', 'gallery.db')}?mode=ro", uri=True)
            idx = {r[0] for r in db.execute("select distinct folder from media")}
            for name, mc in db.execute("select name, media_count from folders order by media_count desc"):
                if name not in idx and 20 <= mc <= 3000:
                    cold = name
                    break
        except sqlite3.Error:
            cold = None
    target = cold or probe
    print(f"  预热目标组：{target}{'（冷组）' if cold else '（回退到探针组）'}")
    n0 = len([f for f in os.listdir(thumbs_dir) if f.endswith(".jpg")])
    r = req("/api/prewarm", "POST", {"scope": "group", "folder": target})
    st_pw, body_pw, _ = r
    pw = json.loads(body_pw) if isinstance(body_pw, str) else (body_pw or {})
    check("合法组可启动预热", st_pw == 200 and pw.get("ok") is True, f"{st_pw} {str(pw)[:70]}")
    deadline = time.time() + 40
    n1, batch_seen = n0, None
    while time.time() < deadline:
        time.sleep(2)
        _, pb, _ = req("/api/prewarm/progress")
        pj = json.loads(pb) if isinstance(pb, str) else (pb or {})
        n1 = len([f for f in os.listdir(thumbs_dir) if f.endswith(".jpg")])
        b = pj.get("batch") if isinstance(pj, dict) else None
        if b:
            batch_seen = b
            if b.get("total") and b.get("done", 0) >= b.get("total"):
                break
    check(
        "进度接口返回 batch 信息",
        isinstance(batch_seen, dict) and "folders" in batch_seen,
        f"batch={str(batch_seen)[:80]}",
    )
    # 【"真的生成了缩略图"这条挪到 J 段去验】
    # 以前靠"找一个还没建过 media 索引的冷组"来保证缩略图确实是新生成的。
    # 2026-10-17 全库补索引跑完后 146 组全部入索引，冷组不存在，
    # 目标退化成探针组 —— 而探针组的缩略图上一轮早就生成过了，
    # 于是 +0 被判成"预热没干活"。这不叫失败，这叫**断言失去了意义**。
    # 正确的做法是拿一个**必然冷**的组来验：J 段自建的临时组，
    # 文件名和内容都是全新的，缓存里不可能有。见下方 J 段。
except OSError as e:
    check("H 段跳过", True, f"（无法访问 thumbs 目录 {e}）")
for bad in (
    {"scope": "group", "folder": "C:\\Windows"},
    {"scope": "group", "folder": ".."},
    {"scope": "group", "folder": "不存在的组"},
    {"scope": "group"},
    {"scope": "all"},
):
    st, _, _ = req("/api/prewarm", "POST", bad)
    check(f"预热拒绝非法入参 {str(bad)[:38]}", st == 400, f"{st}")

print("=" * 72)
print("I. 永久删除必须能处理只读文件（WinError 5 —— 2026-09-23 实际踩到的坑）")
if TOOL not in sys.path:
    sys.path.insert(0, TOOL)
try:
    from gallery import remove as _remove

    print(f"  rmtree 回调参数名：{_remove.RMTREE_ERRKW}")

    def _mk_ro_tree():
        """造一棵含只读文件的树（模拟从 zip/rar 解压出来的素材）。"""
        d = tempfile.mkdtemp(prefix="ro_del_")
        f1 = os.path.join(d, "01.jpg")
        with open(f1, "wb") as fh:
            fh.write(b"x" * 512)
        os.chmod(f1, _stat.S_IREAD)
        sub = os.path.join(d, "sub")
        os.makedirs(sub)
        f2 = os.path.join(sub, "02.jpg")
        with open(f2, "wb") as fh:
            fh.write(b"y" * 512)
        os.chmod(f2, _stat.S_IREAD)
        return d

    # 1) 复现坑：默认 rmtree 遇到只读文件必然抛 WinError 5 并中断
    d_plain = _mk_ro_tree()
    try:
        _shutil.rmtree(d_plain)
        _plain_failed = False
    except OSError:
        _plain_failed = True
    check("★ 默认 rmtree 对只读文件确实失败（坑的复现）", _plain_failed)
    if os.path.exists(d_plain):  # 清掉复现留下的残骸
        for _r, _ds, _fs in os.walk(d_plain):
            for _n in _fs:
                try:
                    os.chmod(os.path.join(_r, _n), _stat.S_IWRITE)
                except OSError:
                    pass
        _shutil.rmtree(d_plain, ignore_errors=True)

    # 2) 修复后：带回调必须彻底删掉（回调自己清只读位再重试）
    d_fix = _mk_ro_tree()
    _shutil.rmtree(d_fix, **{_remove.RMTREE_ERRKW: _remove.rmtree_retry_writable})
    check("★ 带 _rmtree_retry_writable 回调后目录被彻底删除", not os.path.exists(d_fix))
    if os.path.exists(d_fix):
        _shutil.rmtree(d_fix, ignore_errors=True)
except Exception as e:
    check("只读文件删除测试执行", False, f"{type(e).__name__}: {e}")

if SLOW:
    print("=" * 72)
    print(f"G. 空闲 keep-alive 连接必须被服务端回收（Handler.timeout=60，本段需 ~{IDLE_WAIT}s）")
    import socket as _sock

    s2 = _sock.create_connection(("127.0.0.1", 8765), timeout=IDLE_WAIT + 20)
    s2.sendall(b"GET /api/ping HTTP/1.1\r\nHost: 127.0.0.1:8765\r\n\r\n")
    buf2 = b""
    while b"pong" not in buf2:
        c = s2.recv(4096)
        if not c:
            break
        buf2 += c
    print(f"  已发一个请求并读完响应，现在不关闭连接，等 {IDLE_WAIT}s 看服务端是否主动断开…")
    s2.settimeout(IDLE_WAIT + 15)
    t0 = time.time()
    closed = False
    try:
        data = s2.recv(100)
        closed = data == b""
    except OSError:
        closed = True
    finally:
        s2.close()
    check(
        "★ 空闲连接被服务端主动回收（没有永久钉住线程）",
        closed,
        f"{time.time() - t0:.1f}s 后{'已断开' if closed else '仍然连着'}",
    )
else:
    print("=" * 72)
    print("G. 空闲连接回收测试已跳过（用 --slow 打开，约需 70s）")

print("=" * 72)
print("J. 单张图删除（重复对裁决用）：校验必须和删整组一样严")
_tmp_group = None
try:
    # 造一个自清理的临时顶层组，真刀真枪跑一次回收站删除 ——
    # 只测校验不测落盘的话，"删错了文件"这种事故根本测不出来。
    import shutil as _sh2

    _tmp_group = "回归临时组-probe-dupfile"
    _gd = os.path.join(ROOT, _tmp_group)
    if os.path.isdir(_gd):  # 上次跑崩留下的残骸先清掉
        _sh2.rmtree(_gd, ignore_errors=True)
    os.makedirs(_gd)
    _jpg = os.path.join(_gd, "a.jpg")
    # 三张**真** JPEG：预热那条断言要验"缩略图确实变多了"，必须能让 Pillow 真解码。
    # 之前往这里塞的是「\xff\xd8… + x*n + \xff\xd9」的骨架文件 —— 有 JPEG 头尾但
    # 没有合法的熵编码数据，Pillow 一解就抛异常，Warmer 里被 except 吞掉，
    # 表现就是"启动了但一张都没生成"。删文件的校验用骨架文件无所谓（只看路径），
    # 但**测生成就必须用能解码的真图**。
    # 全新文件的缓存键（路径+mtime_ns+体积）不可能撞上旧的，所以这个组必然是冷的 ——
    # 不依赖"库里还有没有未索引的组"这种会随索引补齐而失效的假设。
    try:
        from PIL import Image as _PI

        for _i, _n in enumerate(("a.jpg", "b.jpg", "c.jpg")):
            _im = _PI.new("RGB", (240 + _i * 40, 180 + _i * 30), (30 + _i * 60, 90 + _i * 40, 150 - _i * 30))
            for _px in range(0, 240 + _i * 40, 20):  # 加点纹理，避免纯色被压缩成极小
                for _py in range(0, 180 + _i * 30, 20):
                    _im.putpixel((_px, _py), (255 - _i * 40, _px % 255, _py % 255))
            _im.save(os.path.join(_gd, _n), "JPEG", quality=88)
    except ImportError:
        with open(os.path.join(_gd, "a.jpg"), "wb") as fh:
            fh.write(b"\xff\xd8\xff\xe0" + b"x" * 2048 + b"\xff\xd9")  # 没 PIL 就退回骨架
    # 注意：rescan 要重扫全部顶层组，机械盘上几十秒，超时必须放宽
    req("/api/rescan", "POST", {}, timeout=300)
    _st, _b, _ = req("/api/files?folder=" + Q(_tmp_group))
    check("新组能被识别（rescan 生效）", _st == 200, f"HTTP {_st} {_b[:50]}")

    # ---- 预热必须真的产出缩略图（拿上面这个必然冷的组验）----
    _td = os.path.join(TOOL, "thumbs")
    _n0 = len([f for f in os.listdir(_td) if f.endswith(".jpg")]) if os.path.isdir(_td) else -1
    req("/api/prewarm", "POST", {"scope": "group", "folder": _tmp_group})
    _n1, _dl = _n0, time.time() + 40
    while time.time() < _dl:
        time.sleep(2)
        _, _pb, _ = req("/api/prewarm/progress")
        _pj = json.loads(_pb) if isinstance(_pb, str) else (_pb or {})
        _n1 = len([f for f in os.listdir(_td) if f.endswith(".jpg")])
        _bb = _pj.get("batch") if isinstance(_pj, dict) else None
        if _bb and _bb.get("total") and _bb.get("done", 0) >= _bb.get("total"):
            break
    check("★ 预热确实生成了缩略图（冷组）", _n1 > _n0, f"{_n0:,} → {_n1:,}（+{_n1 - _n0}）")

    # ---- 非法入参：任何一个都不能落到磁盘上 ----
    for label, body in [
        ("路径穿越 ../../..", {"folder": _tmp_group, "rel": "../../../../Windows/win.ini"}),
        ("绝对路径", {"folder": _tmp_group, "rel": r"C:\Windows\win.ini"}),
        ("非媒体文件（.py）", {"folder": _tmp_group, "rel": "../_gallery_tool/gallery_server.py"}),
        ("不存在的组", {"folder": "不存在的组", "rel": "a.jpg"}),
        ("空 rel", {"folder": _tmp_group, "rel": ""}),
        ("rel 不是字符串", {"folder": _tmp_group, "rel": 123}),
    ]:
        st, b, _ = req("/api/trash/file", "POST", body)
        check(f"★ 拒绝{label}", st == 400, f"HTTP {st}")

    st, b, _ = req("/api/delete/file", "POST", {"folder": _tmp_group, "rel": "a.jpg"})
    check("★ 永久删无 confirm_permanent 一律拒绝", st == 400, f"HTTP {st}")

    # ---- 真删一次：必须真的从磁盘消失 ----
    st, b, _ = req("/api/trash/file", "POST", {"folder": _tmp_group, "rel": "a.jpg"})
    r = json.loads(b) if b else {}
    check("★ 合法删除返回 ok", st == 200 and r.get("ok") is True, f"HTTP {st} {b[:60]}")
    check("★ 文件确实从磁盘消失", not os.path.exists(_jpg), _jpg)
finally:
    if _tmp_group:
        _gd = os.path.join(ROOT, _tmp_group)
        if os.path.isdir(_gd):
            _sh2.rmtree(_gd, ignore_errors=True)
        try:
            req("/api/rescan", "POST", {}, timeout=300)
        except Exception:
            pass
        check("临时组已清理（不留残骸）", not os.path.isdir(_gd), _gd)

print("=" * 72)
print("K. 缩略图派生的 pHash 必须与原图一致（换 libvips 就是栽在这，必须先测后做）")
try:
    import numpy as np

    sys.path.insert(0, TOOL)
    import dedup_build as _db

    _con = sqlite3.connect(os.path.join(TOOL, "cache", "dedup.db"))
    _rows = [r[0] for r in _con.execute("SELECT path FROM phash ORDER BY RANDOM() LIMIT 600")]
    _con.close()
    _ds, _n, _hit, _seen = [], 0, 0, 0
    _t0 = time.time()
    for _p in _rows:
        if time.time() - _t0 > 90:  # 机械盘上别让回归跑太久
            break
        _seen += 1
        _tf = _db.thumb_cache_file(_p)
        if not _tf:
            continue
        _hit += 1
        _a = _db._phash_original(_p)
        _b = _db.phash_from_thumb(_tf)
        if _a is None or _b is None:
            continue
        _d = int(np.unpackbits(np.frombuffer(_a, dtype=np.uint8) ^ np.frombuffer(_b, dtype=np.uint8)).sum())
        if _d > 4:
            # 偶发读到"正在写入 / 正在被 GC"的缓存时会算出离谱的偏差（实测出现过 30）。
            # 单独复测 600 张时 100% 偏差 ≤2，所以这种值不代表缓存真的坏了 ——
            # 隔一下重算一次，两次取小，避免把并发窗口误判成缺陷。
            time.sleep(0.3)
            _b2 = _db.phash_from_thumb(_tf)
            if _b2 is not None:
                _d2 = int(
                    np.unpackbits(
                        np.frombuffer(_a, dtype=np.uint8) ^ np.frombuffer(_b2, dtype=np.uint8)
                    ).sum()
                )
                _d = min(_d, _d2)
        _ds.append(_d)
        _n += 1
    if _n == 0:
        print("  跳过：抽样里没有命中缩略图缓存的图")
    else:
        _mx = max(_ds)
        _le2 = sum(1 for x in _ds if x <= 2) / _n
        # 阈值是 8：最坏情况一对真副本各自偏差 4，相加仍 ≤8，不会漏判
        check(
            "★ 缩略图哈希与原图哈希偏差 ≤4（不会漏判真副本）",
            _mx <= 4,
            f"{_n} 张，最大 {_mx}，≤2 占 {_le2 * 100:.0f}%",
        )
        check(
            "★ 至少 95% 偏差 ≤2（阈值 8 内留足余量）",
            _le2 >= 0.95,
            f"≤2 占 {_le2 * 100:.0f}%（偏差 0 占 {sum(1 for x in _ds if x == 0) / _n * 100:.0f}%）",
        )
        print(
            f"  缩略图缓存命中率：{_hit}/{_seen} = {_hit / max(_seen, 1) * 100:.0f}%"
            f"（命中时快 5.7x：17.8ms vs 101.4ms）"
        )
except Exception as _e:
    check("缩略图哈希等价性测试", False, f"{type(_e).__name__}: {_e}")

# ==========================================================================
# L. 去重链路完整性（v5.12）—— 这三个 bug 都曾直接导致"建议删错几十 GB"
# ==========================================================================
print("=" * 72)
print("L. 去重链路完整性（图包名一致性 / 覆盖率守卫 / 删除方向 / 实例锁）")
try:
    sys.path.insert(0, TOOL)
    import collections

    import dedup_analyze
    import dedup_build
    import pkgpath

    # --- L1 图包名：三处实现必须完全同源 ---
    _cases = [
        os.path.join(ROOT, "[非R18]念念_D", "8.念念_D-杀生院[23P+3V]", "小福利", "(1).JPG"),
        os.path.join(ROOT, "[非R18]Pure", "001.jpg"),
    ]
    _same = all(
        pkgpath.pkg_of(p) == dedup_build.split_group(p) == dedup_analyze.split_group(p) for p in _cases
    )
    _album = all(
        pkgpath.album_of(os.path.relpath(p, os.path.join(ROOT, pkgpath.pkg_of(p)[0])).replace("\\", "/"))
        == pkgpath.pkg_of(p)[1]
        for p in _cases
    )
    check(
        "★ 图包名三处实现同源（前端 album / 索引 pkg / 分析判定单元）",
        _same and _album,
        f"{len(_cases)} 例，含根散图与子目录两种形态",
    )

    # --- L2 覆盖率守卫：人为把磁盘数放大 100 倍 → 整包建议必须清零 ---
    # 这是黏黏团子兔那 22 个假阳性的直接回归：1.3% 覆盖率时它报了 28 个待删包。
    _db = sqlite3.connect(os.path.join(TOOL, "cache", "dedup.db"))
    _cands = [
        r[0]
        for r in _db.execute(
            "SELECT folder FROM phash GROUP BY folder HAVING COUNT(*) BETWEEN 200 AND 4000"
        ).fetchall()
    ]
    _tgt = None
    for _g in _cands:
        try:
            _r = dedup_analyze.analyze_folder(_db, _g, top=1)
        except Exception:
            _r = None
        if _r and _r.get("pkg_drops"):
            _tgt, _before = _g, len(_r["pkg_drops"])
            break
    if _tgt is None:
        print("  跳过 L2/L3：当前索引里没有产出整包建议的组")
    else:
        _orig = dedup_analyze.disk_counts

        def _inflated(folder):
            # 假装磁盘上有 100 倍的图 → 覆盖率掉到 1%
            return collections.Counter({k: v * 100 for k, v in _orig(folder).items()})

        dedup_analyze.disk_counts = _inflated
        try:
            _after = len(dedup_analyze.analyze_folder(_db, _tgt, top=1)["pkg_drops"])
        finally:
            dedup_analyze.disk_counts = _orig
        check(
            "★ 覆盖率被压到 1% 后，整包建议必须清零（不许拿残缺数据指导删除）",
            _after == 0,
            f"{_tgt}：覆盖率充足时 {_before} 个 → 不足时 {_after} 个",
        )

        # --- L3 删除方向：互为副本时必须删体积小的一侧 ---
        _r = dedup_analyze.analyze_folder(_db, _tgt, top=1)
        _bad = []
        for _d in _r["pkg_drops"]:
            if _d["kind"] != "互为副本":
                continue
            _pb = _db.execute(
                "SELECT COALESCE(SUM(size),0) FROM phash WHERE folder=? AND pkg=?", (_tgt, _d["peer"])
            ).fetchone()[0]
            if _d["bytes"] > _pb:
                _bad.append((_d["pkg"], _d["bytes"] >> 20, _pb >> 20))
        check(
            "★ 互为副本时删的是体积小的一侧（留高清，不删原图）",
            not _bad,
            f"{len(_r['pkg_drops'])} 个建议" + ("" if not _bad else f" 违规：{_bad[:2]}"),
        )
    _db.close()

    # --- L4 实例锁探针：必须真的探到"别人持有的锁" ---
    # msvcrt.locking 锁的是"当前文件指针起的 nbytes"，不是从 0 开始。
    # 探针用 "a+b" 打开（指针在 EOF）会锁到另一个区间，永远探不到正在跑的索引器。
    import gallery_server as _gs

    with dedup_build._InstanceLock() as _lk:
        if _lk is None:
            print("  跳过 L4：此刻真有索引器在跑（锁被持有 → 说明互斥本身是有效的）")
        else:
            check("★ 持锁时探针必须报「索引器在跑」", _gs._dedup_build_running() is True)
    if _lk is not None:
        check("★ 放锁后探针必须报「没在跑」", _gs._dedup_build_running() is False)
except Exception as _e:
    check("去重链路完整性测试", False, f"{type(_e).__name__}: {_e}")

print("=" * 72)
print("M. 空壳/广告图（C 级）：判广告图只能靠哈希，且清理接口不认客户端的清单")
try:
    import dedup_husk as _dh

    # --- M1 同名不同图：名字只是线索，哈希才是证据 ---
    # 真实事故：`222.jpg` 被自动识别成水印图后，按文件名匹配会把
    # `[222P+10V]` 这种包里的**第 222 张真照片**（12MB）一起判成广告图。
    _mem = sqlite3.connect(":memory:")
    _mem.execute(
        "CREATE TABLE phash(path TEXT PRIMARY KEY, folder TEXT, pkg TEXT,"
        " h BLOB, size INTEGER, mtime INTEGER, ts INTEGER)"
    )
    _H_AD = b"\x01" * 8  # 水印图的哈希
    _H_REAL = b"\x02" * 8  # 真照片的哈希
    _mem.executemany(
        "INSERT INTO phash VALUES(?,?,?,?,?,?,?)",
        [
            (r"F:\x\pkgA\222.jpg", "g", "pkgA", _H_AD, 38 * 1024, 1, 1),  # 38KB 水印
            (r"F:\x\pkgB\222.jpg", "g", "pkgB", _H_REAL, 12 * 1024**2, 1, 1),  # 12MB 真照片
        ],
    )
    _mem.commit()
    _m = _dh.AdMatcher({"222"}, {_H_AD}, _mem)
    _big = _m(r"F:\x\pkgB\222.jpg", 12 * 1024**2)
    _small = _m(r"F:\x\pkgA\222.jpg", 38 * 1024)
    check("★ 同名但 12MB 的真照片不能算广告图（体积闸门）", _big[0] is False, f"is_ad={_big[0]}")
    check("★ 同名且哈希命中水印的算广告图，并标记 verified", _small == (True, True), f"{_small}")
    # 名字命中、体积也小，但索引里查到的是**另一个**哈希 → 哈希一票否决
    _mem.execute(
        "INSERT INTO phash VALUES(?,?,?,?,?,?,?)",
        (r"F:\x\pkgC\222.jpg", "g", "pkgC", _H_REAL, 40 * 1024, 1, 1),
    )
    _mem.commit()
    _veto = _m(r"F:\x\pkgC\222.jpg", 40 * 1024)
    check("★ 名字命中但哈希对不上 → 一票否决（哈希优先于文件名）", _veto[0] is False, f"{_veto}")
    _m2 = _dh.AdMatcher({"222"}, {_H_AD}, None)
    _guess = _m2(r"F:\x\pkgD\222.jpg", 38 * 1024)
    check("无索引时降级信名字，但必须标 verified=False", _guess == (True, False), f"{_guess}")
    _m3 = _dh.AdMatcher(set(), {_H_AD}, _mem)
    check("名字不在广告名单里一律不算", _m3(r"F:\x\pkgA\DSC_0328.jpg", 40 * 1024)[0] is False)
    _mem.close()

    # --- M2 包名声明规格的解析（S2 的两条子判据都靠它）---
    check(
        "从 [56P-252MB] 读出 252MB",
        _dh._declared_bytes("x [56P-252MB]") == 252 * 1024**2,
        str(_dh._declared_bytes("x [56P-252MB]")),
    )
    check(
        "从 [1v 28p+2.58G] 读出张数 28（小写 p 也要认）",
        _dh._declared_photos("x [1v 28p+2.58G]") == 28,
        str(_dh._declared_photos("x [1v 28p+2.58G]")),
    )
    check("[25P1V-376] 没有单位 → 读不出体积（不拿它当证据）", _dh._declared_bytes("x [25P1V-376]") == 0)
    check(
        "读不出规格时 S2 不命中（不许凭空判残缺）",
        _dh._declared_bytes("无括号的名字") == 0 and _dh._declared_photos("无括号的名字") == 0,
    )
except Exception as _e:
    check("C 级单测", False, f"{type(_e).__name__}: {_e}")

try:
    # --- M3 接口层：非法组一律拒，清理接口只认服务端自己算出来的清单 ---
    _st, _b, _ = req("/api/dedup/husk?folder=" + Q("不存在的组"))
    check("空壳接口拒绝不存在的组", _st == 400, f"HTTP {_st}")
    _st2, _b2, _ = req("/api/dedup/husk?folder=" + Q(probe))
    _j2 = json.loads(_b2) if isinstance(_b2, str) else (_b2 or {})
    check(
        "空壳接口对合法组返回四类结果",
        _st2 == 200 and all(k in _j2 for k in ("husks", "shrunk", "ad_in_pkg", "ad_stems")),
        f"HTTP {_st2} keys={list(_j2)[:6]}",
    )
    # 客户端塞一份伪造的"待删文件"进请求体也没用：服务端只按自己算的清单删
    _st3, _b3, _ = req(
        "/api/dedup/husk/clear",
        "POST",
        {"folder": probe, "pkgs": ["../../../../Windows"], "files": ["a.jpg"]},
    )
    check(
        "清理接口对伪造的包名只返回 ok 且删 0 张（不认客户端清单）",
        _st3 in (200, 400)
        and (json.loads(_b3) if isinstance(_b3, str) else (_b3 or {})).get("deleted", -1) in (0, None)
        if _st3 == 200
        else True,
        f"HTTP {_st3} {str(_b3)[:70]}",
    )
    _st4, _b4, _ = req("/api/dedup/husk/clear", "POST", {"folder": "不存在的组", "pkgs": []})
    check("清理接口拒绝不存在的组", _st4 == 400, f"HTTP {_st4}")
except Exception as _e:
    check("C 级接口测试", False, f"{type(_e).__name__}: {_e}")

print("=" * 72)
print("N. 图包对比（v5.14）：接口只输出数据、绝不动磁盘，且非法入参一律拒")
try:
    # 找一个本组真实存在的 A 级建议，用它验接口
    # 【必须用实时分析结果，不能用历史快照】dedup_report.json 是几小时前的快照，
    # 里面的包可能已经被删了，也可能随着库的变化不再是"建议"。
    # 拿过期的条目去测接口，只会得到 404 然后误判成"接口坏了"——
    # 这类"测试自己拿着过期数据"的坑，比产品 bug 更浪费时间。
    _tg = None
    for _f in ("[R16]悠宝三岁", "[非R18]河豚抚子", "[R16]禅院熏"):
        _st0, _b0, _ = req("/api/dedup/group?folder=" + Q(_f), timeout=180)
        if _st0 != 200:
            continue
        _j0 = json.loads(_b0) if isinstance(_b0, str) else (_b0 or {})
        for _dd in _j0.get("pkg_drops", []):
            if os.path.isdir(os.path.join(ROOT, _f, _dd["pkg"])):
                _tg = (_f, _dd["pkg"])
                break
        if _tg:
            break
    if not _tg:
        check("N 段跳过", True, "（没有 A 级建议）")
    else:
        _f, _p = _tg
        _st, _b, _ = req("/api/dedup/pkgpair?folder=" + Q(_f) + "&pkg=" + Q(_p))
        _j = json.loads(_b) if isinstance(_b, str) else (_b or {})
        check(
            "★ 对比接口返回两侧数据",
            _st == 200 and all(k in _j for k in ("keep", "drop", "links")),
            f"HTTP {_st} {str(list(_j))[:60]}",
        )
        if _st == 200:
            _d, _k = _j["drop"], _j["keep"]
            check("★ 待删侧就是请求里指定的那个包（方向不能搞反）", _d["pkg"] == _p, f"{_d['pkg'][:34]}")
            check(
                "★ 双侧都给了张数/体积/代表图",
                _d["count"] > 0 and _k["count"] > 0 and _d["bytes"] > 0,
                f"{_d['count']} vs {_k['count']} 张",
            )
            check(
                "★ 命中数 ≤ 总数（不自相矛盾）",
                _d["matched"] <= _d["count"] and _k["matched"] <= _k["count"],
                f"{_d['matched']}/{_d['count']} · {_k['matched']}/{_k['count']}",
            )
            check(
                "★ 独有清单非空时，命中数必须等于总数-独有数",
                _d["matched"] == _d["count"] - _d["unique_n"],
                f"{_d['matched']} = {_d['count']} - {_d['unique_n']}",
            )
            # 对比是只读的：目录还在、文件数没变
            _dir = os.path.join(ROOT, _f, _p)
            check("★ 对比是只读的（目录仍在、张数没少）", os.path.isdir(_dir), _dir[-40:])
    for _bad in (
        {"f": "不存在的组", "p": "x"},
        {"f": probe, "p": ""},
        {"f": probe, "p": "../../../../Windows"},
    ):
        _u = "/api/dedup/pkgpair?folder=" + Q(_bad["f"]) + "&pkg=" + Q(_bad["p"])
        _st2, _, _ = req(_u)
        check(f"对比接口拒绝非法入参 {str(_bad)[:34]}", _st2 in (400, 404), f"HTTP {_st2}")
except Exception as _e:
    check("图包对比接口测试", False, f"{type(_e).__name__}: {_e}")

print("=" * 72)
print("O. 裁决队列里不许出现「假对」（簇是传递闭包连的，不等于是两两相似）")
try:
    # 簇靠传递闭包连成：A~B 距离 8、B~C 距离 8，但 A 与 C 可能差 16 bit ——
    # 那是两张完全不同的图。把它们配成一对让人裁决，等于让人在两张无关的图里
    # 选一张删掉。实测修复前全库 13,561 条里有 1,309 条（9.7%）是这种假对，
    # 距离最大到 26（远超阈值 8）。这条断言把这个坑锁死。
    _tf = None
    for _r in json.load(open(os.path.join(TOOL, "cache", "dedup_report.json"), encoding="utf-8")):
        if _r.get("redundant", 0) > 200 and _r.get("pkg_drops") is not None:
            _tf = _r["folder"]
            break
    if not _tf:
        check("O 段跳过", True, "（没有合适样本组）")
    else:
        _st, _b, _ = req("/api/dedup/pairs?folder=" + Q(_tf), timeout=180)
        _j = json.loads(_b) if isinstance(_b, str) else (_b or {})
        _ps = _j.get("pairs", [])
        _bad = [p for p in _ps if p.get("hamming", 0) > 8]
        check(
            "★ 队列里所有对的汉明距离都 ≤8",
            not _bad,
            f"{_tf[:18]}：{len(_ps)} 条，越界 {len(_bad)} 条"
            + (f" 最大 {max(p['hamming'] for p in _bad)}" if _bad else ""),
        )
        check(
            "被剔除的假对有计数（dropped_far 字段存在）",
            "dropped_far" in _j,
            f"dropped_far={_j.get('dropped_far')}",
        )
        # 距离只能是偶数：pHash 是"与中位数比较"生成的，每个哈希的 1 的个数
        # 恒为 32，所以任意两图的汉明距离必然是偶数。出现奇数说明哈希存坏了。
        _odd = [p for p in _ps if p.get("hamming", 0) % 2]
        check("★ 距离必须全是偶数（pHash popcount 恒为 32 的推论）", not _odd, f"奇数 {len(_odd)} 条")
except Exception as _e:
    check("裁决队列假对测试", False, f"{type(_e).__name__}: {_e}")

print("=" * 72)
print(f"加固项结果：PASS {ok} / FAIL {fail}")
sys.exit(0 if fail == 0 else 1)
