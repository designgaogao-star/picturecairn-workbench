import { useEffect, useState } from 'preact/hooks';
import { client, isAbort } from '../api';
import { Lru } from './paged';

/**
 * Folder covers. The API has no group cover field (docs/frontend-gaps.md), so a card asks for the
 * group's first package and shows its cover. Only mounted cards request, two at a time, and a card
 * that scrolls away before its turn leaves the queue.
 */
const covers = new Lru<string | null>(1000);
const listeners = new Map<string, Set<() => void>>();
const queue: { id: string; wave: number }[] = [];
const running = new Map<string, AbortController>();
const LIMIT = 2;
/** Counts the render passes that mounted cards; one pass mounts its cards top to bottom. */
let wave = 0;
let waveOpen = false;

function notify(groupId: string) { listeners.get(groupId)?.forEach((fn) => fn()); }

function pump() {
  while (running.size < LIMIT && queue.length) {
    // Newest pass first (the cards the user is looking at now), and within a pass from the top down.
    let pick = 0;
    for (let i = 1; i < queue.length; i++) if (queue[i].wave > queue[pick].wave) pick = i;
    const groupId = queue.splice(pick, 1)[0].id;
    const controller = new AbortController();
    running.set(groupId, controller);
    client.request('get', '/api/v1/groups/{group_id}/packages', {
      params: { path: { group_id: groupId }, query: { offset: 0, limit: 1 } }, signal: controller.signal,
    }).then((page) => {
      covers.set(groupId, page.items[0]?.cover_id ?? null);
      notify(groupId);
    }).catch((error) => {
      // Not cached: the next mount asks again. Listeners learn the attempt ended.
      if (!isAbort(error)) notify(groupId);
    }).finally(() => {
      running.delete(groupId);
      pump();
    });
  }
}

function want(groupId: string, listener: () => void): () => void {
  let set = listeners.get(groupId);
  if (!set) listeners.set(groupId, set = new Set());
  set.add(listener);
  if (!waveOpen) { waveOpen = true; wave++; queueMicrotask(() => { waveOpen = false; }); }
  if (!running.has(groupId) && !queue.some((item) => item.id === groupId)) { queue.push({ id: groupId, wave }); pump(); }
  return () => {
    set!.delete(listener);
    if (set!.size) return;
    listeners.delete(groupId);
    const index = queue.findIndex((item) => item.id === groupId);
    if (index >= 0) queue.splice(index, 1);
    running.get(groupId)?.abort();
  };
}

/** Cover image ID of a group: undefined while unknown, null when the group has no cover. */
export function useGroupCover(groupId: string | undefined, epoch = 0): { cover: string | null | undefined; settled: boolean } {
  const [, setTick] = useState(0);
  const [settled, setSettled] = useState(false);
  useEffect(() => {
    setSettled(false);
    if (!groupId || covers.has(groupId)) return;
    return want(groupId, () => { setSettled(true); setTick((value) => value + 1); });
  }, [groupId, epoch]);
  if (!groupId) return { cover: undefined, settled: true };
  return covers.has(groupId) ? { cover: covers.get(groupId), settled: true } : { cover: undefined, settled };
}

export function clearCovers() { covers.clear(); }
