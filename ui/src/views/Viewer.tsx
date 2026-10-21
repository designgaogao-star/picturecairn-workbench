import type { JSX } from 'preact';
import { useEffect, useLayoutEffect, useRef, useState } from 'preact/hooks';
import {
  client, describeError, isAbort, originalUrl, pickEdge, statusOf, thumbnailUrl,
  type Edge, type ImageContext, type ImageItem, type Mark,
} from '../api';
import { Filmstrip } from '../components/Filmstrip';
import { applyMark, MarkSegment } from '../components/Marks';
import { knownThumb, noteThumb, probeImage } from '../components/Thumb';
import { bytes, count, extension } from '../lib/format';
import { Icon } from '../lib/icons';
import { keyboardOwnedElsewhere, plainKey } from '../lib/keys';
import { Lru } from '../lib/paged';
import { closeViewer, navigate, route, type Route } from '../lib/router';
import {
  currentGroup, currentLibrary, currentPackage, imageAt, imagesList, lastViewed, mediaEpoch, narrow, neighborPackage,
  reportError, requestDelete, savePosition, toast,
} from '../state/app';
import { samples, useSamples } from './Samples';

type Source = { kind: 'preview'; edge: Edge; url: string } | { kind: 'original'; url: string };
/** A decoded layer. `w`/`h` are the element's natural size; `exact` when that is the file's real size. */
interface Shown { id: string; source: Source; src: string; w: number; h: number; exact: boolean }
interface Loading { id: string; source: Source; attempt: number }
interface Failure { id: string; source: Source; attempt: number; text: string }
interface ViewState { id: string; zoom: number | 'fit'; x: number; y: number; rot: number }
interface Size { w: number; h: number }
interface Gesture { kind: 'pan' | 'pinch' | 'swipe'; x: number; y: number; panX: number; panY: number; scale: number; distance: number; time: number; touch: boolean }

const MB = 1024 * 1024;
const contexts = new Lru<ImageContext>(300);
// Preloaded neighbours stay referenced so the browser keeps them decoded until they are shown.
const warm = new Lru<HTMLImageElement>(4);
// Images whose context was reread once their first preview had filled in missing metadata.
const reread = new Lru<true>(500);

const original = (id: string): Source => ({ kind: 'original', url: originalUrl(id) });
const srcOf = (source: Source, attempt: number) => (attempt ? `${source.url}${source.url.includes('?') ? '&' : '?'}attempt=${attempt}` : source.url);

/** Animations (or possible ones while metadata is missing) and files the backend could not preview need the original. */
function needsOriginal(image: ImageItem): boolean {
  if (image.animated) return true;
  if (image.animated == null && ['gif', 'webp'].includes(extension(image.name))) return true;
  return Boolean(image.error);
}

/** Smallest source that covers `needed` device pixels on the longest side. */
function chooseSource(image: ImageItem, needed: number): Source {
  if (needsOriginal(image) || needed > 4200) return original(image.id);
  const edge = pickEdge(needed);
  if (image.width && image.height && Math.max(image.width, image.height) <= edge) return original(image.id);
  return { kind: 'preview', edge, url: thumbnailUrl(image.id, edge) };
}

/** Shrink-only fit: an image smaller than the stage is shown at 100%. */
function fitScale(w: number, h: number, rot: number, stage: Size): number {
  const [rw, rh] = rot % 180 ? [h, w] : [w, h];
  return Math.min(stage.w / rw, stage.h / rh, 1);
}

/** Keeps the image covering the stage while panning; an axis that fits stays centred. */
function clampPan(x: number, y: number, w: number, h: number, rot: number, scale: number, stage: Size) {
  const [rw, rh] = rot % 180 ? [h, w] : [w, h];
  const maxX = Math.max(0, (rw * scale - stage.w) / 2);
  const maxY = Math.max(0, (rh * scale - stage.h) / 2);
  return { x: Math.max(-maxX, Math.min(maxX, x)), y: Math.max(-maxY, Math.min(maxY, y)) };
}

function freshContext(id: string): ImageContext | undefined {
  const context = contexts.get(id);
  const revision = currentLibrary.value?.revision;
  return context && (revision === undefined || context.revision >= revision) ? context : undefined;
}

async function fetchContext(id: string, signal?: AbortSignal): Promise<ImageContext> {
  const context = await client.request('get', '/api/v1/images/{image_id}/context', { params: { path: { image_id: id } }, signal });
  contexts.set(id, context);
  return context;
}

function preload(url: string, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    const element = new Image();
    element.decoding = 'async';
    const finish = () => { signal.removeEventListener('abort', abort); resolve(); };
    const abort = () => { element.removeAttribute('src'); finish(); };
    element.onload = () => { warm.set(url, element); void element.decode().catch(() => undefined).then(finish); };
    element.onerror = finish;
    signal.addEventListener('abort', abort, { once: true });
    element.src = url;
  });
}

