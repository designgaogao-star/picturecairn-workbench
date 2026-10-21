import { client } from '../api';
import {
  connection, currentGroup, loadLibraries, loadTasks, lists, mediaEpoch, refreshCurrentGroup, refreshTask,
} from './app';

/**
 * SSE is only an invalidation channel. Every snapshot (first connect and each reconnect) and every
 * reset reloads libraries and tasks; catalog/review/task events are coalesced into snapshot reads.
 */
let source: EventSource | null = null;
let catalogTimer = 0;
let taskTimer = 0;
let reconnectTimer = 0;
let failures = 0;
let connected = false;
let instance: string | null = null;
const pendingTasks = new Set<string>();

function snapshot(data: string) {
  let id: string | null = null;
  try { id = JSON.parse(data).instance_id ?? null; } catch { /* keep null */ }
  const restarted = instance !== null && id !== null && id !== instance;
  instance = id;
  // Every later snapshot follows a dropped stream (automatic or manual reconnect): media that failed meanwhile retries.
  const reconnected = connected;
  connected = true;
  failures = 0;
  connection.value = 'online';
  if (reconnected) mediaEpoch.value++;
  if (restarted) lists.each(() => true, (list) => list.invalidate());
  else lists.each(() => true, (list) => { if (list.error.value !== null) list.retry(); });
  void loadLibraries();
  void loadTasks();
  void refreshCurrentGroup();
}

function onCatalog() {
  // Library rows carry the index revision; loadLibraries invalidates lists whose revision moved.
  clearTimeout(catalogTimer);
  catalogTimer = window.setTimeout(() => void loadLibraries(), 600);
}

function onReview(data: string) {
  try {
    const id = JSON.parse(data).group_id;
    if (id && currentGroup.value?.id === id) void refreshCurrentGroup();
  } catch { /* ignore */ }
  lists.each((key) => key.startsWith('groups:'), (list) => list.invalidate());
}

function onTask(data: string) {
  try { const id = JSON.parse(data).id; if (id) pendingTasks.add(id); } catch { /* ignore */ }
  clearTimeout(taskTimer);
  taskTimer = window.setTimeout(() => {
    const ids = [...pendingTasks];
    pendingTasks.clear();
    if (ids.length > 6) void loadTasks();
    else for (const id of ids) void refreshTask(id).catch(() => undefined);
  }, 200);
}

function open() {
  source?.close();
  connection.value = failures || connected ? 'reconnecting' : 'connecting';
  const events = source = client.events();
  events.addEventListener('snapshot', (event) => snapshot((event as MessageEvent).data));
  events.addEventListener('reset', () => { void loadLibraries(); void loadTasks(); lists.each(() => true, (list) => list.invalidate()); });
  events.addEventListener('catalog', onCatalog);
  events.addEventListener('review', (event) => onReview((event as MessageEvent).data));
  events.addEventListener('task', (event) => onTask((event as MessageEvent).data));
  events.onerror = () => {
    if (source !== events) return;
    // EventSource retries on its own for transient drops; after repeated failures reopen with backoff
    // so a restarted backend is picked up and a fresh snapshot is read.
    failures++;
    connection.value = failures > 2 ? 'offline' : 'reconnecting';
    if (events.readyState === EventSource.CLOSED || failures > 2) {
      events.close();
      clearTimeout(reconnectTimer);
      reconnectTimer = window.setTimeout(open, Math.min(8000, 1000 * 2 ** Math.min(failures, 3)));
    }
  };
}

export function startEvents() {
  open();
  window.addEventListener('online', () => { if (connection.value !== 'online') reconnectNow(); });
}

export function reconnectNow() { failures = 0; clearTimeout(reconnectTimer); open(); }
