import type { ComponentChildren } from 'preact';
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'preact/hooks';
import { Icon } from '../lib/icons';
import { keyboardOwnedElsewhere } from '../lib/keys';
import type { PagedList } from '../lib/paged';
import { toast } from '../state/app';

export interface Selection {
  active: boolean;
  ids: Set<string>;
  start: () => void;
  stop: () => void;
  toggle: (id: string, range?: boolean) => void;
  clear: () => void;
  remove: (ids: Set<string>) => void;
  selectVisible: () => void;
}

/** Selection mode for batch actions; Escape leaves it. Bounded to `max` items per batch. */
export function useSelection<T extends { id: string }>(scope: string, list: PagedList<T>, selectable: (item: T) => boolean = () => true, max = 500) {
  const [active, setActive] = useState(false);
  const [items, setItems] = useState<Map<string, T>>(new Map());
  const ids = useMemo(() => new Set(items.keys()), [items]);
  const anchor = useRef<string | null>(null);
  const visible = useRef<[number, number]>([0, 0]);
  useLayoutEffect(() => { setActive(false); setItems(new Map()); anchor.current = null; }, [scope]);
  useEffect(() => {
    if (!active) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !keyboardOwnedElsewhere(event)) { setActive(false); setItems(new Map()); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [active]);
  const add = (indices: Iterable<number>) => {
    const next = new Map(items);
    let limited = false;
    for (const index of indices) {
      const item = list.item(index);
      if (!item) { toast('范围中有尚未加载的项目，只选择已加载的连续项'); break; }
      if (!selectable(item) || next.has(item.id)) continue;
      if (next.size >= max) { limited = true; break; }
      next.set(item.id, item);
    }
    if (limited) toast(`每批最多选择 ${max} 项`);
    setItems(next); setActive(true);
  };
  const selection: Selection & { items: Map<string, T>; onVisibleChange: (start: number, end: number) => void } = {
    active, ids, items,
    start: () => setActive(true),
    stop: () => { setActive(false); setItems(new Map()); },
    toggle: (id, range = false) => {
      const index = list.indexOf((item) => item.id === id);
      if (index < 0) return;
      const previousIndex = anchor.current ? list.indexOf((item) => item.id === anchor.current) : -1;
      if (range && previousIndex >= 0) {
        const indices = [];
        const dir = index >= previousIndex ? 1 : -1;
        for (let at = previousIndex; dir > 0 ? at <= index : at >= index; at += dir) {
          indices.push(at);
          if (!list.item(at) || indices.length > max) break;
        }
        add(indices);
      } else if (items.has(id)) { const next = new Map(items); next.delete(id); setItems(next); setActive(true); }
      else add([index]);
      anchor.current = id;
    },
    clear: () => setItems(new Map()),
    remove: (done) => {
      setItems((old) => new Map([...old].filter(([id]) => !done.has(id))));
    },
    selectVisible: () => {
      const [start, end] = visible.current;
      add(Array.from({ length: end - start }, (_, index) => start + index));
    },
    onVisibleChange: (start, end) => { visible.current = [start, end]; },
  };
  return selection;
}

export function SelectionBar({ selection, noun, unit = '个', onDelete, children, before, after }: {
  selection: Selection; noun: string; unit?: string; onDelete: () => void; children?: ComponentChildren; before?: ComponentChildren; after?: ComponentChildren;
}) {
  if (!selection.active) {
    return (
      <div class="toolbar">
        {children}
        <span class="spacer" />
        {before}
        <button class="btn subtle small" onClick={selection.start}><Icon name="SquareCheck" size={14} /><span class="label-wide">选择</span></button>
        {after}
      </div>
    );
  }
  return (
    <div class="toolbar selecting" role="toolbar" aria-label="批量操作">
      <span>已选 <strong>{selection.ids.size}</strong> {unit}{noun}</span>
      <button class="btn subtle small" onClick={selection.selectVisible}>选中可见项</button>
      {selection.ids.size > 0 && <button class="btn subtle small" onClick={selection.clear}>清空</button>}
      <span class="spacer" />
      <button class="btn small danger" disabled={!selection.ids.size} onClick={onDelete}><Icon name="Trash2" size={14} />删除…</button>
      <button class="btn small" onClick={selection.stop}>完成</button>
    </div>
  );
}
