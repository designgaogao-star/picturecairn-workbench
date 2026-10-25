import { useEffect, useMemo, useState } from 'preact/hooks';
import { pickEdge, type Group, type Package } from '../api';
import { GroupMenu, ModeTabs, NarrowMarks, NarrowSizes, ResumeButton, SizeSegment, type Resume } from '../components/GroupHeader';
import { MarkSegment } from '../components/Marks';
import { SelectionBar, useSelection } from '../components/Selection';
import { Thumb } from '../components/Thumb';
import { anchorOf, VirtualGrid } from '../components/VirtualGrid';
import { count, packageParent } from '../lib/format';
import { Icon } from '../lib/icons';
import { navigate, route } from '../lib/router';
import { currentLibrary, lastViewed, packagesList, requestDelete, toast, wallReturn } from '../state/app';
import { ImageWall } from './ImageWall';
import { tileTarget } from './LibraryHome';
import { inspectionScope, useInspection, type InspectResource } from '../state/inspection';

interface TileProps {
  pkg: Package; group: Group; width: number; resume: Resume | null;
  selecting: boolean; selected: boolean; recent: boolean; onToggle: (id: string, range?: boolean) => void; onInspect: (item: Package) => void;
}

function PackageTile({ pkg, group, width, resume, selecting, selected, recent, onToggle, onInspect }: TileProps) {
  const r = route.value;
  const parent = packageParent(pkg.rel, pkg.name, group.rel);
  const edge = pickEdge(width * Math.min(2, window.devicePixelRatio || 1)) === 400 ? 400 : 800;
  const here = resume?.packageId === pkg.id ? resume : null;
  const open = (image: string | null) => {
    if (!image) { navigate({ library: r.library, group: r.group, package: pkg.id }); return; }
    navigate({ library: r.library, group: r.group, package: pkg.id, image });
  };
  const toggle = (range = false) => {
    if (pkg.loose) { toast('散图不是独立的图包，不能整包删除；请进入图片墙逐张选择', 'info'); return; }
    onToggle(pkg.id, range);
  };
  return (
    <div class={`card package-card ${selecting ? 'selecting' : ''} ${selected ? 'selected' : ''} ${recent ? 'recent' : ''}`} onFocusCapture={() => onInspect(pkg)}>
      <button class="card-hit" onClick={(event) => selecting || event.shiftKey ? toggle(event.shiftKey) : open(null)} title={pkg.rel || pkg.name}
        aria-label={`${pkg.loose ? '散图' : pkg.name}，${pkg.image_count} 张`} aria-pressed={selecting ? selected : undefined}
        onKeyDown={(event) => {
          if (event.key === ' ') { event.preventDefault(); toggle(event.shiftKey); }
          else if (event.key === 'Enter') { event.preventDefault(); open(null); }
        }} />
      <div class="card-media">
        {pkg.cover_id ? <Thumb id={pkg.cover_id} edge={edge} /> : <div class="card-placeholder"><Icon name="Image" size={28} /></div>}
        {pkg.loose && <span class="badge loose">散图</span>}
        <span class="badge count">{count(pkg.image_count)}</span>
      </div>
      {!pkg.loose && <button class={`check choice-check ${selected ? 'on' : ''}`} aria-label={`选择图包：${pkg.name}`} aria-pressed={selected}
        onClick={(event) => toggle(event.shiftKey)}><Icon name="Check" size={16} /></button>}
      {!selecting && pkg.cover_id && (
        <button class="tile-corner" title="从封面开始查看" aria-label="从封面开始查看" onClick={() => open(pkg.cover_id)}>
          <Icon name="Maximize" size={16} />
        </button>
      )}
      {!selecting && here && (
        <button class="resume-chip" title={`继续浏览：${here.name}`} onClick={() => open(here.imageId)}>
          <Icon name="History" size={12} />第 {here.index + 1} 张
        </button>
      )}
      <div class="card-body">
        <span class="card-title" title={pkg.name}>{pkg.loose ? '散图' : pkg.name}</span>
        {parent && <span class="card-sub muted" title={parent}>{parent}</span>}
      </div>
    </div>
  );
}

