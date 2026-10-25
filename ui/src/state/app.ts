import { batch, computed, effect, signal } from '@preact/signals';
import {
  client, describeError, isAbort, isActive, readonly, rememberCovers, rememberImages, statusOf,
  type DeleteTarget, type Group, type ImageItem, type JobBody, type Library, type Mark, type Package, type Review, type Task,
} from '../api';
import { ListRegistry, Lru, PagedList } from '../lib/paged';
import { navigate, route } from '../lib/router';

// ---------------------------------------------------------------- notices

export interface Toast { id: number; tone: 'info' | 'error' | 'success'; text: string; action?: { label: string; run: () => void } }
export const toasts = signal<Toast[]>([]);
let toastId = 0;
export function toast(text: string, tone: Toast['tone'] = 'info', action?: Toast['action'], ms = 5000) {
  const id = ++toastId;
  // A repeated notice replaces the earlier copy instead of stacking.
  toasts.value = [...toasts.value.filter((item) => item.text !== text || item.tone !== tone).slice(-3), { id, tone, text, action }];
  if (ms > 0) setTimeout(() => dismissToast(id), ms);
}
export function dismissToast(id: number) { toasts.value = toasts.value.filter((item) => item.id !== id); }
export function reportError(error: unknown, prefix = '') {
  if (isAbort(error)) return;
  toast(prefix + describeError(error), 'error');
}

// ---------------------------------------------------------------- connection

export type Connection = 'connecting' | 'online' | 'reconnecting' | 'offline';
export const connection = signal<Connection>('connecting');
/** Bumped after a reconnect so failed previews try again. */
export const mediaEpoch = signal(0);

// ---------------------------------------------------------------- libraries

export const libraries = signal<Library[]>([]);
export const librariesLoaded = signal(false);
export const librariesError = signal<string | null>(null);
export const currentLibrary = computed(() => libraries.value.find((lib) => lib.id === route.value.library) || null);
let librariesController: AbortController | null = null;

export async function loadLibraries(invalidate = true) {
  librariesController?.abort();
  const controller = librariesController = new AbortController();
  // Libraries this read can judge: already listed, with a loaded task list showing no live scan for them.
  const settled = tasksLoaded.value ? new Set(libraries.value.filter((lib) => !liveScan(lib.id)).map((lib) => lib.id)) : null;
  try {
    const items: Library[] = [];
    for (let offset = 0; ; offset += 500) {
      const page = await client.request('get', '/api/v1/libraries', {
        params: { query: { offset, limit: 500 } }, signal: controller.signal,
      });
      items.push(...page.items);
      if (items.length >= page.total || !page.items.length) break;
    }
    if (controller.signal.aborted) return;
    const before = new Map(libraries.value.map((lib) => [lib.id, lib.revision]));
    const stale = new Set(items.filter((lib) => (lib.scan_status === 'scanning' || lib.scan_status === 'pending')
      && settled?.has(lib.id) && !liveScan(lib.id)).map((lib) => lib.id));
    batch(() => { libraries.value = items; staleScans.value = stale; librariesLoaded.value = true; librariesError.value = null; });
    for (const lib of items) {
      const previous = before.get(lib.id);
      if (invalidate && previous !== undefined && previous !== lib.revision) invalidateLibrary(lib.id);
    }
    const current = route.value.library;
    if ((!current || !items.some((lib) => lib.id === current)) && items.length) {
      const remembered = localStorage.getItem('gt.library');
      const target = items.find((lib) => lib.id === remembered) || items[0];
      navigate({ library: target.id }, { replace: true });
    } else if (current && !items.length) {
      navigate({}, { replace: true });
    }
  } catch (error) {
    if (!isAbort(error)) librariesError.value = describeError(error);
  }
}

export async function addLibrary(path: string, name: string | null) {
  const library = await client.request('post', '/api/v1/libraries', { body: { path, name } });
  await loadTasks();
  await loadLibraries();
  navigate({ library: library.id });
  toast(`已添加“${library.name}”，正在后台建立索引`, 'success');
  return library;
}

export async function renameLibrary(id: string, name: string) {
  const library = await client.request('patch', '/api/v1/libraries/{library_id}', {
    params: { path: { library_id: id } }, body: { name },
  });
  libraries.value = libraries.value.map((item) => item.id === id ? library : item);
  await loadLibraries();
  toast(`图库已改名为“${library.name}”`, 'success');
}

