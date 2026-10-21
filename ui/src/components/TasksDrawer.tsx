import { useEffect, useState } from 'preact/hooks';
import { client, isActive, type Group, type Task } from '../api';
import { bytes, count, time } from '../lib/format';
import { Icon } from '../lib/icons';
import { navigate, type OrganizeTab } from '../lib/router';
import { canCancel, canPause, canResume, kindLabel } from '../lib/tasks';
import {
  cachedGroup, cachedPackage, controlTask, dialog, libraries, loadTasks, reportError, scopeOfTask, submittedHere, submitTask, taskDrawer,
  tasks, tasksError, tasksTotal, toast, trackTask,
} from '../state/app';
import { TaskProgress } from './Progress';

type Result = NonNullable<Task['result']>;
const has = <K extends string>(result: Result, key: K): result is Extract<Result, Record<K, unknown>> => key in result;

/** One line summarizing what a finished task produced. */
export function resultText(task: Task): string {
  const result = task.result;
  if (!result) return '';
  if (has(result, 'items') && has(result, 'failed') && task.kind === 'delete') {
    const done = result.items.filter((item) => item.state === 'completed').length;
    const recycle = result.items.some((item) => item.mode === 'recycle');
    return `${recycle ? '移到回收站' : '已删除'} ${count(done)} 项${result.failed ? `，失败 ${count(result.failed)} 项` : ''}`;
  }
  if (has(result, 'online')) {
    if (!result.online) return '目录离线，未能扫描';
    return `目录 ${count(result.directories)} · 文件 ${count(result.files)}${result.failed_directories ? ` · ${count(result.failed_directories)} 个目录读取失败` : ''}`;
  }
  if (has(result, 'package_pairs_total')) {
    return `指纹覆盖 ${Math.round(result.coverage * 100)}% · 相似图片 ${count(result.pairs)} 对 · 相似图包 ${count(result.package_pairs_total)} 组`;
  }
  if (has(result, 'algorithm')) {
    return result.exact_equal ? '两个图包完全一致' : result.left_contained ? '左侧图包被右侧完整包含'
      : result.right_contained ? '右侧图包被左侧完整包含' : `各有独有文件（${count(result.left_unique_total)} / ${count(result.right_unique_total)}）`;
  }
  if (has(result, 'shells_total')) {
    return `空壳 ${count(result.shells_total)} · 含广告 ${count(result.advertisements_total)} · 不完整 ${count(result.incomplete_total)}`;
  }
  if (has(result, 'hash_version')) return `已建立 ${count(result.indexed)}${result.failed ? `，失败 ${count(result.failed)}` : ''}`;
  if (has(result, 'generated_or_cached')) return `已就绪 ${count(result.generated_or_cached)}${result.failed ? `，失败 ${count(result.failed)}` : ''}`;
  if (has(result, 'limit')) return `缓存 ${bytes(result.bytes)} / ${bytes(result.limit)}，清理 ${count(result.removed)} 项`;
  return '';
}

function libraryName(id: unknown) { return typeof id === 'string' ? libraries.value.find((lib) => lib.id === id)?.name : undefined; }

function scopeText(task: Task): string {
  const group = resultGroup(task);
  if (group) return group.name;
  const lib = libraryName(task.payload.library_id);
  return lib ?? '';
}

const TABS: Record<string, OrganizeTab> = { analyze: 'similar', compare: 'compare', audit: 'audit' };

/** The group whose organize page shows a task's findings; compare payloads name only the two packages. */
function resultGroup(task: Task): Group | undefined {
  const payload = task.payload;
  if (typeof payload.group_id === 'string') return cachedGroup(payload.group_id);
  if (task.kind !== 'compare') return undefined;
  const left = typeof payload.left_id === 'string' ? cachedPackage(payload.left_id) : undefined;
  const scope = scopeOfTask(task.id);
  const groupId = left?.group_id ?? (scope?.startsWith('compare:') ? scope.slice('compare:'.length) : undefined);
  return groupId ? cachedGroup(groupId) : undefined;
}

/** Shows this task's findings on the organize page, replacing whichever run was shown there. */
function openResult(task: Task) {
  if (task.kind === 'delete') { dialog.value = { kind: 'delete-report', taskId: task.id }; return; }
  const tab = TABS[task.kind];
  const group = resultGroup(task);
  if (!tab) return;
  if (!group) { toast('找不到此任务所属的文件夹，请先在侧栏打开对应图库', 'info'); return; }
  trackTask(`${task.kind}:${group.id}`, task.id);
  navigate({ library: group.library_id, group: group.id, view: 'organize', tab });
  taskDrawer.value = false;
}

