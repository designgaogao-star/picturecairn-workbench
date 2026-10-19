"use strict";
/* Viewer：单张媒体（元素复用 + 三缓冲预载 + 变换）
   从 index.html 内联 <script> 抽出（原 421-683 行）。
   加载顺序由文件名数字前缀保证；classic script 共享同一全局词法作用域，
   所以跨文件直接用顶层 const/function 即可，不需要 import。 */
/* =================================================================
 * Viewer：单张媒体（元素复用 + 三缓冲预载 + 变换）
 * ================================================================= */
let imgPool=new Map();       // 预览图预载池 url -> Image（只放预览，不放原图）
let originPool=new Map();    // 原图预载池 url -> Image（严格限 3 张；一张解码后可达 90MB）
let originTimer=0;           // 延后加载原图的定时器
let originProbe=null;        // 正在后台拉的原图探针，切图时要中止掉
let idleTimer=0;             // 「空闲后预载下一张原图」的定时器
function hostEl(){return $('mediaHost');}
// 中止"后台拉原图"：连翻时上一张的 90MB 原图还在传，会跟当前要显示的图抢 IO
function cancelOriginLoad(){
  if(originTimer){clearTimeout(originTimer);originTimer=0;}
  if(idleTimer){clearTimeout(idleTimer);idleTimer=0;}
  if(originProbe){try{originProbe.src='';}catch(e){} originProbe=null;}
}
// 当前张原图就位、而且用户没有再翻之后，才去预载「下一张」的原图。
// 为什么要这么小心：全库原图中位 8.5MB，一次预载 4 张（旧实现）就是 70MB/次翻图，
// 那是卡顿主因；但一张都不预载又会让"翻过去还要等原图"（实测 418ms）。
// 折中：空闲时只预载 1 张，且必须等当前张加载完，绝不与新一页竞争。
function scheduleIdleOrigin(){
  if(idleTimer)clearTimeout(idleTimer);
  idleTimer=setTimeout(()=>{idleTimer=0;preloadNextOrigin();},IDLE_ORIGIN_DELAY);
}
function preloadNextOrigin(){
  if(!S.files.length||S.view!=='single')return;
  const a=albumAt(S.idx),k=S.idx+1;
  if(k>=a.end)return;                       // 不跨图包（红线 C5 的精神）
  const it=S.files[k];if(!it)return;
  const u=murl(S.folder,it.rel);
  if(originPool.has(u))return;
  const im=new Image();im.decoding='async';im.src=u;originPool.set(u,im);
  while(originPool.size>ORIGIN_POOL_MAX){
    const old=originPool.keys().next().value;
    try{originPool.get(old).src='';}catch(e){}
    originPool.delete(old);
  }
}
function ensureMediaEl(){
  const host=hostEl();let el=host.firstElementChild;
  if(el)return el;
  host.innerHTML='';
  el=document.createElement('img');
  el.id='mainMedia';
  el.decoding='async';
  host.appendChild(el);return el;
}
function resetView(){S.zoom=1;S.rot=0;S.tx=0;S.ty=0;applyTransform();updateZLbl();}
function applyTransform(){
  const h=hostEl();
  h.style.transform=`translate(${S.tx}px,${S.ty}px) rotate(${S.rot}deg) scale(${S.zoom})`;
}
function updateZLbl(){$('zLbl').textContent=(S.zoom===1&&S.rot===0)?'适应':Math.round(S.zoom*100)+'%';$('lbLbl').textContent=(S.zoom===1&&S.rot===0)?'适应':Math.round(S.zoom*100)+'%';}
function zoomBy(f, cx, cy){
  if(f!==1)ensureOriginNow();
  const stage=S.fs?$('lbStage'):$('mediaStage');
  const r=stage.getBoundingClientRect();
  if(cx==null){cx=r.left+r.width/2;cy=r.top+r.height/2;}
  const nz=clamp(S.zoom*f,0.08,10);
  // 以光标为锚点：保持光标下的内容点不动
  const ax=cx-r.left-r.width/2, ay=cy-r.top-r.height/2;
  S.tx=ax-(ax-S.tx)*(nz/S.zoom); S.ty=ay-(ay-S.ty)*(nz/S.zoom);
  S.zoom=nz;applyTransform();updateZLbl();
}
function rotateBy(d){ensureOriginNow();S.rot=(S.rot+d+360)%360;applyTransform();updateZLbl();}

