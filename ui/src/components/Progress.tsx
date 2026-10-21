import { isActive, type Task } from '../api';
import { readableError } from '../lib/format';
import { kindLabel, STATE_LABEL, taskFraction, taskProgressText } from '../lib/tasks';

export function ProgressBar({ fraction, tone }: { fraction: number | null; tone?: 'ok' | 'bad' | 'warn' }) {
  return (
    <div class={`progress ${fraction === null ? 'indeterminate' : ''} ${tone || ''}`} role="progressbar"
      aria-valuemin={0} aria-valuemax={100} aria-valuenow={fraction === null ? undefined : Math.round(fraction * 100)}>
      <span style={fraction === null ? undefined : { width: `${Math.round(fraction * 1000) / 10}%` }} />
    </div>
  );
}

export function taskTone(task: Task): 'ok' | 'bad' | 'warn' | undefined {
  if (task.state === 'failed' || task.state === 'interrupted') return 'bad';
  if (task.state === 'cancelled' || task.state === 'paused' || task.state === 'cancelling') return 'warn';
  if (task.state === 'completed') return 'ok';
  return undefined;
}

/** Compact live progress of one task: state, counts, current file and a bar. */
export function TaskProgress({ task, label }: { task: Task; label?: string }) {
  const fraction = task.state === 'queued' ? 0 : taskFraction(task);
  const text = taskProgressText(task);
  return (
    <div class="task-progress">
      <div class="task-progress-line">
        <span class="task-kind">{label ?? kindLabel(task.kind)}</span>
        <span class={`task-state ${task.state}`}>{STATE_LABEL[task.state]}</span>
        {text && <span class="muted num">{text}</span>}
      </div>
      <ProgressBar fraction={fraction} tone={taskTone(task)} />
      {task.current && isActive(task) && <div class="task-current muted" title={task.current}>{task.current}</div>}
      {task.error && <div class="task-error" title={readableError(task.error)}>{readableError(task.error)}</div>}
    </div>
  );
}
