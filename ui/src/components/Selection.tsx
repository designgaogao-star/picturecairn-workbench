import type { ComponentChildren } from 'preact';
import { useEffect, useState } from 'preact/hooks';
import { Icon } from '../lib/icons';

export interface Selection {
  active: boolean;
  ids: Set<string>;
  start: () => void;
  stop: () => void;
  toggle: (id: string) => void;
  clear: () => void;
}

/** Selection mode for batch actions; Escape leaves it. Bounded to `max` items per batch. */
export function useSelection(scope: string, max = 500): Selection {
  const [active, setActive] = useState(false);
  const [ids, setIds] = useState<Set<string>>(new Set());
  useEffect(() => { setActive(false); setIds(new Set()); }, [scope]);
  useEffect(() => {
    if (!active) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !document.querySelector('dialog[open]')) { setActive(false); setIds(new Set()); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [active]);
  return {
    active, ids,
    start: () => setActive(true),
    stop: () => { setActive(false); setIds(new Set()); },
    toggle: (id) => setIds((old) => {
      const next = new Set(old);
      if (next.has(id)) next.delete(id);
      else if (next.size < max) next.add(id);
      return next;
    }),
    clear: () => setIds(new Set()),
  };
}

export function SelectionBar({ selection, noun, unit = '个', onDelete, children }: {
  selection: Selection; noun: string; unit?: string; onDelete: () => void; children?: ComponentChildren;
}) {
  if (!selection.active) {
    return (
      <div class="wall-bar">
        {children}
        <span class="spacer" />
        <button class="btn small" onClick={selection.start}><Icon name="ListChecks" size={14} />选择</button>
      </div>
    );
  }
  return (
    <div class="wall-bar selecting" role="toolbar" aria-label="批量操作">
      <span>已选 <strong>{selection.ids.size}</strong> {unit}{noun}</span>
      {selection.ids.size > 0 && <button class="btn small" onClick={selection.clear}>清空</button>}
      <span class="spacer" />
      <button class="btn small danger" disabled={!selection.ids.size} onClick={onDelete}><Icon name="Trash2" size={14} />删除…</button>
      <button class="btn small" onClick={selection.stop}>完成</button>
    </div>
  );
}
