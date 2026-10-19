"use strict";
/* 外壳：Film / Lightbox / 视图切换 / 指针 / 键盘 / 预热 / 静态绑定 / 启动
   从 index.html 内联 <script> 抽出（原 1185-1574 行）。
   加载顺序由文件名数字前缀保证；classic script 共享同一全局词法作用域，
   所以跨文件直接用顶层 const/function 即可，不需要 import。 */
/* =================================================================
 * Film：当前图包内胶片条（横向虚拟）
 * ================================================================= */
const film=(()=>{
  let r0=-1,r1=-1;
  const sc=$('filmScroller'),spacer=$('filmSpacer'),tape=$('filmTape');
  const mounted=new Map(),free=[];
  function album(){return albumAt(S.idx);}
  function fill(t,gi){
    const it=S.files[gi];
    t.innerHTML=`<img decoding="async" src="${turl(S.folder,it.rel)}" alt="">`;
    t._gi=gi;t.dataset.gi=gi;
    t.onclick=()=>{S.idx=gi;show();};
  }
  function obtain(gi){
    const a=album(),k=gi-a.start;
    const t=free.pop()||document.createElement('div');
    t.className='fthumb';
    t.style.left=k*TH_STEP+'px';
    if(t._gi!==gi)fill(t,gi);
    tape.appendChild(t);mounted.set(gi,t);
  }
  function release(gi){const t=mounted.get(gi);if(!t)return;t.remove();mounted.delete(gi);free.push(t);}
  function layout(){
    const a=album();if(!a)return;
    spacer.style.width=(a.count*TH_STEP)+'px';
    [...mounted.keys()].forEach(release);r0=r1=-1;draw();
  }
  function draw(){
    if(!S.filmOn||S.view!=='single')return;
    const a=album();if(!a)return;
    const left=sc.scrollLeft,v0=Math.max(0,Math.floor(left/TH_STEP)-6),v1=Math.min(a.count,Math.ceil((left+sc.clientWidth)/TH_STEP)+6);
    if(v0!==r0||v1!==r1){
      r0=v0;r1=v1;
      for(const gi of [...mounted.keys()]){const k=gi-a.start;if(k<v0||k>=v1)release(gi);}
      for(let k=v0;k<v1;k++){const gi=a.start+k;if(!mounted.has(gi))obtain(gi);}
    }
    paint();
  }
  function paint(){mounted.forEach((t,gi)=>t.classList.toggle('cur',gi===S.idx));}
  function followCurrent(){
    const a=album();if(!a)return;const k=S.idx-a.start,x=k*TH_STEP;
    if(x<sc.scrollLeft)sc.scrollLeft=x;else if(x+TH_W>sc.scrollLeft+sc.clientWidth)sc.scrollLeft=x+TH_W-sc.clientWidth;
  }
  sc.addEventListener('scroll',draw,{passive:true});
  return {layout,draw,followCurrent};
})();
function toggleFilm(){
  S.filmOn=!S.filmOn;
  $('filmstrip').classList.toggle('on',S.filmOn);
  $('singleView').classList.toggle('film-on',S.filmOn);
  if(S.filmOn){film.layout();film.followCurrent();}
}

/* =================================================================
 * Lightbox：复用 #mediaHost 节点（迁移而非重载）
 * ================================================================= */
function openFs(){if(!S.files.length)return;ensureOriginNow();S.fs=true;$('lightbox').classList.add('on');$('lbStage').appendChild(hostEl());void hostEl().offsetWidth;syncFsMedia();}
function closeFs(){S.fs=false;$('lightbox').classList.remove('on');$('mediaStage').appendChild(hostEl());}
function toggleFs(){S.fs?closeFs():openFs();}
function syncFsMedia(){if(S.fs&&$('lbStage')&&hostEl().parentElement!==$('lbStage'))$('lbStage').appendChild(hostEl());}

/* =================================================================
 * 视图切换 / 打开文件夹
 * ================================================================= */