export async function reconnectLibrary(id: string, path: string) {
  const task = await client.request('post', '/api/v1/libraries/{library_id}/reconnect', {
    params: { path: { library_id: id } }, body: { path },
  });
  await loadTasks();
  await loadLibraries();
  mediaEpoch.value++;
  toast('目录已连接，对账任务已受理，请在后台任务中查看结果', 'info', {
    label: '查看任务', run: () => { taskDrawer.value = true; },
  });
  return task;
}

export async function removeLibrary(id: string) {
  await client.request('delete', '/api/v1/libraries/{library_id}', { params: { path: { library_id: id } } });
  batch(() => {
    libraries.value = libraries.value.filter((item) => item.id !== id);
    if (route.value.library === id) navigate({ library: libraries.value[0]?.id }, { replace: true });
  });
  invalidateLibrary(id);
  await loadLibraries();
  toast('已移出管理，图片和浏览记录已保留', 'success');
}

// ---------------------------------------------------------------- lists

export const lists = new ListRegistry(10);
export interface GroupFilter { state: Mark | ''; category: '' | 'R16' | 'R18' | '非R18' | '其他' }
export const groupFilter = signal<GroupFilter>(JSON.parse(localStorage.getItem('gt.groupFilter') || 'null') || { state: '', category: '' });

export function groupsList(libraryId: string, filter: GroupFilter): PagedList<Group> {
  const key = `groups:${libraryId}:${filter.state}:${filter.category}`;
  return lists.get(key, () => new PagedList<Group>(key, async (offset, limit, signal) => {
    const page = await client.request('get', '/api/v1/libraries/{library_id}/groups', {
      params: { path: { library_id: libraryId }, query: { offset, limit, state: filter.state || undefined, category: filter.category || undefined } }, signal,
    });
    rememberGroups(page.items);
    return page;
  }, 100, 6));
}

export function packagesList(groupId: string): PagedList<Package> {
  const key = `packages:${groupId}`;
  return lists.get(key, () => new PagedList<Package>(key, async (offset, limit, signal) => {
    const page = await client.request('get', '/api/v1/groups/{group_id}/packages', {
      params: { path: { group_id: groupId }, query: { offset, limit } }, signal,
    });
    rememberPackages(page.items);
    return page;
  }));
}

export function imagesList(packageId: string): PagedList<ImageItem> {
  const key = `images:${packageId}`;
  return lists.get(key, () => new PagedList<ImageItem>(key, async (offset, limit, signal) => {
    const page = await client.request('get', '/api/v1/packages/{package_id}/images', {
    params: { path: { package_id: packageId }, query: { offset, limit } }, signal,
    });
    rememberImages(page.items);
    return page;
  }));
}

/** The image at `index` of a package: an already cached list page, else a one-item request. */
export async function imageAt(packageId: string, index: number, signal?: AbortSignal): Promise<ImageItem | null> {
  if (index < 0) return null;
  const cached = lists.peek<ImageItem>(`images:${packageId}`)?.item(index);
  if (cached) return cached;
  const page = await client.request('get', '/api/v1/packages/{package_id}/images', {
    params: { path: { package_id: packageId }, query: { offset: index, limit: 1 } }, signal,
  });
  rememberImages(page.items);
  return page.items[0] ?? null;
}

/** Library revision changed: every visible list of that library refetches its window. */
export function invalidateLibrary(libraryId: string) {
  invalidateCatalog(libraryId);
}

export function invalidateCatalog(libraryId: string, groupIds?: string[], packageIds?: string[]) {
  const groups = new Set(groupIds);
  const packages = new Set(packageIds);
  const full = groupIds === undefined || packageIds === undefined;
  for (const id of [...groupCache.keys()]) {
    const item = groupCache.get(id)!;
    if (item.library_id === libraryId && (full || groups.has(id))) groupCache.delete(id);
  }
  for (const id of [...packageCache.keys()]) {
    const item = packageCache.get(id)!;
    if (item.library_id === libraryId && (full || groups.has(item.group_id) || packages.has(id))) {
      packages.add(id);
      packageCache.delete(id);
    }
  }
  lists.each((key) => full || key.startsWith(`groups:${libraryId}:`) || [...groups].some((id) => key === `packages:${id}`)
    || [...packages].some((id) => key === `images:${id}`), (list) => list.invalidate());
  if (route.value.library === libraryId && (full || groups.has(route.value.group ?? ''))) {
    void refreshCurrentGroup();
  }
  if (route.value.library === libraryId && (full || packages.has(route.value.package ?? ''))) {
    currentPackage.value = null;
    void refreshCurrentPackage();
  }
}

