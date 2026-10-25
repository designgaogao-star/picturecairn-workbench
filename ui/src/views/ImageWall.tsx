import { useEffect, useMemo, useState } from 'preact/hooks';
import { isAbort, type Edge, type Group, type ImageItem, type Package } from '../api';
import { GroupMenu, ImageFitOptions, ModeTabs, NarrowMarks, NarrowSizes, ResumeButton, SizeSegment, type Resume } from '../components/GroupHeader';
import { MarkSegment } from '../components/Marks';
import { Menu } from '../components/Menu';
import { SelectionBar, useSelection } from '../components/Selection';
import { Thumb } from '../components/Thumb';
import { anchorOf, VirtualGrid } from '../components/VirtualGrid';
import { bytes, count, packageParent } from '../lib/format';
import { Icon } from '../lib/icons';
import { navigate, route } from '../lib/router';
import {
  cachedPackage, currentLibrary, currentPackage, imageFit, imagesList, lastViewed, reportError, requestDelete, resolvePackage, tileSize, wallReturn,
} from '../state/app';
import { tileTarget } from './LibraryHome';
import { inspectionScope, useInspection, type InspectResource } from '../state/inspection';

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

interface TileProps { item: ImageItem; width: number; selecting: boolean; selected: boolean; recent: boolean; onOpen: (item: ImageItem) => void; onToggle: (id: string, range?: boolean) => void; onInspect: (item: ImageItem) => void }

function ImageTile({ item, width, selecting, selected, recent, onOpen, onToggle, onInspect }: TileProps) {
  const edge = tileEdge(width);
  return (
    <div class={`card image-card ${selecting ? 'selecting' : ''} ${selected ? 'selected' : ''} ${recent ? 'recent' : ''}`} onFocusCapture={() => onInspect(item)}>
      <button class="card-hit" title={item.name} aria-label={item.name} aria-pressed={selecting ? selected : undefined}
        onClick={(event) => selecting || event.shiftKey ? onToggle(item.id, event.shiftKey) : onOpen(item)}
        onKeyDown={(event) => {
          if (event.key === ' ') { event.preventDefault(); onToggle(item.id, event.shiftKey); }
          else if (event.key === 'Enter') { event.preventDefault(); onOpen(item); }
        }} />
      <div class="card-media">
        <Thumb id={item.id} edge={edge} fit={imageFit.value} />
        {item.animated && <span class="badge anim">动图</span>}
        {item.error && <span class="badge bad" title={item.error}>无法解码</span>}
      </div>
      <button class={`check choice-check ${selected ? 'on' : ''}`} aria-label={`选择图片：${item.name}`} aria-pressed={selected}
        onClick={(event) => onToggle(item.id, event.shiftKey)}><Icon name="Check" size={16} /></button>
      <div class="card-body"><span class="card-title" title={item.name}>{item.name}</span>
        <span class="card-sub muted">{item.width && item.height ? `${item.width} × ${item.height} · ` : ''}{bytes(item.size)}</span></div>
    </div>
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
  const selection = useSelection(packageId, list);
  const [focused, setFocused] = useState<ImageItem | null>(null);
  const selectedInfo = useMemo(() => [...selection.items.values()].map((item): InspectResource => ({ kind: 'image', item })), [selection.items]);
  const focusedInfo = useMemo((): InspectResource | null => focused?.package_id === packageId ? { kind: 'image', item: focused } : null, [focused, packageId]);
  useInspection(inspectionScope(), focusedInfo, selectedInfo);
  const viewed = lastViewed.value?.package === packageId ? lastViewed.value.image : null;
  const recent = viewed ?? (resume?.packageId === packageId ? resume.imageId : null);
  const anchorKey = `images:${packageId}`;
  const [restoredPackage, setRestoredPackage] = useState<string | null>(null);
  const returning = wallReturn.value?.package === packageId ? wallReturn.value : null;
  const initial = restoredPackage !== packageId && anchorOf(anchorKey) === undefined && resume?.packageId === packageId ? resume : null;
  const target = returning?.image ?? initial?.imageId;
  const cachedIndex = target ? list.indexOf((item) => item.id === target) : -1;
  const reveal = cachedIndex >= 0 ? cachedIndex : returning?.index ?? initial?.index ?? -1;
  const revealed = () => {
    setRestoredPackage(packageId);
    if (returning && wallReturn.peek() === returning) wallReturn.value = null;
  };
  const tile = tileTarget();
  const r = route.value;
  const parent = pkg ? packageParent(pkg.rel, pkg.name, group?.rel) : '';

  const open = (item: ImageItem) => navigate({ library: r.library, group: groupId, package: packageId, image: item.id });

  const removeSelected = () => {
    const names: Record<string, string> = {};
    for (const item of selection.items.values()) names[item.id] = item.rel;
    const ids = [...selection.ids];
    requestDelete({
      targets: ids.map((id) => ({ kind: 'image' as const, id })),
      title: ids.length === 1 ? `图片“${names[ids[0]]?.split('/').pop() ?? ''}”` : `${ids.length} 张图片`,
      names, onDone: selection.remove,
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
      <SelectionBar selection={selection} noun="图片" unit="张" onDelete={removeSelected}
        after={<><SizeSegment class="at-wide" />{inline && group && currentLibrary.value
          ? <><MarkSegment class="at-wide" groupId={group.id} value={group.state} /><GroupMenu group={group} lib={currentLibrary.value}><NarrowMarks group={group} /><NarrowSizes /><ImageFitOptions /></GroupMenu></>
          : <Menu label="更多操作"><NarrowSizes /><ImageFitOptions />{pkg && !pkg.loose && <button role="menuitem" class="danger" onClick={removePackage}><Icon name="Trash2" size={16} />删除此图包…</button>}</Menu>}</>}>
        <ModeTabs /><span class="toolbar-sep" />
        {inline ? <ResumeButton resume={resume} /> : <>
          <button class="btn subtle small" onClick={() => navigate({ library: r.library, group: groupId })} title="返回图包列表"><Icon name="ArrowLeft" size={14} /><span class="label-wide">图包</span></button>
          <span class="toolbar-title" title={pkg?.rel}>{pkg ? (pkg.loose ? '散图' : pkg.name) : '…'}</span>
          {parent && <span class="muted toolbar-text at-wide" title={parent}>{parent}</span>}
          <span class="muted num toolbar-count">{total === null ? '' : `${count(total)} 张`}</span>
        </>}
      </SelectionBar>
      <VirtualGrid list={list} tile={tile} height={(width) => Math.round(width) + 56} anchorKey={anchorKey}
        onVisibleChange={selection.onVisibleChange}
        keyOf={(item) => item.id} label="图片" class="cards images" reveal={!r.image && reveal >= 0 ? reveal : null} onReveal={revealed}
        focusKey={!r.image ? viewed ?? focused?.id : null}
        empty={<div class="empty"><Icon name="Image" size={36} /><p>这个图包里没有图片</p></div>}
        render={(item, _index, layout) => {
          drawnEdge.set(tileSize.value, tileEdge(layout.tileWidth));
          return item
            ? <ImageTile item={item} width={layout.tileWidth} selecting={selection.active} selected={selection.ids.has(item.id)}
              recent={item.id === recent} onOpen={open} onToggle={selection.toggle} onInspect={setFocused} />
            : <div class="card skeleton" />;
        }} />
    </div>
  );
}
