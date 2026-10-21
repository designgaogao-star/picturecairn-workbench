/* Interaction reference only. Production keeps Preact and the bounded data layer. */
(() => {
  'use strict';
  const data = window.WORKBENCH_DATA;
  const $ = (selector, root = document) => root.querySelector(selector);
  const esc = (value) => String(value).replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]);
  const icon = (name, size = 18) => `<i data-lucide="${name}" width="${size}" height="${size}" aria-hidden="true"></i>`;
  const ib = (action, symbol, label, extra = '') => `<button class="icon-btn" data-action="${action}" aria-label="${esc(label)}" data-tip="${esc(label)}" ${extra}>${icon(symbol)}</button>`;
  const bytes = (value) => value >= 1048576 ? `${(value / 1048576).toFixed(1)} MB` : `${Math.round(value / 1024)} KB`;
  const query = new URLSearchParams(location.search);
  const scenario = query.get('scene') || '';
  const storageKey = 'gallery-workbench-design-v1';
  let remembered = {};
  try { remembered = JSON.parse(localStorage.getItem(storageKey) || '{}'); } catch { /* Local files may have storage disabled. */ }
  const state = {
    groupId: 'travel', pkgId: null, image: null, mode: 'browse', tab: 'compare',
    theme: remembered.theme || 'light', size: 230, fill: false, selection: false, selected: new Set(),
    filter: 'all', category: 'all', library: 'main', offline: scenario === 'offline', bad: scenario === 'error',
    resume: remembered.resume || { groupId: 'travel', pkgId: 'travel-coast', index: 2 },
    removed: new Set(), panel: null, menu: null, modal: null, deleteTargets: [], report: [],
    permanent: false, confirmed: false, verified: ['stale', 'unique'].includes(scenario),
    checking: false, stale: scenario === 'stale', unique: scenario === 'unique',
    pair: ['travel-lake', 'travel-lake-copy'], viewerInfo: false, zoom: null, pan: { x: 0, y: 0 },
    sampleOffset: 0, sampleCount: 20, taskFilter: 'all', scrollTop: 0, focusTarget: null, inspectedId: null,
    tasks: [
      { id: 'warm', name: '生成静态封面', target: '旅行影像', kind: 'prewarm', state: 'running', done: 48, total: 96 },
      { id: 'scan', name: '扫描图库', target: '我的图片', kind: 'scan', state: 'completed', done: 216, total: 216 },
      { id: 'failure', name: '整包核验', target: '森林深处 / 雨后木桥', kind: 'compare', state: 'failed', done: 7, total: 9 },
    ],
  };
  let toastTimer;
  let lastRangeIndex = 0;
  let viewerWasOpen = false;
  let panelModality = false;
  const scrollPositions = new Map();
  const scopeKey = () => `${state.groupId}:${state.pkgId || ''}:${state.mode}:${state.mode === 'organize' ? state.tab : ''}`;
  const group = () => data.groups.find((item) => item.id === state.groupId) || data.groups[0];
  const packages = () => scenario === 'empty' ? [] : data.packages(state.groupId).filter((item) => !state.removed.has(item.id));
  const pkg = () => packages().find((item) => item.id === state.pkgId) || packages()[0];
  const images = () => pkg() ? data.images(pkg()).filter((item) => !state.removed.has(item.id)) : [];
  const currentImage = () => images()[state.image ?? 0];
  const activeTasks = () => state.tasks.filter((task) => ['running', 'paused', 'pausing', 'cancelling'].includes(task.state));
  const labels = { running: '进行中', completed: '已完成', failed: '失败', paused: '已暂停', pausing: '暂停中', cancelled: '已取消', cancelling: '取消中' };
  const markLabels = { none: '未标记', kept: '保留', marked: '待整理' };

  function save() {
    try { localStorage.setItem(storageKey, JSON.stringify({ theme: state.theme, resume: state.resume })); } catch { /* A preview still works without persistence. */ }
  }

  function paintIcons(root = document) {
    window.lucide.createIcons({ root, attrs: { 'stroke-width': 1.65 } });
  }

  function toast(message, symbol = 'circle-check') {
    clearTimeout(toastTimer);
    $('#toasts').innerHTML = `<div class="toast">${icon(symbol)}<span>${esc(message)}</span></div>`;
    paintIcons($('#toasts'));
    toastTimer = setTimeout(() => { $('#toasts').innerHTML = ''; }, 3400);
  }

  function setTheme() {
    const theme = state.theme === 'system' ? (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light') : state.theme;
    document.documentElement.dataset.theme = theme;
    save();
  }

  function href(options = {}) {
    const next = { groupId: state.groupId, pkgId: state.pkgId, mode: state.mode, tab: state.tab, ...options };
    let value = `#/g/${next.groupId}`;
    if (next.mode === 'organize') value += `/organize/${next.tab}`;
    else if (next.pkgId) value += `/p/${next.pkgId}`;
    if (options.image !== undefined && options.image !== null) value += `/i/${options.image}`;
    return value;
  }

  function go(options) {
    const nextHash = href(options);
    if (nextHash === location.hash) readRoute();
    else location.hash = nextHash;
  }

  function readRoute() {
    const content = $('#content');
    if (content) scrollPositions.set(scopeKey(), content.scrollTop);
    const parts = location.hash.replace(/^#\//, '').split('/');
    const nextGroup = data.groups.some((item) => item.id === parts[1]) ? parts[1] : 'travel';
    const nextMode = parts[2] === 'organize' ? 'organize' : 'browse';
    const nextPkg = parts[2] === 'p' ? parts[3] : null;
    const scopeChanged = state.groupId !== nextGroup || state.pkgId !== nextPkg || state.mode !== nextMode;
    state.groupId = nextGroup;
    state.mode = nextMode;
    state.tab = ['sample', 'similar', 'compare', 'audit'].includes(parts[3]) && nextMode === 'organize' ? parts[3] : 'compare';
    state.pkgId = nextPkg;
    state.image = parts[4] === 'i' && /^\d+$/.test(parts[5]) ? Math.min(Number(parts[5]), Math.max(0, images().length - 1)) : null;
    if (scopeChanged) {
      state.selection = false;
      state.selected.clear();
      state.inspectedId = null;
    }
    state.scrollTop = scrollPositions.get(scopeKey()) || 0;
    if (state.image !== null && currentImage()) {
      state.resume = { groupId: state.groupId, pkgId: pkg().id, index: state.image };
      save();
    }
    state.zoom = null;
    state.pan = { x: 0, y: 0 };
    closeMenu();
    const nav = $('#navigation');
    if (nav.open) nav.close();
    render(false);
  }

  function sidebar(mobile = false) {
    const folders = data.groups.filter((item) => (state.filter === 'all' || item.state === state.filter) && (state.category === 'all' || item.category === state.category));
    const warm = state.tasks.find((task) => task.id === 'warm');
    return `<div class="brand-row">${icon('gallery-vertical-end', 24)}<span class="brand">GalleryTool</span>${mobile ? '<span class="spacer"></span>' + ib('close-nav', 'x', '关闭导航') : ''}</div>
      <div class="library-block">
        <div class="section-label"><span>图库</span>${ib('add-library', 'plus', '添加图库')}</div>
        <label class="library-select">${icon(state.offline ? 'hard-drive' : 'hard-drive', 18)}
          <select aria-label="当前图库" data-change="library"><option value="main" ${state.library === 'main' ? 'selected' : ''}>我的图片</option><option value="disk" ${state.library === 'disk' ? 'selected' : ''}>移动硬盘${state.library === 'disk' && !state.offline ? '' : ' · 离线'}</option></select>
        </label><div class="library-path">${state.library === 'main' ? 'F:\\示例图库' : 'G:\\影像归档'}</div>
      </div>
      <nav class="folder-section" aria-label="图库文件夹">
        <div class="section-label"><span>文件夹</span><span>${data.groups.length}</span></div>
        <div class="folder-filters"><select class="filter-select" aria-label="文件夹状态筛选" data-change="filter">${[['all', '全部状态'], ['none', '未标记'], ['kept', '保留'], ['marked', '待整理']].map(([id, label]) => `<option value="${id}" ${state.filter === id ? 'selected' : ''}>${label}</option>`).join('')}</select>
          <select class="filter-select" aria-label="文件夹分类筛选" data-change="category">${[['all', '全部分类'], ['非R18', '非R18'], ['R16', 'R16'], ['R18', 'R18'], ['其他', '其他']].map(([id, label]) => `<option value="${id}" ${state.category === id ? 'selected' : ''}>${label}</option>`).join('')}</select></div>
        ${folders.map((item) => `<button class="folder-row ${item.id === state.groupId ? 'selected' : ''}" data-action="folder" data-id="${item.id}" ${item.id === state.groupId ? 'aria-current="page"' : ''}>
          ${icon(item.id === state.groupId ? 'folder-open' : 'folder', 18)}<span class="name">${item.name}</span>${item.state === 'marked' ? `<span class="state-mark" aria-label="待整理" title="待整理">${icon('flag', 14)}</span>` : ''}<span class="count" title="${item.photoIds.length * 8} 张图片">${item.photoIds.length * 8}</span></button>`).join('') || '<p class="empty-folders">没有符合状态的文件夹</p>'}
      </nav>
      <div class="side-status"><div class="status-line">${icon(state.offline ? 'unplug' : 'circle-check', 14)}<span>${state.offline ? '磁盘离线 · 保留上次索引' : '索引已就绪'}</span></div>
        <button class="side-task" data-action="tasks"><span>${icon('activity', 14)}${warm.state === 'running' ? '正在生成静态封面' : `静态封面 · ${labels[warm.state]}`}<span class="spacer"></span><span class="num">${warm.done} / ${warm.total}</span></span><span class="track"><span style="width:${warm.done / warm.total * 100}%"></span></span></button>
      </div><div class="side-foot"><span>本地图片工作台</span><span>V2</span></div>`;
  }

  function renderHeader() {
    const current = state.pkgId && pkg() ? pkg().name : group().name;
    const resumePkg = data.packages(state.resume.groupId).find((item) => item.id === state.resume.pkgId);
    const canResume = state.resume.groupId === state.groupId && resumePkg && !state.removed.has(resumePkg.id);
    return `<header class="topbar">
      <button class="icon-btn mobile-menu" data-action="navigation" aria-label="打开导航">${icon('panel-left')}</button><span class="mobile-brand">GalleryTool</span>
      <nav class="breadcrumbs" aria-label="当前位置"><button data-action="library-home">我的图片</button>${icon('chevron-right', 14)}<button class="${state.pkgId ? '' : 'current'} truncate" data-action="group-home" title="${group().name}">${group().name}</button>${state.pkgId ? `${icon('chevron-right', 14)}<span class="current truncate">${esc(current)}</span>` : ''}</nav>
      <div class="top-actions">${ib('appearance', 'sun-moon', '外观', `aria-haspopup="menu" aria-expanded="${state.menu === 'appearance'}"`)}${ib('info', 'panel-right', '信息面板', `aria-expanded="${state.panel === 'info'}"`)}
        <button class="icon-btn task-button" data-action="tasks" aria-label="后台任务，${activeTasks().length} 个活动任务" data-tip="后台任务" aria-expanded="${state.panel === 'tasks'}">${icon('list-checks')}${activeTasks().length ? '<span class="task-indicator"></span>' : ''}</button>
      </div></header>
      <section class="page-head" aria-labelledby="page-title"><div class="title-row"><div class="title-block"><h1 id="page-title" title="${esc(current)}">${esc(current)}</h1><div class="page-meta">${state.pkgId ? `${icon('images', 14)}<span>${images().length} 张图片</span><span>·</span><span>${esc(pkg()?.parent || '')}</span>` : `<span>${packages().length} 个图包</span><span>·</span><span>${packages().reduce((total, item) => total + item.count, 0)} 张图片</span>`}</div></div>
        ${canResume ? `<div class="resume"><div class="resume-meta"><strong>${resumePkg.name}</strong><span>上次看到 ${state.resume.index + 1} / ${resumePkg.count}</span></div><button class="btn" data-action="resume" aria-label="继续浏览 ${resumePkg.name} 第 ${state.resume.index + 1} 张" data-tip="继续浏览">${icon('history', 16)}<span>继续浏览</span></button></div>` : ''}
      </div><div class="tabs-line"><nav class="mode-tabs" aria-label="工作模式"><button class="mode-tab ${state.mode === 'browse' ? 'active' : ''}" data-action="browse" ${state.mode === 'browse' ? 'aria-current="page"' : ''}>${icon('layout-grid', 16)}浏览</button><button class="mode-tab ${state.mode === 'organize' ? 'active' : ''}" data-action="organize" ${state.mode === 'organize' ? 'aria-current="page"' : ''}>${icon('scan-search', 16)}整理</button></nav>
        <label class="folder-state"><span>文件夹状态</span><select data-change="mark" aria-label="${group().name}的文件夹状态">${Object.entries(markLabels).map(([id, label]) => `<option value="${id}" ${group().state === id ? 'selected' : ''}>${label}</option>`).join('')}</select></label>
      </div></section>`;
  }

  function renderToolbar() {
    if (state.mode === 'organize') return '';
    if (state.selection) return `<div class="toolbar selecting" role="toolbar" aria-label="批量操作"><span class="toolbar-label"><strong>已选 ${state.selected.size} ${state.pkgId ? '张图片' : '个图包'}</strong></span><button class="btn quiet" data-action="select-page">${icon('check-check', 14)}选中可见项</button><span class="spacer"></span><button class="btn danger" data-action="delete-selected" ${!state.selected.size ? 'disabled' : ''}>${icon('trash-2', 14)}删除…</button><button class="btn quiet" data-action="selection-done">完成</button></div>`;
    return `<div class="toolbar" role="toolbar" aria-label="浏览工具">
      ${state.pkgId ? `<button class="icon-btn" data-action="group-home" aria-label="返回图包">${icon('arrow-left', 16)}</button><span class="toolbar-label">图片</span>` : '<span class="toolbar-label">全部图包</span>'}
      <button class="btn quiet" data-action="selection-start">${icon('list-check', 14)}选择</button><span class="spacer"></span>
      ${state.pkgId ? `<div class="fit-modes" role="group" aria-label="图片显示方式"><button class="icon-btn ${!state.fill ? 'active' : ''}" data-action="fit" data-value="contain" aria-label="完整显示" aria-pressed="${!state.fill}" data-tip="完整显示">${icon('rectangle-horizontal', 16)}</button><button class="icon-btn ${state.fill ? 'active' : ''}" data-action="fit" data-value="cover" aria-label="填充裁切" aria-pressed="${state.fill}" data-tip="填充裁切">${icon('scan', 16)}</button></div><span class="divider"></span>` : ''}
      <label class="range-control">${icon('image', 14)}<input type="range" min="180" max="310" step="10" value="${state.size}" data-change="tile-size" aria-label="缩略图尺寸">${icon('image', 18)}</label><span class="divider"></span>
      ${ib('more', 'ellipsis', '更多操作', 'aria-haspopup="menu"')}
    </div>`;
  }

  function tile(item, type) {
    const image = type === 'image';
    const source = image ? item : item.photo;
    const selected = state.selected.has(item.id);
    const recent = state.resume.groupId === state.groupId && (image ? state.resume.pkgId === state.pkgId && state.resume.index === item.index : state.resume.pkgId === item.id);
    const bad = state.bad && (image ? item.index === 1 : item.id === packages()[2]?.id);
    return `<article class="tile ${selected ? 'selected' : ''} ${recent ? 'last-viewed' : ''}" data-tile-id="${item.id}" role="listitem">
      <label class="tile-check"><input type="checkbox" data-change="select" data-id="${item.id}" aria-label="选择${esc(item.name)}" ${selected ? 'checked' : ''}></label>
      ${bad ? `<div class="tile-media bad-media">${icon('image-off', 24)}<span class="small">封面读取失败</span><button class="btn" data-action="retry-image">${icon('rotate-cw', 14)}重试</button></div><button class="tile-main" data-action="${image ? 'open-image' : 'open-package'}" data-id="${item.id}" data-index="${item.index ?? 0}"><span class="tile-body"><span class="tile-title"><span class="name">${esc(item.name)}</span></span><span class="tile-meta">文件暂时不可读</span></span></button>` :
        `<button class="tile-main" data-action="${image ? 'open-image' : 'open-package'}" data-id="${item.id}" data-index="${item.index ?? 0}" title="${esc(item.rel)}" aria-label="${image ? '查看' : '打开图包'} ${esc(item.name)}">
        <span class="tile-media"><img src="${source.src}" alt="${esc(source.name)}" loading="lazy" decoding="async" width="${source.width}" height="${source.height}"></span>
        <span class="tile-body"><span class="tile-title">${image ? '' : icon('folder', 14)}<span class="name">${esc(item.name)}</span></span><span class="tile-meta">${image ? `${item.width} × ${item.height}<span class="spacer"></span><span>${bytes(item.bytes)}</span>` : `<span>${item.count} 张</span><span>· ${item.parent}</span><span class="spacer"></span>${recent ? `<span class="last-label">看到 ${state.resume.index + 1} / ${item.count}</span>` : ''}`}</span></span></button>`}
    </article>`;
  }

  function renderWall() {
    const items = state.pkgId ? images() : packages();
    if (!items.length) return `<div class="empty">${icon('folder-open', 24)}<h2>这个文件夹还没有图片</h2><p>${state.offline ? '磁盘恢复连接后，可以重新扫描。' : '扫描完成后，支持的图片会出现在这里。'}</p><button class="btn" data-action="rescan" ${state.offline ? 'disabled' : ''}>${icon('refresh-cw', 16)}重新扫描</button></div>`;
    return `<div class="grid ${state.pkgId ? `image-grid ${state.fill ? 'fill' : ''}` : ''} ${state.selection ? 'selection-active' : ''}" style="--tile-min:${matchMedia('(max-width:600px)').matches ? 150 : state.size}px" role="list" aria-label="${state.pkgId ? '图片' : '图包'}清单">${items.map((item) => tile(item, state.pkgId ? 'image' : 'package')).join('')}</div>`;
  }

  function compareSide(side, item) {
    const left = side === 'left';
    const files = left ? 9 : 10;
    const verified = state.verified && !state.stale;
    return `<section class="compare-side" aria-label="${left ? '左' : '右'}侧图包"><div class="side-label"><span>${left ? '左侧' : '右侧'}</span>${verified && !state.unique && left ? `<span class="evidence-tag">${icon('copy-check', 14)}完整被包含</span>` : ''}</div>
      <img class="comparison-cover" src="${item.photo.src}" alt="${item.name}" width="${item.photo.width}" height="${item.photo.height}">
      <div class="compare-name">${icon('folder', 16)}<h3>${esc(item.name)}</h3></div><p>${verified ? `${files} 个文件 · ${state.unique ? (left ? 1 : 2) : (left ? 0 : 1)} 个独有文件` : '8 张图片 · 包含非图片文件'}</p>
      ${verified ? `<ul class="file-list"><li>${icon('images', 16)}<span>${state.unique ? '图片内容存在差异' : '8 张图片内容相同'}</span>${icon(state.unique ? 'circle-alert' : 'check', 14)}</li><li>${icon('file-text', 16)}<span>README.txt</span><span class="spacer"></span><span class="ok">${state.unique && left ? '左侧独有' : '相同'}</span></li>${left ? '' : `<li>${icon('file-text', 16)}<span>拍摄记录.txt</span><span class="spacer"></span><span class="warn">右侧独有</span></li>`}</ul>` : ''}
      ${verified && left && !state.unique ? `<button class="btn danger" data-action="delete-verified" data-id="${item.id}">${icon('trash-2', 16)}移到回收站…</button>` : ''}
    </section>`;
  }

  function renderCompare() {
    const list = packages();
    if (list.length < 2) return `<div class="empty">${icon('git-compare-arrows', 24)}<h2>需要两个图包才能核验</h2><p>选择包含至少两个图包的文件夹。</p></div>`;
    const left = list.find((item) => item.id === state.pair[0]) || list[0];
    const right = list.find((item) => item.id === state.pair[1]) || list[1];
    const verified = state.verified && !state.stale;
    return `<div class="org-heading"><div><h2>整包核验</h2><p>比较两侧全部文件的内容，包括非图片文件。</p></div><button class="btn primary" data-action="verify" ${state.checking || left.id === right.id ? 'disabled' : ''}>${icon(state.checking ? 'loader-circle' : 'scan-search', 16)}${state.checking ? '核验中' : state.verified ? '重新核验' : '开始核验'}</button></div>
      <div class="compare-picks"><label class="field">左侧图包<select data-change="pair-left">${list.map((item) => `<option value="${item.id}" ${item.id === left.id ? 'selected' : ''}>${item.name}</option>`).join('')}</select></label>${ib('swap', 'arrow-left-right', '交换左右图包')}<label class="field">右侧图包<select data-change="pair-right">${list.map((item) => `<option value="${item.id}" ${item.id === right.id ? 'selected' : ''}>${item.name}</option>`).join('')}</select></label></div>
      <div class="verdict ${verified ? state.unique ? 'warning' : 'success' : state.stale ? 'warning' : ''}" role="status">${icon(verified ? state.unique ? 'files' : 'shield-check' : state.stale ? 'circle-alert' : 'git-compare-arrows', 24)}<div><strong>${state.checking ? '正在核验文件内容' : verified ? state.unique ? '两侧各有独有内容' : '左侧被右侧完整包含' : state.stale ? '核验结果已过期' : '尚未核验'}</strong><p>${state.checking ? '7 / 9 个文件，完成后显示结论。' : verified ? state.unique ? '左侧独有 1 个，右侧独有 2 个文件。删除任一侧都会失去内容。' : '左侧的 9 个文件在右侧均有相同副本；右侧另有 1 个独有文件。' : state.stale ? '核验后图库发生过变化，重新核验后再决定删除。' : '先核验，再根据内容决定保留哪一侧。'}</p></div></div>
      <div class="compare-sides">${compareSide('left', left)}${compareSide('right', right)}</div><p class="method-line">${verified ? '文件内容核验 · SHA-256 · 已包含非图片文件' : '当前范围：' + esc(group().name) + ' · 尚无可用于删除判断的核验结论'}</p>`;
  }

  function renderSimilar() {
    const list = packages();
    return `<div class="org-heading"><div><h2>相似图包</h2><p>视觉相似是候选线索，整包核验用于确认内容关系。</p></div><button class="btn" data-action="analyze">${icon('scan-search', 16)}开始分析</button></div>
      <div class="verdict">${icon('info', 18)}<div><strong>指纹覆盖率 92%</strong><p>当前还有 8% 的图片未建立指纹，候选结果不代表全部内容。</p></div></div>
      ${list.length < 2 ? '<div class="empty"><h2>暂无相似候选</h2></div>' : [0, 2, 4].filter((i) => i + 1 < list.length).map((i) => `<div class="similar-row">${[list[i], list[i + 1]].map((item, j) => `<div class="similar-pkg"><img src="${item.photo.src}" alt="${item.name}" width="88" height="66"><div><strong>${item.name}</strong><p>匹配 ${j ? '75' : '88'}% · 指纹覆盖 ${j ? '88' : '100'}%</p></div></div>`).join('')}<div class="similar-actions"><span>尚未做内容核验</span><button class="btn" data-action="compare-pair" data-left="${list[i].id}" data-right="${list[i + 1].id}">${icon('git-compare-arrows', 16)}核验这两个图包</button></div></div>`).join('')}`;
  }

  function renderSamples() {
    const list = packages();
    const all = list.flatMap((item) => data.images(item));
    const count = Math.min(all.length, state.sampleCount);
    const sample = Array.from({ length: count }, (_, i) => all[(i * 7 + state.sampleOffset) % all.length]);
    return `<div class="org-heading"><div><h2>抽样浏览</h2><p>当前文件夹 · ${count} 张</p></div><div class="sample-controls"><select aria-label="抽样数量" data-change="sample-count">${[20, 40, 100].map((n) => `<option ${n === state.sampleCount ? 'selected' : ''}>${n}</option>`).join('')}</select><button class="btn" data-action="shuffle">${icon('shuffle', 16)}换一批</button></div></div>
      ${sample.length ? `<div class="grid image-grid sample-grid" style="--tile-min:${matchMedia('(max-width:600px)').matches ? 150 : 210}px">${sample.map((item) => `<article class="tile"><button class="tile-main" data-action="sample-open" data-id="${item.packageId}" data-index="${item.index}"><span class="tile-media"><img src="${item.src}" alt="${item.name}" loading="lazy" width="${item.width}" height="${item.height}"></span><span class="tile-body"><span class="tile-title truncate">${item.name}</span><span class="tile-meta truncate">${esc(item.rel.split('/').slice(1, -1).join(' / '))}</span></span></button></article>`).join('')}</div>` : '<div class="empty"><h2>此文件夹没有可抽样的图片</h2></div>'}`;
  }

  function renderAudit() {
    return `<div class="org-heading"><div><h2>清理检查</h2><p>只列出检查结果，由你决定是否删除。</p></div><button class="btn" data-action="audit">${icon('folder-search', 16)}重新检查</button></div>
      <div class="audit-row">${icon('folder-minus', 18)}<div><strong>空壳图包</strong><p>旅行影像 / 旧版 / 待补齐 · 0 张图片，1 个文本文件</p></div><button class="btn quiet" data-action="audit-detail">${icon('file-search', 16)}查看文件</button></div>
      <div class="audit-row">${icon('image-off', 18)}<div><strong>1 个文件未能读取</strong><p>旅行影像 / 沿途 / 森林深处 / 004.jpg</p></div><button class="btn quiet" data-action="retry-image">${icon('rotate-cw', 16)}重新读取</button></div>
      <p class="method-line">没有图片不等于没有内容；非图片文件仍会保留在检查结果中。</p>`;
  }

  function renderOrganize() {
    return `<div class="organize"><nav class="org-tabs" aria-label="整理工具">${[['sample', '抽样'], ['similar', '相似图包'], ['compare', '整包核验'], ['audit', '清理检查']].map(([id, label]) => `<button class="org-tab ${state.tab === id ? 'active' : ''}" data-action="org-tab" data-id="${id}" ${state.tab === id ? 'aria-current="page"' : ''}>${label}</button>`).join('')}</nav>${({ sample: renderSamples, similar: renderSimilar, compare: renderCompare, audit: renderAudit })[state.tab]()}</div>`;
  }

  function render(preserveScroll = true) {
    const content = $('#content');
    if (content && preserveScroll) state.scrollTop = content.scrollTop;
    const focusAction = document.activeElement?.dataset.action;
    const focusId = document.activeElement?.dataset.id;
    $('#app').innerHTML = `<div class="workspace"><aside class="sidebar">${sidebar()}</aside><main class="main">${renderHeader()}
      ${state.offline ? `<div class="notice" role="status">${icon('unplug', 18)}<span>“${state.library === 'main' ? '我的图片' : '移动硬盘'}”暂时离线，显示上次索引。</span><button class="text-btn" data-action="reconnect">重新检查</button></div>` : ''}
      ${renderToolbar()}<div id="content" class="content" tabindex="-1">${state.mode === 'browse' ? renderWall() : renderOrganize()}</div>
      <footer class="statusbar"><span class="num">${state.selected.size ? `已选 ${state.selected.size} 项` : state.pkgId ? `${images().length} 张图片` : `${packages().length} 个图包`}</span><span class="secondary-status">${state.pkgId ? '按文件名顺序' : '按现有目录顺序'}</span><span class="spacer"></span>${icon(state.offline ? 'unplug' : 'circle-check', 14)}<span>${state.offline ? '离线索引' : '本地图库'}</span><button class="secondary-status" data-action="tasks">${activeTasks().length ? `${activeTasks().length} 个后台任务` : '暂无活动任务'}</button></footer>
    </main></div>`;
    $('#navigation').innerHTML = sidebar(true);
    $('#content').scrollTop = state.scrollTop;
    paintIcons($('#app'));
    paintIcons($('#navigation'));
    renderPanel();
    renderViewer();
    if (state.focusTarget) {
      const target = $(`[data-tile-id="${state.focusTarget}"] .tile-main`);
      target?.focus({ preventScroll: true });
      target?.scrollIntoView({ block: 'nearest' });
      state.focusTarget = null;
    } else if (focusAction && !$('#viewer').open && !$('#modal').open) {
      const target = $(`[data-action="${focusAction}"]${focusId ? `[data-id="${focusId}"]` : ''}`, $('#app'));
      target?.focus({ preventScroll: true });
    }
  }

  function taskRow(task) {
    const active = ['running', 'paused', 'pausing', 'cancelling'].includes(task.state);
    const symbol = task.state === 'failed' ? 'circle-alert' : task.state === 'completed' ? 'circle-check' : task.state === 'paused' ? 'pause' : 'loader-circle';
    return `<article class="task-row"><div class="task-title">${icon(symbol, 18)}<span>${task.name}</span><span class="task-state ${task.state}">${labels[task.state]}</span></div><p>${task.target}</p>
      ${active ? `<div class="track" role="progressbar" aria-label="${task.name}" aria-valuenow="${task.done}" aria-valuemin="0" aria-valuemax="${task.total}"><span style="width:${task.done / task.total * 100}%"></span></div><p class="num">${task.done} / ${task.total} ${task.kind === 'prewarm' ? '张已就绪' : '项'}</p>` : `<p>${task.state === 'failed' ? 'README.txt 读取失败 · 文件正在被占用' : task.kind === 'delete' ? task.summary : task.state === 'cancelled' ? `停止于 ${task.done} / ${task.total}，已完成部分保留` : `${task.done} / ${task.total} · 已完成`}</p>`}
      <div class="task-controls">${active ? `${task.state === 'running' ? `<button class="btn quiet" data-action="task-pause" data-id="${task.id}">${icon('pause', 14)}暂停</button>` : task.state === 'paused' ? `<button class="btn quiet" data-action="task-resume" data-id="${task.id}">${icon('play', 14)}继续</button>` : ''}<button class="btn quiet" data-action="task-cancel" data-id="${task.id}" ${['pausing', 'cancelling'].includes(task.state) ? 'disabled' : ''}>${icon('x', 14)}取消</button>` : task.kind === 'delete' ? `<button class="btn quiet" data-action="show-report">${icon('list-checks', 14)}逐项结果</button>` : task.state === 'failed' ? `<button class="btn quiet" data-action="task-retry" data-id="${task.id}">${icon('rotate-cw', 14)}重试</button>` : ''}</div></article>`;
  }

  function infoList(item, isImage) {
    const props = isImage ? [['尺寸', `${item.width} × ${item.height}`], ['大小', bytes(item.bytes)], ['格式', 'JPEG'], ['图包', pkg()?.name || ''], ['相对位置', item.rel]] : [['图片数', `${item.count} 张`], ['文件夹', group().name], ['相对位置', item.rel]];
    return `<dl class="info-list">${props.map(([name, value]) => `<div><dt>${name}</dt><dd class="${name === '相对位置' ? 'path' : ''}">${esc(value)}</dd></div>`).join('')}</dl>`;
  }

  function renderPanel() {
    const panel = $('#panel');
    if (!state.panel) { if (panel.open) panel.close(); return; }
    const type = state.panel;
    panel.classList.toggle('info-panel', type === 'info');
    const focusAction = panel.contains(document.activeElement) ? document.activeElement.dataset.action : null;
    const focusId = document.activeElement?.dataset.id;
    const tasks = state.tasks.filter((task) => state.taskFilter === 'all' || task.state === state.taskFilter);
    const focusedId = state.selected.size === 1 ? [...state.selected][0] : state.inspectedId;
    const focusedImage = state.pkgId ? images().find((entry) => entry.id === focusedId) : null;
    const focusedPackage = !state.pkgId ? packages().find((entry) => entry.id === focusedId) : null;
    const item = focusedImage || focusedPackage || (state.pkgId ? pkg() : null);
    const isImage = Boolean(focusedImage);
    panel.setAttribute('aria-label', type === 'tasks' ? '后台任务' : '信息面板');
    panel.innerHTML = `<header class="panel-head"><h2>${type === 'tasks' ? '后台任务' : isImage ? '图片信息' : item ? '图包信息' : '文件夹信息'}</h2>${ib('close-panel', 'x', '关闭面板')}</header><div class="panel-body">${type === 'tasks' ? `<label class="task-filter">显示<select data-change="task-filter" aria-label="筛选任务"><option value="all" ${state.taskFilter === 'all' ? 'selected' : ''}>全部任务</option>${['running', 'paused', 'failed', 'completed', 'cancelled'].map((id) => `<option value="${id}" ${state.taskFilter === id ? 'selected' : ''}>${labels[id]}</option>`).join('')}</select></label>${tasks.map(taskRow).join('') || '<div class="empty"><h2>没有符合条件的任务</h2></div>'}<details class="routine"><summary>自动维护 · 3 项已完成</summary><p>目录对账 2 次 · 缓存整理 1 次</p></details>` : item ? `<img class="info-preview" src="${isImage ? item.src : item.photo.src}" alt="${item.name}"><h3 class="info-name">${esc(item.name)}</h3>${infoList(item, isImage)}` : `<h3 class="info-name">${group().name}</h3><dl class="info-list"><div><dt>图包</dt><dd>${packages().length} 个</dd></div><div><dt>图片</dt><dd>${packages().reduce((sum, entry) => sum + entry.count, 0)} 张</dd></div><div><dt>状态</dt><dd>${markLabels[group().state]}</dd></div><div><dt>相对位置</dt><dd>${group().name}</dd></div></dl>`}</div><footer class="panel-foot">${type === 'tasks' ? `<div>缩略图缓存 · 1.8 / 12 GiB</div><button class="text-btn" data-action="cache-clean">${icon('hard-drive', 14)}整理缓存</button>` : '<span>位置属于当前图库</span>'}</footer>`;
    paintIcons(panel);
    const nextModality = matchMedia('(max-width:860px)').matches;
    if (panel.open && panelModality !== nextModality) panel.close();
    if (!panel.open) { nextModality ? panel.showModal() : panel.show(); panelModality = nextModality; }
    if (focusAction) $(`[data-action="${focusAction}"]${focusId ? `[data-id="${focusId}"]` : ''}`, panel)?.focus();
  }

  function renderViewer() {
    const viewer = $('#viewer');
    if (state.image === null || !currentImage()) {
      if (viewer.open) viewer.close();
      if (viewerWasOpen) {
        state.focusTarget = state.resume.pkgId === state.pkgId ? `${state.pkgId}-${state.resume.index + 1}` : state.resume.pkgId;
        const target = $(`[data-tile-id="${state.focusTarget}"] .tile-main`);
        target?.focus({ preventScroll: true });
        target?.scrollIntoView({ block: 'nearest' });
        state.focusTarget = null;
      }
      viewerWasOpen = false;
      return;
    }
    if ($('#panel').open) { state.panel = null; $('#panel').close(); }
    const item = currentImage();
    const list = images();
    const previousFocus = viewer.contains(document.activeElement) ? document.activeElement.dataset.action : null;
    const previousIndex = document.activeElement?.dataset.index;
    viewer.innerHTML = `<header class="viewer-top">${ib('close-viewer', 'arrow-left', '返回图片墙')}<div class="viewer-location"><strong class="truncate">${esc(item.name)}</strong><span class="truncate">${group().name} / ${pkg().name}</span></div><span class="viewer-counter">${state.image + 1} / ${list.length}</span><button class="icon-btn viewer-info-toggle ${state.viewerInfo ? 'active' : ''}" data-action="viewer-info" aria-label="图片信息" data-tip="图片信息" aria-expanded="${state.viewerInfo}">${icon('info')}</button>${ib('viewer-more', 'ellipsis', '图片操作', 'aria-haspopup="menu"')}${ib('close-viewer', 'x', '关闭查看器')}</header>
      <div class="viewer-stage"><div class="viewer-canvas ${state.zoom !== null ? 'zoomed' : ''}" data-pan="true"><img class="viewer-image ${state.zoom !== null ? 'zoomed' : ''}" src="${item.src}" alt="${item.name}" draggable="false" width="${item.width}" height="${item.height}" ${state.zoom !== null ? `style="width:${item.width * state.zoom / 100}px;height:${item.height * state.zoom / 100}px;transform:translate(${state.pan.x}px,${state.pan.y}px)"` : `style="max-width:${item.width}px;max-height:${item.height}px"`}>
        <button class="viewer-nav prev" data-action="previous" aria-label="上一张" ${state.image === 0 ? 'disabled' : ''}>${icon('chevron-left', 24)}</button><button class="viewer-nav next" data-action="next" aria-label="下一张" ${state.image === list.length - 1 ? 'disabled' : ''}>${icon('chevron-right', 24)}</button>${state.image === list.length - 1 ? '<span class="boundary" role="status">已到当前图包末尾</span>' : ''}</div>
        ${state.viewerInfo ? `<aside class="viewer-info"><div class="side-label"><h2>图片信息</h2>${ib('viewer-info', 'x', '关闭图片信息')}</div>${infoList(item, true)}</aside>` : ''}
      </div><footer class="viewer-bottom"><div class="viewer-tools"><span class="image-dimensions">${item.width} × ${item.height} · ${bytes(item.bytes)}</span><span class="spacer"></span>${ib('zoom-fit', 'maximize', '适应窗口')}${ib('zoom-out', 'minus', '缩小')}<span class="zoom-value">${state.zoom === null ? '适应' : `${state.zoom}%`}</span>${ib('zoom-in', 'plus', '放大')}${ib('zoom-native', 'scan', '原始尺寸')}</div><nav class="filmstrip" aria-label="当前图包的图片">${list.map((entry, index) => `<button data-action="filmstrip" data-index="${index}" class="${index === state.image ? 'active' : ''}" aria-label="第 ${index + 1} 张，${entry.name}" ${index === state.image ? 'aria-current="true"' : ''}><img src="${entry.src}" alt="" width="78" height="56" loading="lazy"></button>`).join('')}</nav></footer>`;
    paintIcons(viewer);
    if (!viewer.open) viewer.showModal();
    viewerWasOpen = true;
    if (previousFocus) $(`[data-action="${previousFocus}"]${previousIndex !== undefined ? `[data-index="${previousIndex}"]` : ''}`, viewer)?.focus({ preventScroll: true });
    $('.filmstrip .active', viewer)?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  }

  function closeMenu() {
    state.menu = null;
    for (const button of document.querySelectorAll('button[aria-haspopup="menu"]')) button.setAttribute('aria-expanded', 'false');
    $('#menu-root').innerHTML = '';
    const viewerMenu = $('#viewer .popover');
    viewerMenu?.remove();
  }

  function showMenu(type) {
    if (state.menu === type) { closeMenu(); return; }
    closeMenu();
    state.menu = type;
    const action = type === 'appearance' ? 'appearance' : type === 'viewer' ? 'viewer-more' : 'more';
    $(`[data-action="${action}"]`)?.setAttribute('aria-expanded', 'true');
    const appearance = type === 'appearance';
    const markup = appearance ? `<span class="popover-label">外观</span>${[['system', 'monitor', '跟随系统'], ['light', 'sun', '浅色'], ['dark', 'moon', '深色']].map(([id, symbol, label]) => `<button role="menuitemradio" aria-checked="${state.theme === id}" data-action="theme" data-id="${id}">${icon(symbol, 16)}<span>${label}</span>${state.theme === id ? icon('check', 14) : ''}</button>`).join('')}` : type === 'viewer' ? `<button role="menuitem" data-action="viewer-info">${icon('info', 16)}<span>图片信息</span></button><hr><button role="menuitem" class="danger" data-action="delete-current">${icon('trash-2', 16)}<span>删除这张图片…</span></button>` : `<button role="menuitem" data-action="rescan">${icon('refresh-cw', 16)}<span>重新扫描此文件夹</span></button><button role="menuitem" data-action="prewarm">${icon('images', 16)}<span>预先生成缩略图</span></button><hr><button role="menuitem" data-action="info">${icon('info', 16)}<span>查看信息</span></button><button role="menuitem" class="danger" data-action="delete-scope">${icon('trash-2', 16)}<span>删除${state.pkgId ? '当前图包' : '整个文件夹'}…</span></button>`;
    const menu = `<div class="popover" role="menu" aria-label="${appearance ? '外观' : '更多操作'}">${markup}</div>`;
    if (type === 'viewer') $('#viewer').insertAdjacentHTML('beforeend', menu);
    else $('#menu-root').innerHTML = menu;
    paintIcons();
    const root = type === 'viewer' ? $('#viewer .popover') : $('#menu-root');
    $('button', root)?.focus();
  }

  function openModal(type) {
    closeMenu();
    state.modal = type;
    state.permanent = false;
    state.confirmed = false;
    renderModal();
    if (!$('#modal').open) $('#modal').showModal();
  }

  function modalShell(title, body, footer) {
    return `<header class="modal-head"><h2 id="modal-title">${title}</h2>${ib('close-modal', 'x', '关闭对话框')}</header><div class="modal-body">${body}</div><footer class="modal-foot">${footer}</footer>`;
  }

  function renderModal() {
    const modal = $('#modal');
    if (state.modal === 'add') {
      modal.innerHTML = modalShell('添加图库', '<p>图库名称和位置</p><label class="field">名称<input id="library-name" autocomplete="off" value="旅行归档" maxlength="80"></label><label class="field">文件夹路径<input id="library-path" spellcheck="false" value="F:\\旅行归档"></label>', '<button class="btn quiet" data-action="close-modal">取消</button><button class="btn primary" data-action="add-confirm">添加图库</button>');
    } else if (state.modal === 'delete') {
      const targets = state.deleteTargets;
      modal.innerHTML = modalShell(state.permanent ? `永久删除 ${targets.length} 项？` : `将 ${targets.length} 项移到回收站？`, `<p>${targets.some((item) => item.kind !== 'image') ? '包含图包或文件夹内的全部文件，包括非图片文件。' : '从当前图库中移除所选图片。'}</p><ul class="delete-targets">${targets.map((item) => `<li>${icon(item.kind === 'image' ? 'image' : 'folder', 16)}<span>${esc(item.name)}</span></li>`).join('')}</ul><label class="delete-mode"><input type="checkbox" data-change="permanent" ${state.permanent ? 'checked' : ''}><div><strong>永久删除</strong><span>跳过回收站，无法通过回收站恢复。</span></div></label>${state.permanent ? `<div class="permanent-confirm"><label><input type="checkbox" data-change="confirm-permanent" ${state.confirmed ? 'checked' : ''}>我确认永久删除这 ${targets.length} 项</label></div>` : ''}`, `<button class="btn quiet" data-action="close-modal">取消</button><button class="btn danger ${state.permanent ? 'solid' : ''}" data-action="delete-confirm" ${state.permanent && !state.confirmed ? 'disabled' : ''}>${icon('trash-2', 16)}${state.permanent ? '永久删除' : '移到回收站'}</button>`);
    } else if (state.modal === 'report') {
      const failed = state.report.filter((item) => item.failed);
      modal.innerHTML = modalShell('删除结果', `<div class="report-summary">${icon(failed.length ? 'circle-alert' : 'circle-check', 24)}<span>${state.report.length - failed.length} 项完成${failed.length ? `，${failed.length} 项失败` : ''}</span></div><ul class="report-items">${state.report.map((item) => `<li class="${item.failed ? 'failed' : ''}">${icon(item.failed ? 'circle-alert' : 'circle-check', 18)}<div><div>${esc(item.name)}</div><div class="result">${item.failed ? '无法移到回收站：文件正在被占用' : item.permanent ? '已永久删除' : '已移到回收站'}</div></div></li>`).join('')}</ul>`, `${failed.length ? '<button class="btn" data-action="retry-delete">只重试失败项</button>' : ''}<button class="btn primary" data-action="close-modal">完成</button>`);
    } else if (state.modal === 'audit') {
      modal.innerHTML = modalShell('空壳图包的文件', '<p>旅行影像 / 旧版 / 待补齐</p><ul class="delete-targets"><li><i data-lucide="file-text"></i><span>说明.txt · 1.2 KB</span></li></ul>', '<button class="btn" data-action="close-modal">关闭</button>');
    }
    paintIcons(modal);
  }

  function requestDelete(targets) {
    if (!targets.length) return;
    state.deleteTargets = targets;
    openModal('delete');
  }

  function deleteTarget(item, kind) {
    return { id: item.id, name: item.rel || item.name, kind };
  }

  function performDelete(retry = false) {
    if (state.permanent && !state.confirmed && !retry) return;
    const viewingId = state.image !== null ? currentImage()?.id : null;
    const targets = retry ? state.report.filter((item) => item.failed) : state.deleteTargets;
    const results = targets.map((item, index) => ({ ...item, permanent: state.permanent,
      failed: !retry && scenario === 'mixed' && index === targets.length - 1 }));
    for (const item of results) if (!item.failed) {
      state.removed.add(item.id);
      state.selected.delete(item.id);
      if (item.kind === 'group') for (const entry of data.packages(item.id)) state.removed.add(entry.id);
    }
    state.report = retry ? state.report.map((item) => results.find((result) => result.id === item.id) || item) : results;
    const failed = state.report.filter((item) => item.failed).length;
    state.tasks = state.tasks.filter((task) => task.id !== 'delete');
    state.tasks.unshift({ id: 'delete', name: '删除所选项目', target: group().name, kind: 'delete', state: 'completed', done: state.report.length - failed, total: state.report.length, summary: `${state.report.length - failed} 项完成${failed ? `，${failed} 项失败` : ''}` });
    if (viewingId && state.removed.has(viewingId)) { state.image = null; history.replaceState(null, '', href({ image: null })); }
    if (state.pkgId && state.removed.has(state.pkgId)) { state.pkgId = null; history.replaceState(null, '', href({ pkgId: null })); }
    state.selection = failed > 0 && state.selected.size > 0;
    state.modal = 'report';
    state.verified = false;
    render();
    renderModal();
  }

  function startTask(kind, name) {
    const task = { id: `${kind}-${Date.now()}`, kind, name, target: group().name, state: 'running', done: 0, total: 96 };
    state.tasks.unshift(task);
    state.panel = 'tasks';
    closeMenu();
    render();
    toast(`已提交${name}任务`);
    return task;
  }

  function verify() {
    if (state.checking || state.offline) { if (state.offline) toast('图库离线，无法开始核验', 'unplug'); return; }
    state.verified = false;
    state.checking = true;
    const task = { id: `verify-${Date.now()}`, name: '整包核验', target: `${group().name} · 左右图包`, kind: 'compare', state: 'running', done: 7, total: 9 };
    state.tasks.unshift(task);
    render();
    setTimeout(() => {
      if (task.state !== 'running') return;
      task.state = 'completed';
      task.done = 9;
      state.checking = false;
      state.verified = true;
      state.stale = false;
      render();
      toast('整包核验完成');
    }, 850);
  }

  const actions = {
    navigation: () => { $('#navigation').showModal(); },
    'close-nav': () => $('#navigation').close(),
    folder: (button) => go({ groupId: button.dataset.id, pkgId: null, mode: 'browse', image: null }),
    'library-home': () => go({ pkgId: null, mode: 'browse', image: null }),
    'group-home': () => go({ pkgId: null, mode: 'browse', image: null }),
    browse: () => go({ mode: 'browse', image: null }),
    organize: () => go({ pkgId: null, mode: 'organize', image: null }),
    'org-tab': (button) => go({ mode: 'organize', pkgId: null, tab: button.dataset.id, image: null }),
    'open-package': (button) => {
      if (state.selection) { toggleSelection(button.dataset.id); return; }
      go({ pkgId: button.dataset.id, image: null });
    },
    'open-image': (button) => {
      if (state.selection) { toggleSelection(button.dataset.id); return; }
      go({ image: Number(button.dataset.index) });
    },
    'sample-open': (button) => go({ pkgId: button.dataset.id, mode: 'browse', image: Number(button.dataset.index) }),
    resume: () => go({ groupId: state.resume.groupId, pkgId: state.resume.pkgId, mode: 'browse', image: state.resume.index }),
    tasks: () => { state.panel = state.panel === 'tasks' ? null : 'tasks'; render(); },
    info: () => { state.panel = state.panel === 'info' ? null : 'info'; closeMenu(); render(); },
    'close-panel': () => { state.panel = null; render(); },
    appearance: () => showMenu('appearance'),
    theme: (button) => { state.theme = button.dataset.id; setTheme(); closeMenu(); render(); },
    more: () => showMenu('more'),
    'viewer-more': () => showMenu('viewer'),
    fit: (button) => { state.fill = button.dataset.value === 'cover'; render(); },
    'selection-start': () => { state.selection = true; render(); },
    'selection-done': () => { state.selection = false; state.selected.clear(); render(); },
    'select-page': () => { (state.pkgId ? images() : packages()).forEach((item) => state.selected.add(item.id)); render(); },
    'delete-selected': () => requestDelete((state.pkgId ? images() : packages()).filter((item) => state.selected.has(item.id)).map((item) => deleteTarget(item, state.pkgId ? 'image' : 'package'))),
    'delete-current': () => requestDelete([deleteTarget(currentImage(), 'image')]),
    'delete-verified': (button) => { const item = packages().find((entry) => entry.id === button.dataset.id); if (state.verified && !state.stale && !state.unique && item) requestDelete([deleteTarget(item, 'package')]); },
    'delete-scope': () => requestDelete([state.pkgId ? deleteTarget(pkg(), 'package') : { id: state.groupId, name: group().name, kind: 'group' }]),
    'delete-confirm': () => performDelete(),
    'retry-delete': () => performDelete(true),
    'show-report': () => openModal('report'),
    'close-modal': () => { state.modal = null; $('#modal').close(); },
    'add-library': () => { if ($('#navigation').open) $('#navigation').close(); openModal('add'); },
    'add-confirm': () => {
      const name = $('#library-name').value.trim();
      const path = $('#library-path').value.trim();
      if (!name || !path) { toast('请填写图库名称和文件夹路径', 'circle-alert'); return; }
      $('#modal').close(); state.modal = null;
      startTask('scan', '扫描新图库');
      toast(`已添加“${name}”，等待索引`);
    },
    'close-viewer': () => go({ image: null }),
    next: () => { if (state.image < images().length - 1) go({ image: state.image + 1 }); },
    previous: () => { if (state.image > 0) go({ image: state.image - 1 }); },
    filmstrip: (button) => go({ image: Number(button.dataset.index) }),
    'viewer-info': () => { closeMenu(); state.viewerInfo = !state.viewerInfo; renderViewer(); },
    'zoom-fit': () => { state.zoom = null; state.pan = { x: 0, y: 0 }; renderViewer(); },
    'zoom-native': () => { state.zoom = 100; state.pan = { x: 0, y: 0 }; renderViewer(); },
    'zoom-in': () => { state.zoom = Math.min(300, (state.zoom ?? 75) + 25); renderViewer(); },
    'zoom-out': () => { state.zoom = Math.max(25, (state.zoom ?? 100) - 25); renderViewer(); },
    'retry-image': () => { state.bad = false; render(); toast('已重新读取'); },
    reconnect: () => { state.offline = false; render(); toast('图库已重新连接'); },
    rescan: () => state.offline ? toast('图库离线，无法扫描', 'unplug') : startTask('scan', '重新扫描'),
    prewarm: () => state.offline ? toast('图库离线，无法生成封面', 'unplug') : startTask('prewarm', '预先生成缩略图'),
    'cache-clean': () => startTask('collect', '整理缩略图缓存'),
    verify,
    swap: () => { state.pair.reverse(); state.verified = false; render(); },
    'compare-pair': (button) => { state.pair = [button.dataset.left, button.dataset.right]; state.verified = false; go({ mode: 'organize', tab: 'compare', pkgId: null, image: null }); },
    analyze: () => state.offline ? toast('图库离线，无法分析', 'unplug') : startTask('analyze', '相似图包分析'),
    audit: () => startTask('audit', '清理检查'),
    'audit-detail': () => openModal('audit'),
    shuffle: () => { state.sampleOffset = (state.sampleOffset + 3) % 96; render(); toast('已换一批图片'); },
    'task-pause': (button) => {
      const task = state.tasks.find((item) => item.id === button.dataset.id);
      task.state = 'pausing'; render();
      setTimeout(() => { if (task.state === 'pausing') { task.state = 'paused'; render(); } }, 350);
    },
    'task-resume': (button) => { state.tasks.find((item) => item.id === button.dataset.id).state = 'running'; render(); },
    'task-cancel': (button) => {
      const task = state.tasks.find((item) => item.id === button.dataset.id);
      task.state = 'cancelling'; render();
      setTimeout(() => { task.state = 'cancelled'; if (task.kind === 'compare') state.checking = false; render(); }, 350);
    },
    'task-retry': (button) => { const task = state.tasks.find((item) => item.id === button.dataset.id); task.state = 'running'; render(); },
  };

  function toggleSelection(id) {
    state.selection = true;
    if (state.selected.has(id)) state.selected.delete(id); else state.selected.add(id);
    render();
  }

  document.addEventListener('click', (event) => {
    if (event.target.closest('.skip-link')) { event.preventDefault(); $('#content').focus(); return; }
    const button = event.target.closest('button[data-action]');
    if (button && !button.disabled) {
      actions[button.dataset.action]?.(button);
      if (!['appearance', 'more', 'viewer-more'].includes(button.dataset.action)) closeMenu();
    } else if (!event.target.closest('.popover')) closeMenu();
  });

  document.addEventListener('change', (event) => {
    const field = event.target;
    switch (field.dataset.change) {
      case 'library': state.library = field.value; state.offline = field.value === 'disk'; render(); break;
      case 'filter': state.filter = field.value; render(); break;
      case 'category': state.category = field.value; render(); break;
      case 'mark': group().state = field.value; render(); toast(`${group().name} · ${markLabels[field.value]}`); break;
      case 'task-filter': state.taskFilter = field.value; renderPanel(); break;
      case 'select': {
        const list = state.pkgId ? images() : packages();
        const index = list.findIndex((item) => item.id === field.dataset.id);
        state.selection = true;
        state.inspectedId = field.dataset.id;
        if (field.checked) state.selected.add(field.dataset.id); else state.selected.delete(field.dataset.id);
        lastRangeIndex = index;
        render();
        $(`input[data-id="${field.dataset.id}"]`)?.focus({ preventScroll: true });
        break;
      }
      case 'pair-left': state.pair[0] = field.value; state.verified = false; render(); break;
      case 'pair-right': state.pair[1] = field.value; state.verified = false; render(); break;
      case 'sample-count': state.sampleCount = Number(field.value); render(); break;
      case 'permanent': state.permanent = field.checked; state.confirmed = false; renderModal(); $('[data-change="permanent"]')?.focus(); break;
      case 'confirm-permanent': state.confirmed = field.checked; $('[data-action="delete-confirm"]', $('#modal')).disabled = !field.checked; break;
    }
  });

  document.addEventListener('focusin', (event) => {
    const tile = event.target.closest('[data-tile-id]');
    if (!tile) return;
    state.inspectedId = tile.dataset.tileId;
    if (state.panel === 'info') renderPanel();
  });

  document.addEventListener('input', (event) => {
    if (event.target.dataset.change === 'tile-size') {
      state.size = Number(event.target.value);
      const grid = $('.grid', $('#app'));
      if (grid) grid.style.setProperty('--tile-min', `${state.size}px`);
    }
  });

  document.addEventListener('keydown', (event) => {
    const menu = $('.popover');
    if (menu && ['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
      event.preventDefault();
      const buttons = [...menu.querySelectorAll('button')];
      const i = buttons.indexOf(document.activeElement);
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1 : (i + (event.key === 'ArrowDown' ? 1 : -1) + buttons.length) % buttons.length;
      buttons[next].focus();
      return;
    }
    if (event.key === 'Escape' && menu) {
      event.preventDefault();
      const action = state.menu === 'appearance' ? 'appearance' : state.menu === 'viewer' ? 'viewer-more' : 'more';
      closeMenu();
      $(`[data-action="${action}"]`)?.focus();
      return;
    }
    if ($('#modal').open || ['INPUT', 'SELECT', 'TEXTAREA'].includes(event.target.tagName)) return;
    if ($('#viewer').open) {
      if (event.key === 'ArrowRight') { event.preventDefault(); actions.next(); }
      if (event.key === 'ArrowLeft') { event.preventDefault(); actions.previous(); }
      if (event.key === '0') actions['zoom-fit']();
      if (event.key === '1') actions['zoom-native']();
      return;
    }
    if (state.selection && event.key === 'Escape') { event.preventDefault(); actions['selection-done'](); }
    if (state.selection && event.key === 'Delete' && state.selected.size) { event.preventDefault(); actions['delete-selected'](); }
    const tileButton = event.target.closest('.tile-main');
    if (tileButton && event.shiftKey && event.key === ' ') {
      event.preventDefault();
      const list = state.pkgId ? images() : packages();
      const index = list.findIndex((item) => item.id === tileButton.dataset.id);
      if (index < 0) return;
      state.selection = true;
      for (let i = Math.min(index, lastRangeIndex); i <= Math.max(index, lastRangeIndex); i++) state.selected.add(list[i].id);
      render();
    }
  });

  $('#viewer').addEventListener('cancel', (event) => { event.preventDefault(); closeMenu(); go({ image: null }); });
  $('#panel').addEventListener('cancel', (event) => { event.preventDefault(); state.panel = null; render(); });
  $('#modal').addEventListener('cancel', () => { state.modal = null; });
  $('#navigation').addEventListener('click', (event) => { if (event.target === $('#navigation') && event.offsetX > $('#navigation').clientWidth) $('#navigation').close(); });

  let drag = null;
  $('#viewer').addEventListener('pointerdown', (event) => {
    const canvas = event.target.closest('[data-pan]');
    if (canvas && state.zoom !== null && !event.target.closest('button')) {
      drag = { x: event.clientX, y: event.clientY, panX: state.pan.x, panY: state.pan.y };
      canvas.setPointerCapture(event.pointerId);
      canvas.classList.add('dragging');
    }
  });
  $('#viewer').addEventListener('pointermove', (event) => {
    if (!drag) return;
    const canvas = $('.viewer-canvas');
    const item = currentImage();
    const maxX = Math.max(0, (item.width * state.zoom / 100 - canvas.clientWidth) / 2);
    const maxY = Math.max(0, (item.height * state.zoom / 100 - canvas.clientHeight) / 2);
    state.pan = { x: Math.max(-maxX, Math.min(maxX, drag.panX + event.clientX - drag.x)), y: Math.max(-maxY, Math.min(maxY, drag.panY + event.clientY - drag.y)) };
    $('.viewer-image').style.transform = `translate(${state.pan.x}px,${state.pan.y}px)`;
  });
  for (const name of ['pointerup', 'pointercancel']) $('#viewer').addEventListener(name, () => { drag = null; $('.viewer-canvas')?.classList.remove('dragging'); });
  $('#viewer').addEventListener('dblclick', (event) => {
    if (event.target.closest('[data-pan]') && !event.target.closest('button')) {
      state.zoom = state.zoom === null ? 100 : null;
      state.pan = { x: 0, y: 0 };
      renderViewer();
    }
  });

  addEventListener('hashchange', readRoute);
  let resizeTimer;
  addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => render(), 120); });
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => { if (state.theme === 'system') setTheme(); });
  setTheme();
  if (!location.hash) {
    const view = query.get('view');
    const initial = view === 'organize' ? '#/g/travel/organize/compare' : view === 'images' || view === 'viewer' ? `#/g/travel/p/travel-lake${view === 'viewer' ? '/i/0' : ''}` : '#/g/travel';
    history.replaceState(null, '', initial);
  }
  if (query.get('view') === 'tasks') state.panel = 'tasks';
  readRoute();
})();
