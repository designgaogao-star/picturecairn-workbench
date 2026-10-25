import { effect, signal } from '@preact/signals';
import { useLayoutEffect } from 'preact/hooks';
import type { ImageItem, Package } from '../api';
import { route } from '../lib/router';

export type InspectResource = { kind: 'image'; item: ImageItem } | { kind: 'package'; item: Package };
interface Inspection { scope: string; items: InspectResource[] }
export const inspectorOpen = signal(localStorage.getItem('gt.inspector') === '1');
export const inspection = signal<Inspection | null>(null);
export const inspectionScope = () => {
  const r = route.value;
  return `${r.library ?? ''}:${r.group ?? ''}:${r.view}:${r.package ?? ''}`;
};
effect(() => { localStorage.setItem('gt.inspector', inspectorOpen.value ? '1' : '0'); });

/** Only metadata already held by the wall is published; inspecting never enumerates files. */
export function useInspection(scope: string, focused: InspectResource | null, selected: InspectResource[], enabled = true) {
  useLayoutEffect(() => {
    if (!enabled) return;
    const own: Inspection = { scope, items: selected.length ? selected : focused ? [focused] : [] };
    inspection.value = own;
    return () => { if (inspection.peek() === own) inspection.value = null; };
  }, [scope, focused, selected, enabled]);
}
