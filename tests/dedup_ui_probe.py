# -*- coding: utf-8 -*-
"""去重相关界面的回归：C 级标记（空壳/残缺/广告图）+ 图包对比面板。

和 browser_probe.py 的分工：那边管看图主流程和 B 级重复对裁决，
这边盯 v5.13 的三种卡片标记 + 🧹 按钮、v5.14 的图包对比面板，
避免主探针越加越臃肿。

【关于删除】这里**不真删磁盘数据**：删包动作把 api.rmPkg 换成桩，
只验前端链路（计数/跳下一对/dedupMap 更新）。
落到回收站的那一段由 hardening_check.py 的 J 段和 browser_probe.py 覆盖，
同一个行为没必要在三个地方各真删一次真实素材。
"""

import json
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import browser_probe as bp

TOOL = r"F:\图库\_gallery_tool"
STATE = os.path.join(TOOL, "review_state.json")
BACKUP = os.path.join(TOOL, "review_state.json.huskui-backup")
TARGET = "[非R18]黏黏团子兔"  # 7 个空壳 + 33 个夹广告图，全在这个组

ok = fail = 0


def check(name, cond, detail=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS  {name}  {detail}")
    else:
        fail += 1
        print(f"  FAIL  {name}  {detail}")


def main():
    chrome = bp.find_chrome()
    try:
        shutil.copy2(STATE, BACKUP)
    except OSError:
        pass
    proc = bp.launch(chrome, 9334)
    try:
        cdp = bp.open_page(9334, "about:blank")
        cdp.cmd("Page.enable")
        cdp.cmd("Runtime.enable")
        cdp.cmd("Log.enable")
        cdp.cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": """
          window.__probeErrors = [];
          window.addEventListener('error', e => window.__probeErrors.push('error: ' + (e.message||e.type)));
          window.addEventListener('unhandledrejection', e => window.__probeErrors.push(
            'rejection: ' + String((e.reason && e.reason.message) || e.reason)));
        """
            },
        )
        cdp.cmd("Page.navigate", {"url": bp.BASE + "/"})
        if not cdp.wait_for('document.querySelectorAll("#folderList .item").length > 0'):
            check("页面启动", False)
            return 1

        print("=" * 72)
        print(f"1. 打开 {TARGET} —— 卡片上必须出现 C 级标记")
        cdp.js(f"openFolder({json.dumps(TARGET)})", await_promise=True)
        cdp.js('setView("grid")')
        # 【数据可能已经被清完】C 级标记是"曾经有脏东西"的证据，清完就没了。
        # 没有样本时不该判失败，而是验"接口结构正确 + 界面不崩"。
        got = cdp.wait_for("window.__huskLoaded === true", timeout=30)
        size = cdp.js("huskMap.size")
        if size == 0:
            struct_ok = cdp.js(
                """(() => fetch('/api/dedup/husk?folder='
                + encodeURIComponent(S.folder)).then(r=>r.json())
                .then(j=>['husks','shrunk','ad_in_pkg','ad_stems'].every(k=>k in j)))()""",
                await_promise=True,
            )
            check(
                "★ 本组已无 C 级条目（历史脏数据已清理）· 接口结构仍正确",
                struct_ok is True,
                f"huskMap=0 · API keys OK={struct_ok}",
            )
        check("★ 空壳接口数据已进 huskMap（可为 0）", got is not None, f"{size} 个")
        kinds = cdp.js("[...huskMap.values()].reduce((a,h)=>(a[h.kind]=(a[h.kind]||0)+1,a),{})")
        check(
            "★ 标记类型合法（husk/shrink/ad 的子集）",
            set(kinds or {}) <= {"husk", "shrink", "ad"},
            f"{kinds}",
        )

        # 滚到有标记的那张卡片，确认徽标真的画出来了
        idx = cdp.js("""(() => {
            for (let i=0;i<S.albums.length;i++){
                if (huskMap.has(S.albums[i].name)) return i;
            } return -1; })()""")
        if (size or 0) > 0:
            check("至少有一个图包带标记", isinstance(idx, int) and idx >= 0, f"idx={idx}")
        if isinstance(idx, int) and idx >= 0:
            cdp.js(f"wall.select({idx}); setView('grid')")
            time.sleep(0.6)
            n_badge = cdp.js("document.querySelectorAll('#wallTape .al-husk').length")
            cls = cdp.js("[...document.querySelectorAll('#wallTape .al-husk')].map(b=>b.className)")
            check("★ 卡片上画出了 .al-husk 徽标", (n_badge or 0) > 0, f"{n_badge} 个 · {str(cls)[:70]}")
            # A 级标记在右下角、C 级在左下角，不能互相顶掉
            both = cdp.js("""(() => {
                const c=[...document.querySelectorAll('#wallTape .album')]
                  .find(x=>x.querySelector('.al-husk')&&x.querySelector('.al-dup'));
                return !!c; })()""")
            print(f"  （同时带 A 级+C 级标记的卡片：{'有' if both else '本组没有'}）")

        print("=" * 72)
        print("2. 🧹 按钮：显示数量 + 点击弹批量清理确认")
        btn = cdp.js("({hidden:$('huskBtn').hidden, cnt:$('huskCnt').textContent})")
        if (cdp.js("huskMap.size") or 0) > 0:
            check(
                "★ 🧹 按钮已显示且带数量",
                btn and btn.get("hidden") is False and btn.get("cnt") not in (None, "0"),
                f"{btn}",
            )
            check(
                "按钮 title 写清了三类分别是什么",
                "空壳" in (cdp.js("$('huskBtn').title") or ""),
                (cdp.js("$('huskBtn').title") or "")[:40].replace("\n", " / "),
            )
        else:
            # 清完之后按钮必须消失，否则用户点了会看到"本组没有空壳"，那是误导
            check(
                "★ 无 C 级条目时 🧹 按钮自动隐藏（不占位、不误导）",
                btn and btn.get("hidden") is True,
                f"{btn}",
            )

        print("=" * 72)
        print("3. ⇄ 常驻入口：不切图包墙也能进对比")
        btn = cdp.js("({hidden:$('pkBtn').hidden, cnt:$('pkCnt').textContent})")
        check(
            "★ ⇄ 按钮已显示且带建议数",
            btn and btn.get("hidden") is False and btn.get("cnt") not in (None, "0"),
            f"{btn}",
        )
        check(
            "按钮 title 说清了用途",
            "副本" in (cdp.js("$('pkBtn').title") or ""),
            (cdp.js("$('pkBtn').title") or "")[:36].replace("\n", " / "),
        )
        cdp.js("$('pkBtn').click()")
        via_btn = cdp.wait_for("document.getElementById('pkgdup').classList.contains('on')", timeout=20)
        check("★ 从 ⇄ 按钮能直接打开对比面板", via_btn)
        if via_btn:
            cdp.key("Escape")
            time.sleep(0.4)

        print("=" * 72)
        print("4. 图包对比面板（v5.14）—— 卡片标记必须先进对比，不是一点就删")
        # 先找一个带 A 级标记的图包
        dp = cdp.js("""(() => {
            for (let i=0;i<S.albums.length;i++){
                const n=S.albums[i].name;
                if (dedupMap.has(n)) return n;
            } return null; })()""")
        check("本组有 A 级整包重复建议", bool(dp), str(dp)[:40])
        if dp:
            # 桩掉真正的删除，只验前端链路
            cdp.js("""window.__rmCalls = [];
                      api.rmPkg = async (f, p, perm) => {
                          window.__rmCalls.push({f: f, p: p, perm: perm});
                          return {ok: true, freed: 123456};
                      };""")
            n_before = cdp.js("dedupMap.size")
            cdp.js(f"openPkgDup({json.dumps(dp)})", await_promise=True)
            opened = cdp.wait_for("document.getElementById('pkgdup').classList.contains('on')", timeout=15)
            check("★ 点卡片标记打开的是对比面板（不再直接弹确认框）", opened)
            loaded = cdp.wait_for("pk.cur && pk.cur.drop && pk.cur.drop.count > 0", timeout=30)
            check(
                "★ 对比数据加载完成",
                loaded,
                cdp.js("pk.cur ? `${pk.cur.drop.count} vs ${pk.cur.keep.count} 张` : ''"),
            )
            if loaded:
                n_img = cdp.js("document.querySelectorAll('#pkL img, #pkR img').length")
                check("★ 两侧都渲染出代表缩略图", (n_img or 0) >= 6, f"{n_img} 张")
                why = cdp.js("document.getElementById('pkWhy').textContent") or ""
                check(
                    "证据行写了重复率/命中数/距离",
                    "重复率" in why and "找得到" in why,
                    why[:70].replace("\n", " "),
                )
                check(
                    "待删侧标了红色边框（.del）",
                    bool(cdp.js("document.getElementById('pkR').classList.contains('del')")),
                )
                # 「删掉会丢」这一行必须存在 —— 它是拍板的唯一否决项
                lost = cdp.js(
                    "document.querySelector('#pkR .pkUniq') ? document.querySelector('#pkR .pkUniq').textContent : ''"
                )
                check("★ 待删侧有「删掉会丢 / 不损失」的结论行", bool(lost), (lost or "")[:40])

                # 按 2 = 按建议删右侧。删之前先记下右侧到底是谁，别事后瞎猜
                drop_name = cdp.js("pk.cur.drop.pkg")
                cdp.key("2")
                time.sleep(1.5)
                calls = cdp.js("window.__rmCalls || []")
                check(
                    "★ 按 2 删的正是右侧（建议删除的那一个）",
                    bool(calls) and calls[-1].get("p") == drop_name,
                    f"删了 {str(calls[-1].get('p'))[:34] if calls else '（没调用）'}"
                    f" / 应为 {str(drop_name)[:34]}",
                )
                check("★ 走回收站（permanent=false）", bool(calls) and calls[-1].get("perm") is False)
                check(
                    "★ 删完自动跳到下一对，计数 +1",
                    cdp.js("pk.deleted") == 1 and cdp.js("dedupMap.size") == n_before - 1,
                    f"deleted={cdp.js('pk.deleted')} dedupMap {n_before}→{cdp.js('dedupMap.size')}",
                )
                # 按 3 = 两个都留
                cdp.key("3")
                time.sleep(1.0)
                check(
                    "按 3 两个都留（不再发删除请求）",
                    len(cdp.js("window.__rmCalls || []")) == 1,
                    f"累计删除调用 {len(cdp.js('window.__rmCalls') or [])}",
                )
            cdp.key("Escape")
            time.sleep(0.4)
            check(
                "Esc 关闭对比面板", not cdp.js("document.getElementById('pkgdup').classList.contains('on')")
            )
            cdp.js("delete window.__rmCalls")

        print("=" * 72)
        print("5. 版本漂移提示：旧页面必须自己发现自己是旧的")
        # 版本一致时不该提示（否则每次都挂一条黄条是骚扰）
        cdp.js("""window.__stubPing = false;
                   const _f = window.fetch;
                   window.fetch = function(u, o){
                       if (window.__stubPing && String(u).indexOf('/api/ping') >= 0)
                           return Promise.resolve({ok:true,
                               headers:new Headers({'X-Version':'9.99'}),
                               text:()=>Promise.resolve('pong')});
                       return _f(u, o);
                   };""")
        time.sleep(5)
        check("版本一致时不弹横幅（不骚扰）", not cdp.js("!!document.getElementById('staleBar')"), "")
        # 假装服务端升到了 9.99，横幅必须出现且可点击刷新
        cdp.js("window.__stubPing = true")
        appeared = cdp.wait_for(
            "!!document.getElementById('staleBar') && "
            "getComputedStyle(document.getElementById('staleBar')).display !== 'none'",
            timeout=15,
        )
        check(
            "★ 页面版本落后时弹出刷新横幅",
            appeared,
            (
                cdp.js(
                    "document.getElementById('staleBar') ? "
                    "document.getElementById('staleBar').textContent : ''"
                )
                or ""
            )[:50],
        )
        check(
            "横幅可点击刷新（点了就 reload）",
            bool(cdp.js("!!(document.getElementById('staleBar')||{}).onclick")),
        )
        cdp.js(
            "window.__stubPing = false; const b=document.getElementById('staleBar');"
            "if(b) b.style.display='none';"
        )

        print("=" * 72)
        print("5. console 零报错")
        errs = cdp.js("window.__probeErrors || []")
        check("★ 全程零未捕获异常 / 零未处理拒绝", not errs, str(errs)[:200])
    finally:
        try:
            proc.terminate()
        except Exception:
            pass
        time.sleep(0.5)
        try:  # 还原浏览位置（先关浏览器再还原，顺序不能反）
            shutil.copy2(BACKUP, STATE)
            print(f"浏览位置已还原（备份 {os.path.basename(BACKUP)}）")
        except OSError as e:
            print(f"状态还原失败：{e}")
    print("=" * 72)
    print(f"去重界面回归：PASS {ok} / FAIL {fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
