import type { ComponentChildren } from 'preact';
import { useEffect, useMemo, useState } from 'preact/hooks';
import { client, describeError, isAbort, isActive, type Group, type Package, type Task } from '../api';
import { TaskProgress } from '../components/Progress';
import { Thumb } from '../components/Thumb';
import { count, packageParent, time } from '../lib/format';
import { Icon } from '../lib/icons';
import { navigate, type OrganizeTab } from '../lib/router';
import { canCancel, canPause, canResume } from '../lib/tasks';
import {
  cachedPackage, controlTask, currentLibrary, packageIndex, reportError, submitTask, tasks, trackTask, trackedTask,
  trackedVersion, watchTask,
} from '../state/app';

/** The task last started for a scope (e.g. "analyze:<group>"), followed live while it runs. */
export function useTracked(scope: string) {
  const version = trackedVersion.value;
  const id = useMemo(() => trackedTask(scope), [scope, version]);
  const [task, setTask] = useState<Task | null>(null);
  const [gone, setGone] = useState(false);
  useEffect(() => {
    setGone(false);
    setTask(id ? tasks.value.find((item) => item.id === id) ?? null : null);
    if (!id) return;
    return watchTask(id, setTask, () => { setGone(true); setTask(null); });
  }, [id]);
  return { id, task: task && task.id === id ? task : null, gone: gone && Boolean(id) };
}

export const completed = <T,>(task: Task | null) => (task?.state === 'completed' && task.result ? task.result as T : null);

// Evidence carries package IDs only; names come from the group's package pages (bounded, see packageIndex).
const indexes = new Map<string, { revision: number; map: Map<string, Package> }>();

const INDEX_CAP = 5000;

export interface Names {
  get: (id: string) => Package | undefined; all: Package[]; loading: boolean; error: string | null; retry: () => void;
  /** Every package of the group was read, so a miss means the package is gone. */
  complete: boolean;
}

export function usePackageNames(groupId: string): Names {
  const revision = currentLibrary.value?.revision ?? 0;
  const [state, setState] = useState<{ group: string; map: Map<string, Package> | null; error: string | null }>(
    () => ({ group: groupId, map: indexes.get(groupId)?.map ?? null, error: null }));
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const cached = indexes.get(groupId);
    setState((old) => ({ group: groupId, map: cached?.map ?? (old.group === groupId ? old.map : null), error: null }));
    if (cached && cached.revision === revision) return;
    const controller = new AbortController();
    // While a scan bumps the revision repeatedly, reread once things settle.
    const timer = window.setTimeout(() => {
      packageIndex(groupId, controller.signal, INDEX_CAP).then((map) => {
        indexes.delete(groupId);
        indexes.set(groupId, { revision, map });
        while (indexes.size > 3) indexes.delete(indexes.keys().next().value as string);
        setState({ group: groupId, map, error: null });
      }).catch((error) => {
        if (!isAbort(error)) setState((old) => ({ ...old, error: describeError(error) }));
      });
    }, cached ? 1500 : 0);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [groupId, revision, attempt]);
  const map = state.group === groupId ? state.map : null;
  const all = useMemo(() => (map ? [...map.values()] : []), [map]);
  return {
    get: (id) => map?.get(id) ?? cachedPackage(id),
    all, loading: !map && !state.error, error: state.error, retry: () => setAttempt((n) => n + 1),
    complete: Boolean(map && map.size < INDEX_CAP),
  };
}

export const packageLabel = (pkg: Package) => (pkg.loose ? '散图' : pkg.name);

/** Location of a package inside its group, e.g. "作者 / 第1季 / Vol.01"; loose images are named by their folder. */
export function relInGroup(pkg: Package, group: Group): string {
  let rel = pkg.rel;
  if (group.rel && rel.startsWith(group.rel + '/')) rel = rel.slice(group.rel.length + 1);
  else if (rel === group.rel) rel = '';
  return rel.split('/').filter(Boolean).join(' / ');
}

export const pickerLabel = (pkg: Package, group: Group) =>
  (pkg.loose ? `${relInGroup(pkg, group) || '根目录'}（散图）` : relInGroup(pkg, group) || pkg.name);

export function openPackage(group: Group, id: string) {
  navigate({ library: group.library_id, group: group.id, package: id });
}

/** Opens the viewer over the organize page; the package comes from the evidence or the image context. */
export async function openImage(group: Group, tab: OrganizeTab, imageId: string, packageId?: string) {
  let pkg = packageId;
  if (!pkg) {
    try {
      const context = await client.request('get', '/api/v1/images/{image_id}/context', { params: { path: { image_id: imageId } } });
      pkg = context.image.package_id;
    } catch (error) { reportError(error, '无法打开图片：'); return; }
  }
  navigate({ library: group.library_id, group: group.id, view: 'organize', tab, package: pkg, image: imageId });
}

/** Starts an exact all-file comparison and shows it on the compare tab. */
export async function startCompare(group: Group, left: string, right: string) {
  try {
    const task = await submitTask({ kind: 'compare', left_id: left, right_id: right });
    trackTask(`compare:${group.id}`, task.id);
    navigate({ library: group.library_id, group: group.id, view: 'organize', tab: 'compare' });
  } catch (error) { reportError(error, '无法开始整包核验：'); }
}

