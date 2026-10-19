# -*- coding: utf-8 -*-
"""删除链路实测（严格遵守 开发接手报告 §13.1）。

规矩：
  * 只碰本脚本自己创建的专属临时组，绝不涉及任何真实素材；
  * 只走「回收站」路径，绝不调用 /api/delete；
  * 先验证非法入参被拒（这正是 v5.3 新增的护栏）；
  * 跑完后临时组留在回收站里，由收尾步骤还原并清除。

用法：
    python tests/delete_path_check.py create   # 建临时组 + 跑闸门用例 + 送回收站
    python tests/delete_path_check.py verify   # 确认已从磁盘与库中消失
"""

import json
import os
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8765"
ROOT = r"F:\图库"
TEMP_GROUP = "[测试]删除链路临时组"
TEMP_DIR = os.path.join(ROOT, TEMP_GROUP)
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


def req(path, method="GET", body=None, timeout=60):
    h = {}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        h["Content-Type"] = "application/json"
    r = urllib.request.Request(BASE + path, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8", "replace"))
        except Exception:
            return e.code, {}


def make_group():
    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR)
    os.makedirs(os.path.join(TEMP_DIR, "子图包"), exist_ok=True)
    for name, data in [("a.jpg", b"x" * 512), ("b.jpg", b"y" * 256), ("note.txt", b"not a media file")]:
        with open(os.path.join(TEMP_DIR, name), "wb") as f:
            f.write(data)
    with open(os.path.join(TEMP_DIR, "子图包", "c.jpg"), "wb") as f:
        f.write(b"z" * 128)


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "create"

    if action == "verify":
        print("== 确认临时组已消失 ==")
        check("磁盘上不存在", not os.path.exists(TEMP_DIR), TEMP_DIR)
        st, d = req("/api/state")
        check("不在 /api/state 列表里", all(f["name"] != TEMP_GROUP for f in d.get("folders", [])), "")
        st, d = req("/api/files?folder=" + Q(TEMP_GROUP))
        check("接口已拒绝该组（400）", st == 400, f"{st}")
        print(f"结果：PASS {ok} / FAIL {fail}")
        return 0 if fail == 0 else 1

    print("=" * 72)
    print("1. 建专属临时组")
    make_group()
    total = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(TEMP_DIR) for f in fs)
    print(f"  {TEMP_GROUP}  文件 {sum(len(fs) for _, _, fs in os.walk(TEMP_DIR))} 个 / {total} 字节")
    req("/api/rescan", "POST", {})
    st, d = req("/api/state")
    found = [f for f in d.get("folders", []) if f["name"] == TEMP_GROUP]
    check("重扫后已进组列表", bool(found), f"{found[0] if found else '未找到'}")
    if not found:
        print("  ✗ 临时组未进列表，中止以免误判")
        return 1

    print("=" * 72)
    print("2. 非媒体文件不能从 /media 流出（v5.3 B3 新增护栏）")
    st = None
    try:
        r = urllib.request.urlopen(BASE + "/media?folder=" + Q(TEMP_GROUP) + "&file=note.txt", timeout=20)
        st = r.status
    except urllib.error.HTTPError as e:
        st = e.code
    check("读 .txt 被拒 -> 415", st == 415, f"{st}")
    try:
        r = urllib.request.urlopen(BASE + "/media?folder=" + Q(TEMP_GROUP) + "&file=a.jpg", timeout=20)
        st2, n2 = r.status, len(r.read())
    except urllib.error.HTTPError as e:
        st2, n2 = e.code, 0
    check("读 .jpg 正常 -> 200", st2 == 200 and n2 == 512, f"{st2} {n2}B")

    print("=" * 72)
    print("3. 非法入参必须被拒（v5.3 B1 新增护栏）—— 这些如果漏过就是删真数据")
    for label, bad in [
        ("绝对路径", r"C:\Windows"),
        ("父目录", ".."),
        ("含分隔符", r"..\..\Windows"),
        ("UNC 风格", r"\\?\C:\Windows"),
        ("不存在但形态合法", "绝不存在的组xyz"),
        ("空串", ""),
    ]:
        st, d = req("/api/trash", "POST", {"names": [bad]})
        r0 = (d.get("results") or [{}])[0]
        rejected = (st == 400) or (r0.get("ok") is False)
        check(f"回收站拒绝「{label}」", rejected, f"HTTP {st} result={r0.get('error') or r0}")

    print("=" * 72)
    print("4. 合法组的回收站路径（真实删除，但只删本脚本建的临时组）")
    st, d = req("/api/trash", "POST", {"names": [TEMP_GROUP]})
    r0 = (d.get("results") or [{}])[0]
    check("回收站返回成功", st == 200 and r0.get("ok") is True, f"HTTP {st} {r0}")
    check("已从磁盘移除", not os.path.exists(TEMP_DIR), TEMP_DIR)
    check(
        "返回模式为 recycle（走的是回收站而非永久删）", r0.get("mode") == "recycle", f"mode={r0.get('mode')}"
    )
    print(f"  释放计数 = {d.get('freed')} 字节（库中体积快照；新建组可能为 0，不影响删除结果）")

    print("=" * 72)
    print(f"结果：PASS {ok} / FAIL {fail}")
    print()
    print("⚠ 临时组现在在【系统回收站】里，收尾步骤会还原它并从磁盘清除。")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
