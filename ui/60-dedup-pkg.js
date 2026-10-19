"use strict";
/* A 级图包去重标记 + C 级空壳/残缺/广告图（含 🧹 一键清）
   从 ui/70-wall.js 拆出（原文件第 6-177 行）。
   拆之前这四块混在一个 501 行的文件里，改任何一个面板都要跨 500 行找位置。 */
/* =================================================================
 * Wall：图包封面墙（虚拟滚动，DOM 恒定、无图包数上限）
 * ================================================================= */
/* ---- 图包级去重标记（v5.10）----
   实测：组内冗余几乎【全是整包/子目录级】——同一图包存两份，或小包被大包整体包含。
   （Pure 组 3 对 100% 副本；大梨子 4 个小包被「散图部分」整体包含。）
   所以正确操作不是逐张挑，而是在图包墙上标记出来，一次点击删整个目录。 */
let dedupMap=new Map();    // pkg名 -> {kind:'copy'|'sub', peer, rate}
let dedupFor='';           // 已加载去重的组，避免重复请求
/* 本组的索引覆盖率 {cov, disk, indexed}。
   没有它，界面会把"扫了 1.3% 得出的结论"当成全库真相展示给用户。
   实测代价：黏黏团子兔 8,502 张只扫了 109 张，却报出 28 个待删图包，
   其中 22 个是纯假阳性（各包只剩一张 51KB 水印图，撞进同簇就被判 100% 重复）。 */
let dedupCov=null;
function covText(){
  if(!dedupCov||dedupCov.cov>=0.999)return '';
  const c=dedupCov;
  return `⚠ 本组只扫了 ${(c.cov*100).toFixed(0)}% 的图（${c.indexed.toLocaleString()}/${c.disk.toLocaleString()} 张）`
    +`—— 下面是**下界**，没扫过的图里可能还藏着重复`;
}
function paintDup(card,a){
  paintHusk(card,a);
  const old=card.querySelector('.al-dup'); if(old)old.remove();
  card.classList.remove('is-dup');
  const d=dedupMap.get(a.name); if(!d)return;
  card.classList.add('is-dup');
  const b=document.createElement('button');
  b.className='al-dup '+(d.kind==='copy'?'dup-copy':'dup-sub');
  b.textContent=d.kind==='copy'?'副本':'被包含';
  const gb=d.bytes?(d.bytes/1024**3).toFixed(2)+' GB':'';
  b.title=`与「${d.peer}」重复 ${Math.round((d.rate||0)*100)}%${gb?' · '+gb:''}\n`
        +`点击 → 打开对比（先看两包的缩略图和"删掉会丢什么"，再决定删不删）`;
  b.onclick=e=>{e.stopPropagation();openPkgDup(a.name);};
  card.appendChild(b);
}
/* ---- 空壳 / 残缺 / 广告图（C 级，v5.13）----
   和 A、B 级找的不是一类东西：A 找"别处的副本"，B 找"重复对"，
   这一级找的是**压根没有内容**的包——整包只剩一张水印广告图的空壳，
   以及声明 125 张只剩 25 张的残缺包。它们字节太小，A/B 都看不见，
   却正是 A 级假阳性的来源（各包里那张 51KB 水印图被当成共同内容，
   于是 22 个 1.5GB 的大包被判成"互为副本"）。
   三种标记颜色不同、后果也不同：灰=可整包删，蓝=只提示不删，青=只删那张广告图。 */
