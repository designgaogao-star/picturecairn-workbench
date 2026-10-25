import { signal } from '@preact/signals';
import { describeError, isAbort, statusOf, type Page } from '../api';

export type PageFetcher<T> = (offset: number, limit: number, signal: AbortSignal) => Promise<Page<T>>;

interface Slot<T> { items: T[]; revision: number; stale: boolean }

/**
 * Bounded page cache for one server list. Each mounted consumer registers the window it shows;
 * only pages inside some window are fetched, requests that leave every window are aborted, and
 * stale pages keep rendering until their replacement arrives.
 */
export class PagedList<T> {
  readonly total = signal<number | null>(null);
  readonly version = signal(0);
  readonly error = signal<string | null>(null);
  readonly loading = signal(false);
  revision = -1;
  private pages = new Map<number, Slot<T>>();
  private inflight = new Map<number, AbortController>();
  private windows = new Map<string, [number, number]>();
  private disposed = false;
  private generation = 0;
  private attempts = 0;
  private retryTimer = 0;

  constructor(readonly key: string, private fetcher: PageFetcher<T>, readonly pageSize = 100, private maxPages = 10) {}

  item(index: number): T | undefined {
    return this.pages.get(Math.floor(index / this.pageSize))?.items[index % this.pageSize];
  }

  /** Items currently cached, in index order; used for lookups without extra requests. */
  *cached(): Generator<[number, T]> {
    for (const [page, slot] of [...this.pages].sort((a, b) => a[0] - b[0])) {
      for (let i = 0; i < slot.items.length; i++) yield [page * this.pageSize + i, slot.items[i]];
    }
  }

  /** True while some mounted view shows this list; such lists are never evicted. */
  get active() { return this.windows.size > 0; }

  indexOf(match: (item: T) => boolean): number {
    for (const [index, item] of this.cached()) if (match(item)) return index;
    return -1;
  }

  ensure(start: number, end: number, consumer = 'main') {
    if (this.disposed) return;
    const total = this.total.value;
    if (total !== null) end = Math.min(end, total);
    const first = Math.floor(Math.max(0, start) / this.pageSize);
    const last = Math.max(first, Math.floor(Math.max(0, end - 1) / this.pageSize));
    this.windows.set(consumer, [first, last]);
    this.abortUnwanted();
    // A failed list waits for retry() (button, timed retry or reconnect) instead of refiring on every scroll.
    if (this.error.value === null) for (let page = first; page <= last; page++) this.fill(page);
    this.loading.value = this.inflight.size > 0;
  }

  /** Forgets a consumer's window, e.g. when its view unmounts. */
  release(consumer: string) {
    this.windows.delete(consumer);
    this.abortUnwanted();
    this.loading.value = this.inflight.size > 0;
  }

  /**
   * Marks every page stale. Mounted views re-render on the version bump and ensure() their visible
   * window again; lists that are not on screen refetch only when they are next shown.
   */
  invalidate() {
    if (this.disposed) return;
    this.generation++;
    for (const slot of this.pages.values()) slot.stale = true;
    this.clearError();
    this.version.value++;
  }

  /** Reloads the missing or stale pages of every registered window. */
  retry() {
    if (this.disposed) return;
    this.clearError();
    for (const [first, last] of this.windows.values()) for (let page = first; page <= last; page++) this.fill(page);
    this.loading.value = this.inflight.size > 0;
    this.version.value++;
  }

  dispose() {
    this.disposed = true;
    clearTimeout(this.retryTimer);
    for (const controller of this.inflight.values()) controller.abort();
    this.inflight.clear();
    this.pages.clear();
    this.windows.clear();
  }

  private wanted(page: number): boolean {
    for (const [first, last] of this.windows.values()) if (page >= first && page <= last) return true;
    return false;
  }

  private abortUnwanted() {
    for (const [page, controller] of this.inflight) {
      if (!this.wanted(page)) { controller.abort(); this.inflight.delete(page); }
    }
  }

  private fill(page: number) {
    const slot = this.pages.get(page);
    if ((!slot || slot.stale) && !this.inflight.has(page)) void this.load(page);
  }

