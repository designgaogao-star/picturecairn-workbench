'use strict';
const $ = (id) => document.getElementById(id);
const apiBase = '/api/v1';
const state = { libraries: [], library: null, groups: [], group: null, package: null, context: null,
  groupOffset: 0, total: 0, mode: 'packages', pages: new Map(), loading: new Set(), epoch: 0,
  scale: 1, angle: 0, x: 0, y: 0, original: false, groupTotal: 0 };
let wallFrame = 0, catalogTimer = 0, taskTimer = 0, viewerEpoch = 0;
const icons = () => window.lucide?.createIcons();
function notice(message = '') { $('notice').textContent = message; $('notice').hidden = !message; }
async function api(path, options = {}) {
  const response = await fetch(apiBase + path, { ...options,
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) } });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(typeof error.detail === 'string' ? error.detail : error.error || `请求失败 (${response.status})`);
  }
  return response.status === 204 ? null : response.json();
}
function safely(action) { return (...args) => Promise.resolve(action(...args)).catch((e) => notice(e.message)); }
function iconButton(icon, title, action) {
  const button = document.createElement('button'); button.title = title; button.setAttribute('aria-label', title);
  const i = document.createElement('i'); i.dataset.lucide = icon; button.append(i); button.onclick = safely(action); return button;
}
const thumb = (id, edge = 400) => `${apiBase}/images/${id}/thumbnail?edge=${edge}`;
async function loadLibraries() {
  const oldRevision = state.library?.revision;
  state.libraries = (await api('/libraries')).items;
  const previous = state.library?.id || localStorage.getItem('gallery-library');
  $('libraries').replaceChildren(...state.libraries.map((lib) => new Option(lib.name, lib.id)));
  state.library = state.libraries.find((lib) => lib.id === previous) || state.libraries[0] || null;
  if (state.library) {
    $('libraries').value = state.library.id; localStorage.setItem('gallery-library', state.library.id);
    $('library-status').textContent = state.library.online ? (state.library.scan_status === 'scanning' ? '正在更新索引' : '本地图库') : '目录离线';
    await loadGroups();
    if (state.group && oldRevision !== state.library.revision && !$('wall').hidden) {
      state.epoch++; state.pages.clear(); state.loading.clear();
      await loadPage(0, state.epoch);
    }
  } else { $('groups').replaceChildren(); $('empty').hidden = false; }
}
async function loadGroups() {
  if (!state.library) return;
  const libraryId = state.library.id;
  const filter = $('mark-filter').value;
  const page = await api(`/libraries/${libraryId}/groups?offset=${state.groupOffset}&limit=100${filter ? '&state=' + filter : ''}`);
  if (state.library?.id !== libraryId) return;
  state.groups = page.items; state.groupTotal = page.total;
  $('group-count').textContent = `${page.total ? state.groupOffset + 1 : 0}–${Math.min(state.groupOffset + 100, page.total)} / ${page.total}`;
  $('group-prev').disabled = state.groupOffset === 0; $('group-next').disabled = state.groupOffset + 100 >= page.total;
  $('groups').replaceChildren(...page.items.map((group) => {
    const button = document.createElement('button'); const name = document.createElement('span'); const count = document.createElement('small');
    name.textContent = group.name; count.textContent = group.image_count.toLocaleString(); button.append(name, count);
    button.classList.toggle('active', state.group?.id === group.id); button.onclick = safely(() => openGroup(group)); return button;
  }));
  if (!state.group && page.items.length) await openGroup(page.items[0]);
}
function setMarks() { document.querySelectorAll('[data-mark]').forEach((button) => button.classList.toggle('active', button.dataset.mark === state.group?.state)); }
async function openGroup(group) {
  state.group = group; state.package = null; state.context = null; viewerEpoch++;
  $('title').textContent = group.name; $('subtitle').textContent = `${group.image_count.toLocaleString()} 张`;
  $('viewer').hidden = true; $('wall').hidden = false; $('picture').removeAttribute('src');
  setMarks(); await resetWall('packages'); await loadGroups();
}
async function resetWall(mode) {
  state.epoch++; state.mode = mode; state.pages.clear(); state.loading.clear(); state.total = 0;
  $('wall').scrollTop = 0; $('wall-space').replaceChildren(); $('wall-space').style.height = '0px';
  await loadPage(0, state.epoch); renderWall();
}
async function loadPage(page, epoch) {
  if (state.loading.has(page) || state.pages.has(page)) return;
  state.loading.add(page);
  const path = state.mode === 'packages' ? `/groups/${state.group.id}/packages` : `/packages/${state.package.id}/images`;
  try {
    const result = await api(`${path}?offset=${page * 100}&limit=100`);
    if (epoch !== state.epoch) return;
    state.total = result.total; state.pages.set(page, result.items);
    while (state.pages.size > 8) state.pages.delete(state.pages.keys().next().value);
    $('empty').hidden = result.total > 0; renderWall();
  } finally { if (epoch === state.epoch) state.loading.delete(page); }
}
function itemAt(index) { return state.pages.get(Math.floor(index / 100))?.[index % 100]; }
function renderWall() {
  if ($('wall').hidden) return;
  const wall = $('wall'), space = $('wall-space');
  const columns = Math.max(1, Math.floor((wall.clientWidth - 40) / 190));
  const width = Math.floor((wall.clientWidth - 40 - (columns - 1) * 14) / columns);
  const height = Math.round(width * 1.2) + 52, rowHeight = height + 18;
  const first = Math.max(0, Math.floor(wall.scrollTop / rowHeight) - 1) * columns;
  const last = Math.min(state.total, (Math.ceil((wall.scrollTop + wall.clientHeight) / rowHeight) + 1) * columns);
  space.style.height = `${Math.ceil(state.total / columns) * rowHeight + 18}px`;
  const fragment = document.createDocumentFragment();
  for (let index = first; index < last; index++) {
    const item = itemAt(index), button = document.createElement('button'); button.className = 'tile';
    Object.assign(button.style, { left: `${(index % columns) * (width + 14)}px`, top: `${Math.floor(index / columns) * rowHeight + 18}px`, width: `${width}px`, height: `${height}px` });
    if (item) {
      const id = state.mode === 'packages' ? item.cover_id : item.id;
      if (id) { const image = document.createElement('img'); image.src = thumb(id); image.alt = ''; image.loading = 'lazy'; image.onerror = () => { button.classList.add('failed'); image.removeAttribute('src'); }; button.append(image); }
      else { const placeholder = document.createElement('div'); placeholder.className = 'tile-placeholder'; button.append(placeholder); }
      const caption = document.createElement('div'); caption.className = 'caption'; const title = document.createElement('span'); const count = document.createElement('small');
      title.textContent = item.name || '散图'; title.title = title.textContent; count.textContent = state.mode === 'packages' ? `${item.image_count} 张` : '';
      caption.append(title, count); button.append(caption);
      button.onclick = safely(() => state.mode === 'packages' ? openPackage(item) : showImage(item.id));
    } else { safely(() => loadPage(Math.floor(index / 100), state.epoch))(); }
    fragment.append(button);
  }
  space.replaceChildren(fragment);
}
async function openPackage(packageItem) {
  state.package = packageItem; $('subtitle').textContent = packageItem.name || '散图';
  await resetWall('images');
  const review = await api(`/groups/${state.group.id}/review`);
  if (review.image_id) {
    const context = await api(`/images/${review.image_id}/context`).catch(() => null);
    if (context?.image.package_id === packageItem.id) { await showImage(review.image_id); return; }
  }
  const first = itemAt(0); if (first) await showImage(first.id);
}
function transform() { $('picture').style.transform = `translate(${state.x}px,${state.y}px) rotate(${state.angle}deg) scale(${state.scale})`; }
function fit() { state.scale = 1; state.angle = 0; state.x = state.y = 0; transform(); }
async function showImage(id) {
  const epoch = ++viewerEpoch; const context = await api(`/images/${id}/context`);
  if (epoch !== viewerEpoch) return;
  state.context = context; state.original = false; fit();
  $('wall').hidden = true; $('viewer').hidden = false; $('empty').hidden = true;
  $('image-name').textContent = context.image.name; $('image-name').title = context.image.name;
  $('previous').disabled = !context.previous_id; $('next').disabled = !context.next_id;
  const stage = $('image-stage'), longEdge = Math.max(stage.clientWidth, stage.clientHeight) * devicePixelRatio;
  const edge = [1600, 2560, 4200].find((n) => n >= longEdge) || 4200;
  const picture = $('picture'); picture.alt = context.image.name; picture.src = thumb(id, 400);
  const high = new Image(); high.onload = () => { if (viewerEpoch === epoch) picture.src = high.src; }; high.onerror = () => { if (viewerEpoch === epoch) notice('预览生成失败，原图仍可查看'); };
  high.src = context.image.animated ? `${apiBase}/images/${id}/original` : thumb(id, edge);
  if (context.image.animated === null) {
    high.onload = () => { if (viewerEpoch === epoch) { picture.src = high.src; safely(async () => { const updated = await api(`/images/${id}/context`); if (viewerEpoch === epoch && updated.image.animated) picture.src = `${apiBase}/images/${id}/original`; })(); } };
  }
  await api(`/groups/${state.group.id}/position`, { method: 'PUT', body: JSON.stringify({ image_id: id }) });
  const offset = Math.max(0, context.index - 4);
  const film = await api(`/packages/${context.image.package_id}/images?offset=${offset}&limit=9`);
  if (viewerEpoch !== epoch) return;
  $('film').replaceChildren(...film.items.map((image) => { const button = document.createElement('button'); const img = document.createElement('img'); img.src = thumb(image.id); img.alt = image.name; button.title = image.name; button.classList.toggle('active', image.id === id); button.append(img); button.onclick = safely(() => showImage(image.id)); return button; }));
}
async function launch(kind, payload = {}) {
  const task = await api('/tasks', { method: 'POST', body: JSON.stringify({ kind, ...payload }) });
  $('tasks-panel').hidden = false; await loadTasks(); return task;
}
async function loadTasks() {
  const page = await api('/tasks?limit=20');
  const names = { scan: '更新索引', prewarm: '生成封面', build: '相似索引', analyze: '相似分析', compare: '内容核验', delete: '移至回收站', migrate: '迁移旧数据', collect: '缓存整理' };
  const statuses = { queued: '等待', running: '进行中', paused: '已暂停', cancelling: '正在停止', cancelled: '已取消', completed: '完成', failed: '失败', interrupted: '已中断' };
  $('tasks').replaceChildren(...page.items.map((task) => {
    const row = document.createElement('div'); row.className = 'task-row';
    const name = document.createElement('div'); name.textContent = names[task.kind] || task.kind; const status = document.createElement('small'); status.textContent = statuses[task.state]; name.append(status);
    const body = document.createElement('div'); const text = document.createElement('small'); text.textContent = task.error || task.current || `${task.progress.toLocaleString()}${task.total ? ' / ' + task.total.toLocaleString() : ''}`; const progress = document.createElement('progress'); progress.max = task.total || Math.max(task.progress, 1); progress.value = task.progress; body.append(text, progress);
    const actions = document.createElement('div'); actions.className = 'task-actions';
    if (['queued', 'running', 'paused'].includes(task.state)) {
      const action = task.state === 'paused' ? 'resume' : 'pause';
      if (task.kind !== 'delete') actions.append(iconButton(action === 'pause' ? 'pause' : 'play', action === 'pause' ? '暂停' : '继续', () => controlTask(task.id, action)));
      actions.append(iconButton('x', '取消', () => controlTask(task.id, 'cancel')));
    }
    row.append(name, body, actions); return row;
  })); icons();
}
async function controlTask(id, action) { await api(`/tasks/${id}/control`, { method: 'POST', body: JSON.stringify({ action }) }); await loadTasks(); }
$('add-library').onclick = safely(async () => {
  if (window.galleryApp?.chooseDirectory) { const path = await window.galleryApp.chooseDirectory(); if (!path) return; $('library-path').value = path; }
  $('library-dialog').showModal();
});
$('library-cancel').onclick = () => $('library-dialog').close();
$('library-form').onsubmit = safely(async (event) => { event.preventDefault(); const lib = await api('/libraries', { method: 'POST', body: JSON.stringify({ path: $('library-path').value, name: $('library-name').value || null }) }); state.library = lib; state.group = null; state.groupOffset = 0; $('library-dialog').close(); await loadLibraries(); });
$('libraries').onchange = safely(async () => { state.library = state.libraries.find((l) => l.id === $('libraries').value); state.group = null; state.groupOffset = 0; await loadLibraries(); });
$('mark-filter').onchange = safely(async () => { state.groupOffset = 0; await loadGroups(); });
$('group-prev').onclick = safely(async () => { state.groupOffset = Math.max(0, state.groupOffset - 100); await loadGroups(); });
$('group-next').onclick = safely(async () => { state.groupOffset += 100; await loadGroups(); });
$('scan').onclick = safely(() => state.library && launch('scan', { library_id: state.library.id }));
$('job-start').onclick = safely(() => state.group && launch($('job-kind').value, { group_id: state.group.id }));
$('tasks-toggle').onclick = safely(async () => { $('tasks-panel').hidden = !$('tasks-panel').hidden; await loadTasks(); renderWall(); }); $('tasks-close').onclick = () => { $('tasks-panel').hidden = true; renderWall(); };
$('back').onclick = safely(async () => { if (!state.group) return; viewerEpoch++; state.context = null; $('picture').removeAttribute('src'); $('viewer').hidden = true; $('wall').hidden = false; state.package = null; await resetWall('packages'); });
$('resume').onclick = safely(async () => { if (!state.group) return; const review = await api(`/groups/${state.group.id}/review`); if (review.image_id) await showImage(review.image_id); });
document.querySelectorAll('[data-mark]').forEach((button) => { button.onclick = safely(async () => { if (!state.group) return; const result = await api(`/groups/${state.group.id}/review`, { method: 'PATCH', body: JSON.stringify({ state: button.dataset.mark }) }); state.group.state = result.state; setMarks(); }); });
$('previous').onclick = safely(() => state.context?.previous_id && showImage(state.context.previous_id)); $('next').onclick = safely(() => state.context?.next_id && showImage(state.context.next_id));
$('zoom-in').onclick = () => { state.scale = Math.min(8, state.scale * 1.25); transform(); }; $('zoom-out').onclick = () => { state.scale = Math.max(1, state.scale / 1.25); transform(); }; $('fit').onclick = fit; $('rotate').onclick = () => { state.angle = (state.angle + 90) % 360; transform(); };
$('fullscreen').onclick = safely(() => document.fullscreenElement ? document.exitFullscreen() : $('viewer').requestFullscreen());
$('original').onclick = () => { if (state.context) { state.original = true; $('picture').src = `${apiBase}/images/${state.context.image.id}/original`; } };
$('remove-image').onclick = safely(async () => { if (!state.context || !confirm(`将“${state.context.image.name}”移至回收站？`)) return; const { image, next_id, previous_id } = state.context; const task = await api('/operations/delete', { method: 'POST', body: JSON.stringify({ targets: [{ kind: 'image', id: image.id }] }) }); $('tasks-panel').hidden = false; await loadTasks(); const poll = setInterval(safely(async () => { const result = await api(`/tasks/${task.id}`); if (['completed', 'failed', 'cancelled'].includes(result.state)) { clearInterval(poll); if (result.result?.failed || result.state !== 'completed') notice('删除未完成，请查看任务记录'); else if (next_id || previous_id) await showImage(next_id || previous_id); else $('back').click(); } }), 300); });
let dragging = null;
$('image-stage').onpointerdown = (e) => { if (state.scale <= 1) return; dragging = { x: e.clientX - state.x, y: e.clientY - state.y }; e.currentTarget.setPointerCapture(e.pointerId); };
$('image-stage').onpointermove = (e) => { if (dragging) { state.x = e.clientX - dragging.x; state.y = e.clientY - dragging.y; transform(); } };
$('image-stage').onpointerup = () => { dragging = null; };
$('image-stage').onwheel = (e) => { if (state.scale > 1) { e.preventDefault(); state.x -= e.deltaX; state.y -= e.deltaY; transform(); } };
document.onkeydown = (event) => { if (event.repeat || $('library-dialog').open || ['INPUT', 'SELECT', 'TEXTAREA'].includes(event.target.tagName)) return; if (event.key === 'ArrowRight') $('next').click(); if (event.key === 'ArrowLeft') $('previous').click(); if (event.key === 'Escape' && !document.fullscreenElement) $('back').click(); };
$('wall').onscroll = () => { cancelAnimationFrame(wallFrame); wallFrame = requestAnimationFrame(renderWall); };
new ResizeObserver(() => renderWall()).observe($('wall'));
const events = new EventSource(apiBase + '/events');
events.addEventListener('catalog', () => { clearTimeout(catalogTimer); catalogTimer = setTimeout(safely(loadLibraries), 750); });
events.addEventListener('task', () => { clearTimeout(taskTimer); taskTimer = setTimeout(safely(loadTasks), 250); });
const reloadSnapshots = safely(async () => { await loadLibraries(); await loadTasks(); });
events.addEventListener('snapshot', reloadSnapshots);
events.addEventListener('reset', reloadSnapshots);
events.onerror = () => notice('图库服务连接中断'); events.onopen = () => notice();
icons();
