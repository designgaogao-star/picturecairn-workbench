import { GalleryError } from '../api';

let active = 0;
const pending = new Set<() => void>();

async function acquire(signal: AbortSignal) {
  signal.throwIfAborted();
  if (active < 4) { active++; return; }
  if (pending.size >= 128) throw new GalleryError(503, {});
  await new Promise<void>((resolve, reject) => {
    const start = () => { signal.removeEventListener('abort', abort); active++; resolve(); };
    const abort = () => { pending.delete(start); reject(signal.reason); };
    signal.addEventListener('abort', abort, { once: true });
    pending.add(start);
  });
}

/** One resource request supplies both the image bytes and the HTTP failure reason. */
export async function fetchPreview(url: string, signal: AbortSignal): Promise<string> {
  await acquire(signal);
  try {
    signal.throwIfAborted();
    const response = await fetch(url, { signal });
    if (!response.ok) throw new GalleryError(response.status, await response.json().catch(() => ({})));
    return URL.createObjectURL(await response.blob());
  } finally {
    active--;
    const next = pending.values().next().value;
    if (next) { pending.delete(next); next(); }
  }
}