function LayerImage({ src, alt, onReady, onFail }: { src: string; alt: string; onReady?: (element: HTMLImageElement) => void; onFail?: () => void }) {
  const ref = useRef<HTMLImageElement>(null);
  // Leaving the DOM mid-load drops the request instead of letting it finish in the background.
  useEffect(() => {
    const element = ref.current;
    return () => { if (element && !element.complete) element.removeAttribute('src'); };
  }, []);
  return (
    <img ref={ref} class="layer" src={src} alt={alt} draggable={false} decoding="async"
      onLoad={onReady && ((event) => onReady(event.currentTarget))} onError={onFail} />
  );
}

export function Viewer() {
  const r = route.value;
  const imageId = r.image!;
  const groupId = r.group;
  const samplesMode = r.view === 'samples' && !r.package;
  // Opened from the organize page: moves keep it underneath, so closing returns to the evidence.
  const keep: Partial<Route> = r.view === 'organize' ? { view: 'organize', tab: r.tab } : {};
  const revision = currentLibrary.value?.revision;
  const epoch = mediaEpoch.value;
  const isNarrow = narrow.value;
  const dpr = window.devicePixelRatio || 1;

  // ------------------------------------------------------------ context
  const [held, setHeld] = useState<{ id: string; context?: ImageContext; error?: string } | null>(null);
  const [contextTry, setContextTry] = useState(0);
  const stored = contexts.get(imageId);
  const current = Boolean(stored && (revision === undefined || stored.revision >= revision));
  // A context from an older revision keeps showing while it is reread.
  const context = stored ?? (held?.id === imageId ? held.context : undefined);
  const contextError = !context && held?.id === imageId ? held.error ?? null : null;
  useEffect(() => {
    if (current) return;
    const controller = new AbortController();
    fetchContext(imageId, controller.signal)
      .then((value) => setHeld({ id: imageId, context: value }))
      .catch((error) => {
        if (isAbort(error)) return;
        if (statusOf(error) === 404) { toast('这张图片已不存在', 'error'); closeViewer(); return; }
        setHeld({ id: imageId, error: describeError(error) });
      });
    return () => controller.abort();
  }, [imageId, current, revision, contextTry, epoch]);

  // ------------------------------------------------------------ samples
  const sampleSet = useSamples(samplesMode ? groupId : undefined);
  const sampleItems = samplesMode ? sampleSet?.items ?? null : null;
  const sampleIndex = sampleItems ? sampleItems.findIndex((item) => item.id === imageId) : -1;

  // The context is authoritative; until it arrives, the batch or wall list supplies size and name.
  let image = context?.image;
  if (!image && sampleIndex >= 0) image = sampleItems![sampleIndex];
  if (!image && r.package) {
    const list = imagesList(r.package);
    const index = list.indexOf((item) => item.id === imageId);
    if (index >= 0) image = list.item(index);
  }
  const pkg = r.package && currentPackage.value?.id === r.package ? currentPackage.value : null;
  const packageTotal = pkg?.image_count ?? (r.package ? imagesList(r.package).total.value : null);

  // ------------------------------------------------------------ stage & view
  const root = useRef<HTMLDivElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const [stage, setStage] = useState<Size>({ w: 0, h: 0 });
  useLayoutEffect(() => {
    const element = stageRef.current!;
    const measure = () => setStage({ w: element.clientWidth, h: element.clientHeight });
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    measure();
    return () => observer.disconnect();
  }, []);

  const [view, setView] = useState<ViewState>({ id: imageId, zoom: 'fit', x: 0, y: 0, rot: 0 });
  const v: ViewState = view.id === imageId ? view : { id: imageId, zoom: 'fit', x: 0, y: 0, rot: 0 };

  // ------------------------------------------------------------ layers
  const [shown, setShown] = useState<Shown | null>(null);
  const [loading, setLoading] = useState<Loading | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [forceOriginal, setForceOriginal] = useState<string | null>(null);
  const own = shown?.id === imageId ? shown : null;
  const pending = loading?.id === imageId ? loading : null;
  const failed = failure?.id === imageId ? failure : null;

  const known = image?.width && image.height ? { w: image.width, h: image.height } : null;
  const dims: Size | null = known ?? (own ? { w: own.w, h: own.h } : null);
  const exact = Boolean(known) || Boolean(own?.exact);
  const fit = dims && stage.w ? fitScale(dims.w, dims.h, v.rot, stage) : 1;
  const scale = v.zoom === 'fit' ? fit : v.zoom;
  const pan = dims && v.zoom !== 'fit' ? clampPan(v.x, v.y, dims.w, dims.h, v.rot, scale, stage) : { x: 0, y: 0 };
  const panning = v.zoom !== 'fit' && scale > fit * 1.001;

  // The smallest preview covering the displayed size; the original for animation, zooming in and small files.
  let want: Source | null = null;
  if (image && context && stage.w) {
    const needed = Math.ceil((dims ? Math.max(dims.w, dims.h) * scale : Math.max(stage.w, stage.h)) * dpr);
    const kept = own?.source;
    const keep = kept && !(kept.kind === 'preview' && needsOriginal(image)) && (kept.kind === 'original'
      || kept.edge * 1.15 >= needed || (exact && dims !== null && Math.max(dims.w, dims.h) <= kept.edge));
    if (keep) want = kept;
    else if (forceOriginal === imageId || panning) want = original(imageId);
    else want = chooseSource(image, needed);
  }

  // Rapid flipping waits briefly before starting a full load, unless the image was preloaded.
  const lastMove = useRef(0);
  useEffect(() => {
    if (!want) return;
    if (own?.source.url === want.url || pending?.source.url === want.url || failed?.source.url === want.url) return;
    const next: Loading = { id: imageId, source: want, attempt: 0 };
    if (performance.now() - lastMove.current > 300 || warm.has(want.url)) { setLoading(next); return; }
    const timer = window.setTimeout(() => setLoading(next), 150);
    return () => clearTimeout(timer);
  }, [imageId, want?.url, own?.source.url, pending?.source.url, failed?.source.url]);

  const latest = useRef({ known: false, own: null as Shown | null });
  latest.current = { known: Boolean(known), own };

  const promote = (layer: Loading, src: string, element: HTMLImageElement) => {
    const w = element.naturalWidth, h = element.naturalHeight;
    const exactSize = layer.source.kind === 'original' || Math.max(w, h) < layer.source.edge;
    void element.decode().catch(() => undefined).then(() => {
      if (route.value.image !== layer.id) return;
      const before = latest.current;
      // Without metadata the zoom was relative to a downscaled preview; keep the on-screen size.
      if (!before.known && before.own?.id === layer.id && !before.own.exact && exactSize) {
        const ratio = Math.max(before.own.w, before.own.h) / Math.max(w, h);
        setView((state) => (state.id === layer.id && typeof state.zoom === 'number' ? { ...state, zoom: state.zoom * ratio } : state));
      }
      setShown({ id: layer.id, source: layer.source, src, w, h, exact: exactSize });
      setLoading((state) => (state === layer ? null : state));
      setFailure(null);
      if (layer.source.kind === 'preview') noteThumb(layer.id, layer.source.edge);
    });
  };

  const fail = (layer: Loading, src: string) => {
    void probeImage(src).then((result) => {
      if (route.value.image !== layer.id) return;
      if ((result.retry && layer.attempt < 3) || (result.served && layer.attempt === 0)) {
        window.setTimeout(() => setLoading((state) => (state === layer ? { ...layer, attempt: layer.attempt + 1 } : state)), 700 * 2 ** layer.attempt);
        return;
      }
      setLoading((state) => (state === layer ? null : state));
      setFailure({ id: layer.id, source: layer.source, attempt: layer.attempt, text: result.text });
    });
  };

  const retryImage = () => {
    if (!failed) return;
    setFailure(null);
    setLoading({ id: failed.id, source: failed.source, attempt: failed.attempt + 1 });
  };
  const showOriginal = () => { setFailure(null); setForceOriginal(imageId); };
  useEffect(() => { if (failed) retryImage(); }, [epoch]);

  // A first preview fills in size and animation flags on the backend; reread once to pick them up.
  useEffect(() => {
    if (!own || own.source.kind !== 'preview' || !image || reread.has(image.id)) return;
    if (image.width != null && image.animated != null) return;
    reread.set(image.id, true);
    const controller = new AbortController();
    fetchContext(image.id, controller.signal).then((value) => setHeld({ id: value.image.id, context: value })).catch(() => undefined);
    return () => controller.abort();
  }, [own?.src]);

  // ------------------------------------------------------------ settling, position, neighbours
  const visited = useRef<{ group: string; package: string; image: string; index: number } | null>(null);
  useEffect(() => {
    if (!context || context.image.id !== imageId) return;
    const item = context.image;
    if (!samplesMode && (r.library !== item.library_id || r.group !== item.group_id || r.package !== item.package_id)) {
      // The link named another place (moved file or stale link): show the image where it lives.
      navigate({ ...keep, library: item.library_id, group: item.group_id, package: item.package_id, image: item.id }, { replace: true });
      return;
    }
    visited.current = { group: item.group_id, package: item.package_id, image: item.id, index: context.index };
    if (!samplesMode) savePosition(item.group_id, item.id);
  }, [context, r.library, r.group, r.package]);
  useEffect(() => () => { if (visited.current) lastViewed.value = visited.current; }, []);

  const neighbors: [string | null, string | null] = samplesMode
    ? [sampleIndex >= 0 ? sampleItems![sampleIndex + 1]?.id ?? null : null, sampleIndex > 0 ? sampleItems![sampleIndex - 1].id : null]
    : [context?.next_id ?? null, context?.previous_id ?? null];

  useEffect(() => {
    const controller = new AbortController();
    for (const id of neighbors) if (id && !freshContext(id)) void fetchContext(id, controller.signal).catch(() => undefined);
    return () => controller.abort();
  }, [neighbors[0], neighbors[1]]);

  // Once the image is on screen, warm the next one in the travel direction, then the previous one.
  const direction = useRef<1 | -1>(1);
  const settled = Boolean(own) && !pending;
  useEffect(() => {
    if (!settled || !stage.w) return;
    const controller = new AbortController();
    const order = direction.current > 0 ? neighbors : [neighbors[1], neighbors[0]];
    void (async () => {
      for (const id of order) {
        if (!id) continue;
        const next = freshContext(id) ?? await fetchContext(id, controller.signal).catch(() => null);
        if (!next || controller.signal.aborted) return;
        const item = next.image;
        const needed = Math.ceil((item.width && item.height
          ? Math.max(item.width, item.height) * fitScale(item.width, item.height, 0, stage) : Math.max(stage.w, stage.h)) * dpr);
        const source = chooseSource(item, needed);
        if (warm.has(source.url) || (source.kind === 'original' && item.size > 20 * MB)) continue;
        await preload(source.url, controller.signal);
        if (controller.signal.aborted) return;
      }
    })();
    return () => controller.abort();
  }, [settled, imageId, neighbors[0], neighbors[1], stage.w, stage.h]);

  const [stripReady, setStripReady] = useState(false);
  useEffect(() => { if ((own || failed) && !stripReady) setStripReady(true); }, [Boolean(own), Boolean(failed)]);

  // ------------------------------------------------------------ navigation
  const [edge, setEdge] = useState<{ id: string; dir: 1 | -1 } | null>(null);
  const [crossing, setCrossing] = useState(false);
  useEffect(() => {
    if (!edge) return;
    const timer = window.setTimeout(() => setEdge(null), 5000);
    return () => clearTimeout(timer);
  }, [edge]);

  const go = (id: string, packageId = r.package) => {
    lastMove.current = performance.now();
    setEdge(null);
    navigate(samplesMode
      ? { library: r.library, group: r.group, view: 'samples', image: id }
      : { ...keep, library: r.library, group: r.group, package: packageId, image: id }, { replace: true });
  };

  const queued = useRef<0 | 1 | -1>(0);
  const step = (dir: 1 | -1) => {
    direction.current = dir;
    if (samplesMode) {
      if (!sampleItems) return;
      const target = sampleIndex >= 0 ? sampleItems[sampleIndex + dir] : undefined;
      if (target) go(target.id); else setEdge({ id: imageId, dir });
      return;
    }
    if (!context || context.image.id !== imageId) { queued.current = dir; return; }
    const target = dir > 0 ? context.next_id : context.previous_id;
    // Package boundaries are never crossed implicitly; the notice offers an explicit step.
    if (target) go(target); else setEdge({ id: imageId, dir });
  };
  useEffect(() => {
    if (!context || !queued.current) return;
    const dir = queued.current;
    queued.current = 0;
    step(dir);
  }, [context]);

  const jumpController = useRef<AbortController | null>(null);
  useEffect(() => () => jumpController.current?.abort(), []);
  const jump = (where: 'first' | 'last') => {
    if (samplesMode) {
      if (sampleItems?.length) go((where === 'first' ? sampleItems[0] : sampleItems[sampleItems.length - 1]).id);
      return;
    }
    if (!r.package || packageTotal == null) return;
    jumpController.current?.abort();
    const controller = jumpController.current = new AbortController();
    direction.current = where === 'first' ? -1 : 1;
    imageAt(r.package, where === 'first' ? 0 : packageTotal - 1, controller.signal)
      .then((item) => { if (item && !controller.signal.aborted && item.id !== route.value.image) go(item.id); })
      .catch((error) => reportError(error));
  };

  const cross = async (dir: 1 | -1) => {
    const from = context?.image;
    if (!groupId || !from) return;
    setCrossing(true);
    try {
      const next = await neighborPackage(groupId, from.package_id, dir);
      if (route.value.image !== from.id) return;
      if (!next) { toast(dir > 0 ? '这已是此文件夹的最后一个图包' : '这已是此文件夹的第一个图包'); setEdge(null); return; }
      const target = dir > 0 ? next.cover_id ?? (await imageAt(next.id, 0))?.id : (await imageAt(next.id, next.image_count - 1))?.id;
      if (route.value.image !== from.id) return;
      if (!target) { toast('相邻图包中没有图片'); return; }
      direction.current = dir;
      go(target, next.id);
    } catch (error) {
      reportError(error, '无法打开相邻图包：');
    } finally {
      setCrossing(false);
    }
  };

  const viewInPackage = () => {
    const item = context?.image;
    if (item) navigate({ ...keep, library: item.library_id, group: item.group_id, package: item.package_id, image: item.id }, { replace: true });
  };

  // ------------------------------------------------------------ zoom, pan, rotate
  const update = (patch: Partial<ViewState>) => {
    const next: ViewState = { ...v, ...patch, id: imageId };
    if (next.zoom === 'fit') { setView({ ...next, x: 0, y: 0 }); return; }
    if (!dims || !stage.w) return;
    setView({ ...next, ...clampPan(next.x, next.y, dims.w, dims.h, next.rot, next.zoom, stage) });
  };
  const limit = (value: number) => Math.min(Math.max(8, fit), Math.max(Math.min(fit, 0.1), value));
  const zoomAt = (target: number, cx = 0, cy = 0) => {
    if (!dims || !stage.w) return;
    const next = limit(target);
    // Passing through the fitted size stops there, like a detent.
    if ((scale - fit) * (next - fit) < 0 || Math.abs(next - fit) < fit * 0.01) { update({ zoom: 'fit' }); return; }
    const ratio = next / scale;
    update({ zoom: next, x: cx - (cx - pan.x) * ratio, y: cy - (cy - pan.y) * ratio });
  };
  const toggleZoom = (cx = 0, cy = 0) => {
    if (v.zoom === 'fit') zoomAt(fit < 1 ? 1 : 2, cx, cy);
    else update({ zoom: 'fit' });
  };
  const rotate = (delta: number) => update({ rot: (v.rot + delta + 360) % 360 });

  const centred = (clientX: number, clientY: number) => {
    const rect = stageRef.current!.getBoundingClientRect();
    return { x: clientX - rect.left - rect.width / 2, y: clientY - rect.top - rect.height / 2 };
  };

  const wheel = useRef({ total: 0, last: 0, lock: 0 });
  const onWheel = (event: JSX.TargetedWheelEvent<HTMLDivElement>) => {
    event.preventDefault();
    const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? stage.h : 1;
    const dx = event.deltaX * unit, dy = event.deltaY * unit;
    if (event.ctrlKey) {
      const point = centred(event.clientX, event.clientY);
      zoomAt(scale * Math.exp(-dy * 0.002), point.x, point.y);
      return;
    }
    if (panning) { update({ x: pan.x - dx, y: pan.y - dy }); return; }
    const now = performance.now();
    const state = wheel.current;
    if (now - state.last > 250) state.total = 0;
    state.last = now;
    if (now < state.lock) return;
    state.total += Math.abs(dy) >= Math.abs(dx) ? dy : dx;
    if (Math.abs(state.total) >= 50) {
      step(state.total > 0 ? 1 : -1);
      state.total = 0;
      state.lock = now + 180;
    }
  };

  const pointers = useRef(new Map<number, { x: number; y: number }>());
  const gesture = useRef<Gesture | null>(null);
  const pinchStart = (): Gesture => {
    const [a, b] = [...pointers.current.values()];
    const mid = centred((a.x + b.x) / 2, (a.y + b.y) / 2);
    return { kind: 'pinch', x: mid.x, y: mid.y, panX: pan.x, panY: pan.y, scale, distance: Math.hypot(a.x - b.x, a.y - b.y) || 1, time: 0, touch: true };
  };
  const onPointerDown = (event: JSX.TargetedPointerEvent<HTMLDivElement>) => {
    if (event.pointerType === 'mouse' && event.button !== 0) return;
    if ((event.target as HTMLElement).closest('button, a')) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    pointers.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
    if (pointers.current.size === 2 && dims) gesture.current = pinchStart();
    else if (pointers.current.size === 1) {
      gesture.current = {
        kind: panning ? 'pan' : 'swipe', x: event.clientX, y: event.clientY, panX: pan.x, panY: pan.y, scale,
        distance: 0, time: performance.now(), touch: event.pointerType !== 'mouse',
      };
    }
  };
  const onPointerMove = (event: JSX.TargetedPointerEvent<HTMLDivElement>) => {
    if (!pointers.current.has(event.pointerId)) return;
    pointers.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
    const g = gesture.current;
    if (!g) return;
    if (g.kind === 'pan') update({ x: g.panX + event.clientX - g.x, y: g.panY + event.clientY - g.y });
    else if (g.kind === 'pinch' && pointers.current.size >= 2) {
      const [a, b] = [...pointers.current.values()];
      const mid = centred((a.x + b.x) / 2, (a.y + b.y) / 2);
      const next = limit(g.scale * Math.hypot(a.x - b.x, a.y - b.y) / g.distance);
      const ratio = next / g.scale;
      update({ zoom: next, x: mid.x - (g.x - g.panX) * ratio, y: mid.y - (g.y - g.panY) * ratio });
    }
  };
  const onPointerEnd = (event: JSX.TargetedPointerEvent<HTMLDivElement>) => {
    if (!pointers.current.delete(event.pointerId)) return;
    const g = gesture.current;
    if (event.type === 'pointerup' && g?.kind === 'swipe' && g.touch) {
      const dx = event.clientX - g.x, dy = event.clientY - g.y;
      if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy) * 1.5 && performance.now() - g.time < 800) step(dx < 0 ? 1 : -1);
    }
    if (g?.kind === 'pinch' && v.zoom !== 'fit' && scale <= fit * 1.02) update({ zoom: 'fit' });
    const [rest] = [...pointers.current.values()];
    gesture.current = rest && panning
      ? { kind: 'pan', x: rest.x, y: rest.y, panX: pan.x, panY: pan.y, scale, distance: 0, time: performance.now(), touch: true }
      : null;
  };

  // ------------------------------------------------------------ chrome: info, filmstrip, fullscreen
  const [strip, setStrip] = useState(() => {
    const saved = localStorage.getItem('gt.filmstrip');
    return saved === null ? !narrow.value : saved === '1';
  });
  const [info, setInfo] = useState(() => localStorage.getItem('gt.viewerInfo') === '1');
  const toggleStrip = () => { localStorage.setItem('gt.filmstrip', strip ? '0' : '1'); setStrip(!strip); };
  const toggleInfo = () => { localStorage.setItem('gt.viewerInfo', info ? '0' : '1'); setInfo(!info); };

  const [full, setFull] = useState(Boolean(document.fullscreenElement));
  useEffect(() => {
    const sync = () => setFull(Boolean(document.fullscreenElement));
    document.addEventListener('fullscreenchange', sync);
    return () => {
      document.removeEventListener('fullscreenchange', sync);
      if (document.fullscreenElement) void document.exitFullscreen().catch(() => undefined);
    };
  }, []);
  const toggleFull = () => {
    if (document.fullscreenElement) void document.exitFullscreen().catch(() => undefined);
    else document.documentElement.requestFullscreen().catch(() => toast('无法进入全屏', 'error'));
  };
  // In fullscreen the bars float over the image and fade out while the pointer rests.
  const [idle, setIdle] = useState(false);
  useEffect(() => {
    if (!full) { setIdle(false); return; }
    let timer = window.setTimeout(() => setIdle(true), 2500);
    const wake = () => { setIdle(false); clearTimeout(timer); timer = window.setTimeout(() => setIdle(true), 2500); };
    window.addEventListener('pointermove', wake);
    window.addEventListener('keydown', wake);
    return () => { clearTimeout(timer); window.removeEventListener('pointermove', wake); window.removeEventListener('keydown', wake); };
  }, [full]);

  useEffect(() => { root.current?.focus({ preventScroll: true }); }, []);

  // ------------------------------------------------------------ delete
  const remove = () => {
    if (!image) return;
    const target = image;
    const at = context;
    const batch = sampleItems;
    requestDelete({
      targets: [{ kind: 'image', id: target.id }], title: `图片“${target.name}”`, names: { [target.id]: target.rel },
      onDone: (done) => {
        if (!done.has(target.id)) return;
        contexts.clear();
        if (samples.value?.items) samples.value = { ...samples.value, items: samples.value.items.filter((item) => item.id !== target.id) };
        if (route.value.image !== target.id) return;
        let next: string | null | undefined;
        if (batch) {
          const index = batch.findIndex((item) => item.id === target.id);
          next = (batch[index + 1] ?? batch[index - 1])?.id;
        } else next = at?.next_id ?? at?.previous_id;
        if (next) go(next); else closeViewer();
      },
    });
  };

  // ------------------------------------------------------------ keyboard
  const keys = useRef<(event: KeyboardEvent) => boolean>(() => false);
  keys.current = (event) => {
    if (plainKey(event)) {
      const key = event.key.length === 1 ? event.key.toLowerCase() : event.key;
      switch (key) {
        case 'ArrowRight': case 'PageDown': step(1); return true;
        case 'ArrowLeft': case 'PageUp': step(-1); return true;
        case 'Home': jump('first'); return true;
        case 'End': jump('last'); return true;
        case 'Escape': closeViewer(); return true;
        case 'f': toggleFull(); return true;
        case '0': update({ zoom: 'fit' }); return true;
        case '1': zoomAt(1); return true;
        case '+': case '=': zoomAt(scale * 1.25); return true;
        case '-': zoomAt(scale / 1.25); return true;
        case 'r': rotate(90); return true;
        case 'i': toggleInfo(); return true;
        case 'Delete': remove(); return true;
        case 'u': case 'k': case 'm':
          if (!event.repeat && groupId) applyMark(groupId, key === 'u' ? 'none' : key === 'k' ? 'kept' : 'marked');
          return true;
      }
      return false;
    }
    if (plainKey(event, true)) {
      if (event.key === 'R') { rotate(-90); return true; }
      if (event.key === '+') { zoomAt(scale * 1.25); return true; }
      if (event.key === '_') { zoomAt(scale / 1.25); return true; }
    }
    return false;
  };
  useEffect(() => {
    // Capture phase: the viewer owns the keyboard, so walls underneath never see these keys.
    const onKey = (event: KeyboardEvent) => {
      if (keyboardOwnedElsewhere(event)) return;
      if (keys.current(event)) { event.preventDefault(); event.stopImmediatePropagation(); }
    };
    window.addEventListener('keydown', onKey, true);
    return () => window.removeEventListener('keydown', onKey, true);
  }, []);

  // ------------------------------------------------------------ render
  const frame = (w: number, h: number, s: number, x: number, y: number, rot: number) => ({
    width: `${w * s}px`, height: `${h * s}px`,
    transform: `translate(-50%, -50%) translate(${x}px, ${y}px) rotate(${rot}deg)`,
  });
  const currentFrame = dims && stage.w ? frame(dims.w, dims.h, scale, pan.x, pan.y, v.rot) : undefined;
  const frameClass = currentFrame ? 'frame' : 'frame free';
  const placeholderEdge = own ? undefined : knownThumb(imageId);
  // With nothing of the new image to show yet, the previous one stays (dimmed) instead of a blank stage.
  const stale = !own && placeholderEdge === undefined && !failed && shown && shown.id !== imageId ? shown : null;
  const pendingSrc = pending ? srcOf(pending.source, pending.attempt) : '';
  const visible = Boolean(own) || placeholderEdge !== undefined;

  const mark = currentGroup.value?.id === groupId ? (currentGroup.value!.state as Mark) : undefined;
  const hasNext = samplesMode ? sampleIndex >= 0 && sampleIndex < (sampleItems?.length ?? 0) - 1 : context ? context.next_id !== null : true;
  const hasPrev = samplesMode ? sampleIndex > 0 : context ? context.previous_id !== null : true;
  const index = context && context.image.id === imageId ? context.index : null;
  const position = samplesMode
    ? sampleItems && sampleIndex >= 0 ? `抽样 ${sampleIndex + 1} / ${sampleItems.length}` : '抽样'
    : `${index === null ? '…' : count(index + 1)} / ${packageTotal == null ? '…' : count(packageTotal)}`;
  const where = samplesMode ? '' : pkg ? (pkg.loose ? '散图' : pkg.name) : '';
  const animatedNow = own?.source.kind === 'original' && image?.animated;

  const infoPanel = info && image && (
    <aside class="viewer-info" aria-label="图片信息">
      <dl>
        <dt>文件名</dt><dd>{image.name}</dd>
        <dt>位置</dt><dd class="path">{image.rel.slice(0, Math.max(0, image.rel.length - image.name.length - 1)) || '（图库根目录）'}</dd>
        <dt>尺寸</dt>
        <dd>{known ? `${known.w} × ${known.h}` : own?.exact ? `${own.w} × ${own.h}` : '尚未读取（生成预览后补齐）'}</dd>
        <dt>大小</dt><dd>{bytes(image.size)}</dd>
        <dt>格式</dt>
        <dd>{extension(image.name).toUpperCase() || '—'}{image.animated ? ' · 动图' : image.animated == null ? ' · 是否为动图未知' : ''}</dd>
        <dt>修改时间</dt><dd>{new Date(image.mtime_ns / 1e6).toLocaleString('zh-CN')}</dd>
        <dt>当前显示</dt>
        <dd>{own ? `${own.source.kind === 'original' ? '原图' : `预览 ${own.source.edge}px`} · ${Math.round(scale * 100)}%` : failed ? '无法显示' : '载入中'}</dd>
        {image.error && <><dt>后端错误</dt><dd class="bad">{image.error}</dd></>}
      </dl>
    </aside>
  );

  return (
    <div ref={root} tabIndex={-1} class={`viewer ${full ? 'full' : ''} ${full && idle ? 'idle' : ''} ${isNarrow ? 'narrow' : ''}`}
      role="dialog" aria-label={`查看图片：${image?.name ?? ''}`}>
      <header class="viewer-bar">
        <button class="icon-btn" onClick={closeViewer} title="返回（Esc）" aria-label="返回"><Icon name="ArrowLeft" /></button>
        <div class="viewer-title">
          <span class="viewer-name" title={image?.rel}>{image?.name ?? '…'}</span>
          <span class="viewer-sub muted">
            {where && <span class="viewer-pkg" title={pkg?.rel}>{where}</span>}
            <span class="num">{position}</span>
            {animatedNow && <span class="badge anim">动图</span>}
          </span>
        </div>
        <span class="spacer" />
        <div class="viewer-tools wide-only">
          <button class="icon-btn" onClick={() => zoomAt(scale / 1.25)} disabled={!dims} title="缩小（-）" aria-label="缩小"><Icon name="ZoomOut" /></button>
          <button class="btn small zoom-level num" onClick={() => toggleZoom()} disabled={!dims} title="适应窗口 / 100%（0 / 1）">
            {v.zoom === 'fit' ? `适应 ${Math.round(fit * 100)}%` : `${Math.round(scale * 100)}%`}
          </button>
          <button class="icon-btn" onClick={() => zoomAt(scale * 1.25)} disabled={!dims} title="放大（+）" aria-label="放大"><Icon name="ZoomIn" /></button>
          <button class="icon-btn" onClick={() => rotate(-90)} title="逆时针旋转（Shift+R）" aria-label="逆时针旋转"><Icon name="RotateCcw" /></button>
          <button class="icon-btn" onClick={() => rotate(90)} title="顺时针旋转（R）" aria-label="顺时针旋转"><Icon name="RotateCw" /></button>
        </div>
        {samplesMode && context && (
          <button class="btn small" onClick={viewInPackage} title="切换到这张图片所在的图包，按图包顺序浏览">
            <Icon name="Images" size={14} /><span class="wide-only">在图包中查看</span>
          </button>
        )}
        {groupId && <MarkSegment groupId={groupId} value={mark} compact />}
        <button class={`icon-btn ${info ? 'active' : ''}`} onClick={toggleInfo} title="图片信息（I）" aria-label="图片信息" aria-pressed={info}>
          <Icon name="Info" />
        </button>
        {!samplesMode && (
          <button class={`icon-btn ${strip ? 'active' : ''}`} onClick={toggleStrip} title="胶片条" aria-label="胶片条" aria-pressed={strip}>
            <Icon name="PanelBottom" />
          </button>
        )}
        <button class="icon-btn wide-only" onClick={toggleFull} title={full ? '退出全屏（F）' : '全屏（F）'} aria-label="全屏">
          <Icon name={full ? 'Minimize' : 'Maximize'} />
        </button>
        <a class="icon-btn wide-only" href={originalUrl(imageId)} target="_blank" rel="noopener noreferrer" title="在新窗口打开原图" aria-label="打开原图">
          <Icon name="ExternalLink" />
        </a>
        <button class="icon-btn danger-hover" onClick={remove} disabled={!image} title="删除这张图片（Delete）" aria-label="删除这张图片">
          <Icon name="Trash2" />
        </button>
      </header>

      <div class="viewer-main">
        {!isNarrow && (
          <button class={`nav prev ${hasPrev ? '' : 'at-edge'}`} onClick={() => step(-1)} title="上一张（←）" aria-label="上一张">
            <Icon name="ChevronLeft" size={30} />
          </button>
        )}
        <div ref={stageRef} class={`stage ${panning ? 'can-pan' : ''}`} onWheel={onWheel} onDblClick={(event) => {
          const point = centred(event.clientX, event.clientY);
          toggleZoom(point.x, point.y);
        }}
          onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerEnd} onPointerCancel={onPointerEnd}>
          {stale && (
            <div key={`f:${stale.src}`} class="frame stale" style={frame(stale.w, stale.h, fitScale(stale.w, stale.h, 0, stage), 0, 0, 0)}>
              <LayerImage src={stale.src} alt="" />
            </div>
          )}
          {placeholderEdge !== undefined && (
            <div key={`p:${imageId}`} class={`${frameClass} placeholder`} style={currentFrame}>
              <img class="layer" src={thumbnailUrl(imageId, placeholderEdge)} alt="" draggable={false}
                onError={(event) => { event.currentTarget.style.visibility = 'hidden'; }} />
            </div>
          )}
          {own && (
            <div key={`f:${own.src}`} class={frameClass} style={currentFrame}>
              <LayerImage src={own.src} alt={image?.name ?? ''} />
            </div>
          )}
          {pending && pendingSrc !== own?.src && (
            <div key={`f:${pendingSrc}`} class={`${frameClass} pending`} style={currentFrame}>
              <LayerImage src={pendingSrc} alt="" onReady={(element) => promote(pending, pendingSrc, element)}
                onFail={() => fail(pending, pendingSrc)} />
            </div>
          )}

          {!failed && !contextError && (!own || pending) && (
            <div class={`viewer-loading ${visible ? 'corner' : ''}`} aria-hidden="true">
              <Icon name="LoaderCircle" spin size={visible ? 16 : 32} />
              {own && pending?.source.kind === 'original' && <span>正在载入原图…</span>}
            </div>
          )}
          {failed && (
            <div class="viewer-failure" role="alert">
              <Icon name="TriangleAlert" size={28} />
              <strong>{failed.source.kind === 'original' ? '原图无法显示' : '预览无法显示'}</strong>
              <span class="muted">{failed.text}</span>
              <div class="form-actions">
                {failed.source.kind === 'preview' && <button class="btn" onClick={showOriginal}>查看原图</button>}
                <button class="btn primary" onClick={retryImage}>重试</button>
              </div>
            </div>
          )}
          {contextError && (
            <div class="viewer-failure" role="alert">
              <Icon name="CircleAlert" size={28} />
              <strong>无法读取图片信息</strong>
              <span class="muted">{contextError}</span>
              <div class="form-actions">
                <button class="btn" onClick={closeViewer}>返回</button>
                <button class="btn primary" onClick={() => setContextTry((value) => value + 1)}>重试</button>
              </div>
            </div>
          )}
          {edge?.id === imageId && (
            <div class="edge-note" role="status">
              <span>
                {samplesMode
                  ? sampleIndex < 0 ? '这张图片不在当前抽样批次中' : edge.dir > 0 ? '已是本批最后一张' : '已是本批第一张'
                  : edge.dir > 0 ? '已是本图包最后一张' : '已是本图包第一张'}
              </span>
              {!samplesMode && (
                <button class="btn small" disabled={crossing} onClick={() => void cross(edge.dir)}>
                  {edge.dir < 0 && <Icon name="ChevronsLeft" size={14} />}
                  {edge.dir > 0 ? '下一个图包' : '上一个图包'}
                  {edge.dir > 0 && <Icon name="ChevronsRight" size={14} />}
                </button>
              )}
            </div>
          )}
        </div>
        {!isNarrow && (
          <button class={`nav next ${hasNext ? '' : 'at-edge'}`} onClick={() => step(1)} title="下一张（→）" aria-label="下一张">
            <Icon name="ChevronRight" size={30} />
          </button>
        )}
        {!isNarrow && infoPanel}
      </div>

      {isNarrow && infoPanel}
      {strip && !samplesMode && r.package && (
        <Filmstrip packageId={r.package} index={index ?? -1} current={imageId} ready={stripReady}
          onPick={(id) => { if (id !== imageId) go(id); }} />
      )}
      {isNarrow && (
        <footer class="viewer-foot">
          <button class={`btn ${hasPrev ? '' : 'at-edge'}`} onClick={() => step(-1)} aria-label="上一张"><Icon name="ChevronLeft" size={16} />上一张</button>
          <span class="muted num">{position}</span>
          <button class={`btn ${hasNext ? '' : 'at-edge'}`} onClick={() => step(1)} aria-label="下一张">下一张<Icon name="ChevronRight" size={16} /></button>
        </footer>
      )}
    </div>
  );
}