// ---------------------------------------------------------------- group & package lookups
// Details resolve by persistent ID, with bounded caches for repeated navigation.

const groupCache = new Lru<Group>(200);
const packageCache = new Lru<Package>(2000);

export function rememberGroups(items: Group[]) { rememberCovers(items); for (const group of items) groupCache.set(group.id, group); }
export function rememberPackages(items: Package[]) {
  rememberCovers(items);
  const current = currentPackage.value?.id;
  for (const item of items) {
    packageCache.set(item.id, item);
    if (item.id === current) currentPackage.value = item;
  }
}
export const cachedPackage = (id: string) => packageCache.get(id);
export const cachedGroup = (id: string) => groupCache.get(id);

export const currentGroup = signal<Group | null>(null);
export const currentReview = signal<Review | null>(null);
/** Why the open folder could not be read, while no copy of it is cached to show instead. */
export const groupError = signal<{ id: string; text: string } | null>(null);

export async function resolveGroup(groupId: string, signal?: AbortSignal): Promise<Group> {
  const group = await client.request('get', '/api/v1/groups/{group_id}', { params: { path: { group_id: groupId } }, signal });
  rememberGroups([group]);
  return group;
}

/** Loads every package of a group in 500-item pages, up to a bound, for name lookups in evidence views. */
export async function packageIndex(groupId: string, signal?: AbortSignal, cap = 5000): Promise<Map<string, Package>> {
  const result = new Map<string, Package>();
  for (let offset = 0; offset < cap; offset += 500) {
    const page = await client.request('get', '/api/v1/groups/{group_id}/packages', {
      params: { path: { group_id: groupId }, query: { offset, limit: 500 } }, signal,
    });
    for (const item of page.items) result.set(item.id, item);
    rememberPackages(page.items);
    if (offset + page.items.length >= page.total) break;
  }
  return result;
}

/** Pages through a group's packages (500 at a time) until `stop` returns a value. */
async function scanPackages<R>(groupId: string, stop: (items: Package[], offset: number, total: number) => R | undefined,
  signal?: AbortSignal, cap = 50000): Promise<R | undefined> {
  for (let offset = 0; offset < cap; offset += 500) {
    const page = await client.request('get', '/api/v1/groups/{group_id}/packages', {
      params: { path: { group_id: groupId }, query: { offset, limit: 500 } }, signal,
    });
    rememberPackages(page.items);
    const found = stop(page.items, offset, page.total);
    if (found !== undefined) return found;
    if (offset + page.items.length >= page.total || !page.items.length) break;
  }
  return undefined;
}

/** Package metadata by persistent ID. */
export async function resolvePackage(groupId: string, packageId: string, signal?: AbortSignal): Promise<Package | null> {
  const cached = packageCache.get(packageId);
  if (cached?.group_id === groupId) return cached;
  try {
    const item = await client.request('get', '/api/v1/packages/{package_id}', { params: { path: { package_id: packageId } }, signal });
    if (item.group_id !== groupId) return null;
    rememberPackages([item]);
    return item;
  } catch (error) { if (statusOf(error) === 404) return null; throw error; }
}

/** The package before or after `packageId` in its group, for the viewer's explicit "next package" step. */
export async function neighborPackage(groupId: string, packageId: string, step: 1 | -1, signal?: AbortSignal): Promise<Package | null> {
  const list = packagesList(groupId);
  const index = list.indexOf((item) => item.id === packageId);
  const near = index >= 0 ? list.item(index + step) : undefined;
  if (near) return near;
  let previous: Package | null = null;
  let matched = false;
  const found = await scanPackages<Package | null>(groupId, (items) => {
    for (const item of items) {
      if (matched) return item; // the first package after the match, possibly on the next page
      if (item.id === packageId) {
        if (step === -1) return previous;
        matched = true;
        continue;
      }
      previous = item;
    }
    return undefined;
  }, signal);
  return found ?? null;
}

/** The package shown by the route (image wall, viewer), kept fresh as package pages arrive. */
export const currentPackage = signal<Package | null>(null);
let packageController: AbortController | null = null;
export async function refreshCurrentPackage() {
  const { library, group, package: packageId } = route.value;
  if (!group || !packageId) { packageController?.abort(); packageController = null; currentPackage.value = null; return; }
  if (currentPackage.value?.id === packageId) return;
  packageController?.abort();
  const cached = packageCache.get(packageId);
  currentPackage.value = cached ?? null;
  if (cached) return;
  const controller = packageController = new AbortController();
  try {
    const found = await resolvePackage(group, packageId, controller.signal);
    if (controller.signal.aborted) return;
    currentPackage.value = found;
    if (!found) {
      toast('此图包已不在图库中', 'error');
      if (route.value.package === packageId && !route.value.image) navigate({ library, group }, { replace: true });
    }
  } catch (error) { if (!isAbort(error)) reportError(error, '无法读取图包：'); }
}