let huskMap=new Map();    // pkg名 -> {kind:'husk'|'shrink'|'ad', ...}
function huskTitle(h){
  const kb=h.bytes?(h.bytes/1024).toFixed(0)+' KB':'';
  if(h.kind==='husk')return `【空壳】整包只剩 ${h.files} 个广告图${kb?'（'+kb+'）':''}\n`
    + `${(h.names||[]).join('、')}\n\n点击 → 整个图包进回收站（可恢复）`;
  if(h.kind==='shrink')return `【残缺】${h.why==='vol'
      ?`声明 ${(h.declare/1024**2).toFixed(0)} MB，盘上只剩 ${kb}`
      :`声明 ${h.declare_p} 张，盘上只剩 ${h.imgs} 张`}\n`
    + `可能你删过，也可能当年就没下全。\n\n点击 → 只看不删，自己判断`;
  return `【夹着广告图】包内有 ${(h.drop||[]).length} 张发布者的水印广告图`
    + `${kb?'（'+kb+'）':''}\n\n点击 → 只删这几张广告图，图包本身留着`;
}
function paintHusk(card,a){
  const old=card.querySelector('.al-husk'); if(old)old.remove();
  card.classList.remove('is-husk');
  const h=huskMap.get(a.name); if(!h)return;
  card.classList.add('is-husk');
  const cls=h.kind==='husk'?'hk-empty':h.kind==='shrink'?'hk-thin':'hk-ad';
  const txt=h.kind==='husk'?'空壳':h.kind==='shrink'?'残缺':'广告图';
  const b=document.createElement('button');
  b.className='al-husk '+cls; b.textContent=txt;
  b.title=huskTitle(h);
  b.onclick=e=>{e.stopPropagation();askHusk(a.name);};
  card.appendChild(b);
}
async function askHusk(pkg){
  const h=huskMap.get(pkg); if(!h)return;
  if(h.kind==='shrink'){          // 只提示，不代劳
    alert(huskTitle(h).replace(/\n\n点击.*$/,'')+`\n\n${pkg}`);
    return;
  }
  if(h.kind==='ad'){
    if(!confirm(`删掉这个包里的 ${h.drop.length} 张广告图？\n\n${pkg}\n\n`
      +`${h.drop.map(d=>'  '+d.split('/').pop()).join('\n')}\n\n`
      +`图包本身保留。确定 → 进回收站（可恢复）`))return;
    const r=await api.huskClear(S.folder,[pkg]).catch(()=>({ok:false,error:'网络错误'}));
    if(!r.ok){toast('清理失败：'+(r.error||'未知'));return;}
    toast(`已清掉 ${r.deleted} 张广告图 · ${(r.freed/1024).toFixed(0)} KB`
      +(r.emptied&&r.emptied.length?` · 「${r.emptied[0]}」现在整个空了`:''));
    huskMap.delete(pkg);
    await openFolder(S.folder,true);
    return;
  }
  if(!confirm(`删除这个空壳图包？\n\n${pkg}\n\n`
    +`里面只剩 ${h.files} 个广告图（${(h.bytes/1024).toFixed(0)} KB）：\n`
    +`${(h.names||[]).join('、')}\n\n确定 → 进回收站（可恢复）`))return;
  const r=await api.rmPkg(S.folder,pkg,false);
  if(!r.ok){toast('删除失败：'+(r.error||'未知错误'));return;}
  toast('已送进回收站：'+pkg);
  huskMap.delete(pkg);
  await openFolder(S.folder,true);
}
function loadHusk(folder){
  huskMap=new Map();
  window.__huskLoaded=false;
  const btn=$('huskBtn'); if(btn)btn.hidden=true;
  if(!folder){wall.refresh();return;}
  api.dedupHusk(folder).then(r=>{
    if(r.error)return;
    // 【展开符必须在后面】写成 {kind:'husk',...x} 会被 x 自带的 kind 覆盖掉 ——
    // 服务端 husk 条目里的 kind 是 'shell'（=广告壳），这么一写 7 个空壳
    // 全变成"广告图"，点下去只删那张水印，空壳包永远清不掉。
    for(const x of (r.husks||[]))huskMap.set(x.pkg,{...x,kind:'husk'});
    for(const x of (r.shrunk||[]))if(!huskMap.has(x.pkg))huskMap.set(x.pkg,{...x,kind:'shrink'});
    for(const x of (r.ad_in_pkg||[]))if(!huskMap.has(x.pkg))huskMap.set(x.pkg,{...x,kind:'ad'});
    if(huskMap.size){wall.refresh();paintHuskBtn();}
    window.__huskLoaded=true;    // 探针用它判断"扫描结束了没有"，而不是盲等
  }).catch(()=>{window.__huskLoaded=true;});   // 扫描失败也放行，绝不影响看图
}
function paintHuskBtn(){
  const n=k=>[...huskMap.values()].filter(h=>h.kind===k).length;
  const ne=n('husk'),ns=n('shrink'),na=n('ad');
  const btn=$('huskBtn'); if(!btn)return;
  btn.hidden=!(ne+ns+na);
  $('huskCnt').textContent=ne+ns+na;
  btn.title=`本组的空壳与广告图\n\n`
    +`空壳 ${ne} 个（整包只剩广告图，可整包删）\n`
    +`残缺 ${ns} 个（声明的张数对不上实到，只提示不删）\n`
    +`夹广告图 ${na} 个（可只删那张广告图）\n\n`
    +`卡片左下角有标记；点击打开批量清理。`;
}
async function openHusk(){
  const n=k=>[...huskMap.values()].filter(h=>h.kind===k);
  const ne=n('husk'),na=n('ad'),ns=n('shrink');
  if(!(ne.length+na.length+ns.length)){toast('本组没有空壳/残缺/广告图');return;}
  const adBytes=na.reduce((s,x)=>s+(x.bytes||0),0);
  const msg=`本组清理：\n\n`
    +`① 空壳 ${ne.length} 个 —— 整包只剩广告图，建议整包删\n`
    +(ne.length?ne.map(x=>'   '+x.pkg).join('\n')+'\n':'')
    +`② 夹广告图 ${na.length} 个 —— 只删那张广告图（${(adBytes/1024).toFixed(0)} KB），包留着\n`
    +`③ 残缺 ${ns.length} 个 —— 只提示，不动\n\n`
    +`先清理 ② 的广告图？（① 请在卡片上逐个点，② 也支持逐个点）`;
  if(!na.length){alert(msg);return;}
  if(!confirm(msg))return;
  const r=await api.huskClear(S.folder,na.map(x=>x.pkg)).catch(()=>({ok:false,error:'网络错误'}));
  if(!r.ok){toast('清理失败：'+(r.error||'未知'));return;}
  toast(`已清掉 ${r.deleted} 张广告图 · ${(r.freed/1024).toFixed(0)} KB`
    +(r.emptied&&r.emptied.length?`\n另有 ${r.emptied.length} 个包现在整个空了（卡片上会标成「空壳」）`:''));
  await openFolder(S.folder,true);
}
async function loadDedup(folder){
  dedupMap=new Map(); dedupFor=folder||'';
  if(!folder){wall.refresh();return;}
  try{
    const r=await api.dedupGroup(folder);
    dedupCov=(typeof r.coverage==='number')
      ?{cov:r.coverage,disk:r.disk_images||0,indexed:r.indexed||0}:null;
    // 用 pkg_drops（去重后的唯一删除清单），不用 pkg_pairs：
    // pairs 里同一个包会出现很多次，且互为副本时两边都可能被判"该删"。
    for(const d of (r.pkg_drops||[])){
      if(!d.pkg)continue;   // 根散图不是一个可删的子目录
      dedupMap.set(d.pkg,{kind:(d.kind==='互为副本')?'copy':'sub',
        peer:d.peer, rate:d.rate||0, bytes:d.bytes||0});
    }
    if(dedupMap.size)toast(`本组 ${dedupMap.size} 个图包是别处的副本（卡片右下角已标记）`);
    else if(covText())toast(covText());
  }catch(e){/* 索引没建或接口失败就静默，绝不影响看图 */}
  paintPkBtn();
  wall.refresh();
}
function paintPkBtn(){
  const btn=$('pkBtn'); if(!btn)return;
  btn.hidden=!dedupMap.size;
  $('pkCnt').textContent=dedupMap.size;
  btn.title=dedupMap.size
    ? `本组 ${dedupMap.size} 个图包是别处的副本\n\n`
      +`点这里或按 ⇄ 打开对比：两侧缩略图 + 「删掉会丢什么」，看完再决定删不删。\n`
      +`（也可以直接在图包墙的卡片上点红线标记进入）`
    : '本组没有整包重复建议';
}
