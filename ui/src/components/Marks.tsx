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

export function MarkSegment({ groupId, value, compact, shortcuts = false, class: className = '' }: {
  groupId: string; value: Mark | undefined; compact?: boolean; shortcuts?: boolean; class?: string;
}) {
  return (
    <div class={`segment marks ${compact ? 'compact' : ''} ${className}`} role="radiogroup" aria-label="文件夹状态">
      {MARKS.map((mark) => (
        <button key={mark.value} role="radio" aria-label={mark.label} aria-checked={value === mark.value} title={shortcuts ? `${mark.label}（${mark.key}）` : mark.label}
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
