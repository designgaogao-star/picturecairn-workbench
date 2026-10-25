import { useEffect, useState } from 'preact/hooks';
import {
  client, describeError, isAbort, isActive, statusOf,
  type DeleteItem, type DeleteResult, type DeleteTarget, type Operation, type Task,
} from '../api';
import { readableError } from '../lib/format';
import { Icon } from '../lib/icons';
import {
  dialog, libraries, loadLibraries, refreshTask, requestDelete, toast, watchTask, type DeleteRequestState,
} from '../state/app';
import { Dialog } from './Dialog';
import { TaskProgress } from './Progress';

type RowState = 'completed' | 'failed' | 'cancelled' | 'pending' | 'skipped';
export interface ReportRow { targetId: string; kind: string; path: string; mode: string; state: RowState; error: string | null }

const KIND_TEXT: Record<string, string> = { image: '图片', package: '图包', group: '文件夹' };
const ROW_TEXT: Record<RowState, string> = {
  completed: '已删除', failed: '失败', cancelled: '已取消', pending: '状态未知', skipped: '未执行',
};
const ORDER: RowState[] = ['failed', 'pending', 'cancelled', 'skipped', 'completed'];

const isDeleteResult = (result: Task['result']): result is DeleteResult => !!result && 'items' in result && 'failed' in result;
const rowState = (state: string): RowState => (ORDER.includes(state as RowState) ? state as RowState : 'pending');
const fromItem = (item: DeleteItem): ReportRow => ({
  targetId: item.target_id, kind: item.kind, path: item.path, mode: item.mode, state: rowState(item.state), error: item.error,
});
const fromOperation = (item: Operation): ReportRow => ({
  targetId: item.target_id, kind: item.target_kind, path: item.path, mode: item.mode, state: rowState(item.state), error: item.error,
});

/**
 * Per-item outcome of a finished delete task. A cancelled or failed task may carry no result, so the
 * operation log is read instead; targets the task never reached are listed as not executed.
 */
export async function deleteRows(task: Task, signal?: AbortSignal): Promise<ReportRow[]> {
  let rows: ReportRow[];
  if (isDeleteResult(task.result)) rows = task.result.items.map(fromItem);
  else {
    const operations: Operation[] = [];
    for (let offset = 0; offset < 5000; offset += 500) {
      const page = await client.request('get', '/api/v1/operations', { params: { query: { task_id: task.id, offset, limit: 500 } }, signal });
      operations.push(...page.items);
      if (offset + page.items.length >= page.total || !page.items.length) break;
    }
    rows = operations.map(fromOperation);
  }
  const seen = new Set(rows.map((row) => row.targetId));
  const targets = (Array.isArray(task.payload.targets) ? task.payload.targets : []) as DeleteTarget[];
  for (const target of targets) {
    if (!seen.has(target.id)) rows.push({ targetId: target.id, kind: target.kind, path: '', mode: '', state: 'skipped', error: null });
  }
  return rows.sort((a, b) => ORDER.indexOf(a.state) - ORDER.indexOf(b.state));
}