export function PackageWall({ group, resume }: { group: Group; resume: Resume | null }) {
  const list = packagesList(group.id);
  const total = list.total.value;
  const version = list.version.value;
  const selection = useSelection(group.id, list, (item) => !item.loose);
  const [focused, setFocused] = useState<Package | null>(null);
  const selectedInfo = useMemo(() => [...selection.items.values()].map((item): InspectResource => ({ kind: 'package', item })), [selection.items]);
  const focusedInfo = useMemo((): InspectResource | null => focused?.group_id === group.id ? { kind: 'package', item: focused } : null, [focused, group.id]);
  useInspection(inspectionScope(), focusedInfo, selectedInfo, !(total === 1 && list.item(0)));
  const recent = (lastViewed.value?.group === group.id ? lastViewed.value.package : null) ?? resume?.packageId ?? null;
  const anchorKey = `wall:${list.key}`;
  const [restoredGroup, setRestoredGroup] = useState<string | null>(null);
  const returning = wallReturn.value?.group === group.id ? wallReturn.value : null;
  const initial = restoredGroup !== group.id && anchorOf(anchorKey) === undefined ? resume?.packageId : null;
  const target = returning?.package ?? initial;
  const reveal = target ? list.indexOf((pkg) => pkg.id === target) : -1;
  const revealed = () => {
    setRestoredGroup(group.id);
    if (returning && wallReturn.peek() === returning) wallReturn.value = null;
  };
  const tile = tileTarget();
  // The inline view mounts no grid for this list, so it keeps page 0 registered to notice packages added or removed later.
  useEffect(() => { if (total === 1) list.ensure(0, 1, 'single'); else list.release('single'); }, [list, total, version]);
  useEffect(() => () => list.release('single'), [list]);

  // A folder holding a single package shows its images directly instead of a wall of one.
  const only = total === 1 ? list.item(0) : undefined;
  if (only) return <ImageWall groupId={group.id} group={group} packageId={only.id} inline resume={resume} />;

  const remove = () => {
    const ids = [...selection.ids];
    const names: Record<string, string> = {};
    for (const pkg of selection.items.values()) names[pkg.id] = pkg.rel || pkg.name;
    requestDelete({
      targets: ids.map((id) => ({ kind: 'package' as const, id })),
      title: ids.length === 1 ? `图包“${names[ids[0]] ?? ''}”` : `${ids.length} 个图包`,
      names, includesFolders: true,
      onDone: selection.remove,
    });
  };

  return (
    <div class="wall">
      <SelectionBar selection={selection} noun="图包" onDelete={remove}
        before={<span class="toolbar-text toolbar-count">{total === null ? '正在读取图包…' : `${count(total)} 个图包`}</span>}
        after={<><SizeSegment class="at-wide" /><MarkSegment class="at-wide" groupId={group.id} value={group.state} />
          {currentLibrary.value && <GroupMenu group={group} lib={currentLibrary.value}><NarrowMarks group={group} /><NarrowSizes /></GroupMenu>}</>}>
        <ModeTabs /><span class="toolbar-sep" /><ResumeButton resume={resume} />
      </SelectionBar>
      <VirtualGrid list={list} tile={tile} height={(width) => Math.round(width * 4 / 3) + 52} anchorKey={anchorKey}
        onVisibleChange={selection.onVisibleChange}
        keyOf={(pkg) => pkg.id} label="图包" class="cards" reveal={!route.value.image && reveal >= 0 ? reveal : null} onReveal={revealed}
        focusKey={!route.value.image && lastViewed.value?.group === group.id ? lastViewed.value.package : null}
        empty={<div class="empty"><Icon name="FolderOpen" size={36} /><p>此文件夹中没有图片</p></div>}
        render={(pkg, _index, layout) => (pkg
          ? <PackageTile pkg={pkg} group={group} width={layout.tileWidth} resume={resume} selecting={selection.active}
            selected={selection.ids.has(pkg.id)} recent={pkg.id === recent} onToggle={selection.toggle} onInspect={setFocused} />
          : <div class="card skeleton" />)} />
    </div>
  );
}