function setView(v){
  S.view=v;
  $('wall').classList.toggle('on',v==='grid');
  $('singleView').classList.toggle('on',v==='single');
  $('viewGrid').classList.toggle('on',v==='grid');
  $('viewSingle').classList.toggle('on',v==='single');
  $('emptyHint').style.display=S.files.length?'none':'flex';
  if(v==='grid'){wall.layout();setCounter();
    $('v-file').textContent=`${S.folder} · ${S.albums.length} 图包 · ${S.files.length} 张图片`;}
  else{show();}
  history.replaceState(null,'','?folder='+encodeURIComponent(S.folder)+'&view='+v);
}
let folderRequest=0;
async function openFolder(name,keepIdx){
  const requestId=++folderRequest;
  if(S.fs)closeFs();   // 全屏状态下切文件夹：必须先退出全屏，否则 mediaHost 还挂在 #lbStage 上，会卡在旧图的全屏里
  S.folder=name;$('v-title').textContent=name;$('v-file').textContent='加载中…';
  const saved=S.review[name]&&typeof S.review[name].index==='number'?S.review[name].index:0;
  let d;
  try{ d=await api.files(name); }catch(e){ if(requestId===folderRequest)$('v-file').textContent='加载失败：本地服务可能已断开，恢复后会自动重连，或双击「启动图库预览.bat」'; return; }
  if(requestId!==folderRequest)return;
  S.files=d.files||[];
  const m=buildAlbums(S.files);S.albums=m.albums;S.albumOf=m.of;
  imgPool.clear();     // 上一组的预载对象已无用
  originPool.clear();  // 原图池每张解码后可达 90MB，换组必须清
  wall.reset();        // 关键：换组必须清空卡片池。否则 draw() 的可见范围与上一组重合时不会重填，
                       // 图包墙会继续显示上一个组的封面和图包名（详见 代码体检报告 F1）
  // 进度与视图必须分开处理：以前"用图包墙打开一组"会顺手把 S.idx 清成 0，
  // 于是刷新一下 / 点开一个 &view=grid 的链接，辛苦翻到的位置就没了。
  // 正确做法是——只要是合法的历史进度就恢复，keepIdx 只决定【进哪个视图】。
  const resume=saved>0&&saved<S.files.length;
  S.idx=resume?saved:0;
  S.albumSel=resume?(S.albumOf[S.idx]||0):0;
  setView(keepIdx&&resume?'single':'grid');
  renderList();syncStateBtns();
  loadDedup(name);    // 异步，不阻塞看图；标记出本组里是别处副本的图包
  loadHusk(name);     // 同上；标出空壳 / 残缺 / 夹广告图的图包
}