export function PackageRef({ id, names, group, children }: { id: string; names: Names; group: Group; children?: ComponentChildren }) {
  const pkg = names.get(id);
  const parent = pkg ? (pkg.loose ? relInGroup(pkg, group) : packageParent(pkg.rel, pkg.name, group.rel)) : '';
  const missing = names.loading ? '正在读取图包信息…' : names.complete ? '（未找到此图包，可能已删除）' : '（图包信息未载入）';
  return (
    <div class="pkg-ref">
      <button class="pkg-cover" onClick={() => openPackage(group, id)} title="打开图片墙" aria-label="打开图片墙">
        {pkg?.cover_id ? <Thumb id={pkg.cover_id} edge={400} /> : <Icon name={pkg ? 'Folder' : 'CircleAlert'} size={22} />}
      </button>
      <div class="pkg-text">
        <button class="link pkg-name" title={pkg?.rel || id} onClick={() => openPackage(group, id)}>
          {pkg ? packageLabel(pkg) : missing}
        </button>
        <span class="muted pkg-sub">{[parent, pkg ? `${count(pkg.image_count)} 张` : ''].filter(Boolean).join(' · ')}</span>
        {children}
      </div>
    </div>
  );
}

/** Live progress and controls of the tracked task; failures offer a fresh start. */
export function TaskBlock({ task, label, onRestart }: { task: Task; label: string; onRestart: () => void }) {
  if (task.state === 'completed') return <p class="muted task-done"><Icon name="Check" size={14} />{label}完成于 {time(task.updated)}</p>;
  const active = isActive(task);
  return (
    <div class={`org-task ${task.state}`}>
      <TaskProgress task={task} label={label} />
      <div class="org-task-actions">
        {task.state === 'interrupted' && <span class="muted">服务重启时任务被中断</span>}
        {task.state === 'cancelled' && <span class="muted">任务已取消，没有结果</span>}
        <span class="spacer" />
        {canPause(task) && <button class="btn small" onClick={() => void controlTask(task.id, 'pause')}><Icon name="Pause" size={14} />暂停</button>}
        {canResume(task) && <button class="btn small" onClick={() => void controlTask(task.id, 'resume')}><Icon name="Play" size={14} />继续</button>}
        {canCancel(task) && <button class="btn small" onClick={() => void controlTask(task.id, 'cancel')}><Icon name="X" size={14} />取消</button>}
        {!active && <button class="btn small" onClick={onRestart}><Icon name="RotateCcw" size={14} />重新开始</button>}
      </div>
    </div>
  );
}

export function Stat({ label, value, tone }: { label: string; value: string; tone?: 'warn' | 'bad' | 'ok' | '' }) {
  return <div class={`stat ${tone || ''}`}><span class="stat-value num">{value}</span><span class="stat-label">{label}</span></div>;
}

export function Pager({ page, pages, onPage }: { page: number; pages: number; onPage: (page: number) => void }) {
  if (pages <= 1) return null;
  return (
    <div class="pager" role="navigation" aria-label="翻页">
      <button class="icon-btn small" disabled={page === 0} onClick={() => onPage(0)} aria-label="第一页"><Icon name="ChevronsLeft" size={16} /></button>
      <button class="icon-btn small" disabled={page === 0} onClick={() => onPage(page - 1)} aria-label="上一页"><Icon name="ChevronLeft" size={16} /></button>
      <span class="num">{page + 1} / {pages}</span>
      <button class="icon-btn small" disabled={page >= pages - 1} onClick={() => onPage(page + 1)} aria-label="下一页"><Icon name="ChevronRight" size={16} /></button>
      <button class="icon-btn small" disabled={page >= pages - 1} onClick={() => onPage(pages - 1)} aria-label="最后一页"><Icon name="ChevronsRight" size={16} /></button>
    </div>
  );
}

/**
 * One page of server-side findings. Page 0 is the preview embedded in the task result; later pages are
 * read from /tasks/{id}/findings so only `size` rows exist at a time.
 */
export function useFindings<T>(taskId: string, kind: 'left_unique' | 'right_unique' | 'shell' | 'advertisement' | 'incomplete' | 'package_pair',
  preview: T[], total: number, size: number) {
  const [page, setPage] = useState(0);
  const [state, setState] = useState<{ key: string; items?: T[]; error?: string }>({ key: '' });
  const [attempt, setAttempt] = useState(0);
  const pages = Math.max(1, Math.ceil(total / size));
  const key = `${taskId}:${kind}:${page}`;
  const inline = preview.length >= total || (page + 1) * size <= preview.length;
  useEffect(() => { setPage(0); }, [taskId, kind]);
  useEffect(() => {
    if (inline) return;
    const controller = new AbortController();
    client.request('get', '/api/v1/tasks/{task_id}/findings', {
      params: { path: { task_id: taskId }, query: { kind, offset: page * size, limit: size } }, signal: controller.signal,
    }).then((result) => setState({ key, items: result.items as T[] }))
      .catch((error) => { if (!isAbort(error)) setState({ key, error: describeError(error) }); });
    return () => controller.abort();
  }, [key, inline, attempt]);
  const items = inline ? preview.slice(page * size, (page + 1) * size) : state.key === key ? state.items ?? null : null;
  return {
    page, pages, setPage, items,
    error: !inline && state.key === key ? state.error ?? null : null,
    retry: () => setAttempt((n) => n + 1),
  };
}

export function ListState({ error, retry, loading }: { error: string | null; retry: () => void; loading: boolean }) {
  if (error) return <div class="vgrid-error" role="alert"><span>读取失败：{error}</span><button class="btn small" onClick={retry}>重试</button></div>;
  if (loading) return <p class="muted list-loading"><Icon name="LoaderCircle" spin size={16} />正在读取…</p>;
  return null;
}
