import { useEffect } from 'preact/hooks';
import { pickEdge, type Group, type Package } from '../api';
import type { Resume } from '../components/GroupHeader';
import { SelectionBar, useSelection } from '../components/Selection';
import { Thumb } from '../components/Thumb';
import { VirtualGrid } from '../components/VirtualGrid';
import { count, packageParent } from '../lib/format';
import { Icon } from '../lib/icons';
import { navigate, route } from '../lib/router';
import { lastViewed, packagesList, requestDelete, toast } from '../state/app';
import { ImageWall } from './ImageWall';
import { tileTarget } from './LibraryHome';

interface TileProps {
  pkg: Package; group: Group; width: number; resume: Resume | null;
  selecting: boolean; selected: boolean; recent: boolean; onToggle: (id: string) => void;
}

function PackageTile({ pkg, group, width, resume, selecting, selected, recent, onToggle }: TileProps) {
  const r = route.value;
  const parent = packageParent(pkg.rel, pkg.name, group.rel);
  const edge = pickEdge(width * Math.min(2, window.devicePixelRatio || 1)) === 400 ? 400 : 800;
  const here = resume?.packageId === pkg.id ? resume : null;
  const open = (image: string | null) => {
    if (!image) { navigate({ library: r.library, group: r.group, package: pkg.id }); return; }
    navigate({ library: r.library, group: r.group, package: pkg.id, image });
  };
  const click = () => {
    if (!selecting) { open(pkg.cover_id); return; }
    if (pkg.loose) { toast('散图不是独立的图包，不能整包删除；请进入图片墙逐张选择', 'info'); return; }
    onToggle(pkg.id);
  };
  return (
    <div class={`card package-card ${selected ? 'selected' : ''} ${recent ? 'recent' : ''}`}>
      <button class="card-media" onClick={click} title={pkg.rel || pkg.name}
        aria-label={`${pkg.loose ? '散图' : pkg.name}，${pkg.image_count} 张`} aria-pressed={selecting ? selected : undefined}>
        {pkg.cover_id ? <Thumb id={pkg.cover_id} edge={edge} /> : <div class="card-placeholder"><Icon name="Image" size={28} /></div>}
        {selecting && !pkg.loose && <span class={`check ${selected ? 'on' : ''}`}><Icon name="Check" size={16} /></span>}
        {pkg.loose && <span class="badge loose">散图</span>}
        <span class="badge count">{count(pkg.image_count)}</span>
      </button>
      {!selecting && (
        <button class="tile-corner" title="图片墙：查看此图包的全部图片" aria-label="打开图片墙" onClick={() => open(null)}>
          <Icon name="LayoutGrid" size={16} />
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
  const selection = useSelection(group.id);
  const recent = (lastViewed.value?.group === group.id ? lastViewed.value.package : null) ?? resume?.packageId ?? null;
  const reveal = recent ? list.indexOf((pkg) => pkg.id === recent) : -1;
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
    for (const [, pkg] of list.cached()) if (selection.ids.has(pkg.id)) names[pkg.id] = pkg.rel || pkg.name;
    requestDelete({
      targets: ids.map((id) => ({ kind: 'package' as const, id })),
      title: ids.length === 1 ? `图包“${names[ids[0]] ?? ''}”` : `${ids.length} 个图包`,
      names, includesFolders: true,
      onDone: () => selection.stop(),
    });
  };

  return (
    <div class="wall">
      <SelectionBar selection={selection} noun="图包" onDelete={remove}>
        <span class="muted">{total === null ? '正在读取图包…' : `${count(total)} 个图包`}</span>
      </SelectionBar>
      <VirtualGrid list={list} tile={tile} height={(width) => Math.round(width * 4 / 3) + 52} anchorKey={`wall:${list.key}`}
        keyOf={(pkg) => pkg.id} label="图包" class="cards" reveal={reveal >= 0 ? reveal : null}
        empty={<div class="empty"><Icon name="FolderOpen" size={36} /><p>此文件夹中没有图片</p></div>}
        render={(pkg, _index, layout) => (pkg
          ? <PackageTile pkg={pkg} group={group} width={layout.tileWidth} resume={resume} selecting={selection.active}
            selected={selection.ids.has(pkg.id)} recent={pkg.id === recent} onToggle={selection.toggle} />
          : <div class="card skeleton" />)} />
    </div>
  );
}
