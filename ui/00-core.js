"use strict";
/* 基础层：Utils / API / Store / Model / Sidebar / 浏览位置落盘
   从 index.html 内联 <script> 抽出（原 202-420 行）。
   加载顺序由文件名数字前缀保证；classic script 共享同一全局词法作用域，
   所以跨文件直接用顶层 const/function 即可，不需要 import。 */
/* =====================================================================
 * 图库审查台 v5.3 —— 分层架构
 *  Utils / API / Store(单一状态) / Model(图包聚合) / Sidebar /
 *  Wall(虚拟图包墙) / Viewer(媒体复用+三缓冲+变换) / Film(虚拟胶片) /
 *  Lightbox(复用媒体节点) / Keys(键位→动作)
 * ===================================================================== */

/* ---------------- Utils ---------------- */
const $=id=>document.getElementById(id);
const CARD_W=200, CARD_GAP=14, CARD_H=196, AL_INFO=40, CARD_STEP=CARD_W+CARD_GAP, ROW_STEP=CARD_H+AL_INFO+CARD_GAP;
const TH_W=54, TH_GAP=5, TH_STEP=TH_W+TH_GAP;
const PREVIEW_EDGE_MIN=1600; // 预览长边下限（窄屏也别低于这个，缩放放大时留点余量）
const PREVIEW_EDGE_MAX=4200; // 与服务端 THUMB_EDGE_MAX 对齐；4K 屏需要 3840，必须够
const PREVIEW_Q=80;        // 预览图质量
const ORIGIN_DELAY=320;    // 停下多少毫秒后才去拉原图（见 show() 里的说明）
const PREVIEW_POOL_MAX=8;  // 预览池上限（4200px 的位图不小，别再放大）
const ORIGIN_POOL_MAX=3;   // 原图预载池上限——每张解码后可达 90MB，必须严格限制
const IDLE_ORIGIN_DELAY=800; // 当前张原图到位后，再空闲这么久才预载「下一张」的原图
// 预览长边按实际显示需要算，不写死：宽屏（2560）上 1600/1400 会被拉伸到 2000+ 而发虚，
// 逼着用户等原图（实测 418ms）才看得清；窄屏又没必要为 3000 买单。所以两头夹一下。
// 注意：改了它 URL 会变、旧预览缓存会 miss，所以只在启动和窗口尺寸变化时重算。
let previewEdge=PREVIEW_EDGE_MIN;
function calcPreviewEdge(){
  const dpr=window.devicePixelRatio||1;
  const st=$('mediaStage');
  const w=Math.max(st?st.clientWidth:0, window.innerWidth||0)*dpr;
  return Math.max(PREVIEW_EDGE_MIN, Math.min(PREVIEW_EDGE_MAX, Math.ceil(w)));
}
const WHEEL_COOLDOWN=70;   // 滚轮翻图的最小间隔（ms）——防连发把 IO 和解码打爆
const WHEEL_GESTURE_GAP=250; // 超过这个间隔视为新手势，清掉累积量（防松手后继续"惯性"翻）
const fmtSize=b=>{b=Number(b)||0;if(b>=1073741824)return (b/1073741824).toFixed(2)+' GB';if(b>=1048576)return (b/1048576).toFixed(1)+' MB';return (b/1024).toFixed(0)+' KB';};
const esc=s=>(''+(s??'')).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const murl=(f,r)=>'/media?folder='+encodeURIComponent(f)+'&file='+encodeURIComponent(r);
const turl=(f,r,edge,q)=>'/thumb?folder='+encodeURIComponent(f)+'&file='+encodeURIComponent(r)+(edge?`&edge=${edge}&q=${q||80}`:'');
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
const rafThrottle=fn=>{let q=false;return (...a)=>{if(q)return;q=true;requestAnimationFrame(()=>{q=false;fn(...a);});};};
let toastTimer;
function toast(msg){const t=$('toast');t.textContent=msg;t.style.display='block';clearTimeout(toastTimer);toastTimer=setTimeout(()=>t.style.display='none',1400);}