let showToken=0;
let lastErrUrl='';           // 同一张图失败只提示一次，避免缩略图/原图两次 onerror 连弹两条 toast
function setFileInfo(it,a,w,h){
  const dims=(w&&h)?` · ${w}×${h}`:'';
  $('v-file').textContent=`图包 ${S.albumSel+1}/${S.albums.length}「${a.name}」· ${it.rel}${dims} · ${fmtSize(it.size)}`;
}
// 预览已经够屏幕大时，就不该再拉原图：预览尺寸本身就是按屏幕算的（4K 要 3840，上限 4200），
// 再拉一张 8.5MB 原图（解码后是 91MB 位图）在屏幕上根本看不出区别，纯浪费 IO / 内存 / CPU。
// 真要看细节（缩放 / 旋转 / 全屏）由 ensureOriginNow() 立刻拉原图。
// 只有屏幕物理像素超过 PREVIEW_EDGE_MAX（比如 5K+）时才需要走"延后拉原图"那条路。
function needOrigin(){
  const dpr=window.devicePixelRatio||1;
  const st=$('mediaStage');
  const needPx=Math.max(st?st.clientWidth:0, window.innerWidth||0)*dpr;
  return previewEdge < Math.ceil(needPx);
}
// 用户主动细看（缩放/旋转/全屏）时，若还没到原图，就补拉原图保证放大后清晰。
// 注意两个坑：
//  1. 直接改 el.src 会先清空画面（新图没解码完之前是空的），缩放时会闪一下；
//  2. 原图可达 7952×5304、解码后 161MB 位图，同步解码会撞上正在进行的滚轮操作。
// 所以先在后台 decode() 好，再换 src —— 画面一直有内容，解码也不在主线程上。
let ensurePending=false;
function ensureOriginNow(){
  // _previewOnly 表示"当前显示的是够用的预览、故意没拉原图" —— 这种情况仍要拉
  if(S._originReady&&!S._previewOnly)return;
  const it=S.files[S.idx];if(!it)return;
  const originUrl=murl(S.folder,it.rel);
  const el=ensureMediaEl();
  if(el.getAttribute('src')===originUrl){        // 已经是原图了，只收尾
    S._originReady=true;S._previewOnly=false;cancelOriginLoad();return;
  }
  if(ensurePending)return;                       // 正在解码，别重复起
  S._previewOnly=false;cancelOriginLoad();
  ensurePending=true;
  const pre=new Image();pre.decoding='async';pre.src=originUrl;
  const swap=()=>{
    ensurePending=false;
    if(S.files[S.idx]!==it)return;   // 已经翻页了，别覆盖新图
    S._originReady=true;
    const host=ensureMediaEl();
    host.classList.remove('origin-loading');
    host.src=originUrl;
  };
  if(pre.decode){pre.decode().then(swap,swap);}else{pre.onload=swap;pre.onerror=swap;}
}
function show(){
  if(!S.files.length)return;
  const it=S.files[S.idx],a=albumAt(S.idx);S.albumSel=S.albumOf[S.idx];
  const el=ensureMediaEl();
  const originUrl=murl(S.folder,it.rel);
  el.onclick=()=>{if(S.zoom===1)openFs();else resetView();};
  // 图库常被外部增删文件，抓到 404/解码失败时给一条明确提示，而不是留一个无解释的破图
  el.onerror=()=>{
    el.classList.remove('origin-loading');
    const u=el.src||'';
    if(u&&u!==lastErrUrl){lastErrUrl=u;toast('这个文件打不开（可能已损坏或被外部移动）');}
  };
  const myTok=++showToken;
  cancelOriginLoad();
  S._previewOnly=false;
  el.src=turl(S.folder,it.rel,previewEdge,PREVIEW_Q);
  setFileInfo(it,a);
  if(!needOrigin()){
    // 预览足够覆盖屏幕时，避免完整解码原图和大位图模糊。
    S._originReady=true;S._previewOnly=true;
    el.classList.remove('origin-loading');
    api.dim(S.folder,it.rel).then(d=>{
      if(myTok===showToken&&d&&d.w)setFileInfo(it,a,d.w,d.h);
    }).catch(()=>{});
  }else{
    S._originReady=false;el.classList.add('origin-loading');
    const pre=originPool.get(originUrl);
    if(pre&&pre.complete&&pre.naturalWidth){
      S._originReady=true;el.classList.remove('origin-loading');
      el.src=originUrl;setFileInfo(it,a,pre.naturalWidth,pre.naturalHeight);
      scheduleIdleOrigin();
    }else{
      originTimer=setTimeout(()=>{
        originTimer=0;
        const probe=new Image();probe.decoding='async';originProbe=probe;
        const settle=(w,h)=>{if(myTok!==showToken)return;
          originProbe=null;S._originReady=true;const host=ensureMediaEl();
          host.classList.remove('origin-loading');host.src=originUrl;setFileInfo(it,a,w,h);
          scheduleIdleOrigin();};
        probe.onload=()=>settle(probe.naturalWidth,probe.naturalHeight);
        probe.onerror=()=>settle();
        probe.src=originUrl;
      },ORIGIN_DELAY);
    }
  }
  resetView();
  $('counter').textContent=`${S.idx-a.start+1}/${a.count} · 包${S.albumSel+1}/${S.albums.length}`;
  if(S.folder){S.review[S.folder]=S.review[S.folder]||{};S.review[S.folder].index=S.idx;}
  preloadAround();scheduleProgress();
  if(S.filmOn){film.layout();film.followCurrent();}
  if(S.fs)syncFsMedia();
}
function preloadAround(){
  // 只预载邻居的预览（几百 KB/张），绝不预载原图——原图由 scheduleIdleOrigin 空闲时单独处理。
  // 窗口取前后各 3 张：滚轮翻图很密，±2 在快速滚动时会跟不上。
  const a=albumAt(S.idx);
  const win=(previewEdge>2400)?2:3;   // 预览越大生成越慢，窗口相应收窄
  for(const k of [S.idx-win,S.idx-1,S.idx+1,S.idx+win]){
    if(k<a.start||k>=a.end)continue;
    const it=S.files[k];
    const u=turl(S.folder,it.rel,previewEdge,PREVIEW_Q);
    if(!imgPool.has(u)){
      const im=new Image();im.decoding='async';im.src=u;imgPool.set(u,im);
      if(imgPool.size>PREVIEW_POOL_MAX){
        const oldest=imgPool.keys().next().value;
        try{imgPool.get(oldest).src='';}catch(e){}   // 主动中止，别让过期的图继续占 IO
        imgPool.delete(oldest);
      }
    }
  }
}