/* ---------------- 指针交互：拖拽平移 + 滚轮缩放 + 双击 ---------------- */
function bindStagePointer(stage){
  let drag=null;
  // 滚轮状态（每个 stage 一份）。为什么要有累积 + 冷却：机械滚轮和触控板一次滑动会连发
  // 几十个事件，不加节流的话一次滑动能连翻十几张，把 HDD 和解码线程一起打爆 —— 正是卡顿来源。
  let wheelAcc=0, wheelAt=0, wheelLast=0;
  stage.addEventListener('pointerdown',e=>{
    if(e.target.closest('.hit')||e.target.closest('#zoomBar')||e.target.closest('#lbBar'))return;
    if(S.zoom===1&&S.rot===0)return; // 适配态不拖拽
    drag={x:e.clientX,y:e.clientY,tx:S.tx,ty:S.ty};stage.setPointerCapture(e.pointerId);
  });
  stage.addEventListener('pointermove',e=>{
    if(!drag)return;S.tx=drag.tx+(e.clientX-drag.x);S.ty=drag.ty+(e.clientY-drag.y);applyTransform();
  });
  stage.addEventListener('pointerup',()=>drag=null);
  stage.addEventListener('wheel',e=>{
    if(S.view!=='single'&&!S.fs)return;      // 图包墙下滚轮仍是原生滚动
    e.preventDefault();
    // Ctrl/⌘ + 滚轮 → 以光标为锚点缩放（浏览器自身的页面缩放被 preventDefault 挡掉）
    if(e.ctrlKey||e.metaKey){
      wheelAcc=0;
      zoomBy(e.deltaY<0?1.12:0.89,e.clientX,e.clientY);
      return;
    }
    // 【放大/旋转状态下滚轮 = 平移，不翻页】这是最影响看图的 bug：
    // 用户放大想看细节，一滚就跳到下一张、缩放还被重置，等于"刚对准就没了"。
    if(S.zoom!==1||S.rot!==0){
      wheelAcc=0;
      S.tx-=(e.deltaX||0)-(e.shiftKey?e.deltaY:0);
      S.ty-=(e.shiftKey?0:e.deltaY);
      applyTransform();
      return;
    }
    // 滚轮 / 触控板 → 翻到下一张或上一张（图包边界照旧不跨包，由 step() 负责）
    const now=performance.now();
    if(now-wheelLast>WHEEL_GESTURE_GAP)wheelAcc=0;   // 新手势，清掉上次残留
    wheelLast=now;
    const unit=e.deltaMode===1?16:(e.deltaMode===2?100:1);  // 像素/行/页 统一折算
    wheelAcc+=(e.deltaY*unit)/100;
    if(Math.abs(wheelAcc)>3)wheelAcc=Math.sign(wheelAcc)*3; // 别攒太多，否则松手后还在翻
    if(Math.abs(wheelAcc)<0.5)return;                        // 还没到一格
    if(now-wheelAt<WHEEL_COOLDOWN)return;
    wheelAt=now;
    const dir=wheelAcc>0?1:-1;
    wheelAcc-=dir;
    step(dir);
  },{passive:false});
  stage.addEventListener('dblclick',e=>{
    if(e.target.closest('.hit'))return;
    if(S.zoom===1&&S.rot===0)zoomBy(2,e.clientX,e.clientY);else resetView();
  });
}

/* ---------------- 键盘：键位 → 动作 ---------------- */
const KEYS={
  ArrowLeft:e=>{e.preventDefault();step(-1);},
  ArrowRight:e=>{e.preventDefault();step(1);},
  ' ':e=>{e.preventDefault();if(!e.repeat)jumpAlbum(1);},
  Tab:e=>{e.preventDefault();if(!e.repeat)jumpAlbum(e.shiftKey?1:-1);},
  Enter:e=>{if(S.view==='grid'){e.preventDefault();S.albumSel=clamp(S.albumSel,0,S.albums.length-1);S.idx=S.albums[S.albumSel].start;setView('single');}},
  Home:e=>{e.preventDefault();firstInAlbum();},
  End:e=>{e.preventDefault();lastInAlbum();},
  n:()=>jumpFolder(1), p:()=>jumpFolder(-1),
  g:()=>setView(S.view==='grid'?'single':'grid'),
  f:()=>toggleFs(), h:()=>toggleFilm(),
  r:()=>rotateBy(90),
  '+':()=>zoomBy(1.2),'=':()=>zoomBy(1.2),'-':()=>zoomBy(1/1.2),'_':()=>zoomBy(1/1.2),'0':()=>resetView(),
  // 标记类操作必须挡 e.repeat：按住 K 不放会连续触发"标记 + 跳下一组"，
  // 一秒能跳掉七八组，而且每组都写了盘 —— 这比误删更难挽回。
  k:e=>{if(e.repeat)return;decideAndNext('kept');},
  x:e=>{if(e.repeat)return;decideAndNext('marked');},
  d:()=>openDup(),
  '?':()=>$('help').classList.add('on'),
  Escape:()=>{if(S.fs)closeFs();else $('help').classList.remove('on');}
};
document.addEventListener('keydown',e=>{
  if(e.target.tagName==='INPUT'||e.target.tagName==='SELECT')return;
  // 裁决面板打开时完全接管键盘：不这么做的话按 2 会翻图、按空格会切图包，
  // 在"一键删一张"的场景下就是误删。
  if($('dup').classList.contains('on')){
    const k=e.key;
    if(k==='Escape'){e.preventDefault();closeDup();return;}
    if(k==='1'){e.preventDefault();dupDecide('L');return;}      // 删左（留右）
    if(k==='2'){e.preventDefault();dupDecide('R');return;}      // 删右（留左，推荐）
    if(k==='3'||k===' '){e.preventDefault();dupSkip();return;}  // 都留
    if(k==='ArrowLeft'){e.preventDefault();dupPrev();return;}
    if(k==='ArrowRight'){e.preventDefault();dupSkip();return;}
    return;
  }
  // 图包对比面板同样完全接管键盘（同一个理由：按 2 会翻图、空格会切图包）
  if($('pkgdup').classList.contains('on')){
    const k=e.key;
    if(k==='Escape'){e.preventDefault();closePkgDup();return;}
    if(k==='1'){e.preventDefault();pkDecide('L');return;}      // 删左（推翻建议）
    if(k==='2'){e.preventDefault();pkDecide('R');return;}      // 删右（按建议）
    if(k==='3'||k===' '){e.preventDefault();pkSkipPair();return;}
    if(k==='ArrowLeft'){e.preventDefault();pkPrevP();return;}
    if(k==='ArrowRight'){e.preventDefault();pkNextP();return;}
    return;
  }
  const fn=KEYS[e.key]||KEYS[e.key.toLowerCase()];
  if(fn)fn(e);
});
// 点按钮即失焦，避免空格/回车二次激活
document.addEventListener('click',e=>{if(e.target.tagName==='BUTTON')e.target.blur();},true);

