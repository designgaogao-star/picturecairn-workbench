// 忠实复刻 index.html 中 wall 虚拟滚动的 obtain/release/draw/fillCard 逻辑，
// 模拟「切换文件夹」这一动作，检查已挂载卡片的内容是否刷新。
// 逻辑逐行对照 index.html 555-630 行。

const CARD_W = 200, CARD_GAP = 14, CARD_H = 196, AL_INFO = 40;
const CARD_STEP = CARD_W + CARD_GAP, ROW_STEP = CARD_H + AL_INFO + CARD_GAP;

// ---- 受测状态（对应 index.html 的局部变量）----
let cols = 1, range0 = -1, range1 = -1, lastCols = -1;
const mounted = new Map();   // ai -> card
const free = [];             // 回收池
let fillCalls = 0;           // 记录 fillCard 实际执行次数
let hit = 0;                 // 记录「复用了别人的内容」的次数

// ---- 宿主元素桩 ----
const el = { clientWidth: 1400, clientHeight: 900, scrollTop: 0 };
const spacer = {};
// S 是全局 store，对应 index.html 的 const S
const S = {
  albums: [], files: [],
  folder: '', albumSel: 0, view: 'grid',
  // 每个 album 换个可读的名字，用来判断卡片上挂的是哪个文件夹的内容
  coverOf: () => ''
};

function calcCols() { const w = el.clientWidth - CARD_GAP; cols = Math.max(1, Math.floor(w / CARD_STEP)); }
function rows() { return Math.ceil(S.albums.length / cols); }

function fillCard(card, ai) {
  fillCalls++;
  // index.html 里这里写的是 S.files[S.albums[ai].coverIdx] 的缩略图 src + 图包名
  card.content = `${S.folder} / 图包${ai + 1}`;   // 内容带上文件夹名，便于观察
  card._ai = ai;
}
function obtain(ai) {
  const card = free.pop() || { cls: 'album' };
  if (card._ai !== ai) {
    if (card._ai !== undefined) hit++;            // 复用了一块属于别的 ai 的卡片
    fillCard(card, ai);
  }
  card.dataset_ai = ai;
  mounted.set(ai, card);
}
function release(ai) { const c = mounted.get(ai); if (!c) return; mounted.delete(ai); free.push(c); }

function layout() {
  calcCols();
  spacer.height = rows() * ROW_STEP + 'px';
  if (cols !== lastCols) { lastCols = cols; [...mounted.keys()].forEach(release); range0 = range1 = -1; }
  draw();
}
function visibleRange() {
  const top = el.scrollTop, vh = el.clientHeight, o = 2;
  const r0 = Math.max(0, Math.floor(top / ROW_STEP) - o);
  const r1 = Math.min(rows() - 1, Math.ceil((top + vh) / ROW_STEP) + o);
  return [r0 * cols, Math.min(S.albums.length, (r1 + 1) * cols)];
}
function draw() {
  if (S.view !== 'grid' || !S.albums.length) return;
  const [v0, v1] = visibleRange();
  if (v0 !== range0 || v1 !== range1) {
    range0 = v0; range1 = v1;
    for (const ai of [...mounted.keys()]) { if (ai < v0 || ai >= v1) release(ai); }
    for (let ai = v0; ai < v1; ai++) { if (!mounted.has(ai)) obtain(ai); }
  } else {
    // index.html 在这条分支下什么都不做：不 release、不 obtain、不重填
  }
}

// ---- 模拟 ----
function loadFolder(name, albumCount) {
  S.folder = name;
  S.albums = Array.from({ length: albumCount }, (_, i) => ({ i }));
  S.files = S.albums;                 // 只为让 fillCard 有东西可读
  el.scrollTop = 0;                   // 用户点侧栏切文件夹，滚动条回到顶部
}

console.log('窗口 1400x900 → 每行列数 cols =', (() => { calcCols(); return cols; })(), '，每行高', ROW_STEP, 'px');
console.log('');

// 第一次：打开一个有 189 个图包的组（真实数据里 189 是常见量级）
loadFolder('[非R18]蠢沫沫', 189);
layout();
console.log('① 打开「[非R18]蠢沫沫」(189 图包)');
console.log('   已挂载卡片数 =', mounted.size, ' fillCard 调用 =', fillCalls);
const before = [...mounted.keys()].sort((a, b) => a - b).slice(0, 4)
  .map(ai => `卡${ai}="${mounted.get(ai).content}"`);
console.log('   前 4 张卡片内容：', before.join('  '));
console.log('');

// 用户点侧栏，切到另一个有 50 个图包的组
const fc1 = fillCalls, hit1 = hit;
loadFolder('[非R18]安静Maleah', 50);
layout();
console.log('② 切换文件夹 → 「[非R18]安静Maleah」(50 图包)');
console.log('   已挂载卡片数 =', mounted.size, ` fillCard 调用 = ${fillCalls}（本次新增 ${fillCalls - fc1}）`);
const after = [...mounted.keys()].sort((a, b) => a - b).slice(0, 4)
  .map(ai => `卡${ai}="${mounted.get(ai).content}"`);
console.log('   前 4 张卡片内容：', after.join('  '));

const stale = [...mounted.entries()].filter(([ai, c]) => c.content !== `${S.folder} / 图包${ai + 1}`);
console.log('');
console.log('=== 判定 ===');
console.log(`屏幕上的 ${mounted.size} 张卡片中，仍显示「上一个文件夹」内容的有 ${stale.length} 张`);
if (stale.length) {
  console.log('☠ 复现成功：切换文件夹后图包墙不刷新，仍在展示上一个组的封面与图包名。');
  console.log('   卡片来源分布：', [...new Set([...mounted.values()].map(c => c.content.split(' / ')[0]))].join(', '));
  console.log('   只有用户主动滚动（改变可见行范围）才会触发重填。');
} else {
  console.log('✓ 未复现，图包墙已正确刷新。');
}
console.log('');
console.log('对照修复：若在 openFolder 里 buildAlbums 之后补一行 wall.reset()，');
console.log('reset() 会 release 全部卡片并把 lastCols 置 -1，下一张卡片必然走 fillCard 重填。');
// 演示 reset 后行为
function reset() { range0 = range1 = -1; lastCols = -1; [...mounted.keys()].forEach(release); free.length = 0; el.scrollTop = 0; layout(); }
const fc2 = fillCalls;
loadFolder('[非R18]再换一个组', 50); reset();
const stale2 = [...mounted.entries()].filter(([ai, c]) => c.content !== `${S.folder} / 图包${ai + 1}`);
console.log(`   实测：补 reset() 后，残留旧内容 ${stale2.length} 张，本次 fillCard 调用 ${fillCalls - fc2} 次 → 全部重填 ✓`);