/* ---------------- API（带超时，避免服务不可达时无限等待） ---------------- */
function fetchTO(url, opt, ms){
  const ctl=new AbortController(), tm=setTimeout(()=>ctl.abort(),ms||15000);
  return fetch(url, Object.assign({signal:ctl.signal}, opt||{})).finally(()=>clearTimeout(tm));
}
const api = {
  async state() {
    return (await fetchTO('/api/state', null, 12000)).json();
  },
  async files(name, refresh) {
    let url = '/api/files?folder=' + encodeURIComponent(name);
    if (refresh) url += '&refresh=1';
    return (await fetchTO(url, null, 30000)).json();   // 大文件夹首次建索引可能较慢
  },
  post(url, body) {
    return fetchTO(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    }, 15000);
  },
  reviewState(name, state) {
    return this.post('/api/review/state', { name, state });
  },
  progress(name, index) {
    return this.post('/api/review/progress', { name, index });
  },
  clear() {
    return this.post('/api/review/clear', {});
  },
  rescan() {
    return this.post('/api/rescan', {});
  },
  thumbStats() {
    return fetchTO('/api/thumb/stats', null, 8000).then(r=>r.json());
  },
  thumbGc() {
    return this.post('/api/thumb/gc', {}).then(r => r.json());
  },
  remove(names, permanent) {
    return this.post(permanent ? '/api/delete' : '/api/trash', { names }).then(r => r.json());
  },
  // 图包级去重：查重结果 + 删单个图包子目录
  dedupStatus() {
    return fetchTO('/api/dedup/status', null, 8000).then(r => r.json());
  },
  dedupGroup(folder, th) {
    return fetchTO('/api/dedup/group?folder=' + encodeURIComponent(folder)
      + (th ? '&th=' + th : ''), null, 60000).then(r => r.json());   // 大组两两比对可能数秒
  },
  rmPkg(folder, pkg, permanent) {
    return this.post(permanent ? '/api/delete/pkg' : '/api/trash/pkg',
      { folder, pkg, ...(permanent ? { confirm_permanent: true } : {}) }).then(r => r.json());
  },
  // 重复对裁决队列（B 级）
  dedupPairs(folder, th) {
    return fetchTO('/api/dedup/pairs?folder=' + encodeURIComponent(folder)
      + (th ? '&th=' + th : ''), null, 60000).then(r => r.json());
  },
  // 图包对比：删整包前的肉眼复核（A 级建议 → 两侧清单 + 代表图 + 独有文件）
  dedupPkgPair(folder, pkg) {
    return fetchTO('/api/dedup/pkgpair?folder=' + encodeURIComponent(folder)
      + '&pkg=' + encodeURIComponent(pkg), null, 30000).then(r => r.json());
  },
  // 空壳/残缺/广告图（C 级）
  dedupHusk(folder) {
    return fetchTO('/api/dedup/husk?folder=' + encodeURIComponent(folder),
      null, 30000).then(r => r.json());
  },
  // 只删包内那几张广告图，包本身留着。文件清单由服务端当场重算，前端传的只是包名
  huskClear(folder, pkgs) {
    return this.post('/api/dedup/husk/clear', { folder, pkgs }).then(r => r.json());
  },
  // 传 folder='' 就是整库。几小时的长活，由服务端用计划任务拉起，不挂在当前会话下
  dedupBuild(folder) {
    return this.post('/api/dedup/build', { folder: folder || '' }).then(r => r.json());
  },
  rmFile(folder, rel, permanent) {
    return this.post(permanent ? '/api/delete/file' : '/api/trash/file',
      { folder, rel, ...(permanent ? { confirm_permanent: true } : {}) }).then(r => r.json());
  },
  prewarm(scope, folder, viewEdge) {
    return this.post('/api/prewarm', { scope, folder, view_edge: viewEdge || 0 }).then(r => r.json());
  },
  prewarmStop() {
    return this.post('/api/prewarm/stop', {}).then(r => r.json());
  },
  prewarmProgress() {
    return fetchTO('/api/prewarm/progress', null, 8000).then(r => r.json());
  },
  dim(f, r) {
    return fetchTO('/api/dim?folder=' + encodeURIComponent(f) + '&file=' + encodeURIComponent(r), null, 8000)
      .then(x => x.json());
  }
};

