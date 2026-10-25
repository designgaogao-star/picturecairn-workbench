import type { Task } from '../api';
import { Icon, type IconName } from '../lib/icons';
import { canCancel, canPause, canResume } from '../lib/tasks';
import { controlTask, taskControls } from '../state/app';

export function TaskControls({ task, size = 'small' }: { task: Task; size?: 'small' | 'tiny' }) {
  const pending = taskControls.value[task.id];
  const controls: { action: 'pause' | 'resume' | 'cancel'; label: string; waiting: string; icon: IconName; enabled: boolean }[] = [
    { action: 'pause', label: '暂停', waiting: '暂停中…', icon: 'Pause', enabled: canPause(task) },
    { action: 'resume', label: '继续', waiting: '继续中…', icon: 'Play', enabled: canResume(task) },
    { action: 'cancel', label: '取消', waiting: '取消中…', icon: 'X', enabled: canCancel(task) },
  ];
  return <>{controls.filter((control) => control.enabled).map((control) => (
    <button key={control.action} class={`btn ${size}`} disabled={Boolean(pending)} aria-busy={pending === control.action}
      onClick={() => void controlTask(task.id, control.action)}>
      <Icon name={pending === control.action ? 'LoaderCircle' : control.icon} spin={pending === control.action} size={14} />
      {pending === control.action ? control.waiting : control.label}
    </button>
  ))}</>;
}
