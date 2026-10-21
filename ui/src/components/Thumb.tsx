import { useEffect, useRef, useState } from 'preact/hooks';
import { describeError, GalleryError, isAbort, originalUrl, statusOf, thumbnailUrl, type Edge } from '../api';
import { Icon } from '../lib/icons';
import { fetchPreview } from '../lib/preview';
import { mediaEpoch } from '../state/app';

/**
 * Reads why an image request failed: the <img> error event carries no status or detail. A busy queue
 * or dropped connection is worth retrying; a file served fine but undecodable is not.
 */
export async function probeImage(url: string): Promise<{ retry: boolean; served: boolean; text: string }> {
  const controller = new AbortController();
  try {
    const response = await fetch(url, { cache: 'no-store', signal: controller.signal });
    if (response.ok) {
      controller.abort(); // only the status matters; don't read a large original again
      return { retry: false, served: true, text: '浏览器无法解码此图片（文件可能已损坏或格式不受支持）' };
    }
    const detail = await response.json().catch(() => ({}));
    return { retry: [502, 503, 504].includes(response.status), served: false, text: describeError(new GalleryError(response.status, detail)) };
  } catch (error) {
    return { retry: true, served: false, text: describeError(error) };
  }
}

type Phase = 'loading' | 'ready' | 'error' | 'original' | 'original-ready' | 'original-error';

// Preview sizes that loaded in this session; the viewer uses them as instant placeholders because
// the browser already holds them, while an unknown size could start a slow generation.
const loaded = new Map<string, Edge>();
export function noteThumb(id: string, edge: Edge) {
  const known = loaded.get(id);
  loaded.delete(id);
  loaded.set(id, known && known > edge ? known : edge);
  while (loaded.size > 4000) loaded.delete(loaded.keys().next().value as string);
}
export const knownThumb = (id: string): Edge | undefined => loaded.get(id);

interface Props { id: string; edge?: Edge; fit?: 'cover' | 'contain'; alt?: string }
interface State { key: string; attempt: number; phase: Phase; reason: string; retryable: boolean; src?: string }
const fresh = (key: string): State => ({ key, attempt: 0, phase: 'loading', reason: '', retryable: false });

/**
 * Static wall preview. A busy image queue or unreachable backend (502–504) is retried with backoff up to three times,
 * then offers a manual retry; other failures show the backend's reason and offer the original file instead.
 */
export function Thumb({ id, edge = 400, fit = 'cover', alt = '' }: Props) {
  // Keyed to id/edge so a reset can't land after a memory-cached image already fired onLoad,
  // and late callbacks for a recycled cell's previous image are dropped.
  const url = thumbnailUrl(id, edge);
  const key = url;
  const [state, setState] = useState<State>(() => fresh(key));
  const current = state.key === key ? state : fresh(key);
  const update = (patch: Partial<State>) => setState((prev) => ({ ...(prev.key === key ? prev : fresh(key)), ...patch }));
  const timer = useRef(0);
  const element = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const epoch = mediaEpoch.value;
  const { attempt, phase, reason, retryable } = current;
  const retry = () => update({ attempt: attempt + 1, phase: 'loading', reason: '', retryable: false });

  const original = phase.startsWith('original');
  useEffect(() => {
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) { setVisible(true); observer.disconnect(); }
    }, { rootMargin: '200px' });
    if (element.current) observer.observe(element.current);
    return () => observer.disconnect();
  }, [key]);

  useEffect(() => {
    if (!visible || original) return;
    const controller = new AbortController();
    let owned = '';
    update({ phase: 'loading', src: undefined });
    fetchPreview(url, controller.signal).then((src) => {
      if (controller.signal.aborted) { URL.revokeObjectURL(src); return; }
      owned = src;
      update({ src });
    }).catch((error) => {
      if (isAbort(error) || controller.signal.aborted) return;
      const retryable = error instanceof TypeError || [502, 503, 504].includes(statusOf(error) ?? 0);
      if (retryable && attempt < 3) {
        timer.current = window.setTimeout(() => update({ attempt: attempt + 1 }), 700 * 2 ** attempt);
      } else update({ reason: describeError(error), phase: 'error', retryable });
    });
    return () => { controller.abort(); clearTimeout(timer.current); if (owned) URL.revokeObjectURL(owned); };
  }, [url, visible, original, attempt]);

  // After a reconnect, failed previews get a fresh attempt.
  useEffect(() => {
    if (phase === 'error') retry();
  }, [epoch]);

  if (phase === 'error' || phase === 'original-error') {
    return (
      <div ref={element} class="thumb thumb-error" title={reason}>
        <Icon name="TriangleAlert" size={20} />
        <span class="thumb-error-text">{phase === 'error' ? '预览失败' : '原图也无法显示'}</span>
        {phase === 'error' && (retryable
          ? <button class="btn tiny" onClick={(event) => { event.stopPropagation(); retry(); }}><Icon name="RotateCw" size={14} />重试</button>
          : <button class="btn tiny" onClick={(event) => { event.stopPropagation(); update({ phase: 'original' }); }}>查看原图</button>)}
      </div>
    );
  }
  const src = original ? originalUrl(id) : current.src;
  return (
    <div ref={element} class={`thumb fit-${fit} ${phase.endsWith('ready') ? 'is-ready' : 'is-loading'}`}>
      {src && <img key={src} src={src} alt={alt} draggable={false} decoding="async"
        onLoad={() => { if (!original) noteThumb(id, edge); update({ phase: original ? 'original-ready' : 'ready' }); }}
        onError={() => update({ phase: original ? 'original-error' : 'error', retryable: false,
          reason: '浏览器无法解码此图片（文件可能已损坏或格式不受支持）' })} />}
    </div>
  );
}
