"use strict";
/* 图包封面墙（虚拟滚动：DOM 恒定，图包数无上限）
   从 ui/70-wall.js 拆出（原文件第 428-507 行）。
   拆之前这四块混在一个 501 行的文件里，改任何一个面板都要跨 500 行找位置。 */
const wall=(()=>{
  let cols=1,range0=-1,range1=-1,lastCols=-1;
  const el=$('wall'),spacer=$('wallSpacer'),tape=$('wallTape');
  const mounted=new Map();   // ai -> 卡片节点（只保留可见+overscan）
  const free=[];             // 回收的卡片节点，滚动时复用，避免反复建 DOM / 重复解码封面
  // n 列实际占宽 = n×卡片 + (n-1)×间距 = n×STEP - GAP，
  // 所以能放下 n 列的条件是 n ≤ (W + GAP) / STEP。
  // 原先写的是 floor((W-GAP)/STEP)，等于把两侧各扣了一次间距 ——
  // 1440 窗口下右边缘白白空出 238px，本来能排 5 列只排了 4 列。
  function calcCols(){
    const w=el.clientWidth;
    cols=Math.max(1,Math.floor((w+CARD_GAP)/CARD_STEP));
  }
  function rows(){return Math.ceil(S.albums.length/cols);}
  function fillCard(card,ai){   // 仅在节点绑定到新图包时填充一次内容（含封面 src）
    const a=S.albums[ai],it=S.files[a.coverIdx];
    card.innerHTML=`<span class="al-idx">${ai+1}</span><img class="cover" decoding="async" src="${turl(S.folder,it.rel)}" alt="">
      <div class="al-info"><div class="al-name">${esc(a.name)}</div><div class="al-cnt">${a.count} 张</div></div>`;
    paintDup(card,a);
    card._ai=ai;
    card.onclick=()=>{S.albumSel=ai;S.idx=S.albums[ai].start;setView('single');};
  }
  function obtain(ai){
    const card=free.pop()||document.createElement('div');
    card.className='album';
    const r=Math.floor(ai/cols),c=ai%cols;
    card.style.top=r*ROW_STEP+'px';card.style.left=c*CARD_STEP+'px';
    if(card._ai!==ai)fillCard(card,ai);   // 复用同一 ai 时不重设 src，杜绝闪烁/重复解码
    card.dataset.ai=ai;
    tape.appendChild(card);mounted.set(ai,card);
  }
  function release(ai){const card=mounted.get(ai);if(!card)return;card.remove();mounted.delete(ai);free.push(card);}
  function layout(){
    calcCols();
    spacer.style.height=rows()*ROW_STEP+'px';
    if(cols!==lastCols){lastCols=cols;[...mounted.keys()].forEach(release);range0=range1=-1;} // 列数变化才整体重排
    draw();
  }
  function visibleRange(){
    const top=el.scrollTop,vh=el.clientHeight,o=2;
    const r0=Math.max(0,Math.floor(top/ROW_STEP)-o);
    const r1=Math.min(rows()-1,Math.ceil((top+vh)/ROW_STEP)+o);
    return [r0*cols,Math.min(S.albums.length,(r1+1)*cols)];
  }
  function draw(){
    if(S.view!=='grid'||!S.albums.length)return;
    const [v0,v1]=visibleRange();
    if(v0!==range0||v1!==range1){
      range0=v0;range1=v1;
      for(const ai of [...mounted.keys()]){if(ai<v0||ai>=v1)release(ai);} // 离开窗口→回收
      for(let ai=v0;ai<v1;ai++){if(!mounted.has(ai))obtain(ai);}          // 进入窗口→取池/新建
    }
    paintSel();
  }
  function paintSel(){mounted.forEach((c,ai)=>c.classList.toggle('cur',ai===S.albumSel));}
  // 滚动跟随当前图包（顶部第一个可见）
  function followScroll(){
    const [v0]=visibleRange();
    if(v0!==S.albumSel&&v0<S.albums.length){S.albumSel=v0;S.idx=S.albums[v0].start;paintSel();setCounter();}
  }
  function select(ai){ // 键盘移动：滚动到可见 + 高亮
    S.albumSel=ai;
    const r=Math.floor(ai/cols);const cardTop=r*ROW_STEP;
    if(cardTop<el.scrollTop)el.scrollTop=cardTop;
    else if(cardTop+ROW_STEP>el.scrollTop+el.clientHeight)el.scrollTop=cardTop+ROW_STEP-el.clientHeight;
    draw();setCounter();
  }
  function reset(){range0=range1=-1;lastCols=-1;[...mounted.keys()].forEach(release);free.length=0;el.scrollTop=0;layout();}
  // 去重结果异步到达后重刷所有可见卡片的标记（不重建 DOM、不重设 src，避免闪烁）
  function refresh(){mounted.forEach((c,ai)=>{if(S.albums[ai])paintDup(c,S.albums[ai]);});}
  el.addEventListener('scroll',()=>{draw();followScroll();},{passive:true});
  window.addEventListener('resize',rafThrottle(()=>{if(S.view==='grid'){range0=range1=-1;layout();}}));
  return {layout,reset,select,refresh,get el(){return el;}};
})();
function moveWallSel(d){
  const ni=clamp(S.albumSel+d,0,S.albums.length-1);
  if(ni===S.albumSel){toast(d<0?'已是第一个图包':'已是最后一个图包');return;}
  S.albumSel=ni;S.idx=S.albums[ni].start;wall.select(ni);
}
function setCounter(){
  if(S.view==='grid')$('counter').textContent=`图包 ${S.albumSel+1}/${S.albums.length}`;
}