let groupController: AbortController | null = null;
export async function refreshCurrentGroup() {
  const { library, group } = route.value;
  groupController?.abort();
  groupError.value = null;
  if (!library || !group) { currentGroup.value = null; currentReview.value = null; return; }
  const controller = groupController = new AbortController();
  const cached = groupCache.get(group);
  if (cached && currentGroup.value?.id !== group) currentGroup.value = cached;
  try {
    const [found, review] = await Promise.all([
      resolveGroup(group, controller.signal),
      client.request('get', '/api/v1/groups/{group_id}/review', { params: { path: { group_id: group } }, signal: controller.signal }),
    ]);
    if (controller.signal.aborted) return;
    batch(() => {
      currentGroup.value = found ? { ...found, state: review.state, resume_image_id: review.image_id } : null;
      currentReview.value = review;
    });
    if (!found) {
      toast('此文件夹已不在图库中', 'error');
      if (route.value.group === group) navigate({ library }, { replace: true });
    }
  } catch (error) {
    if (isAbort(error)) return;
    if (statusOf(error) === 404) { toast('此文件夹已不存在', 'error'); navigate({ library }, { replace: true }); return; }
    if (currentGroup.value?.id !== group) groupError.value = { id: group, text: describeError(error) };
    // Pages that wait for the folder show the error in place; the others keep working and get a notice.
    if (currentGroup.value?.id === group || route.value.package) reportError(error, '无法读取文件夹信息：');
  }
}

export async function setMark(groupId: string, state: Mark) {
  if (readonly) { toast('只读联调模式：未保存标记', 'info'); return; }
  const review = await client.request('patch', '/api/v1/groups/{group_id}/review', { params: { path: { group_id: groupId } }, body: { state } });
  if (currentGroup.value?.id === groupId) {
    batch(() => {
      currentReview.value = review;
      currentGroup.value = currentGroup.value ? { ...currentGroup.value, state: review.state } : null;
    });
  }
  const cached = groupCache.get(groupId);
  if (cached) groupCache.set(groupId, { ...cached, state: review.state });
  lists.each((key) => key.startsWith('groups:'), (list) => list.invalidate());
}

// Positions are bound to image IDs and written after the viewer settles on an image.
let positionTimer = 0;
let pendingPosition: { group: string; image: string } | null = null;
export function savePosition(groupId: string, imageId: string) {
  if (readonly) return;
  pendingPosition = { group: groupId, image: imageId };
  clearTimeout(positionTimer);
  positionTimer = window.setTimeout(flushPosition, 600);
}
export function flushPosition() {
  clearTimeout(positionTimer);
  const pending = pendingPosition;
  pendingPosition = null;
  if (!pending) return;
  client.request('put', '/api/v1/groups/{group_id}/position', { params: { path: { group_id: pending.group } }, body: { image_id: pending.image } })
    .then((review) => {
      if (currentGroup.value?.id === pending.group) {
        currentReview.value = review;
        currentGroup.value = currentGroup.value ? { ...currentGroup.value, resume_image_id: review.image_id } : null;
      }
      const cached = groupCache.get(pending.group);
      if (cached) groupCache.set(pending.group, { ...cached, resume_image_id: review.image_id });
    })
    .catch((error) => { if (statusOf(error) !== 404 && statusOf(error) !== 409) reportError(error, '保存浏览位置失败：'); });
}
window.addEventListener('pagehide', flushPosition);

// ---------------------------------------------------------------- tasks

export const tasks = signal<Task[]>([]);
export const tasksTotal = signal(0);
export const taskDrawer = signal(false);
export const tasksError = signal<string | null>(null);
export const activeTaskCount = computed(() => tasks.value.filter(isActive).length);
const tasksLoaded = signal(false);
const watchers = new Map<string, Set<(task: Task) => void>>();

const liveScan = (libraryId: string) => tasks.value.some((task) => task.kind === 'scan' && task.payload.library_id === libraryId && isActive(task));
/** Libraries whose last read still said 'scanning'/'pending' after their scan task was gone. */
const staleScans = signal<ReadonlySet<string>>(new Set());