/* ---------------- 预热缩略图 ---------------- */
let pwTimer=0;
function pwOpen(){$('pw').classList.add('on');pwPoll();if(!pwTimer)pwTimer=setInterval(pwPoll,1200);}
function pwClose(){$('pw').classList.remove('on');}
async function pwPoll(){
  let p;
  try{ p=await api.prewarmProgress(); }catch(e){ return; }
  const el=$('pwProg');if(!el)return;
  const b=p.batch;
  if(b){
    el.innerHTML=`进行中：<b>${b.done}</b> / ${b.total} 张　·　组 <b>${b.folders_done}</b>/${b.folders}`
      +`<br><span style="color:var(--faint)">当前组：${esc(b.current_folder||'（正在建清单…）')}</span>`;
  }else if(p.queued>0){
    el.innerHTML=`队列剩余 <b>${p.queued}</b> 张<br><span style="color:var(--faint)">剩余组由预热线程逐个追加</span>`;
  }else{
    el.innerHTML='空闲';
  }
}
async function pwStart(scope){
  if(scope==='group'&&!S.folder){toast('先选一个文件夹');return;}
  try{
    // 当前组：连单张看图用的预览尺寸一起生成（同一张原图只读一次），翻页才会真的秒开。
    // 未判定组：只生成封面，大预览要 8 小时以上，不值。
    const r=await api.prewarm(scope,S.folder,scope==='group'?previewEdge:0);
    if(r&&r.ok){
      toast(scope==='group'?'已开始预热当前组（含单张预览）':'已开始预热未判定组（后台跑，可继续浏览）');
      pwPoll();if(!pwTimer)pwTimer=setInterval(pwPoll,1200);
    }else toast('预热启动失败：'+(r&&r.error||'未知'));
  }catch(e){ toast('预热启动失败，服务可能已断开'); }
}
async function pwStop(){
  try{ await api.prewarmStop(); toast('已停止预热'); }catch(e){}
  pwPoll();
}

