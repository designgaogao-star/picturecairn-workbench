import { useEffect, useLayoutEffect, useRef, useState } from 'preact/hooks';
import { imagesList } from '../state/app';
import { Thumb } from './Thumb';

const CELL = 72;
const GAP = 6;
const STEP = CELL + GAP;
const PAD = 8;
const OVERSCAN = 3;

interface Props {
  packageId: string;
  /** Index of the shown image in its package, -1 while unknown. */
  index: number;
  current: string;
  /** Thumbnails wait until the main image has loaded, so they never compete with it. */
  ready: boolean;
  onPick: (id: string) => void;
}

/** Horizontal, virtualized strip of the package's images around the one being viewed. */
export function Filmstrip({ packageId, index, current, ready, onPick }: Props) {
  const list = imagesList(packageId);
  const total = list.total.value;
  list.version.value;
  const ref = useRef<HTMLDivElement>(null);
  const [view, setView] = useState({ left: 0, width: 0 });
  const frame = useRef(0);

  useLayoutEffect(() => {
    const element = ref.current!;
    const observer = new ResizeObserver(() => setView({ left: element.scrollLeft, width: element.clientWidth }));
    observer.observe(element);
    return () => { observer.disconnect(); cancelAnimationFrame(frame.current); };
  }, []);

  // Keep the current image in the middle; long jumps scroll instantly instead of animating through.
  useLayoutEffect(() => {
    const element = ref.current;
    if (!element || index < 0 || !view.width || total === null) return;
    const target = Math.max(0, PAD + index * STEP + CELL / 2 - element.clientWidth / 2);
    const distance = Math.abs(element.scrollLeft - target);
    if (distance > 1) element.scrollTo({ left: target, behavior: distance < element.clientWidth * 1.5 && !matchMedia('(prefers-reduced-motion: reduce)').matches ? 'smooth' : 'auto' });
  }, [index, view.width > 0, total === null]);

  const known = view.width > 0 && total !== null;
  const first = known ? Math.max(0, Math.floor((view.left - PAD) / STEP) - OVERSCAN) : Math.max(0, index - 10);
  const last = known ? Math.min(total - 1, Math.ceil((view.left + view.width) / STEP) + OVERSCAN) : Math.max(0, index) + 10;

  useEffect(() => { list.ensure(first, last + 1, 'filmstrip'); }, [list, first, last, list.version.value]);
  useEffect(() => () => list.release('filmstrip'), [list]);

  const onScroll = () => {
    cancelAnimationFrame(frame.current);
    frame.current = requestAnimationFrame(() => {
      const element = ref.current;
      if (element) setView({ left: element.scrollLeft, width: element.clientWidth });
    });
  };
  const onWheel = (event: WheelEvent) => {
    const element = ref.current;
    if (!element || Math.abs(event.deltaY) <= Math.abs(event.deltaX)) return;
    event.preventDefault();
    element.scrollLeft += event.deltaY;
  };

  const cells = [];
  if (total !== null) {
    for (let i = first; i <= last && i < total; i++) {
      const item = list.item(i);
      const style = { transform: `translateX(${PAD + i * STEP}px)` };
      if (!item) { cells.push(<div key={`#${i}`} class="film-cell skeleton" style={style} />); continue; }
      const active = item.id === current;
      cells.push(
        <button key={item.id} class={`film-cell ${active ? 'active' : ''}`} style={style} title={`${i + 1}. ${item.name}`}
          aria-label={`第 ${i + 1} 张：${item.name}`} aria-current={active ? 'true' : undefined} onClick={() => onPick(item.id)}>
          {ready || active ? <Thumb id={item.id} edge={400} retryButton={false} /> : <span class="film-wait" />}
        </button>,
      );
    }
  }

  return (
    <div class="filmstrip" ref={ref} onScroll={onScroll} onWheel={onWheel} aria-label="本图包图片">
      <div class="film-space" style={{ width: `${PAD * 2 + Math.max(0, (total ?? 0) * STEP - GAP)}px` }}>{cells}</div>
    </div>
  );
}