/**
 * Index status for display. The backend resets 'scanning' only when a scan is cancelled, so a crashed or failed
 * scan leaves it behind; with no scan task left it is shown as interrupted (or not yet scanned) instead of busy.
 */
export function scanStatus(lib: Library): string {
  const status = lib.scan_status;
  if (status !== 'scanning' && status !== 'pending') return status;
  if (!staleScans.value.has(lib.id) || liveScan(lib.id)) return status;
  return status === 'scanning' ? 'interrupted' : 'unscanned';
}

// A failed scan publishes no catalog event: once a library's scan task is gone, read the libraries again to judge it.
let confirmTimer = 0;
effect(() => {
  const stale = staleScans.value;
  const unjudged = tasksLoaded.value && libraries.value.some((lib) => (lib.scan_status === 'scanning' || lib.scan_status === 'pending')
    && !stale.has(lib.id) && !liveScan(lib.id));
  if (unjudged && !confirmTimer) confirmTimer = window.setTimeout(() => { confirmTimer = 0; void loadLibraries(); }, 1000);
});

export async function loadTasks() {
  try {
    const [page, live] = await Promise.all([
      client.request('get', '/api/v1/tasks', { params: { query: { offset: 0, limit: 50 } } }),
      client.request('get', '/api/v1/tasks', { params: { query: { active: true, limit: 500 } } }),
    ]);
    const items = [...new Map([...live.items, ...page.items].map((task) => [task.id, task])).values()];
    batch(() => { tasks.value = items; tasksTotal.value = page.total; tasksLoaded.value = true; tasksError.value = null; });
    for (const task of items) watchers.get(task.id)?.forEach((fn) => fn(task));
  } catch (error) { if (!isAbort(error)) tasksError.value = describeError(error); }
}

export async function refreshTask(id: string): Promise<Task | null> {
  try {
    const task = await client.request('get', '/api/v1/tasks/{task_id}', { params: { path: { task_id: id } } });
    const index = tasks.value.findIndex((item) => item.id === id);
    if (index >= 0) { const next = tasks.value.slice(); next[index] = task; tasks.value = next; }
    else tasks.value = [task, ...tasks.value].slice(0, 180);
    watchers.get(id)?.forEach((fn) => fn(task));
    return task;
  } catch (error) {
    if (statusOf(error) === 404) return null;
    throw error;
  }
}

/**
 * Subscribe to one task; SSE drives updates and a slow poll covers a dropped event stream.
 * `onGone` runs when the backend no longer knows the task.
 */
export function watchTask(id: string, listener: (task: Task) => void, onGone?: () => void): () => void {
  let set = watchers.get(id);
  if (!set) watchers.set(id, set = new Set());
  set.add(listener);
  let stopped = false;
  const poll = async () => {
    if (stopped) return;
    let task: Task | null | undefined;
    try { task = await refreshTask(id); } catch { task = undefined; }
    if (stopped) return;
    if (task === null) { onGone?.(); return; }
    const delay = connection.value === 'online' ? 4000 : 1500;
    if (task === undefined || isActive(task)) timer = window.setTimeout(poll, delay);
  };
  let timer = window.setTimeout(poll, 0);
  return () => { stopped = true; clearTimeout(timer); set!.delete(listener); if (!set!.size) watchers.delete(id); };
}

/** Last task started per scope (e.g. "analyze:<group>"), so evidence survives reloads. */
const TRACKED = 'gt.trackedTasks';
export const trackedVersion = signal(0);
function trackedMap(): Record<string, string> {
  try { return JSON.parse(localStorage.getItem(TRACKED) || '{}') as Record<string, string>; } catch { return {}; }
}
export function trackedTask(scope: string): string | null { return trackedMap()[scope] ?? null; }
export function trackTask(scope: string, id: string | null) {
  try {
    const map = trackedMap();
    if (id) { delete map[scope]; map[scope] = id; } else delete map[scope];
    const keys = Object.keys(map);
    for (const key of keys.slice(0, Math.max(0, keys.length - 200))) delete map[key];
    localStorage.setItem(TRACKED, JSON.stringify(map));
  } catch { /* storage unavailable */ }
  trackedVersion.value++;
}

export async function submitTask(body: JobBody): Promise<Task> {
  const task = await client.request('post', '/api/v1/tasks', { body });
  tasks.value = [task, ...tasks.value.filter((item) => item.id !== task.id)].slice(0, 180);
  return task;
}

