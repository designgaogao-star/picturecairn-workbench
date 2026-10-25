import { useEffect, useRef, useState } from 'preact/hooks';
import { describeError, GalleryError, isAbort, statusOf, thumbnailUrl, type Edge } from '../api';
import { Icon } from '../lib/icons';
import { fetchPreview } from '../lib/preview';
import { mediaEpoch } from '../state/app';
import { ImageElement } from './ImageElement';

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

type Phase = 'loading' | 'ready' | 'error';

// Sizes already generated this session; the viewer can reuse the derivative and HTTP cache
// for its placeholder, while an unknown size could start a slow generation.
const loaded = new Map<string, Edge>();
export function noteThumb(id: string, edge: Edge) {
  const known = loaded.get(id);
  loaded.delete(id);
  loaded.set(id, known && known > edge ? known : edge);
  while (loaded.size > 4000) loaded.delete(loaded.keys().next().value as string);
}
export const knownThumb = (id: string): Edge | undefined => loaded.get(id);

interface Props { id: string; edge?: Edge; fit?: 'cover' | 'contain'; alt?: string; retryButton?: boolean }
interface State { attempt: number; phase: Phase; reason: string; retryable: boolean; src?: string }
const fresh = (): State => ({ attempt: 0, phase: 'loading', reason: '', retryable: false });

/**
 * Static wall preview. A busy image queue or unreachable backend (502–504) is retried with backoff up to three times,
 * then offers a manual retry. The wall never falls back to an animated original.
 */
export function Thumb({ id, edge = 400, fit = 'cover', alt = '', retryButton = true }: Props) {
  const url = thumbnailUrl(id, edge);
  return <Preview key={url} id={id} edge={edge} fit={fit} alt={alt} retryButton={retryButton} url={url} />;
}

/** Each resource owns its observers and callbacks; a previous image cannot reset a new resource. */
function Preview({ id, edge, fit, alt, retryButton, url }: Required<Props> & { url: string }) {
  const [state, setState] = useState<State>(fresh);
  const update = (patch: Partial<State>) => setState((prev) => ({ ...prev, ...patch }));
  const timer = useRef(0);
  const element = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const epoch = mediaEpoch.value;
  const { attempt, phase, reason } = state;
  const retry = () => update({ attempt: attempt + 1, phase: 'loading', reason: '', retryable: false });

  useEffect(() => {
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) { setVisible(true); observer.disconnect(); }
    }, { rootMargin: '200px' });
    if (element.current) observer.observe(element.current);
    return () => observer.disconnect();
  }, [url]);

  useEffect(() => {
    if (!visible) return;
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
  }, [url, visible, attempt]);

  // After a reconnect, failed previews get a fresh attempt.
  useEffect(() => {
    if (phase === 'error') retry();
  }, [epoch]);

  if (phase === 'error') {
    return (
      <div ref={element} class="thumb thumb-error" title={reason}>
        <Icon name="TriangleAlert" size={20} />
        <span class="thumb-error-text">{reason || '预览失败'}</span>
        {retryButton && <button class="btn tiny" onClick={(event) => { event.stopPropagation(); retry(); }}><Icon name="RotateCw" size={14} />重试</button>}
      </div>
    );
  }
  const src = state.src;
  return (
    <div ref={element} class={`thumb fit-${fit} ${phase.endsWith('ready') ? 'is-ready' : 'is-loading'}`}>
      {src && <ImageElement key={src} src={src} alt={alt} draggable={false} decoding="async"
        onLoad={() => { noteThumb(id, edge); update({ phase: 'ready' }); }}
        onError={() => update({ phase: 'error', retryable: false,
          reason: '浏览器无法解码此图片（文件可能已损坏或格式不受支持）' })} />}
    </div>
  );
}
