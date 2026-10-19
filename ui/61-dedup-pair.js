"use strict";
/* B 级重复对裁决队列（一张张过，按键 2/3 裁决）
   从 ui/70-wall.js 拆出（原文件第 178-284 行）。
   拆之前这四块混在一个 501 行的文件里，改任何一个面板都要跨 500 行找位置。 */
/* ---- 重复对裁决队列（B 级，v5.11）----
   立论：实测冗余里 82% 是「成对」（size-2 簇），≥3 张的簇只占 2.3%。
   所以正确粒度是逐对裁决，不是"每簇自动留一张"。
   队列已排除 A 级建议整包删除的图包 —— 先 A 后 B，否则重叠计数（实测重叠 1,215 条）。 */
const dup={list:[],i:0,folder:'',deleted:0,freed:0,gone:new Set()};
function dupRel(p,side){return side==='L'?p.keep.rel:p.drop.rel;}
function paintDupPair(){
  const p=dup.list[dup.i];
  const L=$('dupL'),R=$('dupR');
  if(!p||dup.gone.has(p.keep.rel)||dup.gone.has(p.drop.rel)){
    L.querySelector('img').removeAttribute('src');R.querySelector('img').removeAttribute('src');
    L.querySelector('figcaption').innerHTML='';R.querySelector('figcaption').innerHTML='';
    L.querySelector('.badge')&&L.querySelector('.badge').remove();
    R.querySelector('.badge')&&R.querySelector('.badge').remove();
    L.classList.remove('rec');
    $('dupWhy').textContent='';
    $('dupProg').textContent=`已删 ${dup.deleted} 张 · 释放 ${(dup.freed/1048576).toFixed(0)} MB · 队列已清空`;
    return;
  }
  const mb=b=>(b/1048576).toFixed(1)+' MB';
  const cap=(side)=>{
    const f=side==='L'?p.keep:p.drop;
    const nm=f.rel.split('/').pop();
    return `<div class="nm">${esc(nm)}</div><div>${mb(f.size)} · <b>${esc(f.pkg||'（根目录散图）')}</b></div>`
         + `<div style="opacity:.7">${esc(f.rel)}</div>`;
  };
  // 左 = 建议保留，右 = 建议删除
  L.classList.add('rec');
  L.querySelector('img').src=turl(dup.folder||S.folder,p.keep.rel,760,82);
  R.querySelector('img').src=turl(dup.folder||S.folder,p.drop.rel,760,82);
  L.querySelector('figcaption').innerHTML=cap('L');
  R.querySelector('figcaption').innerHTML=cap('R');
  if(!L.querySelector('.badge')){const b=document.createElement('span');b.className='badge';b.textContent='建议保留';L.appendChild(b);}
  if(!R.querySelector('.badge')){const b=document.createElement('span');b.className='badge';b.textContent='建议删';R.appendChild(b);}
  $('dupWhy').innerHTML=`体积比 <b>×${p.ratio}</b> · 汉明距离 <b>${p.hamming}</b>（≤8 判为重复） · ${esc(p.why)}`
    +`<br>第 <b>${dup.i+1}</b> / ${dup.list.length} 对 · 删除后进<b>回收站</b>，可恢复`;
  $('dupProg').textContent=`${dup.i+1}/${dup.list.length} · 已删 ${dup.deleted} 张 · ${(dup.freed/1048576).toFixed(0)} MB`;
}
function dupAdvance(d){
  for(let k=0;k<dup.list.length;k++){
    dup.i=(dup.i+d+dup.list.length)%dup.list.length;
    const p=dup.list[dup.i];
    if(p&&!dup.gone.has(p.keep.rel)&&!dup.gone.has(p.drop.rel))return;
  }
  dup.i=0;
}
async function dupDecide(dropSide){
  const p=dup.list[dup.i]; if(!p)return;
  const rel=dupRel(p,dropSide);
  const r=await api.rmFile(dup.folder||S.folder,rel,false).catch(()=>({ok:false,error:'网络错误'}));
  if(!r.ok){toast('删除失败：'+(r.error||'未知错误'));return;}
  dup.deleted++; dup.freed+=r.freed||0; dup.gone.add(rel);
  dupAdvance(1); paintDupPair();
}
function dupSkip(){dupAdvance(1);paintDupPair();}
function dupPrev(){dupAdvance(-1);paintDupPair();}
function closeDup(){
  $('dup').classList.remove('on');
  if(dup.deleted>0){toast(`已送进回收站 ${dup.deleted} 张 · ${(dup.freed/1048576).toFixed(0)} MB`);
    if(S.folder===dup.folder)openFolder(S.folder,true);}   // 刷新该组，墙/胶片同步
}
async function openDup(){
  if(!S.folder){toast('先选一个文件夹');return;}
  $('dup').classList.add('on');
  $('dupProg').textContent='正在比对…'; $('dupHint').textContent='';
  $('dupWhy').textContent='';
  try{
    const r=await api.dedupPairs(S.folder);
    if(r.error){
      $('dupProg').textContent='本组无法裁决：'+(r.error==='no index for this folder'?'还没建索引（浏览或后台扫描后会补上）':r.error);
      return;
    }
    // 队列长度同样是"只看得见的部分"——先说清楚扫了多少，别让 1% 的成果冒充全貌
    dedupCov=(typeof r.coverage==='number')
      ?{cov:r.coverage,disk:r.disk_images||0,indexed:r.indexed||0}:null;
    const low=dedupCov&&dedupCov.cov<0.999;
    // 文字和按钮分开写：直接 textContent 会把按钮冲掉
    $('dupCovTxt').textContent=low
      ?`⚠ 本组只扫了 ${(dedupCov.cov*100).toFixed(0)}% 的图`
        +`（${dedupCov.indexed.toLocaleString()}/${dedupCov.disk.toLocaleString()} 张）——`
        +`下面这些对只是**已经看见的**重复，补完索引还会有更多`:'';
    // 每次开面板都把按钮复位，否则上次"已启动"会一直挂到下次
    $('dupBuild').hidden=!low;
    $('dupBuild').disabled=false;
    $('dupBuild').textContent='补索引（后台，可边跑边看图）';
    // 换组时"已删"名单必须作废：不同组的 rel 可能重名，留着会误过滤
    if(dup.folder!==S.folder)dup.gone=new Set();
    dup.list=(r.pairs||[]).filter(p=>!dup.gone.has(p.keep.rel)&&!dup.gone.has(p.drop.rel));
    dup.i=0; dup.folder=S.folder; dup.deleted=0; dup.freed=0;
    if(!dup.list.length){
      $('dupHint').textContent=''; $('dupProg').textContent='本组没有待裁决的重复对';
      L_clear(); return;
    }
    $('dupHint').textContent=`共 ${dup.list.length} 对 · 左=建议保留 / 右=建议删除 · `
      +`键盘 1 删左 · 2 删右（推荐）· 3 都留 · ← → 换一对 · 全部进回收站可恢复`;
    paintDupPair();
  }catch(e){$('dupProg').textContent='加载失败：'+e.message;}
}
function L_clear(){
  const L=$('dupL'),R=$('dupR');
  L.querySelector('img').removeAttribute('src');R.querySelector('img').removeAttribute('src');
  L.querySelector('figcaption').innerHTML='';R.querySelector('figcaption').innerHTML='';
  L.classList.remove('rec');
  const b=L.querySelector('.badge');if(b)b.remove();
  const b2=R.querySelector('.badge');if(b2)b2.remove();
}