function TaskRow({ task }: { task: Task }) {
  const active = isActive(task);
  const summary = active ? '' : resultText(task);
  const scope = scopeText(task);
  const openable = task.kind === 'delete' || (!active && task.state === 'completed' && Boolean(TABS[task.kind]) && Boolean(resultGroup(task)));
  return (
    <li class={`task-row ${task.state}`}>
      <TaskProgress task={task} label={kindLabel(task.kind) + (scope ? ` · ${scope}` : '')} />
      {summary && <div class="task-summary">{summary}</div>}
      <div class="task-row-foot">
        <span class="muted">{time(task.created)}</span>
        <span class="spacer" />
        {canPause(task) && <button class="btn tiny" onClick={() => void controlTask(task.id, 'pause')}><Icon name="Pause" size={14} />暂停</button>}
        {canResume(task) && <button class="btn tiny" onClick={() => void controlTask(task.id, 'resume')}><Icon name="Play" size={14} />继续</button>}
        {canCancel(task) && <button class="btn tiny" onClick={() => void controlTask(task.id, 'cancel')}><Icon name="X" size={14} />取消</button>}
        {openable && <button class="btn tiny" onClick={() => openResult(task)}><Icon name="ExternalLink" size={14} />{task.kind === 'delete' ? '逐项结果' : '查看结果'}</button>}
      </div>
    </li>
  );
}

/** A clean scan or cache clean-up the backend ran on its own (watcher or 10-minute maintenance). */
function routine(task: Task): boolean {
  if (task.state !== 'completed' || submittedHere(task.id)) return false;
  if (task.kind === 'collect') return true;
  const result = task.result;
  return task.kind === 'scan' && Boolean(result) && has(result!, 'online') && result.online && !result.failed_directories;
}

function RoutineTasks({ items }: { items: Task[] }) {
  const [open, setOpen] = useState(false);
  const scans = items.filter((task) => task.kind === 'scan').length;
  return (
    <details class="task-routine" open={open} onToggle={(event) => setOpen((event.currentTarget as HTMLDetailsElement).open)}>
      <summary>
        <Icon name={open ? 'ChevronDown' : 'ChevronRight'} size={14} />
        <span>自动维护 {items.length} 个均正常完成</span>
        <span class="muted">扫描目录 {scans} · 清理缓存 {items.length - scans}</span>
      </summary>
      {open && <ul class="task-list">{items.map((task) => <TaskRow key={task.id} task={task} />)}</ul>}
    </details>
  );
}

function CacheLine() {
  const [cache, setCache] = useState<{ bytes: number; limit: number } | null>(null);
  const [busy, setBusy] = useState(false);
  const load = () => client.request('get', '/api/v1/cache')
    .then((stats) => setCache({ bytes: stats.bytes ?? 0, limit: stats.limit ?? 0 })).catch(() => setCache(null));
  useEffect(() => { void load(); }, []);
  const collect = async () => {
    setBusy(true);
    try { await submitTask({ kind: 'collect' }); toast('已开始整理缩略图缓存', 'info'); }
    catch (error) { reportError(error, '无法整理缓存：'); }
    finally { setBusy(false); window.setTimeout(load, 1500); }
  };
  return (
    <footer class="drawer-foot">
      <span class="muted">缩略图缓存 {cache ? `${bytes(cache.bytes)} / ${bytes(cache.limit)}` : '—'}</span>
      <button class="btn tiny" disabled={busy} onClick={collect}>整理缓存</button>
    </footer>
  );
}

export function TasksDrawer() {
  const open = taskDrawer.value;
  useEffect(() => { if (open) void loadTasks(); }, [open]);
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape' && !document.querySelector('dialog[open]')) { taskDrawer.value = false; } };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);
  if (!open) return null;
  const items = tasks.value;
  const error = tasksError.value;
  const active = items.filter(isActive);
  const finished = items.filter((task) => !isActive(task));
  const automatic = finished.filter(routine);
  const shown = finished.filter((task) => !routine(task));
  return (
    <>
      <div class="drawer-scrim" onClick={() => { taskDrawer.value = false; }} />
      <aside class="drawer" aria-label="后台任务">
        <header class="drawer-head">
          <h2>后台任务</h2>
          <button class="icon-btn" title="刷新" aria-label="刷新任务" onClick={() => void loadTasks()}><Icon name="RefreshCw" size={16} /></button>
          <button class="icon-btn" title="关闭" aria-label="关闭" onClick={() => { taskDrawer.value = false; }}><Icon name="X" /></button>
        </header>
        <div class="drawer-body">
          {error && (
            <div class="vgrid-error" role="alert">
              <Icon name="CircleAlert" size={16} />
              <span>无法读取任务列表：{error}</span>
              <button class="btn tiny" onClick={() => void loadTasks()}>重试</button>
            </div>
          )}
          {!items.length && !error && <p class="muted pad">还没有后台任务。扫描、生成缩略图、相似分析、核验和删除都会显示在这里。</p>}
          {active.length > 0 && (
            <section>
              <h3>进行中 <span class="muted">{active.length}</span></h3>
              <ul class="task-list">{active.map((task) => <TaskRow key={task.id} task={task} />)}</ul>
            </section>
          )}
          {finished.length > 0 && (
            <section>
              <h3>最近完成 {tasksTotal.value > items.length && <span class="muted">（显示最近 {items.length} / {tasksTotal.value} 个）</span>}</h3>
              {shown.length > 0 && <ul class="task-list">{shown.map((task) => <TaskRow key={task.id} task={task} />)}</ul>}
              {automatic.length > 0 && <RoutineTasks items={automatic} />}
            </section>
          )}
        </div>
        <CacheLine />
      </aside>
    </>
  );
}