/* 导航（纯边界，绝不跨图包） */
function step(d){
  if(!S.files.length)return;
  if(S.view==='grid'){moveWallSel(d);return;}
  const a=albumAt(S.idx),ni=S.idx+d;
  if(ni<a.start){toast('已是本图包第一张 · Tab 回上一图包');return;}
  if(ni>a.end-1){toast('已是本图包最后一张 · 空格进下一图包');return;}
  S.idx=ni;show();
}
function firstInAlbum(){const a=curAlbum();if(!a)return;S.idx=a.start;if(S.view==='single')show();}
function lastInAlbum(){const a=curAlbum();if(!a)return;S.idx=a.end-1;if(S.view==='single')show();}
function jumpAlbum(d){
  if(!S.albums.length)return;
  const ai=S.view==='single'?S.albumOf[S.idx]:S.albumSel,ni=ai+d;
  if(ni<0){toast('已是第一个图包');return;}
  if(ni>=S.albums.length){toast('已是最后一个图包 · N 下一文件夹');return;}
  S.albumSel=ni;S.idx=S.albums[ni].start;
  if(S.view==='grid')wall.select(ni);else show();
}
function jumpFolder(d){
  if(!S.filtered.length)return;
  let p=S.filtered.findIndex(f=>f.name===S.folder);
  if(p===-1){openFolder(S.filtered[0].name);return;}
  p=(p+d+S.filtered.length)%S.filtered.length;
  openFolder(S.filtered[p].name);
}
async function setReviewState(name,state){
  if(!name)return false;      // 未选文件夹时 v-head 的标记按钮仍可见，直接忽略，不往后端写
  try{
    await api.reviewState(name,state);
  }catch(e){
    toast('标记失败：本地服务可能已断开，恢复后请重试');
    return false;
  }
  if(state==='none')delete S.review[name];else S.review[name]=Object.assign(S.review[name]||{index:S.idx||0},{state});
  applyFilter();renderList();updateProgress();syncStateBtns();
  return true;
}
// 防重入锁：K/X 是"写盘 + 跳组"的组合动作，一次要几百毫秒。
// 没有这个锁的时候，K 和 X 几乎同时按下（或系统级连环键）会算出两个 anchor，
// 第二个 setReviewState 落到刚跳过去的那组上 —— 表现是"标记了一组没看过的"。
let __deciding=false;
async function decideAndNext(state){
  if(!S.folder||__deciding)return;
  __deciding=true;
  const anchor=S.folder;
  try{
    await flushProgress();
    if(!await setReviewState(anchor,state))return; // 标记没落库就不跳组，避免漏审
    jumpFolderAfter(anchor,1);
  }finally{
    __deciding=false;
  }
}
/* 标记完跳到「列表顺序上的下一组」。
   注意不能再用 jumpFolder：setReviewState 内部的 applyFilter 会把刚标记的组移出 S.filtered，
   此时 findIndex 返回 -1，老逻辑的兜底是 filtered[0] —— 用「未看」筛选从顶端顺序看时恰好等价，
   但只要你跳着看（或换了别的筛选），就会莫名其妙跳回列表首项。 */
function jumpFolderAfter(anchor,d){
  if(!S.filtered.length)return;
  const cur=S.filtered.findIndex(f=>f.name===anchor);
  if(cur>=0){openFolder(S.filtered[(cur+d+S.filtered.length)%S.filtered.length].name);return;}
  const order=S.folders.map(f=>f.name);
  const base=order.indexOf(anchor);
  if(base<0){openFolder(S.filtered[0].name);return;}
  const next=d>0
    ? S.filtered.find(f=>order.indexOf(f.name)>base)
    : [...S.filtered].reverse().find(f=>order.indexOf(f.name)<base);
  openFolder((next||S.filtered[0]).name);
}
