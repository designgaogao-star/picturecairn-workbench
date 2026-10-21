import { useEffect, useState } from 'preact/hooks';
import { isAbort, type Edge, type Group, type ImageItem, type Package } from '../api';
import type { Resume } from '../components/GroupHeader';
import { SelectionBar, useSelection } from '../components/Selection';
import { Thumb } from '../components/Thumb';
import { VirtualGrid } from '../components/VirtualGrid';
import { count, packageParent } from '../lib/format';
import { Icon } from '../lib/icons';
import { navigate, route } from '../lib/router';
import {
  cachedPackage, currentPackage, imagesList, lastViewed, reportError, requestDelete, resolvePackage, tileSize,
} from '../state/app';
import { tileTarget } from './LibraryHome';

/** Package metadata by ID, from the route's package, the cache or the group's package pages. */
export function usePackage(groupId: string, packageId: string): Package | null {
  const current = currentPackage.value;
  const [found, setFound] = useState<Package | null>(() => cachedPackage(packageId) ?? null);
  useEffect(() => {
    if (current?.id === packageId) return;
    const cached = cachedPackage(packageId);
    setFound(cached ?? null);
    if (cached) return;
    const controller = new AbortController();
    resolvePackage(groupId, packageId, controller.signal)
      .then((pkg) => { if (!controller.signal.aborted) setFound(pkg); })
      .catch((error) => { if (!isAbort(error)) reportError(error, '无法读取图包：'); });
    return () => controller.abort();
  }, [groupId, packageId, current?.id === packageId]);
  return current?.id === packageId ? current : found?.id === packageId ? found : null;
}

const tileEdge = (width: number): Edge => (width * Math.min(2, window.devicePixelRatio || 1) > 400 ? 800 : 400);
// Edge the tiles were last drawn at per tile size: stretched columns can need a larger one than the nominal width.
const drawnEdge = new Map<string, Edge>();
/** Thumbnail edge the image wall loads at the current tile size, so prewarmed thumbnails are the ones it shows. */
export const wallEdge = (): Edge => drawnEdge.get(tileSize.value) ?? tileEdge(tileTarget());

interface TileProps { item: ImageItem; width: number; selecting: boolean; selected: boolean; recent: boolean; onOpen: (item: ImageItem) => void; onToggle: (id: string) => void }

function ImageTile({ item, width, selecting, selected, recent, onOpen, onToggle }: TileProps) {
  const edge = tileEdge(width);
  return (
    <button class={`card image-card ${selected ? 'selected' : ''} ${recent ? 'recent' : ''}`} title={item.name}
      aria-label={item.name} aria-pressed={selecting ? selected : undefined}
      onClick={() => (selecting ? onToggle(item.id) : onOpen(item))}>
      <div class="card-media">
        <Thumb id={item.id} edge={edge} />
        {selecting && <span class={`check ${selected ? 'on' : ''}`}><Icon name="Check" size={16} /></span>}
        {item.animated && <span class="badge anim">动图</span>}
        {item.error && <span class="badge bad" title={item.error}>无法解码</span>}
        <span class="card-caption">{item.name}</span>
      </div>
    </button>
  );
}

interface Props {
  groupId: string;
  group: Group | null;
  packageId: string;
  /** Shown inside the group page (a folder with a single package): no way back to a package wall. */
  inline?: boolean;
  /** The group's saved position, marked and revealed when nothing was viewed in this session. */
  resume?: Resume | null;
}

export function ImageWall({ groupId, group, packageId, inline, resume }: Props) {
  const list = imagesList(packageId);
  const total = list.total.value;
  list.version.value;
  const pkg = usePackage(groupId, packageId);
  const selection = useSelection(packageId);
  const viewed = lastViewed.value?.package === packageId ? lastViewed.value.image : null;
  const recent = viewed ?? (resume?.packageId === packageId ? resume.imageId : null);
  const reveal = recent ? list.indexOf((item) => item.id === recent) : -1;
  const tile = tileTarget();
  const r = route.value;
  const parent = pkg ? packageParent(pkg.rel, pkg.name, group?.rel) : '';

  const open = (item: ImageItem) => navigate({ library: r.library, group: groupId, package: packageId, image: item.id });

  const removeSelected = () => {
    const names: Record<string, string> = {};
    for (const [, item] of list.cached()) if (selection.ids.has(item.id)) names[item.id] = item.rel;
    const ids = [...selection.ids];
    requestDelete({
      targets: ids.map((id) => ({ kind: 'image' as const, id })),
      title: ids.length === 1 ? `图片“${names[ids[0]]?.split('/').pop() ?? ''}”` : `${ids.length} 张图片`,
      names, onDone: () => selection.stop(),
    });
  };

  const removePackage = () => {
    if (!pkg) return;
    requestDelete({
      targets: [{ kind: 'package', id: pkg.id }], title: `图包“${pkg.name}”（${count(pkg.image_count)} 张）`,
      names: { [pkg.id]: pkg.rel }, includesFolders: true,
      onDone: (done) => { if (done.has(pkg.id) && route.value.package === pkg.id) navigate({ library: r.library, group: groupId }, { replace: true }); },
    });
  };

  return (
    <div class={`wall image-wall ${inline ? 'inline' : ''}`}>
      <SelectionBar selection={selection} noun="图片" unit="张" onDelete={removeSelected}>
        {!inline && (
          <button class="btn small" onClick={() => navigate({ library: r.library, group: groupId })} title="返回图包列表">
            <Icon name="ArrowLeft" size={14} />图包
          </button>
        )}
        <span class="wall-title" title={pkg?.rel}>{pkg ? (pkg.loose ? '散图' : pkg.name) : '…'}</span>
        {parent && <span class="muted wall-sub" title={parent}>{parent}</span>}
        <span class="muted num">{total === null ? '' : `${count(total)} 张`}</span>
        {pkg && !pkg.loose && (
          <button class="icon-btn small danger-hover" title="删除整个图包…" aria-label="删除整个图包" onClick={removePackage}>
            <Icon name="Trash2" size={16} />
          </button>
        )}
      </SelectionBar>
      <VirtualGrid list={list} tile={tile} height={(width) => Math.round(width * 4 / 3)} anchorKey={`images:${packageId}`}
        keyOf={(item) => item.id} label="图片" class="cards images" reveal={reveal >= 0 ? reveal : null}
        empty={<div class="empty"><Icon name="Image" size={36} /><p>这个图包里没有图片</p></div>}
        render={(item, _index, layout) => {
          drawnEdge.set(tileSize.value, tileEdge(layout.tileWidth));
          return item
            ? <ImageTile item={item} width={layout.tileWidth} selecting={selection.active} selected={selection.ids.has(item.id)}
              recent={item.id === recent} onOpen={open} onToggle={selection.toggle} />
            : <div class="card skeleton" />;
        }} />
    </div>
  );
}