  private async load(page: number) {
    const generation = this.generation;
    const controller = new AbortController();
    this.inflight.set(page, controller);
    this.loading.value = true;
    try {
      const result = await this.fetcher(page * this.pageSize, this.pageSize, controller.signal);
      if (this.disposed || this.inflight.get(page) !== controller) return;
      this.inflight.delete(page);
      const newer = this.revision >= 0 && result.revision > this.revision;
      if (newer) for (const [other, slot] of this.pages) if (other !== page) slot.stale = true;
      this.revision = Math.max(this.revision, result.revision);
      this.total.value = result.total;
      this.pages.delete(page);
      // A refresh arriving during this request still needs a read after this response.
      this.pages.set(page, { items: result.items, revision: result.revision,
        stale: generation !== this.generation || result.revision < this.revision });
      this.error.value = null;
      this.attempts = 0;
      this.evict();
      this.version.value++;
      if (newer) for (const [first, last] of this.windows.values()) for (let p = first; p <= last; p++) this.fill(p);
    } catch (error) {
      if (!isAbort(error) && this.inflight.get(page) === controller) {
        this.inflight.delete(page);
        this.error.value = describeError(error);
        this.version.value++;
        // Transient failures (busy queue, dropped connection) retry twice; a vanished list does not.
        if (statusOf(error) !== 404 && this.attempts < 2) {
          this.attempts++;
          clearTimeout(this.retryTimer);
          this.retryTimer = window.setTimeout(() => this.retry(), 1500 * this.attempts);
        }
      }
    } finally {
      if (this.inflight.get(page) === controller) this.inflight.delete(page);
      this.loading.value = this.inflight.size > 0;
    }
  }

  private clearError() {
    clearTimeout(this.retryTimer);
    if (this.error.value !== null) this.error.value = null;
  }

  private evict() {
    for (const page of [...this.pages.keys()]) {
      if (this.pages.size <= this.maxPages) break;
      if (!this.wanted(page)) this.pages.delete(page);
    }
  }
}

/** Small LRU of list instances so returning to a wall reuses its pages and scroll anchor. */
export class ListRegistry {
  private lists = new Map<string, PagedList<unknown>>();
  constructor(private capacity = 8) {}

  get<T>(key: string, create: () => PagedList<T>): PagedList<T> {
    let list = this.lists.get(key) as PagedList<T> | undefined;
    if (list) { this.lists.delete(key); this.lists.set(key, list as PagedList<unknown>); return list; }
    list = create();
    this.lists.set(key, list as PagedList<unknown>);
    for (const [old, value] of [...this.lists]) {
      if (this.lists.size <= this.capacity) break;
      if (old !== key && !value.active) { value.dispose(); this.lists.delete(old); }
    }
    return list;
  }

  /** An existing list, without creating one or touching its recency. */
  peek<T>(key: string): PagedList<T> | undefined { return this.lists.get(key) as PagedList<T> | undefined; }

  each(match: (key: string) => boolean, action: (list: PagedList<unknown>) => void) {
    for (const [key, list] of [...this.lists]) if (match(key)) action(list);
  }

  drop(match: (key: string) => boolean) {
    for (const [key, list] of [...this.lists]) if (match(key)) { list.dispose(); this.lists.delete(key); }
  }
}

/** Bounded string-keyed cache with LRU eviction. */
export class Lru<V> {
  private map = new Map<string, V>();
  constructor(private capacity: number, private onEvict?: (value: V) => void) {}
  get(key: string): V | undefined {
    const value = this.map.get(key);
    if (value !== undefined) { this.map.delete(key); this.map.set(key, value); }
    return value;
  }
  has(key: string) { return this.map.has(key); }
  set(key: string, value: V) {
    const old = this.map.get(key);
    if (old !== undefined && old !== value) this.onEvict?.(old);
    this.map.delete(key);
    this.map.set(key, value);
    while (this.map.size > this.capacity) {
      const [first, firstValue] = this.map.entries().next().value as [string, V];
      this.map.delete(first);
      this.onEvict?.(firstValue);
    }
  }
  delete(key: string) {
    const value = this.map.get(key);
    if (value !== undefined) { this.map.delete(key); this.onEvict?.(value); }
  }
  keys() { return this.map.keys(); }
  clear() { for (const value of this.map.values()) this.onEvict?.(value); this.map.clear(); }
}
