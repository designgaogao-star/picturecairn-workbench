import type { ComponentChildren } from 'preact';
import { useEffect, useLayoutEffect, useRef, useState } from 'preact/hooks';
import type { PagedList } from '../lib/paged';
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
  empty?: ComponentChildren;
  class?: string;
  label?: string;
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
  useLayoutEffect(() => { anchor.current = anchors.get(anchorKey) ?? 0; restored.current = false; }, [anchorKey]);

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
    anchor.current = Math.min(anchor.current, Math.max(0, total - 1));
    element.scrollTop = Math.floor(anchor.current / columns) * rowHeight;
    measure();
  }, [columns, rowHeight, total === null, anchorKey]);

  useLayoutEffect(() => {
    const element = scroller.current;
    if (reveal == null || !element || !rowHeight || total === null) return;
    const top = pad + Math.floor(reveal / columns) * rowHeight;
    if (top < element.scrollTop || top + rowHeight > element.scrollTop + element.clientHeight) {
      element.scrollTop = Math.max(0, top - (element.clientHeight - rowHeight) / 2);
      measure();
    }
  }, [reveal, columns, rowHeight, total === null]);

  const overscan = 2;
  const firstRow = Math.min(Math.max(0, rowCount - 1), Math.max(0, rows[0] - overscan));
  const lastRow = Math.min(Math.max(0, rowCount - 1), rows[1] + overscan);

  useEffect(() => {
    if (!size.width) return;
    list.ensure(firstRow * columns, (lastRow + 1) * columns, consumer);
  }, [list, firstRow, lastRow, columns, size.width, list.version.value]);
  useEffect(() => () => list.release(consumer), [list]);

  useEffect(() => () => cancelAnimationFrame(frame.current), []);
  const onScroll = () => {
    cancelAnimationFrame(frame.current);
    frame.current = requestAnimationFrame(() => {
      const element = scroller.current;
      // Resize can dispatch scroll before ResizeObserver has updated the grid tracks.
      if (!element || element.clientWidth !== size.width || element.clientHeight !== size.height) return;
      const first = measure();
      if (first !== undefined && restored.current && total !== null) {
        anchor.current = first * columns;
        rememberAnchor(anchorKey, anchor.current);
      }
    });
  };

  const cells = [];
  if (size.width && (total ?? 1) > 0) {
    const end = total === null ? (lastRow + 1) * columns : Math.min(total, (lastRow + 1) * columns);
    for (let index = firstRow * columns; index < end; index++) {
      const item = total === null ? undefined : list.item(index);
      const row = Math.floor(index / columns), column = index % columns;
      cells.push(
        <div key={item ? keyOf(item) : `#${index}`} class="vgrid-cell" role="listitem" style={{
          width: `${tileWidth}px`, height: `${tileHeight}px`,
          transform: `translate(${pad + column * (tileWidth + gap)}px, ${pad + row * rowHeight}px)`,
        }}>{render(item, index, layout)}</div>,
      );
    }
  }

  return (
    <div class={`vgrid-wrap ${props.class || ''}`}>
      <div class="vgrid" ref={scroller} onScroll={onScroll}>
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