/* ---------------- 静态控件绑定（只绑一次） ---------------- */
function bindStatic(){
  let searchTm;
  $('search').oninput=()=>{clearTimeout(searchTm);searchTm=setTimeout(()=>{applyFilter();renderList();},140);};
  $('catFilter').onchange=()=>{applyFilter();renderList();};
  $('stateFilter').onchange=()=>{applyFilter();renderList();};
  $('viewGrid').onclick=()=>setView('grid');
  $('viewSingle').onclick=()=>setView('single');
  $('hitPrev').onclick=()=>step(-1);$('hitNext').onclick=()=>step(1);
  $('prevBtn').onclick=()=>step(-1);$('nextBtn').onclick=()=>step(1);
  $('prevAlbumBtn').onclick=()=>jumpAlbum(-1);$('nextAlbumBtn').onclick=()=>jumpAlbum(1);
  $('prevFolderBtn').onclick=()=>jumpFolder(-1);$('nextFolderBtn').onclick=()=>jumpFolder(1);
  $('fsBtn').onclick=toggleFs;$('filmBtn').onclick=toggleFilm;
  $('dupBtn').onclick=openDup;$('dupClose').onclick=closeDup;
  $('huskBtn').onclick=openHusk;
  $('pkBtn').onclick=()=>openPkgDup(null);
  $('pkClose').onclick=closePkgDup;
  $('pkKeepL').onclick=()=>pkDecide('R');   // 删右 · 留左 = 按建议删
  $('pkKeepR').onclick=()=>pkDecide('L');   // 删左 · 留右 = 推翻建议
  $('pkSkip').onclick=pkSkipPair;
  $('pkPrev').onclick=pkPrevP;$('pkNext').onclick=pkNextP;
  $('dupBuild').onclick=async()=>{
    const btn=$('dupBuild');btn.disabled=true;btn.textContent='正在启动…';
    try{
      const r=await api.dedupBuild(S.folder||'');
      if(r.error){toast('启动失败：'+r.error);btn.textContent='补索引（后台，可边跑边看图）';}
      else{
        btn.textContent='已启动，正在后台补索引';
        toast(r.note||'后台补索引已启动');
      }
    }catch(e){toast('启动失败：'+e.message);btn.disabled=false;}
  };
  $('dupKeepL').onclick=()=>dupDecide('L');$('dupKeepR').onclick=()=>dupDecide('R');
  $('dupSkip').onclick=dupSkip;$('dupPrev').onclick=dupPrev;$('dupNext').onclick=dupSkip;
  $('zIn').onclick=()=>zoomBy(1.2);$('zOut').onclick=()=>zoomBy(1/1.2);$('zReset').onclick=resetView;$('zRot').onclick=()=>rotateBy(90);
  $('lbZIn').onclick=()=>zoomBy(1.2);$('lbZOut').onclick=()=>zoomBy(1/1.2);$('lbRot').onclick=()=>rotateBy(90);$('lbClose').onclick=closeFs;
  $('lbPrev').onclick=()=>step(-1);$('lbNext').onclick=()=>step(1);
  $('goBtn').onclick=()=>{const v=parseInt($('jump').value,10);if(isNaN(v)||!S.files.length)return;const a=curAlbum();S.idx=clamp(v-1,a.start,a.end-1);if(S.view==='single')show();else{S.albumSel=S.albumOf[S.idx];setView('single');}};
  $('jump').onkeydown=e=>{if(e.key==='Enter')$('goBtn').click();};
  $('btnKept').onclick=()=>setReviewState(S.folder,stateOf(S.folder)==='kept'?'none':'kept');
  $('btnMarked').onclick=()=>setReviewState(S.folder,stateOf(S.folder)==='marked'?'none':'marked');
  $('keepNextBtn').onclick=()=>decideAndNext('kept');
  $('markNextBtn').onclick=()=>decideAndNext('marked');
  $('clearBtn').onclick=async()=>{if(!confirm('确定清空全部审查标记和浏览位置吗？'))return;await api.clear();S.review={};applyFilter();renderList();updateProgress();syncStateBtns();};
  $('rescanBtn').onclick=async()=>{$('rescanBtn').textContent='扫描中…';await api.rescan();$('rescanBtn').textContent='重扫体积';await boot(true);};
  $('thumbGcBtn').onclick=async()=>{
    const btn=$('thumbGcBtn');btn.textContent='统计中…';
    let st;try{st=await api.thumbStats();}catch(e){btn.textContent='清缩略图';toast('读取缓存信息失败');return;}
    const gb=st.bytes/1073741824, lim=st.limit/1073741824;
    if(st.bytes<=st.limit){btn.textContent='清缩略图';toast(`缩略图缓存 ${gb.toFixed(2)} GB / ${lim.toFixed(0)} GB，无需清理`);return;}
    if(!confirm(`缩略图缓存已 ${gb.toFixed(2)} GB（软上限 ${lim.toFixed(0)} GB）。\n将只删除最旧的缓存图、回落到上限的 85%，不碰任何原图（删后浏览会按需重新生成）。是否清理？`)){btn.textContent='清缩略图';return;}
    btn.textContent='清理中…';
    try{const r=await api.thumbGc();toast(`已清 ${r.removed} 张缓存 · 释放 ${fmtSize(r.freed)}`);}
    catch(e){toast('清理失败，服务可能已断开');}
    btn.textContent='清缩略图';
  };
  $('purgeBtn').onclick=async()=>{
    const list=S.folders.filter(f=>stateOf(f.name)==='marked');
    if(!list.length){toast('还没有标为「待删」的文件夹');return;}
    const sz=list.reduce((a,b)=>a+(+b.size||0),0);
    if(!confirm(`将 ${list.length} 个「待删」文件夹（共 ${fmtSize(sz)}）移入系统回收站？\n（可从回收站还原；要永久删除请用抽样快审页）`))return;
    const btn=$('purgeBtn');btn.textContent='删除中…';
    try{
      const r=await api.remove(list.map(f=>f.name),false);
      const ok=r.results.filter(x=>x.ok).length, fail=r.results.length-ok;
      toast(`已移入回收站 ${ok} 个 · 释放 ${fmtSize(r.freed)}`+(fail?` · ${fail} 个失败`:''));
      await boot(true);
    }catch(e){toast('删除失败，服务可能已断开');btn.textContent='🗑 删除待删';}
  };
  $('prewarmBtn').onclick=pwOpen;
  $('pwGroup').onclick=()=>pwStart('group');
  $('pwUnrev').onclick=()=>pwStart('unreviewed');
  $('pwStop').onclick=pwStop;
  $('pwClose').onclick=pwClose;
  $('pw').addEventListener('click',e=>{if(e.target===$('pw'))pwClose();});
  $('helpBtn').onclick=()=>$('help').classList.add('on');
  $('helpClose').onclick=()=>$('help').classList.remove('on');
  $('lightbox').addEventListener('click',e=>{if(e.target===$('lightbox')||e.target===$('lbStage'))closeFs();});
  bindStagePointer($('mediaStage'));bindStagePointer($('lbStage'));
  window.addEventListener('beforeunload',()=>{flushProgress();});
  // 窗口/全屏尺寸变了，预览尺寸要跟着变；变了就清池（URL 里的 edge 变了，旧缓存全 miss）
  window.addEventListener('resize',rafThrottle(()=>{
    const pe=calcPreviewEdge();
    if(pe!==previewEdge){previewEdge=pe;imgPool.clear();}
  }));
}

