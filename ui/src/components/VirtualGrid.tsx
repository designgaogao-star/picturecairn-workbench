import type { ComponentChildren } from 'preact';
import { useEffect, useLayoutEffect, useRef, useState } from 'preact/hooks';
import type { PagedList } from '../lib/paged';
import { plainKey } from '../lib/keys';
import { narrow } from '../state/app';

export interface GridLayout { columns: number; tileWidth: number; tileHeight: number; rowHeight: number; gap: number; pad: number }

// First visible index per list, so returning to a wall (or reloading) lands where the user left it.
const anchors = new Map<string, number>();
try { for (const [key, index] of JSON.parse(localStorage.getItem('gt.anchors') || '[]')) anchors.set(key, index); } catch { /* ignore */ }
let persistTimer = 0;
function rememberAnchor(key: string, index: number) {
  anchors.delete(key);
  anchors.set(key, index);
  while (anchors.size > 80) anchors.delete(anchors.keys().next().value as string);
  clearTimeout(persistTimer);
  persistTimer = window.setTimeout(() => {
    try { localStorage.setItem('gt.anchors', JSON.stringify([...anchors])); } catch { /* ignore */ }
  }, 800);
}
export const anchorOf = (key: string) => anchors.get(key);
let consumers = 0;

interface Props<T> {
  list: PagedList<T>;
  /** Target tile width in CSS pixels; columns are derived from the available width. */
  tile: number;
  /** Tile height for a given tile width. */
  height: (tileWidth: number) => number;
  gap?: number;
  pad?: number;
  keyOf: (item: T) => string;
  render: (item: T | undefined, index: number, layout: GridLayout) => ComponentChildren;
  anchorKey: string;
  /** Index to bring into view when it changes. */
  reveal?: number | null;
  /** Called once the requested item has been positioned, so a one-time request can be cleared. */
  onReveal?: () => void;
  /** Resource to return keyboard focus to after the viewer closes. */
  focusKey?: string | null;
  empty?: ComponentChildren;
  class?: string;
  label?: string;
  onVisibleChange?: (start: number, end: number) => void;
}

/**
 * Virtualized grid over a PagedList. Only rows near the viewport are rendered and only their
 * pages are requested; the first visible index is kept as the scroll anchor across resizes.
 */
