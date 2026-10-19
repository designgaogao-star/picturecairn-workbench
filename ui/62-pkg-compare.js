"use strict";
/* 图包对比：删整包前的肉眼复核
   从 ui/70-wall.js 拆出（原文件第 285-427 行）。
   拆之前这四块混在一个 501 行的文件里，改任何一个面板都要跨 500 行找位置。 */
/* ---- 图包对比：删整包前的肉眼复核（v5.14）----
   A 级结论是**概率性**的（pHash ≤8）。以前卡片上点一下，只弹一行
   「与「X」重复 97%」的文字就删了 —— 可用户要判断的根本不是这个百分比，
   而是「删掉会丢什么」。所以这里把两侧摆出来：
     · 代表缩略图（一眼看是不是同一套图）
     · "删掉会丢"清单 —— 待删侧里对手包找不到的文件，这是唯一的否决项
     · 代表图 ↔ 对手图的对应 + 汉明距离，把 algal 判定摊开给人看
   看完再按 2（按建议删）/ 1（反向删）/ 3（都留）。 */
const pk={list:[],i:0,folder:'',cur:null,loading:false,deleted:0,freed:0,gone:new Set()};
function pkSideHtml(s,tag){
  const mb=(s.bytes/1048576).toFixed(0);
  const grid=(s.sample||[]).slice(0,6).map(
    r=>`<img src="${turl(pk.folder,r,320,80)}" alt="" loading="lazy">`).join('');
  let h=`<div class="pkName">${esc(s.pkg)}</div><div class="pkGrid">${grid}</div>`;
  h+=`<div class="pkMeta"><span>${s.count} 项</span><span>${mb} MB</span>`
    +`<span>${s.matched}/${s.count} 在对方找得到</span></div>`;
  if(s.unique_n){
    const nm=s.unique.map(u=>esc(u.rel.split('/').pop())).join('、');
    h+= tag==='R'
      ? `<div class="pkUniq" style="color:#e2443f">删掉会丢 ${s.unique_n} 个：${nm}</div>`
      : `<div class="pkUniq" style="color:#e8b64c">左侧缺 ${s.unique_n} 个：${nm}</div>`;
  }else{
    h+=`<div class="pkUniq" style="color:var(--ok,#3fb950)">和对方的内容完全互相覆盖，删了不损失</div>`;
  }
  return h;
}
function paintPkgPair(){
  const L=$('pkL'),R=$('pkR'),c=pk.cur;
  L.classList.remove('rec');L.classList.remove('del');
  R.classList.remove('rec');R.classList.remove('del');
  if(!c){L.querySelector('figcaption').innerHTML='';R.querySelector('figcaption').innerHTML='';
    $('pkWhy').textContent='';return;}
  L.classList.add('rec');R.classList.add('del');
  if(!L.querySelector('.badge')){const b=document.createElement('span');b.className='badge';b.textContent='建议保留';L.appendChild(b);}
  if(!R.querySelector('.badge')){const b=document.createElement('span');b.className='badge';b.textContent='建议删除';R.appendChild(b);}
  L.querySelector('figcaption').innerHTML=pkSideHtml(c.keep,'L');
  R.querySelector('figcaption').innerHTML=pkSideHtml(c.drop,'R');
  const r=c.drop.bytes&&c.keep.bytes?(c.keep.bytes/c.drop.bytes):0;
  const lk=(c.links||[]).slice(0,6).map(x=>
    `<span class="lk">${esc(x.rel.split('/').pop())} ↔ <b>${esc(x.peer.split('/').pop())}</b> 距离${x.dist}</span>`).join('');
  $('pkWhy').innerHTML=
     `重复率 <b>${Math.round((c.rate||0)*100)}%</b> · ${esc(c.kind||'')} · 体积比 <b>×${r.toFixed(2)}</b>`
    +` · 右侧 <b>${c.drop.matched}/${c.drop.count}</b> 在左侧找得到`
    +(c.dist_max!==null&&c.dist_max!==undefined
      ? ` · 抽样 ${c.dist_zero}/${(c.links||[]).length} 幅<b>距离 0</b>，最大 ${c.dist_max}（阈值 8）`:'')
    +`<br>${lk}`
    +`<br>第 <b>${pk.i+1}</b> / ${pk.list.length} 对 · 按 <b>2</b> 删右侧（推荐）· <b>1</b> 反向删 · <b>3</b> 都留 · 删除进<b>回收站</b>`;
  $('pkProg').textContent=`${pk.i+1}/${pk.list.length} · 已删 ${pk.deleted} 个 · ${(pk.freed/1048576).toFixed(0)} MB`;
}
async function pkLoad(){
  const name=pk.list[pk.i]; if(!name)return;
  pk.loading=true;
  $('pkHint').textContent='正在比对…';
  try{
    const r=await api.dedupPkgPair(pk.folder,name);
    if(r.error){$('pkHint').textContent='这一对比不了：'+r.error;pk.cur=null;paintPkgPair();return;}
    pk.cur=r; $('pkHint').textContent='左=建议保留 · 右=建议删除。';
    paintPkgPair();
  }catch(e){$('pkHint').textContent='加载失败：'+(e.message||e);pk.cur=null;}
  finally{pk.loading=false;}
}
function pkAdvance(d){
  for(let k=0;k<pk.list.length;k++){
    pk.i=(pk.i+d+pk.list.length)%pk.list.length;
    const n=pk.list[pk.i];
    if(n&&!pk.gone.has(n))return;
  }
  pk.i=0;
}
async function openPkgDup(pkg){
  if(!S.folder){toast('先选一个文件夹');return;}
  if(!dedupMap.size){toast('本组没有整包重复建议');return;}
  pk.list=[...dedupMap.keys()];
  if(pk.folder!==S.folder)pk.gone=new Set();
  pk.folder=S.folder;pk.deleted=0;pk.freed=0;
  const at=pkg?pk.list.indexOf(pkg):-1;
  pk.i=at>=0?at:0;
  $('pkgdup').classList.add('on');
  await pkLoad();
}
async function pkDecide(dropSide){
  if(pk.loading||!pk.cur)return;
  const target=dropSide==='R'?pk.cur.drop.pkg:pk.cur.keep.pkg;
  const other=dropSide==='R'?pk.cur.keep.pkg:pk.cur.drop.pkg;
  const cur=pk.cur;
  // 顺着建议删（删右侧）不再弹窗——面板已经把该看的都摆出来了，再弹一次是噪音；
  // 反向删（1）必须弹，因为它保留的是"系统说该删的那个"，属于推翻建议。
  if(dropSide==='L'&&!confirm(`反向删除：删掉「${target}」、保留「${other}」？\n\n`
      +`这会保留建议删除的那一侧。确定 → 进回收站（可恢复）`))return;
  const r=await api.rmPkg(pk.folder,target,false).catch(()=>({ok:false,error:'网络错误'}));
  if(!r.ok){toast('删除失败：'+(r.error||'未知错误'));return;}
  pk.deleted++; pk.freed+=cur[dropSide==='R'?'drop':'keep'].bytes;
  pk.gone.add(target);
  // 队列重建后 **不能沿用旧索引**：旧 list 的第 i 项被删掉后，
  // 新 list 的第 i 项是"原来第 i+1 项的后一个"，会跳过一条建议。
  // 先按名字定位"下一个该看谁"，再重建。
  const nextName=pkNameAfter(target);
  dedupMap.delete(target);
  pk.list=[...dedupMap.keys()];
  pk.i=Math.max(0,pk.list.indexOf(nextName));
  toast(`已送进回收站：${target}`);
  await pkLoad();
}
function pkNameAfter(curName){
  const i=pk.list.indexOf(curName);
  if(i<0)return pk.list[0]||'';
  for(let k=1;k<=pk.list.length;k++){
    const n=pk.list[(i+k)%pk.list.length];
    if(n&&!pk.gone.has(n)&&n!==curName)return n;
  }
  return '';
}
function pkSkipPair(){
  if(!pk.cur)return;
  const curName=pk.cur.drop.pkg;
  const nextName=pkNameAfter(curName);
  pk.gone.add(curName); dedupMap.delete(curName);
  pk.list=[...dedupMap.keys()];
  pk.i=Math.max(0,pk.list.indexOf(nextName));
  pkLoad();
}
function pkPrevP(){pkAdvance(-1);pkLoad();}
function pkNextP(){pkAdvance(1);pkLoad();}
function closePkgDup(){
  $('pkgdup').classList.remove('on');
  if(pk.deleted>0){toast(`已送进回收站 ${pk.deleted} 个图包 · ${(pk.freed/1048576).toFixed(0)} MB`);
    openFolder(S.folder,true);}
}
async function askDropPkg(pkg){
  const d=dedupMap.get(pkg); if(!d)return;
  const gb=d.bytes?` · ${(d.bytes/1024**3).toFixed(2)} GB`:'';
  const msg=`删除这个图包？\n\n${pkg}${gb}\n\n它与「${d.peer}」重复 ${Math.round((d.rate||0)*100)}%。\n\n确定 → 送进回收站（可恢复）`;
  if(!confirm(msg))return;
  try{
    const r=await api.rmPkg(S.folder,pkg,false);
    if(!r.ok){toast('删除失败：'+(r.error||'未知错误'));return;}
    toast('已送进回收站：'+pkg);
    dedupMap.delete(pkg);
    await openFolder(S.folder,true);
  }catch(e){toast('删除失败：'+(e.message||e));}
}