/* ---------------- 启动 ---------------- */
async function boot(skipRoute){
  let d;
  try{
    d=await api.state();
  }catch(e){
    // 【必须把 __offline 置 true】断线横幅的恢复逻辑是
    //   const was=__offline; __offline=false; setOffline(false);
    //   if(was) boot(true);
    // 这里不置位的话 __offline 一直是 false，ping 恢复后 was=false，
    // 于是永远不会重新 boot —— 表现是"横幅消失了，但侧栏永远空白，刷新也没用"。
    __offline=true;
    const bar=$('offline');
    bar.textContent='⚠ 连不上本地服务 · 点击这里重试（或双击「后台启动图库.vbs」）';
    bar.style.cursor='pointer';
    bar.onclick=()=>location.reload();
    bar.style.display='block';
    return;
  }
  S.folders=d.folders;S.review=d.review||{};
  $('rootPath').textContent=d.root+' · v'+(d.version||'?')+(d.thumb?'':' · 缩略图组件未加载');
  applyFilter();renderList();updateProgress();
  if(skipRoute)return;
  // view 也要读：setView 每次都把 &view= 写进地址栏，但以前从来不读它，
  // 导致刷新/分享一个"图包墙"链接会掉回单图视图（v5.10）。
  const q=new URLSearchParams(location.search),f=q.get('folder'),v=q.get('view');
  if(f&&S.folders.some(x=>x.name===f))openFolder(f,v!=='grid');
  else{$('emptyHint').style.display='flex';}
}
const OFFLINE_TXT=$('offline').textContent;   // 记住原始文案，恢复时要还原
let __offline=false, __failN=0;
/* 断线横幅：前 2 次说"正在重连"，第 3 次起必须改口说"关标签页"。
   因为服务重启后浏览器连接池里那条长连接已经死了，而 F5 / Ctrl+F5
   **复用同一个连接池**——刷新根本救不回来，只会让人以为工具坏了。
   实测：服务端健康（keep-alive 连发 12 次全 200），用户端仍一直显示断开。 */
