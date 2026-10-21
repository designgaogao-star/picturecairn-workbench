import { signal } from '@preact/signals';
import { useEffect, useRef } from 'preact/hooks';
import { client, describeError, isAbort, rememberImages, type Group, type ImageItem } from '../api';
import { Thumb } from '../components/Thumb';
import { count } from '../lib/format';
import { Icon } from '../lib/icons';
import { navigate, route } from '../lib/router';
import { lastViewed, mediaEpoch } from '../state/app';
import { tileTarget } from './LibraryHome';

export interface SampleSet { group: string; seed: number; count: number; items: ImageItem[] | null; error: string | null }
export const COUNTS = [20, 40, 100];

// The seed is kept per tab, so a reload or a deep link into the viewer reproduces the same batch.
const KEY = (group: string) => `gt.sample:${group}`;
const newSeed = () => Math.floor(Math.random() * 2 ** 31);

function savedParams(group: string): { seed: number; count: number } {
  try {
    const saved = JSON.parse(sessionStorage.getItem(KEY(group)) || 'null') as { seed?: unknown; count?: unknown } | null;
    if (saved && Number.isInteger(saved.seed) && COUNTS.includes(saved.count as number)) {
      return { seed: saved.seed as number, count: saved.count as number };
    }
  } catch { /* fall through */ }
  return { seed: newSeed(), count: 40 };
}

export const samples = signal<SampleSet | null>(null);
let controller: AbortController | null = null;

export function loadSamples(group: string, params = savedParams(group)) {
  controller?.abort();
  const own = controller = new AbortController();
  try { sessionStorage.setItem(KEY(group), JSON.stringify(params)); } catch { /* storage unavailable */ }
  samples.value = { group, ...params, items: null, error: null };
  client.request('get', '/api/v1/groups/{group_id}/samples', {
    params: { path: { group_id: group }, query: { count: params.count, seed: params.seed } }, signal: own.signal,
  }).then((items) => {
    rememberImages(items);
    if (controller === own) samples.value = { group, ...params, items, error: null };
  }).catch((error) => {
    if (!isAbort(error) && controller === own) samples.value = { group, ...params, items: null, error: describeError(error) };
  });
}

/** The current batch for a group, loading the saved one when another group's batch is held. */
export function useSamples(group: string | undefined): SampleSet | null {
  const current = samples.value;
  useEffect(() => {
    if (group && samples.value?.group !== group) loadSamples(group);
  }, [group]);
  return current && current.group === group ? current : null;
}

/** Directory of an image relative to its group, e.g. "第1季 / Vol.01". */
function folderOf(item: ImageItem, group: Group | null): string {
  let rel = item.rel.slice(0, Math.max(0, item.rel.length - item.name.length - 1));
  if (group?.rel && rel.startsWith(group.rel)) rel = rel.slice(group.rel.length).replace(/^\//, '');
  return rel.split('/').filter(Boolean).join(' / ');
}

function SampleTile({ item, group, recent }: { item: ImageItem; group: Group | null; recent: boolean }) {
  const ref = useRef<HTMLButtonElement>(null);
  const viewing = Boolean(route.value.image);
  // Coming back from the viewer: bring the last viewed sample into view.
  useEffect(() => { if (recent && !viewing) ref.current?.scrollIntoView({ block: 'nearest' }); }, [recent, viewing]);
  const edge = tileTarget() * Math.min(2, window.devicePixelRatio || 1) > 400 ? 800 : 400;
  const folder = folderOf(item, group);
  const r = route.value;
  return (
    <button ref={ref} class={`card image-card ${recent ? 'recent' : ''}`} title={`${item.name}${folder ? `\n${folder}` : ''}`}
      onClick={() => navigate({ library: r.library, group: r.group, view: 'samples', image: item.id })}>
      <div class="card-media">
        <Thumb id={item.id} edge={edge} />
        {item.animated && <span class="badge anim">动图</span>}
        {item.error && <span class="badge bad" title={item.error}>无法解码</span>}
      </div>
      <div class="card-body">
        <span class="card-title">{item.name}</span>
        {folder && <span class="card-sub muted">{folder}</span>}
      </div>
    </button>
  );
}

export function Samples({ groupId, group }: { groupId: string; group: Group | null }) {
  const set = useSamples(groupId);
  mediaEpoch.value; // a reconnect re-renders failed previews
  const recent = lastViewed.value?.group === groupId ? lastViewed.value.image : null;
  const reshuffle = (size = set?.count ?? 40) => loadSamples(groupId, { seed: newSeed(), count: size });
  const items = set?.items;
  return (
    <div class="wall samples">
      <div class="wall-bar">
        <span>随机抽取</span>
        <div class="segment" role="radiogroup" aria-label="抽样数量">
          {COUNTS.map((value) => (
            <button key={value} role="radio" aria-checked={set?.count === value} class={set?.count === value ? 'active' : ''}
              onClick={() => { if (set?.count !== value) loadSamples(groupId, { seed: set?.seed ?? newSeed(), count: value }); }}>
              {value} 张
            </button>
          ))}
        </div>
        {items && <span class="muted">{items.length < (set?.count ?? 0) ? `文件夹中共 ${count(items.length)} 张，已全部列出` : ''}</span>}
        <span class="spacer" />
        <button class="btn small" onClick={() => reshuffle()} disabled={!set || (!items && !set.error)}>
          <Icon name="Dices" size={14} />换一批
        </button>
      </div>
      <div class="sample-scroll">
        {set?.error && (
          <div class="vgrid-error" role="alert">
            <span>抽样失败：{set.error}</span>
            <button class="btn small" onClick={() => loadSamples(groupId, { seed: set.seed, count: set.count })}>重试</button>
          </div>
        )}
        {!set?.error && !items && <div class="empty"><Icon name="LoaderCircle" spin size={28} /><p>正在抽取…</p></div>}
        {items && !items.length && <div class="empty"><Icon name="Image" size={36} /><p>此文件夹中没有图片</p></div>}
        {items && items.length > 0 && (
          <div class="sample-grid" style={{ '--tile': `${tileTarget()}px` }} role="list" aria-label="抽样图片">
            {items.map((item) => <SampleTile key={item.id} item={item} group={group} recent={item.id === recent} />)}
          </div>
        )}
      </div>
    </div>
  );
}