/* ---------------- Store（全局唯一状态） ---------------- */
const S={
  folders:[], review:{}, filtered:[],
  folder:null, files:[], idx:0,
  view:'grid',                 // 'grid' | 'single'
  albums:[], albumOf:[], albumSel:0,
  // viewer 变换
  zoom:1, rot:0, tx:0, ty:0,
  fs:false, filmOn:false,
  _originReady:false,          // 当前显示的是否已是"最终画质"
  _previewOnly:false           // 最终画质就是预览（够屏幕大），没拉原图
};
const stateOf=n=>(S.review[n]&&S.review[n].state)||'unreviewed';

/* ---------------- Model：扁平 files → 图包 ---------------- */
function buildAlbums(files){
  const albums=[], of=[]; let cur=null;
  for(let i=0;i<files.length;i++){
    const key=files[i].album||'';
    if(!cur||cur.key!==key){
      if(cur)cur.end=i;
      cur={key,name:key||'（根目录散图）',start:i,end:files.length,count:0,coverIdx:i};
      albums.push(cur);
    }
    cur.count++; of.push(albums.length-1);
  }
  if(cur)cur.end=files.length;
  return {albums, of};
}
const albumAt=i=>S.albums[S.albumOf[i]];
const curAlbum=()=>!S.albums.length?null:(S.view==='single'?albumAt(S.idx):S.albums[S.albumSel]);

/* ---------------- Sidebar ---------------- */
function applyFilter(){
  const kw=$('search').value.trim().toLowerCase(),cat=$('catFilter').value,sf=$('stateFilter').value;
  S.filtered=S.folders.filter(f=>{
    if(kw&&!f.name.toLowerCase().includes(kw))return false;
    if(cat&&f.category!==cat)return false;
    if(sf&&stateOf(f.name)!==sf)return false;
    return true;
  });
}
function updateProgress(){
  let done=0,marked=0,msz=0;
  S.folders.forEach(f=>{const s=stateOf(f.name);if(s==='kept'||s==='marked')done++;if(s==='marked'){marked++;msz+=+f.size||0;}});
  const pct=S.folders.length?Math.round(done/S.folders.length*100):0;
  $('progressBar').style.width=pct+'%';
  $('progressTxt').textContent=`${done}/${S.folders.length}`;
  $('markedStat').textContent=marked?`待删 ${marked} · ${fmtSize(msz)}`:'';
  const pb=$('purgeBtn');if(pb){pb.textContent=marked?`🗑 删除待删 (${marked})`:'🗑 删除待删';pb.disabled=(marked===0);pb.style.opacity=marked?1:.45;}
}
function renderList(){
  const box=$('folderList');box.innerHTML='';
  const frag=document.createDocumentFragment();
  S.filtered.forEach(f=>{
    const s=stateOf(f.name),ico=s==='marked'?'✕':s==='kept'?'✓':'○';
    const seen=S.review[f.name]&&typeof S.review[f.name].index==='number'?S.review[f.name].index:null;
    const d=document.createElement('div');
    d.className='item '+(s==='marked'?'st-marked':s==='kept'?'st-kept':'')+(S.folder===f.name?' active':'');
    d.innerHTML=`<div class="stico">${ico}</div><div class="meta">
      <div class="nm"><span class="tag tag-${f.category}">${f.category}</span>${esc(f.name)}</div>
      <div class="sub"><span class="sz">${fmtSize(f.size)}</span> · ${f.media_count}张${seen!==null?` · 看到${seen+1}`:''}</div></div>`;
    d.onclick=()=>openFolder(f.name);
    frag.appendChild(d);
  });
  box.appendChild(frag);
  const act=box.querySelector('.item.active'); if(act)act.scrollIntoView({block:'nearest'});
}
function syncStateBtns(){
  const s=stateOf(S.folder);
  $('btnKept').classList.toggle('on',s==='kept');
  $('btnMarked').classList.toggle('on',s==='marked');
}

/* ---------------- 浏览位置落盘（防抖） ---------------- */
let progTimer;
function scheduleProgress(){if(!S.folder)return;clearTimeout(progTimer);progTimer=setTimeout(flushProgress,1200);}
function flushProgress(){
  if(!S.folder)return Promise.resolve();
  S.review[S.folder]=S.review[S.folder]||{};S.review[S.folder].index=S.idx;
  return api.progress(S.folder,S.idx).catch(()=>{});
}
