# -*- coding: utf-8 -*-
"""零依赖 Chrome DevTools Protocol 驱动 —— 在真实浏览器里回归前端页面。

为什么需要它：本机没有 Playwright/Selenium，装一套要拉几百 MB 的 Chromium；但系统里
已经有 Chrome/Edge，而 CDP 只需要一个 WebSocket 客户端 —— 用标准库手搓一个就够。
这样 开发接手报告 §11.3 里"网页回归只能靠人工"这一条就补上了。

用法：
    python tests/browser_probe.py            # 跑内置前端回归用例
    python tests/browser_probe.py --shots    # 额外存两张截图到 tests/_shots/

副作用（必须先知道）：
  * 脚本会像真人一样浏览，因此会写入"浏览位置"(index)——这是本工具的常规行为，不改变 kept/marked。
  * 开头自动把 review_state.json 备份成 review_state.json.probe-backup；
    结束时逐键比对，若有非预期差异会打印精确差异并提示还原方式。
"""

import argparse
import base64
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request
from urllib.parse import quote

BASE = "http://127.0.0.1:8765"
TOOL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_FILE = os.path.join(TOOL_DIR, "review_state.json")
STATE_BACKUP = STATE_FILE + ".probe-backup"
SHOTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_shots")
CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

ok = fail = 0