export function VirtualGrid<T>(props: Props<T>) {
  const { list, tile, height, gap = narrow.value ? 8 : 12, pad = narrow.value ? 12 : 16, keyOf, render, anchorKey, reveal, empty } = props;
  const scroller = useRef<HTMLDivElement>(null);
  const frame = useRef(0);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [rows, setRows] = useState<[number, number]>([0, 0]);
  const anchor = useRef(anchors.get(anchorKey) ?? 0);
  const restored = useRef(false);
  const focused = useRef<string | null>(null);
  const cursor = useRef<{ index: number; key: string } | null>(null);
  const cursorVisible = useRef(false);
  const intent = useRef<number | null>(null);
  const [navigation, setNavigation] = useState<number | null>(null);
  const [consumer] = useState(() => `grid${++consumers}`);
  const total = list.total.value;
  list.version.value; // re-render when pages arrive or go stale
  const error = list.error.value;

  const inner = Math.max(0, size.width - pad * 2);
  const columns = Math.max(1, Math.floor((inner + gap) / (tile + gap)));
  const tileWidth = columns ? (inner - gap * (columns - 1)) / columns : 0;
  const tileHeight = Math.round(height(tileWidth));
  const rowHeight = tileHeight + gap;
  const layout: GridLayout = { columns, tileWidth, tileHeight, rowHeight, gap, pad };
  const rowCount = total === null ? Math.ceil(size.height / Math.max(1, rowHeight)) : Math.ceil(total / columns);

  useLayoutEffect(() => {
    const element = scroller.current!;
    const observer = new ResizeObserver(() => setSize({ width: element.clientWidth, height: element.clientHeight }));
    observer.observe(element);
    setSize({ width: element.clientWidth, height: element.clientHeight });
    return () => observer.disconnect();
  }, []);

  // New list: restore its anchor once its length is known.
  useLayoutEffect(() => {
    anchor.current = anchors.get(anchorKey) ?? 0;
    restored.current = false;
    cursor.current = null;
    cursorVisible.current = false;
    intent.current = null;
    setNavigation(null);
  }, [anchorKey]);

  const measure = () => {
    const element = scroller.current;
    if (!element || !rowHeight) return;
    const top = Math.max(0, element.scrollTop - pad);
    const first = Math.floor(top / rowHeight);
    const last = Math.floor((top + element.clientHeight) / rowHeight);
    setRows((old) => (old[0] === first && old[1] === last ? old : [first, last]));
    return first;
  };

  // Keep the anchor item in place when the column count or tile size changes, and restore it on mount.
  useLayoutEffect(() => {
    const element = scroller.current;
    if (!element || !size.width || !rowHeight) return;
    cancelAnimationFrame(frame.current);
    if (total === null) { measure(); return; }
    if (!restored.current) restored.current = true;
    if (cursor.current && cursorVisible.current && element.contains(document.activeElement)) {
      anchor.current = cursor.current.index;
      intent.current = Math.min(cursor.current.index, Math.max(0, total - 1));
      setNavigation(intent.current);
      element.focus({ preventScroll: true });
    }
    anchor.current = Math.min(anchor.current, Math.max(0, total - 1));
    element.scrollTop = Math.floor(anchor.current / columns) * rowHeight;
    measure();
  }, [columns, rowHeight, total === null, anchorKey]);

  useLayoutEffect(() => {
    const element = scroller.current;
    if (reveal == null || !element || !size.width || !rowHeight || total === null || !total) return;
    const top = pad + Math.floor(reveal / columns) * rowHeight;
    if (top < element.scrollTop || top + rowHeight > element.scrollTop + element.clientHeight) {
      element.scrollTop = Math.max(0, top - (element.clientHeight - rowHeight) / 2);
      measure();
    }
    props.onReveal?.();
  }, [reveal, columns, rowHeight, total === null, size.width]);

  const overscan = 2;
  useLayoutEffect(() => {
    props.onVisibleChange?.(rows[0] * columns, Math.min(total ?? 0, (rows[1] + 1) * columns));
  }, [rows[0], rows[1], columns, total, props.onVisibleChange]);
  const firstRow = Math.min(Math.max(0, rowCount - 1), Math.max(0, rows[0] - overscan));
  const lastRow = Math.min(Math.max(0, rowCount - 1), rows[1] + overscan);

  useEffect(() => {
    if (!size.width) return;
    list.ensure(firstRow * columns, (lastRow + 1) * columns, consumer);
  }, [list, firstRow, lastRow, columns, size.width, list.version.value]);
  useEffect(() => () => list.release(consumer), [list]);
  useEffect(() => {
    if (navigation === null) list.release(`${consumer}:focus`);
    else list.ensure(navigation, navigation + 1, `${consumer}:focus`);
    return () => list.release(`${consumer}:focus`);
  }, [list, navigation, list.version.value]);

  useEffect(() => () => cancelAnimationFrame(frame.current), []);
  const onScroll = () => {
    cancelAnimationFrame(frame.current);
    frame.current = requestAnimationFrame(() => {
      const element = scroller.current;
      // Resize can dispatch scroll before ResizeObserver has updated the grid tracks.
      if (!element || element.clientWidth !== size.width || element.clientHeight !== size.height) return;
      const first = measure();
      if (first !== undefined && restored.current && total !== null) {
        if (intent.current === null && cursor.current) {
          const last = Math.floor((Math.max(0, element.scrollTop - pad) + element.clientHeight) / rowHeight);
          cursorVisible.current = cursor.current.index >= first * columns && cursor.current.index < (last + 1) * columns;
        }
        anchor.current = first * columns;
        rememberAnchor(anchorKey, anchor.current);
      }
    });
  };

  const mainButton = (cell: Element) => cell.querySelector<HTMLButtonElement>('.card-hit, .group-row');
  const onFocus = (event: FocusEvent) => {
    const button = (event.target as HTMLElement).closest('.card-hit, .group-row');
    const cell = button?.closest<HTMLElement>('[data-grid-index]');
    if (!cell?.dataset.resourceId) return;
    cursor.current = { index: Number(cell.dataset.gridIndex), key: cell.dataset.resourceId };
    cursorVisible.current = true;
    for (const item of scroller.current!.querySelectorAll('.vgrid-cell')) {
      const main = mainButton(item);
      if (main) main.tabIndex = main === button ? 0 : -1;
    }
  };
  const onKeyDown = (event: KeyboardEvent) => {
    if (event.defaultPrevented || event.isComposing || !plainKey(event, true) || !total) return;
    const element = scroller.current!;
    const target = event.target as HTMLElement;
    if (target !== element && !target.matches('.card-hit, .group-row')) return;
    // A revision can move the focused resource while its keyed button keeps focus. Read the
    // current cell index from the DOM before calculating the next destination; the stored index
    // is only a fallback while the destination page is being fetched.
    const focusedCell = target.closest<HTMLElement>('.vgrid-cell[data-resource-id]');
    const liveIndex = focusedCell ? Number(focusedCell.dataset.gridIndex) : undefined;
    if (focusedCell?.dataset.resourceId && cursor.current?.key === focusedCell.dataset.resourceId && liveIndex !== undefined) {
      cursor.current.index = liveIndex;
    }
    const at = intent.current ?? liveIndex ?? cursor.current?.index;
    if (at === undefined) return;
    const page = columns * Math.max(1, Math.floor(size.height / rowHeight));
    const destinations: Record<string, number> = {
      ArrowLeft: at - 1, ArrowRight: at + 1, ArrowUp: at - columns, ArrowDown: at + columns,
      Home: 0, End: total - 1, PageUp: at - page, PageDown: at + page,
    };
    if (!(event.key in destinations)) return;
    event.preventDefault();
    const next = Math.max(0, Math.min(total - 1, destinations[event.key]));
    intent.current = next;
    setNavigation(next);
    // Keep key repeats attached to this grid while the destination page is loading.
    element.focus({ preventScroll: true });
    const top = pad + Math.floor(next / columns) * rowHeight;
    if (top < element.scrollTop) element.scrollTop = top;
    else if (top + tileHeight > element.scrollTop + element.clientHeight) element.scrollTop = top + tileHeight - element.clientHeight;
    measure();
  };

  const gridHadFocus = Boolean(scroller.current?.contains(document.activeElement));
  const cells = [];
  if (size.width && (total ?? 1) > 0) {
    const end = total === null ? (lastRow + 1) * columns : Math.min(total, (lastRow + 1) * columns);
    const indices = Array.from({ length: Math.max(0, end - firstRow * columns) }, (_, index) => firstRow * columns + index);
    // Retain the focused DOM node through track changes until its new row is brought into view.
    const activeKey = cursor.current?.key;
    const cachedActive = activeKey ? list.indexOf((item) => keyOf(item) === activeKey) : -1;
    if (cachedActive >= 0 && cursor.current) cursor.current.index = cachedActive;
    const active = cachedActive >= 0 ? cachedActive : cursor.current?.index;
    if (active !== undefined && active < (total ?? 0) && gridHadFocus && !indices.includes(active)) indices.push(active);
    for (const index of indices) {
      const item = total === null ? undefined : list.item(index);
      const row = Math.floor(index / columns), column = index % columns;
      cells.push(
        <div key={item ? keyOf(item) : `#${index}`} class="vgrid-cell" role="listitem" data-resource-id={item ? keyOf(item) : undefined}
          data-grid-index={index} aria-posinset={index + 1} aria-setsize={total ?? undefined} style={{
          width: `${tileWidth}px`, height: `${tileHeight}px`,
          transform: `translate(${pad + column * (tileWidth + gap)}px, ${pad + row * rowHeight}px)`,
        }}>{render(item, index, layout)}</div>,
      );
    }
  }

  useLayoutEffect(() => {
    const element = scroller.current!;
    const cells = [...element.querySelectorAll<HTMLElement>('.vgrid-cell[data-resource-id]')];
    const current = cursor.current && cells.find((cell) => cell.dataset.resourceId === cursor.current!.key);
    if (current && cursor.current) cursor.current.index = Number(current.dataset.gridIndex);
    // Reordering a keyed node can blur it when the browser moves that node in the DOM.
    if (current && gridHadFocus && document.activeElement === document.body) mainButton(current)?.focus({ preventScroll: true });
    const entry = current ?? cells.find((cell) => Number(cell.dataset.gridIndex) >= rows[0] * columns) ?? cells[0];
    for (const cell of cells) {
      const button = mainButton(cell);
      if (button) button.tabIndex = cell === entry ? 0 : -1;
    }
    if (navigation === null || document.activeElement !== element) return;
    const cell = cells.find((item) => Number(item.dataset.gridIndex) === navigation);
    const button = cell && mainButton(cell);
    if (button) {
      button.focus({ preventScroll: true });
      intent.current = null;
      setNavigation(null);
    }
  });

  useLayoutEffect(() => {
    const key = props.focusKey;
    if (!key) { focused.current = null; return; }
    if (focused.current === key) return;
    const target = scroller.current?.querySelector<HTMLButtonElement>(`[data-resource-id="${CSS.escape(key)}"] .card-hit`);
    if (target) { target.focus({ preventScroll: true }); focused.current = key; }
  }, [props.focusKey, list.version.value, firstRow, lastRow]);

  return (
    <div class={`vgrid-wrap ${props.class || ''}`}>
      <div class="vgrid" ref={scroller} onScroll={onScroll} tabIndex={-1} onKeyDown={onKeyDown}
        onFocusCapture={onFocus} onBlurCapture={(event) => {
          if (!scroller.current?.contains(event.relatedTarget as Node | null)) {
            intent.current = null;
            setNavigation(null);
          }
        }}>
        <div class="vgrid-space" role="list" aria-label={props.label} aria-busy={list.loading.value}
          style={{ height: `${pad * 2 + Math.max(0, rowCount * rowHeight - gap)}px` }}>
          {cells}
        </div>
      </div>
      {total === 0 && !error && <div class="vgrid-empty">{empty}</div>}
      {error && (
        <div class="vgrid-error" role="alert">
          <span>加载失败：{error}</span>
          <button class="btn small" onClick={() => list.retry()}>重试</button>
        </div>
      )}
    </div>
  );
}
