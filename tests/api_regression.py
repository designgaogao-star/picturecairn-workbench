# -*- coding: utf-8 -*-
"""
图库工具 · API 层回归脚本（服务必须已在 127.0.0.1:8765 运行）

用法：
    "C:\\Users\\79974\\AppData\\Local\\Programs\\Python\\Python312\\python.exe" tests\\api_regression.py
    ... python.exe tests\\api_regression.py --deep   # 额外跑「危险路径探测」（只读，见下）

定位：配合 开发接手报告.md §11 的验证流程。它覆盖「后端整条链路 + 接口闸门」，
      但不能替代 §11.3 的浏览器回归（DOM/虚拟滚动/blur-up 那部分只能真机看）。

安全约束（守 §13.1）：
  * 全部请求只读；不调用 /api/trash、不调用带 confirm_permanent 的 /api/delete。
  * 删除接口只验「非法入参必须 400」这一种情况。
  * --deep 会探测 folder 参数越界（读 1 个已知系统小文件如 win.ini），全程只读、不写库、不删任何东西；
    默认不跑，避免在别人的机器上读不该读的文件。
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8765"
Q = urllib.parse.quote

_ok = _fail = 0
_findings = []


def req(path, method="GET", body=None, headers=None, raw=False, timeout=60):
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


def check(name, cond, detail=""):
    global _ok, _fail
    if cond:
        _ok += 1
        print(f"  PASS  {name}  {detail}")
    else:
        _fail += 1
        print(f"  FAIL  {name}  {detail}")


def note(text):
    _findings.append(text)
    print(f"  注意  {text}")


def j(s):
    try:
        return json.loads(s)
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deep", action="store_true", help="额外做 folder 越界探测（只读）")
    args = ap.parse_args()

    print("=" * 72)
    print("1. 连通性 / 静态页")
    st, body, _ = req("/api/ping", timeout=10)
    check("GET /api/ping", st == 200 and body == "pong", f"{st} {body!r}")
    st, body, _ = req("/")
    check("GET / 主站", st == 200 and "<title>GalleryTool</title>" in body, f"{st} {len(body)}B")
    st, body, _ = req("/survey")
    check("GET /survey 抽样页", st == 200 and "抽样快审" in body, f"{st} {len(body)}B")
    st, _, _ = req("/favicon.ico")
    check("GET /favicon.ico -> 204", st == 204, f"{st}")

    print("=" * 72)
    print("2. /api/state + 扫描 TTL 缓存")
    t0 = time.time()
    st, body, _ = req("/api/state")
    t_cold = (time.time() - t0) * 1000
    d = j(body)
    check(
        "200 且结构完整",
        st == 200 and d and {"root", "folders", "review", "thumb", "version"} <= set(d),
        f"{st} v={d.get('version') if d else None}",
    )
    if not d:
        print("  ✗ /api/state 不可用，后续跳过")
        return
    fs = d["folders"]
    check("thumb 组件已加载（Pillow）", d.get("thumb") is True, f"Pillow={d.get('thumb')}")
    dot = [f["name"] for f in fs if f["name"].startswith(".")]
    und = [f["name"] for f in fs if f["name"].startswith("_")]
    check("无 . 或 _ 开头的幽灵组", not dot and not und, f"点开头={dot} 下划线开头={und}")
    check(
        "按体积降序（前 50）",
        all(fs[i]["size"] >= fs[i + 1]["size"] for i in range(min(50, len(fs) - 1))),
        "",
    )
    # 先静默超过 SCAN_TTL(2.5s)，让"冷"确实是冷的。不能假设"脚本的第一次请求必然命中冷路径"：
    # 期间可能有别的东西（上一轮测试、浏览器标签、残留连接）刚好把扫描缓存捂热，断言会随机翻车。
    time.sleep(3.0)
    t0 = time.time()
    req("/api/state")
    t_cold = (time.time() - t0) * 1000
    hots = []
    for _ in range(5):
        t0 = time.time()
        req("/api/state")
        hots.append((time.time() - t0) * 1000)
    t_hot = sorted(hots)[len(hots) // 2]
    check(
        "TTL 缓存生效（热耗时中位数 × 3 < 冷）",
        t_hot * 3 < t_cold,
        f"冷 {t_cold:.1f}ms / 热中位 {t_hot:.1f}ms（5 次: {[round(x, 1) for x in hots]}）",
    )
    print(f"        {len(fs)} 组 · review {len(d['review'])} 条")

    print("=" * 72)
    print("3. /api/files 媒体清单")
    cands = sorted(
        [f for f in fs if 10 <= f["media_count"] <= 1500 and not f["name"].startswith((".", "_"))],
        key=lambda f: f["size"],
    )
    img_fol = img_it = None
    for f in cands[:8]:
        st, body, _ = req("/api/files?folder=" + Q(f["name"]))
        fl = (j(body) or {}).get("files") or []
        if not img_it:
            it = next((x for x in fl if x["kind"] == "image"), None)
            if it:
                img_fol, img_it = f, it
        if img_it:
            break
    if img_fol:
        st, body, _ = req("/api/files?folder=" + Q(img_fol["name"]))
        d2 = j(body)
        fl = d2["files"]
        check(
            "总数与 folders.media_count 一致",
            d2["total"] == len(fl) == img_fol["media_count"],
            f"{img_fol['name']} {d2['total']}",
        )
        check("rel 正斜杠无盘符", all("\\" not in x["rel"] and not x["rel"].startswith("/") for x in fl), "")
        check(
            "album = rel 一级目录",
            all(x["album"] == (x["rel"].split("/")[0] if "/" in x["rel"] else "") for x in fl),
            "",
        )
        check("kind 只有 image", all(x["kind"] == "image" for x in fl), "")
        check(
            "按 (album, rel) 升序", fl == sorted(fl, key=lambda x: (x["album"].lower(), x["rel"].lower())), ""
        )
        t0 = time.time()
        req("/api/files?folder=" + Q(img_fol["name"]))
        t = (time.time() - t0) * 1000
        check("二次请求走内存 LRU（<50ms）", t < 50, f"{t:.0f} ms")
    else:
        note("没找到含图片的小组，跳过 3/4/5 段")

    print("=" * 72)
    print("4. /thumb 缩略图")
    if img_fol and img_it:
        u = f"/thumb?folder={Q(img_fol['name'])}&file={Q(img_it['rel'])}"
        st, raw, h = req(u, raw=True)
        check(
            "默认 400/q72 是真 JPEG",
            st == 200 and raw[:2] == b"\xff\xd8" and h.get("Content-Type") == "image/jpeg",
            f"{st} {len(raw)}B",
        )
        t0 = time.time()
        req(u, raw=True)
        t1 = (time.time() - t0) * 1000
        check("缓存命中 <100ms", t1 < 100, f"{t1:.0f} ms")
        st, raw2, _ = req(f"{u}&edge=1600&q=80", raw=True)
        check(
            "edge=1600 独立缓存键且更大",
            st == 200 and raw2[:2] == b"\xff\xd8" and len(raw2) > len(raw),
            f"400->{len(raw)}B / 1600->{len(raw2)}B",
        )
        st, _, _ = req(f"/thumb?folder={Q(img_fol['name'])}&file={Q('绝对不存在.jpg')}")
        check("缺失图 -> 404", st == 404, f"{st}")
    print("=" * 72)
    print("5. /media：ETag 304 + Range 206")
    if img_fol and img_it:
        u = f"/media?folder={Q(img_fol['name'])}&file={Q(img_it['rel'])}"
        st, raw, h = req(u, raw=True)
        etag, n = h.get("ETag"), len(raw)
        check("200 全量且字节数与库一致", st == 200 and n == img_it["size"], f"{n}B / DB {img_it['size']}B")
        check("Accept-Ranges: bytes", h.get("Accept-Ranges") == "bytes", "")
        st, _, _ = req(u, headers={"If-None-Match": etag or "x"})
        check("ETag 命中 -> 304", st == 304, f"{st}")
        st, raw2, h2 = req(u, headers={"Range": "bytes=100-199"}, raw=True)
        check(
            "Range 中段切片精确",
            st == 206 and len(raw2) == 100 and h2.get("Content-Range") == f"bytes 100-199/{n}",
            f"{st} {len(raw2)}B",
        )
        st, raw3, _ = req(u, headers={"Range": "bytes=0-"}, raw=True)
        check("Range 开区间到结尾", st == 206 and len(raw3) == n, f"{st} {len(raw3)}B")
        st, _, h3 = req(u, headers={"Range": f"bytes={n + 100}-"}, raw=True)
        check("Range 起点越界 -> 416", st == 416, f"{st} {h3.get('Content-Range')}")
        st, raw4, _ = req(u, headers={"Range": "bytes=-100"}, raw=True)
        if st == 206 and len(raw4) == 100 and raw4 == raw[-100:]:
            check("后缀 Range bytes=-100 合规", True, "返回末尾 100 字节")
        else:
            check(
                "后缀 Range bytes=-100 合规",
                False,
                f"{st} {len(raw4)}B（RFC 7233 要求返回末尾 100 字节，实际取了开头）",
            )
        st, _, _ = req(f"/media?folder={Q(img_fol['name'])}&file={Q('没有这个文件.jpg')}")
        check("缺失文件 -> 404", st == 404, f"{st}")
    print("=" * 72)
    print("6. 抽样页 API")
    st, body, _ = req("/api/survey/list")
    check(
        "survey/list",
        st == 200 and j(body) is not None and "items" in j(body),
        f"{len(j(body).get('items', [])) if j(body) else '?'} 未处理组",
    )
    if img_fol:
        st, body, _ = req(f"/api/survey/samples?folder={Q(img_fol['name'])}&n=20&seed=1")
        d3 = j(body)
        check(
            "survey/samples",
            st == 200 and d3 is not None and "samples" in d3,
            f"抽到 {len(d3['samples']) if d3 else '?'} 张",
        )
        if d3 and d3["samples"]:
            b1 = [x["rel"] for x in d3["samples"]]
            st, b2, _ = req(f"/api/survey/samples?folder={Q(img_fol['name'])}&n=20&seed=1")
            check("同 seed 可复现", b1 == [x["rel"] for x in j(b2)["samples"]], "")
            st, b3, _ = req(f"/api/survey/samples?folder={Q(img_fol['name'])}&n=20&seed=2")
            check("异 seed 结果不同", b1 != [x["rel"] for x in j(b3)["samples"]], "")
            st, b4, _ = req(
                f"/api/survey/samples?folder={Q(img_fol['name'])}&n=20&seed=3&exclude={Q(','.join(b1[:5]))}"
            )
            overlap = set(x["rel"] for x in j(b4)["samples"]) & set(b1[:5])
            check("exclude 零重叠", not overlap, f"重叠 {len(overlap)}")
        st, body, _ = req(f"/api/survey/samples?folder={Q(img_fol['name'])}&n=99999")
        check("n 上限 200 生效", len(j(body)["samples"]) <= 200, f"{len(j(body)['samples'])}")

    print("=" * 72)
    print("7. 预热队列 / 缩略图缓存统计")
    st, body, _ = req("/api/warm/progress")
    check("warm/progress", st == 200 and j(body) is not None, f"{body}")
    st, body, _ = req("/api/thumb/stats")
    d4 = j(body)
    check("thumb/stats", st == 200 and d4 and "files" in d4, f"{d4}")
    if d4:
        print(
            f"        {d4['files']} 张 / {d4['bytes'] / 1024**2:.0f} MB / 上限 {d4['limit'] / 1024**3:.0f} GB"
        )

    print("=" * 72)
    print("8. 危险接口 —— 只验闸门，不触真实数据")
    st, body, _ = req("/api/delete", "POST", {"names": ["__回归测试_不会真删__"]})
    check("缺 confirm_permanent -> 400", st == 400, f"{st} {body[:70]}")
    st, body, _ = req("/api/delete", "POST", {"names": ["x"], "confirm_permanent": "true"})
    check("字符串 'true' 不算 -> 400", st == 400, f"{st}")
    st, body, _ = req("/api/delete", "POST", {"names": ["x"], "confirm_permanent": 1})
    check("数字 1 不算 -> 400", st == 400, f"{st}")
    st, body, _ = req("/api/trash", "POST", {"names": []})
    check("trash 空 names -> 400（无副作用）", st == 400, f"{st} {body[:50]}")

    print("=" * 72)
    print("9. 路由兜底 / 参数健壮性")
    st, _, _ = req("/api/" + Q("不存在"))
    check("未知 GET -> 404", st == 404, f"{st}")
    st, _, _ = req("/api/" + Q("不存在"), "POST", {})
    check("未知 POST -> 404", st == 404, f"{st}")
    st, body, _ = req("/api/files?folder=" + Q("___绝对不存在的组___"))
    check("非顶层组 -> 400（白名单拒绝，v5.3 起的行为）", st == 400, f"{st} {body[:60]}")
    st, body, _ = req("/api/files?folder=")
    check("空 folder -> 400（不再触发全库遍历）", st == 400, f"{st} {body[:60]}")
    if img_fol:
        st, _, _ = req("/api/survey/samples?folder=" + Q(img_fol["name"]) + "&n=abc&seed=xyz")
        check("samples 非数字参数不 500", st == 200, f"{st}")
        st, _, _ = req(f"/thumb?folder={Q(img_fol['name'])}&file={Q(img_it['rel'])}&edge=abc&q=abc")
        check("thumb 非数字参数回落默认", st == 200, f"{st}")

    print("=" * 72)
    print("10. folder 参数白名单")
    # 这一条不碰系统文件：只验证「非顶层目录名」是否被拒（合法实现应返回 400/404）
    st, body, _ = req("/media?folder=" + Q("_gallery_tool") + "&file=" + Q("review_state.json"))
    if st == 200:
        note(
            f"/media?folder=_gallery_tool 返回 200（{len(body)}B）：folder 参数未做白名单校验，"
            f"可读取非图库顶层目录下的文件 —— 见体检报告 B2"
        )
    else:
        check("非顶层 folder 被拒", st in (400, 403, 404), f"{st}")
    if args.deep:
        st, body, _ = req("/media?folder=" + Q("C:\\Windows") + "&file=" + Q("win.ini"))
        if st == 200 and body.strip():
            note(
                "绝对路径 folder 越界成功（读到 C:\\Windows\\win.ini）：os.path.join 丢弃 ROOT —— 见体检报告 B2"
            )
        else:
            check("绝对路径 folder 被拒", st in (400, 403, 404), f"{st}")

    print("=" * 72)
    print(f"结果：PASS {_ok} / FAIL {_fail}")
    if _findings:
        print("需要人工确认的条目：")
        for f in _findings:
            print("  · " + f)
    return 0 if _fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