/** A path inside a library reads like the package paths elsewhere, relative to the library root. */
function shownPath(path: string): string {
  const norm = (value: string) => value.replace(/\//g, '\\').replace(/\\+$/, '').toLowerCase();
  const target = norm(path);
  for (const lib of libraries.value) {
    const root = norm(lib.path);
    if (target === root) return lib.name;
    if (target.startsWith(`${root}\\`)) return path.slice(root.length + 1).replace(/\\/g, '/');
  }
  return path;
}

// The task only lists target IDs, and a target it never reached gets no path; keep the names it was submitted
// with, so a report reopened from the task list can still say what was not deleted.
const submittedRequests = new Map<string, DeleteRequestState>();
function rememberRequest(taskId: string, request: DeleteRequestState) {
  submittedRequests.set(taskId, request);
  if (submittedRequests.size > 20) submittedRequests.delete(submittedRequests.keys().next().value as string);
}

function summary(rows: ReportRow[]) {
  const by = (state: RowState) => rows.filter((row) => row.state === state).length;
  return { done: by('completed'), failed: by('failed') + by('pending'), skipped: by('skipped') + by('cancelled') };
}

// Delete tasks are followed even after their dialog closes, so callers always learn the outcome once.
const followed = new Set<string>();
function follow(taskId: string, request: DeleteRequestState) {
  if (followed.has(taskId)) return;
  followed.add(taskId);
  let settled = false;
  const stop = watchTask(taskId, (task) => {
    if (settled || isActive(task)) return;
    settled = true;
    stop();
    void settle(task, request);
  }, () => { stop(); followed.delete(taskId); toast('删除任务的记录已不存在，请在回收站或文件夹中确认结果', 'error', undefined, 0); });
}

async function settle(task: Task, request: DeleteRequestState) {
  followed.delete(task.id);
  let rows: ReportRow[] = [];
  try { rows = await deleteRows(task); } catch (error) { console.warn('delete rows', error); }
  const counts = summary(rows);
  request.onDone?.(new Set(rows.filter((row) => row.state === 'completed').map((row) => row.targetId)));
  void loadLibraries();
  const clean = task.state === 'completed' && !counts.failed && !counts.skipped;
  const text = clean ? `已删除 ${counts.done} 项` : `删除结束：成功 ${counts.done} 项，失败 ${counts.failed} 项${counts.skipped ? `，未执行 ${counts.skipped} 项` : ''}`;
  const open = () => { dialog.value = { kind: 'delete-report', taskId: task.id }; };
  // The dialog that started the task shows the report itself while it stays open.
  if (dialog.value !== request) toast(text, clean ? 'success' : 'error', { label: '查看结果', run: open }, clean ? 6000 : 0);
}

function ReportList({ task, names }: { task: Task; names?: Record<string, string> }) {
  const [rows, setRows] = useState<ReportRow[] | null>(null);
  const [error, setError] = useState('');
  const [limit, setLimit] = useState(200);
  useEffect(() => {
    const controller = new AbortController();
    setRows(null); setError('');
    deleteRows(task, controller.signal).then(setRows).catch((failure) => { if (!isAbort(failure)) setError(describeError(failure)); });
    return () => controller.abort();
  }, [task.id, task.state]);
  if (error) return <p class="form-error" role="alert"><Icon name="CircleAlert" size={16} />无法读取逐项结果：{error}</p>;
  if (!rows) return <p class="muted"><Icon name="LoaderCircle" spin size={16} /> 正在读取逐项结果…</p>;
  const counts = summary(rows);
  const recycle = rows.some((row) => row.mode === 'recycle');
  const failed = rows.filter((row) => row.state === 'failed' && ['image', 'package', 'group'].includes(row.kind));
  const retryFailed = () => {
    const original = submittedRequests.get(task.id);
    requestDelete({
      targets: failed.map((row) => ({ kind: row.kind as DeleteTarget['kind'], id: row.targetId })),
      title: `${failed.length} 个失败项目`,
      names: Object.fromEntries(failed.map((row) => [row.targetId, row.path ? shownPath(row.path) : names?.[row.targetId] ?? `ID ${row.targetId}`])),
      includesFolders: failed.some((row) => row.kind !== 'image'),
      libraryName: original?.libraryName ?? libraries.value.find((lib) => lib.id === task.scope.library_id)?.name,
      onDone: original?.onDone,
    });
  };
  return (
    <div class="report">
      <div class="report-summary">
        {(counts.done > 0 || !(counts.failed || counts.skipped)) && (
          <span class="ok"><Icon name="Check" size={16} />{recycle ? '已移到回收站' : '已删除'} {counts.done}</span>
        )}
        {counts.failed > 0 && <span class="bad"><Icon name="CircleAlert" size={16} />失败 {counts.failed}</span>}
        {counts.skipped > 0 && <span class="warn"><Icon name="Circle" size={16} />未执行 {counts.skipped}</span>}
      </div>
      {task.state !== 'completed' && (
        <div class="report-note">
          <p class="hint">
            {task.state === 'cancelled' ? '任务已取消：取消前已处理的项目保持现状，其余项目没有执行。'
              : `任务${task.state === 'failed' ? '中途失败' : '被中断'}：已处理的项目见下表，其余项目没有执行。`}
          </p>
          {task.error && <p class="report-task-error" title={readableError(task.error)}>{readableError(task.error)}</p>}
        </div>
      )}
      <ul class="report-rows">
        {rows.slice(0, limit).map((row, index) => {
          const name = row.path ? shownPath(row.path) : names?.[row.targetId];
          return (
            <li key={row.targetId + index} class={`report-row ${row.state}`}>
              <span class="report-state">{ROW_TEXT[row.state]}</span>
              <span class="report-kind">{KIND_TEXT[row.kind] || row.kind}</span>
              <span class={`report-path${name ? '' : ' muted'}`} title={row.path || (name ? undefined : `ID ${row.targetId}`)}>
                {name ?? `名称不可用 · ${row.targetId.slice(0, 8)}`}
              </span>
              {row.error && <span class="report-error" title={readableError(row.error)}>{readableError(row.error)}</span>}
            </li>
          );
        })}
      </ul>
      {rows.length > limit && <button class="btn small" onClick={() => setLimit(limit + 200)}>显示更多（还有 {rows.length - limit} 项）</button>}
      {failed.length > 0 && <button class="btn small" onClick={retryFailed}><Icon name="RotateCcw" size={14} />只重试失败项</button>}
    </div>
  );
}

function RunningOrReport({ task, names }: { task: Task; names?: Record<string, string> }) {
  if (isActive(task)) {
    return (
      <div class="delete-running">
        <TaskProgress task={task} label="正在删除" />
        <p class="hint">可以关闭此窗口，删除会在后台继续；完成后会提示结果。</p>
      </div>
    );
  }
  return <ReportList task={task} names={names} />;
}

export function DeleteDialog({ request }: { request: DeleteRequestState }) {
  const [permanent, setPermanent] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [task, setTask] = useState<Task | null>(null);
  const close = () => { dialog.value = null; };

  useEffect(() => {
    if (!task) return;
    return watchTask(task.id, setTask);
  }, [task?.id]);

  const submit = async () => {
    if (busy || (permanent && !confirmed)) return;
    setBusy(true); setError('');
    try {
      const accepted = await client.request('post', '/api/v1/operations/delete', {
        body: { targets: request.targets, permanent, confirm_permanent: permanent && confirmed },
      });
      setTask(accepted);
      rememberRequest(accepted.id, request);
      follow(accepted.id, request);
    } catch (failure) {
      setError(statusOf(failure) === 404 ? '部分目标已不在索引中（可能已被删除或移动），请刷新后重新选择。' : describeError(failure));
    } finally { setBusy(false); }
  };

  if (task) {
    const finished = !isActive(task);
    return (
      <Dialog title={finished ? '删除结果' : '正在删除'} onClose={close} wide
        footer={<button class="btn" onClick={close}>{finished ? '完成' : '在后台继续'}</button>}>
        <p class="delete-what">{request.title}</p>
        <RunningOrReport task={task} names={request.names} />
      </Dialog>
    );
  }

  return (
    <Dialog title="确认删除" onClose={close} locked={busy}
      footer={(
        <>
          <button class="btn" onClick={close} disabled={busy} autoFocus>取消</button>
          <button class="btn danger" onClick={submit} disabled={busy || (permanent && !confirmed)}>
            {busy ? <Icon name="LoaderCircle" spin /> : <Icon name="Trash2" />}{permanent ? '永久删除' : '移到回收站'}
          </button>
        </>
      )}>
      <p class="delete-what">将删除：<strong>{request.title}</strong></p>
      {request.libraryName && <p class="muted delete-library">图库：{request.libraryName}</p>}
      <ul class="delete-targets" aria-label="删除目标">{request.targets.map((target) => (
        <li key={target.id}><span class="muted">{KIND_TEXT[target.kind]}</span><span>{request.names?.[target.id] ?? `ID ${target.id}`}</span></li>
      ))}</ul>
      {request.includesFolders && <p class="hint">图包和文件夹会连同其中的全部文件（包括非图片文件）一起删除。</p>}
      <p class="hint">默认移到 Windows 回收站，操作日志保留。</p>
      <label class="permanent-option"><input type="checkbox" checked={permanent} onChange={(event) => { setPermanent(event.currentTarget.checked); setConfirmed(false); }} />永久删除，不经过回收站</label>
      {permanent && (
        <label class="confirm-permanent">
          <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.currentTarget.checked)} />
          <span>我确认永久删除这些文件，且无法恢复</span>
        </label>
      )}
      <p class="hint">提交后由后台任务逐项执行；结果会逐项列出，失败的项目保持原状。</p>
      {error && <p class="form-error" role="alert"><Icon name="CircleAlert" size={16} />{error}</p>}
    </Dialog>
  );
}

export function DeleteReportDialog({ taskId }: { taskId: string }) {
  const [task, setTask] = useState<Task | null | undefined>(undefined);
  const [error, setError] = useState('');
  const close = () => { dialog.value = null; };
  useEffect(() => {
    setTask(undefined);
    refreshTask(taskId).then(setTask).catch((failure) => setError(describeError(failure)));
    return watchTask(taskId, setTask, () => setTask(null));
  }, [taskId]);
  return (
    <Dialog title="删除结果" onClose={close} wide footer={<button class="btn" onClick={close}>关闭</button>}>
      {error && <p class="form-error"><Icon name="CircleAlert" size={16} />{error}</p>}
      {task === null && <p class="muted">这个任务的记录已不存在。</p>}
      {task === undefined && !error && <p class="muted"><Icon name="LoaderCircle" spin size={16} /> 正在读取…</p>}
      {task && <RunningOrReport task={task} names={submittedRequests.get(taskId)?.names} />}
    </Dialog>
  );
}
