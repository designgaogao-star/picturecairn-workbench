import { signal } from '@preact/signals';

export type GroupView = 'packages' | 'organize';
export type OrganizeTab = 'samples' | 'similar' | 'compare' | 'audit';

const ORGANIZE_TABS: OrganizeTab[] = ['samples', 'similar', 'compare', 'audit'];

/** The organize tool last used in this window, so 整理 reopens where it was left. */
export function lastOrganizeTab(): OrganizeTab {
  let saved: string | null = null;
  try { saved = sessionStorage.getItem('gt.organizeTab'); } catch { /* storage unavailable */ }
  return ORGANIZE_TABS.includes(saved as OrganizeTab) ? saved as OrganizeTab : 'samples';
}

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
  let legacy = false;
  for (let i = 0; i < parts.length; i++) {
    const key = KEYS[parts[i]];
    if (key && parts[i + 1]) { (route as unknown as Record<string, string>)[key] = parts[++i]; continue; }
    if (parts[i] === 'organize') route.view = 'organize';
    // Samples used to be a view of its own; old links open the 抽样 tool.
    else if (parts[i] === 'samples') { route.view = 'organize'; legacy = true; }
  }
  if (legacy && !route.tab) route.tab = 'samples';
  if (route.tab && !ORGANIZE_TABS.includes(route.tab)) route.tab = undefined;
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

function readLocation(): Route {
  const value = parseRoute(location.hash);
  if (/\/g\/[^/]+\/samples(\/|$)/.test(location.hash)) history.replaceState(null, '', formatRoute(value));
  return value;
}
export const route = signal<Route>(readLocation());

/**
 * Where the viewer was pushed from. Closing it while it still shows the same package in the same view
 * returns with history.back(), so the wall or tool underneath, inline or not, is the one left.
 */
interface Opened { library?: string; group?: string; package?: string; view: GroupView; tab?: OrganizeTab }
let opened: Opened | null = null;
const openedAt = (to: Route): Opened => ({ library: to.library, group: to.group, package: to.package, view: to.view, tab: to.tab });

export function navigate(next: Partial<Route>, options: { replace?: boolean } = {}) {
  const full: Route = { view: 'packages', ...next };
  const hash = formatRoute(full);
  if (hash === location.hash && !options.replace) return;
  const openingViewer = Boolean(full.image) && !route.value.image;
  const origin = openingViewer && !options.replace ? openedAt(full) : null;
  if (options.replace) history.replaceState(full.image ? history.state : null, '', hash);
  else history.pushState(origin ? { galleryViewerOrigin: origin } : null, '', hash);
  if (openingViewer) opened = options.replace ? null : openedAt(full);
  if (!full.image) opened = null;
  route.value = full;
  try { localStorage.setItem('gt.lastRoute', hash); } catch { /* storage full or disabled */ }
}

/** Back to the wall the viewer covers; after moving to another package, to that package's wall instead. */
export function closeViewer() {
  const current = route.value;
  if (!current.image) return;
  if (opened && opened.library === current.library && opened.group === current.group && opened.package === current.package && opened.view === current.view && opened.tab === current.tab) {
    opened = null;
    history.back();
    return;
  }
  // Organize tools list images from many packages; closing returns to the tool, not to one package.
  navigate({ ...current, image: undefined, package: current.view === 'organize' ? undefined : current.package }, { replace: true });
}

window.addEventListener('popstate', () => {
  route.value = readLocation();
  // Only entries pushed by navigate know their wall. A pasted hash is a deep link, not a return target.
  opened = route.value.image ? history.state?.galleryViewerOrigin ?? null : null;
  try { localStorage.setItem('gt.lastRoute', location.hash); } catch { /* ignore */ }
});

export function restoreLastRoute() {
  if (location.hash.length > 2) return;
  const saved = localStorage.getItem('gt.lastRoute');
  if (!saved) return;
  // Replace, so closing a restored viewer returns to its package wall instead of leaving the app.
  navigate(parseRoute(saved), { replace: true });
}
