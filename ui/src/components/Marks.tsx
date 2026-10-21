import type { Mark } from '../api';
import { Icon, type IconName } from '../lib/icons';
import { reportError, setMark } from '../state/app';

export const MARKS: { value: Mark; label: string; icon: IconName; key: string }[] = [
  { value: 'none', label: '未标记', icon: 'Circle', key: 'U' },
  { value: 'kept', label: '保留', icon: 'Check', key: 'K' },
  { value: 'marked', label: '待整理', icon: 'Flag', key: 'M' },
];

export const markLabel = (mark: string) => MARKS.find((item) => item.value === mark)?.label ?? mark;

/** Applies a mark from a shortcut; repeated keydown events are ignored by the caller. */
export function applyMark(groupId: string, mark: Mark) {
  setMark(groupId, mark).catch((error) => reportError(error, '保存标记失败：'));
}

export function MarkSegment({ groupId, value, compact }: { groupId: string; value: Mark | undefined; compact?: boolean }) {
  return (
    <div class={`segment marks ${compact ? 'compact' : ''}`} role="radiogroup" aria-label="整理状态">
      {MARKS.map((mark) => (
        <button key={mark.value} role="radio" aria-checked={value === mark.value} title={`${mark.label}（${mark.key}）`}
          class={`mark-${mark.value} ${value === mark.value ? 'active' : ''}`} onClick={() => applyMark(groupId, mark.value)}>
          <Icon name={mark.icon} size={16} />{!compact && <span>{mark.label}</span>}
        </button>
      ))}
    </div>
  );
}

export function MarkBadge({ state }: { state: string }) {
  if (state === 'kept') return <span class="badge mark-kept" title="保留"><Icon name="Check" size={12} />保留</span>;
  if (state === 'marked') return <span class="badge mark-marked" title="待整理"><Icon name="Flag" size={12} />待整理</span>;
  return null;
}