function setOffline(on){
  const bar=$('offline');
  if(!on){__failN=0;bar.textContent=OFFLINE_TXT;bar.style.display='none';return;}
  __failN++;
  if(__failN>=3){
    bar.innerHTML=`⚠ 连不上本地服务（已重试 <b>${__failN}</b> 次）——`
      +`<b>请关闭本标签页后重新打开</b>。单纯刷新不行：浏览器会继续复用同一条已失效的连接。`
      +`<br>若一直这样，双击「启动图库预览.bat」。`;
  }else{
    bar.textContent=OFFLINE_TXT;
  }
  bar.style.display='block';
}
/* 版本漂移提示：服务重启/升级后，还开着的旧页面跑的是旧 JS。
   表现就是"新加的按钮点了没反应"——非常难自查，因为页面看起来一切正常。
   所以让前端每轮 ping 都顺便比对版本，对不上就在顶部挂一条可点击刷新的横幅。 */
// 【不在这里写死版本号】服务端每次返回 index.html 时会把 data-ver 填成自己的版本。
// 于是"这份 HTML 对应的版本"和"服务端现在跑的版本"天然可比，改前端不用记得同步改常量。
// （这个项目栽过一次复制常量的亏：v5.10 的 pkg/album 命名各写一套 → 28 个标记画不出来）
const FE_VERSION=document.documentElement.getAttribute('data-ver')||'0';
function showStale(ver){
  let el=$('staleBar');
  if(!el){
    el=document.createElement('div');el.id='staleBar';
    el.style.cssText='position:fixed;top:0;left:0;right:0;z-index:1000;background:#8a6d1f;'
      +'color:#fff;text-align:center;font-size:12.5px;padding:7px;cursor:pointer';
    el.onclick=()=>location.reload();
    document.body.appendChild(el);
  }
  el.textContent=`⚠ 工具已更新到 ${ver}，当前页面还是旧的 —— 点这里刷新后新功能才生效`;
  el.style.display='block';
}
previewEdge=calcPreviewEdge();       // 必须在 boot 之前定下来：它决定预览图的 URL
setInterval(async()=>{
  try{
    const r=await fetch('/api/ping',{cache:'no-store'});
    const ver=r.headers.get('X-Version')||'';
    await r.text();          // 必须把 body 读掉，否则 keep-alive 连接上会残留未读数据
    // 只认 x.y 形态，且必须比自己新，避免版本号写法变化导致误报
    if(ver&&ver!==FE_VERSION&&/^\d+\.\d+$/.test(ver))showStale(ver);
    const was=__offline;__offline=false;setOffline(false);
    // 【boot 必须自己兜住异常】ping 已经成功 = 服务是好的。此时 boot 抛错若冒到
    // 外层 catch，会被误判成"断线"，界面就挂着断开横幅而服务明明正常 ——
    // 这正是"服务好着但一直显示断开"最隐蔽的一条路径。
    if(was){
      try{ await boot(true); }        // skipRoute=true，不打断当前视图
      catch(e){ console.warn('断线恢复后刷新列表失败（不影响本地状态）', e); }
    }
  }catch(e){__offline=true;setOffline(true);}
},4000);
bindStatic();
boot();