def check(name, cond, detail=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS  {name}  {detail}")
    else:
        fail += 1
        print(f"  FAIL  {name}  {detail}")


# ------------------------------- WebSocket -------------------------------
class WS:
    """RFC 6455 客户端侧最小实现：文本帧 + 掩码 + 分片重组 + ping/pong。"""

    def __init__(self, url, timeout=30):
        rest = url[5:]
        hostport, _, path = rest.partition("/")
        host, _, port = hostport.partition(":")
        self.sock = socket.create_connection((host, int(port or 80)), timeout=timeout)
        self.sock.settimeout(timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall(
            (
                f"GET /{path} HTTP/1.1\r\nHost: {hostport}\r\n"
                f"Upgrade: websocket\r\nConnection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
            ).encode()
        )
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise RuntimeError("WebSocket 握手失败：连接被关闭")
            buf += chunk
        head, _, self.buf = buf.partition(b"\r\n\r\n")
        if b" 101 " not in head.split(b"\r\n")[0] + b" ":
            raise RuntimeError("WebSocket 握手失败：" + head.decode("latin1")[:200])

    def _take(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(max(4096, n - len(self.buf)))
            if not chunk:
                raise RuntimeError("WebSocket 连接已断开")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def send(self, text):
        payload = text.encode("utf-8")
        n = len(payload)
        head = bytearray([0x81])
        if n < 126:
            head.append(0x80 | n)
        elif n < 65536:
            head.append(0x80 | 126)
            head += struct.pack(">H", n)
        else:
            head.append(0x80 | 127)
            head += struct.pack(">Q", n)
        mask = os.urandom(4)
        head += mask
        self.sock.sendall(bytes(head) + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

    def recv(self):
        data = b""
        while True:
            b0, b1 = self._take(2)
            fin, opcode = b0 & 0x80, b0 & 0x0F
            length = b1 & 0x7F
            if length == 126:
                length = struct.unpack(">H", self._take(2))[0]
            elif length == 127:
                length = struct.unpack(">Q", self._take(8))[0]
            mask = self._take(4) if (b1 & 0x80) else None
            payload = self._take(length) if length else b""
            if mask:
                payload = bytes(c ^ mask[i % 4] for i, c in enumerate(payload))
            if opcode == 0x9:
                self._ctrl(0xA, payload)
                continue
            if opcode == 0xA:
                continue
            if opcode == 0x8:
                raise RuntimeError("服务端关闭了 WebSocket")
            data += payload
            if fin:
                return data.decode("utf-8", "replace")

    def _ctrl(self, opcode, payload):
        mask = os.urandom(4)
        head = bytearray([0x80 | opcode, 0x80 | len(payload)]) + mask
        try:
            self.sock.sendall(bytes(head) + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))
        except Exception:
            pass

    def close(self):
        self._ctrl(0x8, b"")
        try:
            self.sock.close()
        except Exception:
            pass


class CDP:
    def __init__(self, ws_url):
        self.ws = WS(ws_url)
        self._id = 0
        self.events = []  # 旁路收到的事件（Network.* 等），供断言使用

    def cmd(self, method, params=None, timeout=60):
        self._id += 1
        mid = self._id
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        deadline = time.time() + timeout
        while time.time() < deadline:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"{method} 失败: {msg['error']}")
                return msg.get("result", {})
            if "method" in msg:
                self.events.append(msg)
        raise TimeoutError(f"{method} 超时（{timeout}s）")

    def urls_seen(self, clear=True):
        """返回已记录到的 Network 请求 URL 列表（需要事先 Network.enable）。"""
        out = [
            e["params"]["request"]["url"]
            for e in self.events
            if e.get("method") == "Network.requestWillBeSent"
        ]
        if clear:
            self.events = [e for e in self.events if e.get("method") != "Network.requestWillBeSent"]
        return out

    def drain(self):
        """发一个空 evaluate 把积压的事件读干净。"""
        try:
            self.js("1")
        except Exception:
            pass

    def js(self, expr, await_promise=False, timeout=60):
        r = self.cmd(
            "Runtime.evaluate",
            {"expression": expr, "returnByValue": True, "awaitPromise": await_promise},
            timeout=timeout,
        )
        if r.get("exceptionDetails"):
            d = r["exceptionDetails"]
            desc = (d.get("exception") or {}).get("description") or d.get("text")
            raise RuntimeError("页面 JS 异常: " + str(desc)[:400])
        return r.get("result", {}).get("value")

    def key(self, k):
        """真发一个按键（走 CDP 输入通道），用来测键盘裁决而不是直接调函数。

        keyDown 需要同时给 windowsVirtualKeyCode + nativeVirtualKeyCode，
        否则页面里读到的 e.key 可能是空字符串，快捷键分支根本不走。
        """
        code = ord(k) if len(k) == 1 else 0
        base = {
            "key": k,
            "code": f"Digit{k}" if k.isdigit() else "",
            "windowsVirtualKeyCode": code,
            "nativeVirtualKeyCode": code,
        }
        for t in ("keyDown", "keyUp"):
            self.cmd("Input.dispatchKeyEvent", {"type": t, **base}, timeout=15)

    def wait_for(self, expr, timeout=45, interval=0.3):
        t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                if self.js(expr, timeout=15):
                    return True
            except Exception:
                pass
            time.sleep(interval)
        return False

    def shot(self, path):
        r = self.cmd("Page.captureScreenshot", {"format": "png"})
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(base64.b64decode(r["data"]))
        return path

    def close(self):
        self.ws.close()


# ------------------------------- 启动/连接 -------------------------------
def find_chrome():
    for p in CHROME_CANDIDATES:
        if os.path.isfile(p):
            return p
    raise RuntimeError("未找到 Chrome/Edge")


def launch(chrome, port):
    ud = os.path.join(tempfile.gettempdir(), f"gallery_cdp_ud_{port}")
    args = [
        chrome,
        "--headless=new",
        f"--remote-debugging-port={port}",
        f"--user-data-dir={ud}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions",
        "--disable-background-networking",
        "--disable-sync",
        "--disable-gpu",
        "--hide-scrollbars",
        "--window-size=1440,900",
        "about:blank",
    ]
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(100):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1) as r:
                r.read()
            return proc
        except Exception:
            time.sleep(0.25)
    proc.kill()
    raise RuntimeError("Chrome 调试端口未就绪")


def open_page(port, url):
    tgt = None
    for method in ("PUT", "GET"):
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/json/new?{quote(url, safe='')}", method=method
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                tgt = json.loads(r.read())
            break
        except Exception:
            time.sleep(0.5)
    if tgt is None:
        raise RuntimeError("无法新建标签页")
    return CDP(tgt["webSocketDebuggerUrl"])


def state_now():
    return json.load(urllib.request.urlopen(BASE + "/api/state", timeout=90))


def post_state(name, st):
    req = urllib.request.Request(
        BASE + "/api/review/state",
        data=json.dumps({"name": name, "state": st}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return json.load(urllib.request.urlopen(req, timeout=30))


# ------------------------------- 用例 -------------------------------
WALL_SNIPPET = (
    '(()=>{const c=[...document.querySelectorAll("#wallTape .album")];'
    'return [c.length, c.slice(0,5).map(x=>{const t=x.querySelector(".al-name");'
    'return t?t.textContent:"?";})];})()'
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=BASE + "/")
    ap.add_argument("--port", type=int, default=9333)
    ap.add_argument("--shots", action="store_true")
    args = ap.parse_args()

    chrome = find_chrome()
    print(f"浏览器：{chrome}")
    try:
        shutil.copy2(STATE_FILE, STATE_BACKUP)
        print(f"已备份状态文件 -> {STATE_BACKUP}")
    except OSError as e:
        print(f"⚠ 状态文件备份失败（{e}），仍继续")
    proc = launch(chrome, args.port)
    cdp = None
    try:
        cdp = open_page(args.port, "about:blank")
        cdp.cmd("Page.enable")
        cdp.cmd("Runtime.enable")
        cdp.cmd("Log.enable")
        cdp.cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": """
          window.__probeErrors = [];
          window.addEventListener('error', e => window.__probeErrors.push('error: ' + (e.message || e.type)));
          window.addEventListener('unhandledrejection', e => window.__probeErrors.push(
            'rejection: ' + String((e.reason && e.reason.message) || e.reason)));
        """
            },
        )
        cdp.cmd("Page.navigate", {"url": args.url})

        print("=" * 72)
        print("1. 页面启动")
        booted = cdp.wait_for('document.querySelectorAll("#folderList .item").length > 0')
        n_items = cdp.js('document.querySelectorAll("#folderList .item").length')
        check("侧栏渲染出组列表", booted, f"{n_items} 项")
        check(
            "rootPath 已填",
            bool(cdp.js('$("rootPath").textContent.trim()')),
            str(cdp.js('$("rootPath").textContent'))[:40],
        )

        print("=" * 72)
        print("2. 图包墙：切换文件夹必须刷新封面（体检报告 F1 修复验证）")
        names = cdp.js("S.folders.filter(f=>f.media_count>40).slice(0,2).map(f=>f.name)")
        a, b = names[0], names[1]
        print(f"  样本组：A={a}  B={b}")

        cdp.js(f"openFolder({json.dumps(a)})", await_promise=True)
        cdp.js('setView("grid")')
        time.sleep(0.8)
        st1 = cdp.js(WALL_SNIPPET)
        a_albums = cdp.js("S.albums.map(x=>x.name).slice(0,5)")
        check("A 组墙上有卡片且内容正确", st1[0] > 0 and st1[1] == a_albums, f"{st1[0]} 张 {st1[1][:3]}")

        cdp.js(f"openFolder({json.dumps(b)})", await_promise=True)
        cdp.js('setView("grid")')
        time.sleep(0.8)
        st2 = cdp.js(WALL_SNIPPET)
        b_albums = cdp.js("S.albums.map(x=>x.name).slice(0,5)")
        check("切换后卡片数量与之前相同（老 bug 的触发条件）", st2[0] == st1[0], f"{st1[0]} -> {st2[0]}")
        check("★ 切换后卡片已换成 B 组内容（F1 修复生效）", st2[1] == b_albums, f"{st2[1][:3]}")

        print("=" * 72)
        print("3. 单张视图 + 图包硬边界（红线 C5）")
        cdp.js(f"openFolder({json.dumps(a)})", await_promise=True)
        cdp.js('setView("single")')
        time.sleep(1.5)
        check("单张视图已激活", cdp.js('$("singleView").classList.contains("on")'), "")
        tag = cdp.js('(document.querySelector("#mediaHost img, #mediaHost video")||{}).tagName||""')
        check("媒体元素已生成", tag in ("IMG", "VIDEO"), str(tag))
        check(
            "计数器已渲染",
            "/" in str(cdp.js('$("counter").textContent')),
            str(cdp.js('$("counter").textContent')),
        )
        cdp.js("lastInAlbum()")
        time.sleep(0.5)
        i1 = cdp.js("S.idx")
        # 【别直接读 toast.textContent】去重标记的异步回调（loadDedup 返回后）
        # 会在 step() 弹完"最后一张"之后再弹一条，把文本覆盖掉 ——
        # 页面本身没问题，是断言读得太晚/太早都会踩空。
        # 改成挂钩 toast() 记录所有消息，不管后面被谁覆盖。
        cdp.js(
            "window.__toasts=[];if(!window.__toastHooked){"
            "const _t=window.toast;"
            "window.toast=function(m){window.__toasts.push(String(m));"
            "return _t.apply(null,arguments)};"
            "window.__toastHooked=true}"
        )
        cdp.js("step(1)")
        time.sleep(0.6)
        check("★ 图包尾部再往后不跨包", cdp.js("S.idx") == i1, f"idx {i1} -> {cdp.js('S.idx')}")
        _msgs = str(cdp.js("window.__toasts.join(' | ')"))
        check("越界有提示文案", "最后一张" in _msgs, _msgs or "(没有弹任何 toast)")
        cdp.js("firstInAlbum()")
        time.sleep(0.4)
        i2 = cdp.js("S.idx")
        cdp.js("step(-1)")
        time.sleep(0.4)
        check("★ 图包首部再往前不跨包", cdp.js("S.idx") == i2, f"idx {i2}")

        print("=" * 72)
        print("4. 图包墙虚拟滚动：节点数不失控")
        cdp.js('setView("grid")')
        time.sleep(0.6)
        cdp.js('$("wall").scrollTop = 3000')
        time.sleep(0.7)
        n_mid = cdp.js('document.querySelectorAll("#wallTape .album").length')
        cdp.js('$("wall").scrollTop = 9000')
        time.sleep(0.7)
        n_bot = cdp.js('document.querySelectorAll("#wallTape .album").length')
        check(
            "滚动后挂载节点数仍受限（节点池未泄漏）",
            0 < n_mid < 120 and 0 < n_bot < 120,
            f"中部 {n_mid} / 底部 {n_bot}",
        )
        cdp.js('$("wall").scrollTop = 0')
        time.sleep(0.6)
        after = cdp.js(WALL_SNIPPET)[1]
        check("滚回顶部后内容仍正确", after == a_albums, f"{after[:3]}")

        print("=" * 72)
        print("5. 单张视图下的胶片条 / 全屏 / 全屏下切组（体检报告 F3 修复验证）")
        cdp.js('setView("single")')
        time.sleep(1.5)
        check(
            "单张视图已激活（胶片条只在单张视图生效）", cdp.js('$("singleView").classList.contains("on")'), ""
        )
        cdp.js("openFs()")
        time.sleep(1.0)
        check("全屏已打开", cdp.js('$("lightbox").classList.contains("on")'), "")
        check(
            "mediaHost 迁移到 lbStage（复用节点而非重建）",
            cdp.js('$("mediaHost").parentElement.id') == "lbStage",
            str(cdp.js('$("mediaHost").parentElement.id')),
        )
        cdp.js("toggleFilm()")
        time.sleep(0.8)
        check("胶片条已开", cdp.js('$("filmstrip").classList.contains("on")'), "")
        nf = cdp.js('document.querySelectorAll("#filmTape .fthumb").length')
        check("胶片有缩略块", nf > 0, f"{nf} 块")
        cdp.js(f"openFolder({json.dumps(b)})", await_promise=True)
        time.sleep(1.6)
        fs_on = cdp.js('$("lightbox").classList.contains("on")')
        check("★ 全屏下切文件夹自动退出全屏（F3 修复生效）", fs_on is False, f"lightbox.on={fs_on}")
        check(
            "mediaHost 迁回 mediaStage",
            cdp.js('$("mediaHost").parentElement.id') == "mediaStage",
            str(cdp.js('$("mediaHost").parentElement.id')),
        )
        cdp.js("if(S.filmOn)toggleFilm()")
        cdp.js('setView("grid")')
        time.sleep(0.6)

        print("=" * 72)
        print("6. 未选文件夹时点标记按钮 —— 不得污染状态文件（体检报告 F2 修复验证）")
        before = state_now()["review"]
        cdp.js("S.folder=null")
        cdp.js('$("btnKept").click()')
        time.sleep(1.6)
        after6 = state_now()["review"]
        check(
            "★ 状态文件记录数不变（F2 修复生效）",
            len(before) == len(after6),
            f"{len(before)} -> {len(after6)}",
        )
        check("没有 null/None 假键", "null" not in after6 and "None" not in after6, "")
        check(
            "kept 计数未虚增",
            sum(1 for v in after6.values() if v.get("state") == "kept")
            == sum(1 for v in before.values() if v.get("state") == "kept"),
            "",
        )

        print("=" * 72)
        print("7. 标记后跳下一组的锚点（体检报告 F4 修复验证）")
        # F4 的失效场景必须靠筛选触发：当前组被筛选条件排除后，老逻辑会跳回列表首项。
        # 所以这里显式打开「未看」筛选，并且【只碰完全没有记录的组】，避免动到真实审查进度。
        cdp.js('$("catFilter").value=""')
        cdp.js('$("search").value=""')
        cdp.js('$("stateFilter").value="unreviewed"')
        cdp.js("applyFilter()")
        free = cdp.js("""(()=>{const f=S.folders.filter(x=>!S.review[x.name]);
                       return f.slice(0,4).map(x=>x.name);})()""")
        print(f"  完全无记录的组样本：{free}")
        if len(free) >= 3:
            anchor = free[1]  # 故意从第 2 个开始，模拟"跳着看"
            # 独立算出期望值：按 S.folders 的顺序，取 anchor 之后第一个仍未处理的组
            expected = cdp.js(
                """(()=>{const order=S.folders.map(f=>f.name);
                       const base=order.indexOf(%s);
                       for(let i=base+1;i<order.length;i++){const n=order[i];
                         const st=stateOf(n); if(st!=="kept"&&st!=="marked")return n;}
                       return order[0];})()"""
                % json.dumps(anchor)
            )
            cdp.js(f"openFolder({json.dumps(anchor)})", await_promise=True)
            time.sleep(1.0)
            cdp.js("decideAndNext('kept')")
            time.sleep(2.2)
            landed = cdp.js("S.folder")
            check(
                "★ 筛选下按 K 落到列表位置的下一个（F4 修复生效）",
                landed == expected,
                f"从 {anchor} 跳到 {landed}，期望 {expected}",
            )
            # 只还原 anchor：landed 全程没被改过，绝不能去动它的记录
            post_state(anchor, "none")
        else:
            check("样本不足，跳过 F4 用例", True, "（无记录的组少于 3 个）")
        cdp.js('$("stateFilter").value=""')
        cdp.js("applyFilter()")
        time.sleep(1.6)
        back = state_now()["review"]
        check(
            "★ 测试结束后状态文件与开始前完全一致（零副作用）",
            back == before,
            f"{len(before)} 条 -> {len(back)} 条"
            + ("" if back == before else f"；差异键={sorted(set(before) ^ set(back))[:5]}"),
        )

        print("=" * 72)
        print("8. 断线恢复")
        cdp.js("S.folders.length=0")
        cdp.js("boot()", await_promise=True)
        time.sleep(1.2)
        n2 = cdp.js('document.querySelectorAll("#folderList .item").length')
        check("boot() 可重复执行且组列表恢复", n2 > 0, f"{n2} 项")

        print("=" * 72)
        print("9. 滚轮语义 + 翻图性能（滚轮翻图 / Ctrl+滚轮缩放 / 连翻不拉原图）")
        cdp.cmd("Network.enable")
        cdp.js(f"openFolder({json.dumps(a)})", await_promise=True)
        cdp.js('setView("single")')
        time.sleep(1.5)
        # 定位到包中段，避免一上来就撞边界
        cdp.js("S.idx = Math.min(albumAt(S.idx).start + 2, albumAt(S.idx).end - 3)")
        cdp.js("show()")
        time.sleep(2.0)  # 等当前这张的原图加载完
        cdp.drain()
        cdp.urls_seen()

        def wheel(dy, ctrl=False, n=1):
            mods = 2 if ctrl else 0
            for _ in range(n):
                cdp.cmd(
                    "Input.dispatchMouseEvent",
                    {
                        "type": "mouseWheel",
                        "x": 800,
                        "y": 420,
                        "deltaX": 0,
                        "deltaY": dy,
                        "modifiers": mods,
                        "pointerType": "mouse",
                    },
                )
                time.sleep(0.12)

        # 9a 连续快翻 8 张（间隔 120ms，短于 ORIGIN_DELAY=320ms，所以中途不会触发原图）
        # 注意：别在最后一次翻图后 sleep 超过 ORIGIN_DELAY，否则那一张的原图会正常补上，
        # 这是预期行为，不是 bug —— 所以阈值取「≤1」而不是「=0」，仍然能挡住回归
        # （旧实现约 5 次/张，8 张就是 40 次原图请求）。
        i0 = cdp.js("S.idx")
        cdp.urls_seen()
        wheel(120, n=8)
        time.sleep(0.15)
        cdp.drain()
        fast = cdp.urls_seen()
        n_origin_fast = sum(1 for u in fast if "/media?" in u)
        n_prev_fast = sum(1 for u in fast if "/thumb?" in u and "edge=1600" in u)
        i1 = cdp.js("S.idx")
        print(f"  快翻 8 次：idx {i0} → {i1}（+{i1 - i0}）")
        print(f"    期间网络请求：原图 /media = {n_origin_fast} 次，预览 /thumb edge=1600 = {n_prev_fast} 次")
        check("★ 滚轮向下翻图（8 次 → 索引前进 8）", i1 - i0 == 8, f"+{i1 - i0}")
        check(
            "★ 连翻 8 张最多只补 1 张原图（旧实现约 40 次）",
            n_origin_fast <= 1,
            f"原图请求 {n_origin_fast} 次",
        )
        check("连翻时邻居预览有被预载", n_prev_fast > 0, f"{n_prev_fast} 次")

        # 9b 预览尺寸够屏幕时：**根本不拉原图**，翻过去立刻就是清晰预览，只补一个真实分辨率。
        # 理由：预览尺寸按屏幕算（4K 要 3840，上限 4200），再拉一张 8.5MB 原图
        # （解码后 91MB 位图）屏幕上看不出差别，纯浪费 IO/内存/CPU。
        cdp.js("jumpAlbum(1)")
        time.sleep(0.6)
        need_origin = cdp.js("needOrigin()")
        pe = cdp.js("previewEdge")
        cdp.urls_seen()
        time.sleep(2.0)  # 若还要拉原图，这段时间足够发生
        cdp.drain()
        slow = cdp.urls_seen()
        n_origin_slow = sum(1 for u in slow if "/media?" in u)
        if need_origin is False:
            check(
                "★ 预览够屏幕时完全不拉原图",
                n_origin_slow == 0,
                f"previewEdge={pe} · 原图请求 {n_origin_slow} 次",
            )
        else:
            check(
                "★ 预览不够屏幕时补拉当前张原图",
                n_origin_slow >= 1,
                f"previewEdge={pe} · 原图请求 {n_origin_slow} 次",
            )

        # 9b2 翻过去必须立刻可看清（不再有"先糊后清"）
        cdp.js("S.idx = Math.min(albumAt(S.idx).start + 1, albumAt(S.idx).end - 4)")
        cdp.js("show()")
        time.sleep(2.0)
        cdp.urls_seen()
        wheel(120, n=1)
        time.sleep(0.6)
        cdp.drain()
        after = cdp.urls_seen()
        n_med = sum(1 for u in after if "/media?" in u)
        st_now = cdp.js(
            "(()=>{const i=document.querySelector('#mediaHost img');"
            "const s=(i&&i.getAttribute('src'))||'';"
            "return {k:s.indexOf('/media?')>=0?'origin':(s.indexOf('/thumb?')>=0?'preview':'none'),"
            "c:!!(i&&i.complete),blur:i?i.classList.contains('origin-loading'):null,"
            "nw:i?i.naturalWidth:0};})()"
        )
        check(
            "★ 翻过去立刻可看清（complete 且非模糊态）",
            st_now["c"] is True and st_now["blur"] is False,
            f"kind={st_now['k']} complete={st_now['c']} blur={st_now['blur']} nw={st_now['nw']}",
        )
        if need_origin is False:
            check("★ 该次翻页没有付出原图代价（0 次 /media）", n_med == 0, f"新请求 {n_med} 次")
        # 真实分辨率必须还能显示（靠 /api/dim 只读文件头，不解码像素）
        # 顺带把「缩放卡顿」的根因钉死：预览即最终画质时绝不能带 origin-loading。
        # 那层 blur(5px) 要对整张位图做高斯模糊 —— 原图可达 7952×5304（解码后 161MB 位图），
        # 实测 4K 下加/解一次 blur 会产生 4 次长帧、最长 50ms，正是 Ctrl+滚轮缩放卡顿的真凶。
        cls_now = cdp.js(
            "(()=>{const i=document.querySelector('#mediaHost img');return i?i.className:'';})()"
        )
        if need_origin is False:
            check(
                "★ 预览即最终画质时不加 blur（缩放卡顿的根因）",
                "origin-loading" not in (cls_now or ""),
                f"class='{cls_now}'",
            )
        info = str(cdp.js('$("v-file").textContent'))
        import re as _re

        m = _re.search(r"(\d{3,5})×(\d{3,5})", info)
        check(
            "★ 分辨率照常显示（走 /api/dim，不为两个数字解码大图）", bool(m), (m.group(0) if m else info[:70])
        )

        # 9c 屏幕比预览上限还大（5K+）时，应回退到"延后拉原图"那条路
        cdp.cmd(
            "Emulation.setDeviceMetricsOverride",
            {"width": 4400, "height": 2400, "deviceScaleFactor": 1, "mobile": False},
        )
        cdp.cmd("Page.navigate", {"url": args.url})
        cdp.wait_for(
            'typeof previewEdge !== "undefined" && document.querySelectorAll("#folderList .item").length>0',
            timeout=60,
        )
        time.sleep(1.0)
        check(
            "5K 场景下 needOrigin() 为真（回退到原图路径）",
            cdp.js("[previewEdge, needOrigin()]")[1] is True,
            f"previewEdge={cdp.js('previewEdge')}",
        )
        cdp.cmd("Emulation.clearDeviceMetricsOverride")
        cdp.cmd("Page.navigate", {"url": args.url})
        cdp.wait_for(
            'typeof previewEdge !== "undefined" && document.querySelectorAll("#folderList .item").length>0',
            timeout=60,
        )
        cdp.js(f"openFolder({json.dumps(a)})", await_promise=True)
        cdp.js('setView("single")')
        time.sleep(2.0)

        # 9c 滚轮向上（先挪到图包中段，否则落在包首会被 C5 边界正确拦住）
        cdp.js("S.idx = Math.min(albumAt(S.idx).start + 3, albumAt(S.idx).end - 1)")
        cdp.js("show()")
        time.sleep(0.8)
        i2 = cdp.js("S.idx")
        wheel(-120, n=3)
        time.sleep(0.4)
        check("滚轮向上回翻", cdp.js("S.idx") == i2 - 3, f"{i2} → {cdp.js('S.idx')}")

        # 9d Ctrl+滚轮只缩放，不动索引；且缩放时必须去拉原图（预览被放大就糊了）
        cdp.js("resetView()")
        i3 = cdp.js("S.idx")
        cdp.urls_seen()
        wheel(-120, ctrl=True, n=2)
        time.sleep(0.9)
        cdp.drain()
        zoom_urls = cdp.urls_seen()
        n_zoom_origin = sum(1 for u in zoom_urls if "/media?" in u)
        z = cdp.js("S.zoom")
        check("★ Ctrl+滚轮 缩放生效", z > 1.05, f"zoom={z:.2f}")
        check("★ Ctrl+滚轮 不改变当前张", cdp.js("S.idx") == i3, f"idx={cdp.js('S.idx')}")
        check(
            "★ 缩放时才去拉原图（放大后必须清晰）", n_zoom_origin >= 1, f"缩放触发 /media {n_zoom_origin} 次"
        )
        cdp.js("resetView()")

        # 9e 包边界不跨包（红线 C5，滚轮也不能破）
        cdp.js("lastInAlbum()")
        time.sleep(0.6)
        i4 = cdp.js("S.idx")
        wheel(120, n=4)
        time.sleep(0.6)
        check("★ 滚轮到图包末尾不跨包（红线 C5）", cdp.js("S.idx") == i4, f"idx {i4} → {cdp.js('S.idx')}")

        print("=" * 72)
        print("10. 预热对话框的接线（不真的触发预热，那由 hardening_check 的 H 段覆盖）")
        cdp.js('$("prewarmBtn").click()')
        time.sleep(0.4)
        check("点「预热」能打开对话框", cdp.js('$("pw").classList.contains("on")'), "")
        check("对话框里有「当前组 / 未判定组」两个入口", cdp.js('!!$("pwGroup") && !!$("pwUnrev")'), "")
        check(
            "进度区有内容",
            len(str(cdp.js('$("pwProg").textContent'))) > 0,
            str(cdp.js('$("pwProg").textContent'))[:20],
        )
        cdp.js('$("pwClose").click()')
        time.sleep(0.3)
        check("能关闭对话框", cdp.js('$("pw").classList.contains("on")') is False, "")

        print("=" * 72)
        print("11. 图包级去重标记（v5.10）—— 依赖 dedup 索引，未建索引时优雅跳过")
        # 先问服务端哪些组已索引且有整包重复，避免硬编码某个组名
        dup_ok = False
        try:
            st = json.load(urllib.request.urlopen(BASE + "/api/dedup/status", timeout=15))
            cov = st.get("coverage", 0)
            print(f"  索引覆盖：{st.get('indexed', 0):,} / {st.get('total_media', 0):,} = {cov * 100:.1f}%")
            # 从已索引组里找一个有整包重复的
            cand = None
            for f in json.load(urllib.request.urlopen(BASE + "/api/state", timeout=30))["folders"]:
                try:
                    r = json.load(
                        urllib.request.urlopen(
                            BASE + "/api/dedup/group?folder=" + urllib.parse.quote(f["name"]), timeout=60
                        )
                    )
                    if r.get("pkg_drops"):
                        cand = (f["name"], r)
                        break
                except urllib.error.HTTPError:
                    continue
                if cand:
                    break
            if cand:
                name, r = cand
                print(
                    f"  样本组：{name}（{r['total']} 张，整包关系 {len(r['pkg_pairs'])} 对"
                    f" → 建议删 {len(r['pkg_drops'])} 个）"
                )
                # 无头窗口默认 clientHeight=0，墙的可视区算出来是 0，只会挂载 3 张卡片
                # —— 那样无论标记对不对都测不出来。先给一个真实视口。
                cdp.cmd(
                    "Emulation.setDeviceMetricsOverride",
                    {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False},
                )
                cdp.cmd(
                    "Page.navigate", {"url": BASE + "/?folder=" + urllib.parse.quote(name) + "&view=grid"}
                )
                time.sleep(3.0)
                # loadDedup 是异步的，轮询等它落地
                got = 0
                for _ in range(30):
                    # 注意：dedupMap 是顶层 let 声明，不挂 window，只能按词法名直接读
                    got = cdp.js("(typeof dedupMap!=='undefined'&&dedupMap)?dedupMap.size:0") or 0
                    if got:
                        break
                    time.sleep(0.5)
                # 滚到第一个被标记的图包，保证它一定被挂载（否则"该标没标"测不出来）
                first = cdp.js("S.albums.findIndex(a=>dedupMap.has(a.name))")
                if isinstance(first, int) and first >= 0:
                    cdp.js(f"wall.select({first})")
                    time.sleep(1.0)
                dom = cdp.js('document.querySelectorAll("#wallTape .al-dup").length') or 0
                # 墙是虚拟滚动的，只挂载可视+overscan 的卡片，所以 DOM 里的标记数【必然】
                # 小于 dedupMap.size。正确断言是"已挂载且被标记"的卡片数 == DOM 标记数。
                exp = (
                    cdp.js(
                        "(()=>{const cs=[...document.querySelectorAll('#wallTape .album')];"
                        "return cs.filter(c=>c._ai!=null&&S.albums[c._ai]"
                        "&&dedupMap.has(S.albums[c._ai].name)).length})()"
                    )
                    or 0
                )
                check(
                    "★ 后端删除清单非空且去重（每包一条）",
                    len(r["pkg_drops"]) > 0
                    and len({d["pkg"] for d in r["pkg_drops"]}) == len(r["pkg_drops"]),
                    f"{len(r['pkg_drops'])} 个待删图包",
                )
                check(
                    "★ 待删包的字节不重复累加",
                    r.get("bytes_recoverable", 0) <= sum(d.get("bytes", 0) for d in r["pkg_drops"]) + 1,
                    f"{r.get('bytes_recoverable', 0) / 1024**3:.2f} GB",
                )
                check(
                    "★ 前端 dedupMap 已填充",
                    got == len(r["pkg_drops"]),
                    f"map={got} 后端={len(r['pkg_drops'])}",
                )
                check("★ 图包墙上渲染出去重标记", dom > 0, f"DOM 中 {dom} 个 .al-dup")
                check(
                    "★ 挂载卡片里该标记的都标了（虚拟滚动下按挂载数比对）",
                    exp > 0 and dom == exp,
                    f"DOM={dom} 应标={exp} map={got}",
                )
                dup_ok = True
            else:
                print("  跳过：已索引的组里还没有整包重复样本")
        except Exception as e:
            check("去重标记探测", False, f"{type(e).__name__}: {e}")
        if not dup_ok:
            print("  （未产生断言：索引尚未覆盖到有重复的组，属正常）")

        print("=" * 72)
        print("12. 重复对裁决面板（B 级，v5.11）—— 依赖 dedup 索引")
        pq_ok = False
        try:
            # 找一个真的有重复对的组（不硬编码组名）
            pname, pr = None, None
            for f in json.load(urllib.request.urlopen(BASE + "/api/state", timeout=30))["folders"]:
                try:
                    r = json.load(
                        urllib.request.urlopen(
                            BASE + "/api/dedup/pairs?folder=" + urllib.parse.quote(f["name"]), timeout=60
                        )
                    )
                    if r.get("total_pairs"):
                        pname, pr = f["name"], r
                        break
                except urllib.error.HTTPError:
                    continue
            if not pname:
                print("  跳过：已索引的组里还没有重复对样本")
            else:
                print(
                    f"  样本组：{pname}（{pr['total_pairs']} 对 · "
                    f"排除 A 级整包 {pr.get('excluded_pkgs', 0)} 个）"
                )
                cdp.cmd(
                    "Page.navigate", {"url": BASE + "/?folder=" + urllib.parse.quote(pname) + "&view=grid"}
                )
                time.sleep(3.0)
                cdp.js('document.getElementById("dupBtn").click()')
                time.sleep(2.5)
                on = cdp.js('document.getElementById("dup").classList.contains("on")')
                check("★ 点「去重」打开裁决面板", on is True, "")
                got = cdp.js("(typeof dup!=='undefined'&&dup)?dup.list.length:-1") or 0
                check("★ 队列加载成功", got == pr["total_pairs"], f"前端 {got} / 后端 {pr['total_pairs']}")
                srcL = cdp.js('document.querySelector("#dupL img").getAttribute("src")') or ""
                srcR = cdp.js('document.querySelector("#dupR img").getAttribute("src")') or ""
                capL = cdp.js('document.querySelector("#dupL figcaption").textContent.trim()') or ""
                check(
                    "★ 左右两张图都渲染出来",
                    bool(srcL) and bool(srcR) and srcL != srcR,
                    f"{srcL[-28:]} | {srcR[-28:]}",
                )
                check("★ 说明文字填了（包/体积）", len(capL) > 4, capL[:40])
                check(
                    "★ 左=建议保留 / 右=建议删除 有徽标",
                    (cdp.js('document.querySelector("#dupL .badge").textContent') or "").find("保留") >= 0
                    and (cdp.js('document.querySelector("#dupR .badge").textContent') or "").find("删") >= 0,
                    "",
                )
                # 真删会动到素材，所以把 api.rmFile 换成记录器：验证"按 2 删的是右（drop）那张"
                cdp.js(
                    "window.__rm=[];api.rmFile=async(f,rel,p)=>{window.__rm.push({f,rel,p});"
                    "return {ok:true,freed:1024};}"
                )
                first_drop = pr["pairs"][0]["drop"]["rel"]
                cdp.key("2")
                time.sleep(1.0)
                rm = cdp.js("window.__rm") or []
                check(
                    "★ 按 2 = 删右（后端建议的那张）",
                    bool(rm) and rm[-1].get("rel") == first_drop,
                    (rm[-1].get("rel", "")[-34:] if rm else "无调用"),
                )
                check("★ 走的是回收站而不是永久删", bool(rm) and rm[-1].get("p") is False, "")
                cdp.key("1")
                time.sleep(1.0)
                rm = cdp.js("window.__rm") or []
                check(
                    "★ 按 1 = 删左（反向裁决）",
                    len(rm) >= 2 and rm[-1].get("rel") != first_drop,
                    (rm[-1].get("rel", "")[-34:] if len(rm) >= 2 else "无调用"),
                )
                # 被删掉的 rel 不能再次出现在队列里
                check(
                    "★ 已删的图不会再出现（gone 名单生效）",
                    cdp.js(f"dup.gone.has({json.dumps(first_drop)})") is True,
                    "",
                )
                cdp.key("Escape")
                time.sleep(0.8)
                check(
                    "★ Esc 关闭面板",
                    cdp.js('document.getElementById("dup").classList.contains("on")') is False,
                    "",
                )
                pq_ok = True
        except Exception as e:
            check("重复对裁决面板探测", False, f"{type(e).__name__}: {e}")
        if not pq_ok:
            print("  （未能完成，后续断言以实际结果为准）")

        print("=" * 72)
        print("13. console 零报错")
        errs = cdp.js("window.__probeErrors||[]")
        noise = ("favicon", "Failed to load resource", "net::ERR_")
        real = [e for e in (errs or []) if not any(k in e for k in noise)]
        check("★ 自 boot 起零未捕获异常 / 零未处理拒绝", not real, f"{real[:3] if real else '干净'}")

        if args.shots:
            cdp.js(f"openFolder({json.dumps(a)})", await_promise=True)
            cdp.js('setView("grid")')
            time.sleep(1.5)
            print("  截图：" + cdp.shot(os.path.join(SHOTS, "01_图包墙.png")))
            cdp.js('setView("single")')
            time.sleep(2.0)
            print("  截图：" + cdp.shot(os.path.join(SHOTS, "02_单张.png")))

        print("=" * 72)
        print(f"浏览器回归结果：PASS {ok} / FAIL {fail}")
        _rc = 0 if fail == 0 else 1
    finally:
        # 【顺序很关键】必须先彻底断开浏览器，再做自清理。
        # 页面还开着的时候还原浏览位置，前端会立刻再保存一次进度把还原结果冲掉
        # —— v5.11 实测：还原成 20 之后又被写成 80，自清理形同虚设。
        try:
            if cdp:
                cdp.close()
        except Exception:
            pass
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        _restore_and_compare()
    return _rc


def _restore_and_compare():
    """自清理 + 逐键比对。必须在浏览器关掉之后调用，理由见上面的 finally。"""
    # 自清理：探针像真人一样翻图，必然改动"浏览位置"(index)——那不是用户的行为，
    # 留着就是污染。比对之前先把 index 还原回备份值（state/ts 不动）。
    try:
        _s0 = json.load(open(STATE_BACKUP, encoding="utf-8"))
        _f0 = json.load(open(STATE_FILE, encoding="utf-8"))
        _fixed = []
        for _k, _v in _s0.items():
            if not (isinstance(_v, dict) and isinstance(_f0.get(_k), dict)):
                continue
            if _v.get("index") == _f0[_k].get("index"):
                continue
            try:
                _rq = urllib.request.Request(
                    BASE + "/api/review/progress",
                    data=json.dumps({"name": _k, "index": int(_v.get("index") or 0)}).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                urllib.request.urlopen(_rq, timeout=20).read()
                _fixed.append(_k)
            except Exception:
                pass
        if _fixed:
            time.sleep(1.5)  # 等服务端落盘
            print(f"浏览位置已还原：{len(_fixed)} 组（{_fixed[0]}{'…' if len(_fixed) > 1 else ''}）")
    except Exception:
        pass
    # 全局兜底：把最终状态与开头备份逐键比对，非预期差异必须暴露出来
    try:
        snap = json.load(open(STATE_BACKUP, encoding="utf-8"))
        final = json.load(open(STATE_FILE, encoding="utf-8"))
        lost = [k for k in snap if k not in final]
        gained = [k for k in final if k not in snap]
        changed = [k for k in snap if k in final and snap[k] != final[k]]
        # 精确拆解"变了什么字段"：ts 是"最后操作时间"，被浏览一下就会刷新，属无害；
        # index/state 是用户的真实决策，一动就必须报警。旧实现把两者混为一谈，
        # 打印的"N 条 index 有正常变动"甚至与实际不符（可能只有 ts 动）——会误导人。
        ts_only, semantic = [], []
        for k in changed:
            a, b = snap[k], final[k]
            fields = {kk for kk in (set(a) | set(b)) if a.get(kk) != b.get(kk)}
            (ts_only if fields == {"ts"} else semantic).append((k, fields))
        if lost or gained or semantic:
            print("⚠ 状态文件出现非预期差异！")
            for k in lost:
                print(f"   丢失 {k!r} 原值={snap[k]}")
            for k in gained:
                print(f"   新增 {k!r} 值={final[k]}")
            for k, f in semantic:
                print(f"   语义变更 {k!r} 字段={sorted(f)} {snap[k]} -> {final[k]}")
            print(f'   还原命令：copy /Y "{STATE_BACKUP}" "{STATE_FILE}"（需先停服务）')
        else:
            tail = f"；{len(ts_only)} 条仅 ts 刷新（无害）" if ts_only else ""
            print(f"状态文件键集一致（{len(final)} 条{tail}）")
        print(f"备份留存：{STATE_BACKUP}（键级差异时可据此还原；确认无碍可删）")
    except Exception as e:
        print(f"状态比对跳过：{e}")


if __name__ == "__main__":
    sys.exit(main())