type TaskAction = 'pause' | 'resume' | 'cancel';
export const taskControls = signal<Record<string, TaskAction>>({});
export async function controlTask(id: string, action: TaskAction) {
  if (taskControls.peek()[id]) return;
  taskControls.value = { ...taskControls.peek(), [id]: action };
  try {
    await client.request('post', '/api/v1/tasks/{task_id}/control', { params: { path: { task_id: id } }, body: { action } });
    await refreshTask(id);
  } catch (error) { reportError(error, '任务操作失败：'); }
  finally {
    const next = { ...taskControls.peek() };
    delete next[id];
    taskControls.value = next;
  }
}

// ---------------------------------------------------------------- dialogs

export interface DeleteRequestState {
  kind: 'delete';
  targets: DeleteTarget[];
  /** What is being deleted, e.g. "图片 001.jpg" or "3 个图包". */
  title: string;
  /** Display names by target ID, for targets the result reports without a path. */
  names?: Record<string, string>;
  libraryName?: string;
  /** Directory targets (packages, folders) are removed with every file inside, images or not. */
  includesFolders?: boolean;
  /** Called once the delete task has finished, with the IDs that were removed. */
  onDone?: (completed: Set<string>) => void;
}
export interface DeleteReportState { kind: 'delete-report'; taskId: string }
export type LibraryAction = 'rename' | 'reconnect' | 'remove';
export interface LibraryRequestState { kind: 'library'; action: LibraryAction; library: Library; draft?: string }
export type DialogState = { kind: 'add-library' } | LibraryRequestState | DeleteRequestState | DeleteReportState;
export const dialog = signal<DialogState | null>(null);

export function manageLibrary(library: Library, action: LibraryAction) {
  dialog.value = { kind: 'library', library, action };
}

export function requestDelete(request: Omit<DeleteRequestState, 'kind'>) {
  if (readonly) { toast('只读联调模式：不执行删除', 'info'); return; }
  dialog.value = { kind: 'delete', libraryName: currentLibrary.value?.name, ...request };
}

export interface ViewedImage { group: string; package: string; image: string; index?: number }
/** Viewing history stays available for recent-item highlights after a return has been handled. */
export const lastViewed = signal<ViewedImage | null>(null);
/** A one-time return request, separate from history so later scrolling and resizes keep their anchor. */
export const wallReturn = signal<ViewedImage | null>(null);
effect(() => {
  const pending = wallReturn.value;
  const current = route.value;
  if (pending && (current.image || current.view !== 'packages' || current.group !== pending.group
    || (current.package && current.package !== pending.package))) wallReturn.value = null;
});

// ---------------------------------------------------------------- UI prefs

export type TileSize = 's' | 'm' | 'l';
export const tileSize = signal<TileSize>((localStorage.getItem('gt.tileSize') as TileSize) || 'm');
export const imageFit = signal<'contain' | 'cover'>(localStorage.getItem('gt.imageFit') === 'cover' ? 'cover' : 'contain');
effect(() => { localStorage.setItem('gt.imageFit', imageFit.value); });
export const sidebarOpen = signal(localStorage.getItem('gt.sidebar') !== '0');
export const narrow = signal(window.matchMedia('(max-width: 860px)').matches);
window.matchMedia('(max-width: 860px)').addEventListener('change', (event) => { narrow.value = event.matches; });
export function persistPrefs() {
  localStorage.setItem('gt.tileSize', tileSize.value);
  // The narrow layout's overlay sidebar is transient; only the wide layout's choice is remembered.
  if (!narrow.value) localStorage.setItem('gt.sidebar', sidebarOpen.value ? '1' : '0');
  localStorage.setItem('gt.groupFilter', JSON.stringify(groupFilter.value));
  if (route.value.library) localStorage.setItem('gt.library', route.value.library);
}

/** Follows the system unless pinned. Only the root attribute changes, so no image reloads. */
export type Theme = 'system' | 'light' | 'dark';
const THEME_KEY = 'gt.theme';
function savedTheme(): Theme {
  try {
    const value = localStorage.getItem(THEME_KEY);
    return value === 'light' || value === 'dark' ? value : 'system';
  } catch { return 'system'; }
}
export const theme = signal<Theme>(savedTheme());
effect(() => {
  const value = theme.value;
  const root = document.documentElement;
  if (value === 'system') delete root.dataset.theme;
  else root.dataset.theme = value;
  try {
    if (value === 'system') localStorage.removeItem(THEME_KEY);
    else localStorage.setItem(THEME_KEY, value);
  } catch { /* storage unavailable */ }
});
