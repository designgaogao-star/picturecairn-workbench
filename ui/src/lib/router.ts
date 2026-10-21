import { signal } from '@preact/signals';

export type GroupView = 'packages' | 'samples' | 'organize';
export type OrganizeTab = 'similar' | 'compare' | 'audit';

/** Every location is expressed with persistent IDs, so reloads restore the same place. */
export interface Route {
  library?: string;
  group?: string;
  package?: string;
  image?: string;
  view: GroupView;
  tab?: OrganizeTab;
}

const KEYS: Record<string, keyof Route> = { l: 'library', g: 'group', p: 'package', i: 'image', t: 'tab' };

export function parseRoute(hash: string): Route {
  const parts = hash.replace(/^#\/?/, '').split('/').filter(Boolean).map(decodeURIComponent);
  const route: Route = { view: 'packages' };
  for (let i = 0; i < parts.length; i++) {
    const key = KEYS[parts[i]];
    if (key && parts[i + 1]) { (route as unknown as Record<string, string>)[key] = parts[++i]; continue; }
    if (parts[i] === 'samples' || parts[i] === 'organize') route.view = parts[i] as GroupView;
  }
  return route;
}

export function formatRoute(route: Partial<Route>): string {
  const parts: string[] = [];
  const push = (key: string, value?: string) => { if (value) parts.push(key, encodeURIComponent(value)); };
  push('l', route.library);
  push('g', route.group);
  if (route.group && route.view && route.view !== 'packages') parts.push(route.view);
  if (route.view === 'organize') push('t', route.tab);
  push('p', route.package);
  push('i', route.image);
  return '#/' + parts.join('/');
}

export const route = signal<Route>(parseRoute(location.hash));

/**
 * Where the viewer was pushed from. Closing it while it still shows the same package (or the same
 * sample batch) returns with history.back(), so the wall underneath, inline or not, is the one left.
 */
interface Opened { group?: string; package?: string; view: GroupView }
let opened: Opened | null = null;
const openedAt = (to: Route): Opened => ({ group: to.group, package: to.package, view: to.view });

export function navigate(next: Partial<Route>, options: { replace?: boolean } = {}) {
  const full: Route = { view: 'packages', ...next };
  const hash = formatRoute(full);
  if (hash === location.hash && !options.replace) return;
  const openingViewer = Boolean(full.image) && !route.value.image;
  if (options.replace) history.replaceState(null, '', hash);
  else history.pushState(null, '', hash);
  if (openingViewer) opened = options.replace ? null : openedAt(full);
  if (!full.image) opened = null;
  route.value = full;
  try { localStorage.setItem('gt.lastRoute', hash); } catch { /* storage full or disabled */ }
}

/** Back to the wall the viewer covers; after moving to another package, to that package's wall instead. */
export function closeViewer() {
  const current = route.value;
  if (!current.image) return;
  if (opened && opened.group === current.group && opened.package === current.package && opened.view === current.view) {
    opened = null;
    history.back();
    return;
  }
  navigate({ ...current, image: undefined }, { replace: true });
}

window.addEventListener('popstate', () => {
  const before = route.value;
  route.value = parseRoute(location.hash);
  // Forward into a viewer entry: the entry before it is normally the wall it was opened from.
  if (route.value.image && !before.image) opened = openedAt(route.value);
  if (!route.value.image) opened = null;
  try { localStorage.setItem('gt.lastRoute', location.hash); } catch { /* ignore */ }
});

export function restoreLastRoute() {
  if (location.hash.length > 2) return;
  const saved = localStorage.getItem('gt.lastRoute');
  if (!saved) return;
  // Replace, so closing a restored viewer returns to its package wall instead of leaving the app.
  navigate(parseRoute(saved), { replace: true });
}
