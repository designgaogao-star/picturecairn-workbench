import type { Task } from '../api';

export const KIND_LABEL: Record<string, string> = {
  scan: '扫描目录', prewarm: '生成缩略图', collect: '清理缓存', delete: '删除', build: '建立指纹',
  analyze: '相似分析', compare: '整包核验', audit: '清理检查', migrate: '导入旧数据',
};

export const STATE_LABEL: Record<Task['state'], string> = {
  queued: '排队中', running: '进行中', paused: '已暂停', cancelling: '正在取消',
  cancelled: '已取消', completed: '已完成', failed: '失败', interrupted: '已中断',
};

export const kindLabel = (kind: string) => KIND_LABEL[kind] || kind;

/** 0..1 when the task reports a total, otherwise null (indeterminate). */
export function taskFraction(task: Task): number | null {
  if (task.state === 'completed') return 1;
  if (!task.total) return null;
  return Math.max(0, Math.min(1, task.progress / task.total));
}

/** Final counters remain available after completion or cancellation. */
export function taskProgressText(task: Task): string {
  if (task.total) return `${task.progress} / ${task.total}`;
  if (task.progress) return `${task.progress}`;
  return '';
}

/** Pause is offered for long read-only jobs; deletes run to completion or are cancelled. */
export const canPause = (task: Task) => task.kind !== 'delete' && (task.state === 'running' || task.state === 'queued');
export const canResume = (task: Task) => task.state === 'paused';
export const canCancel = (task: Task) => ['queued', 'running', 'paused'].includes(task.state);
