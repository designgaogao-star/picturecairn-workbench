import { pickEdge, type Group, type Library } from '../api';
import { AddLibraryForm } from '../components/AddLibraryDialog';
import { MarkBadge } from '../components/Marks';
import { FilterBar, libraryStatus, rescanLibrary } from '../components/Sidebar';
import { Thumb } from '../components/Thumb';
import { VirtualGrid } from '../components/VirtualGrid';
import { bytes, count, stripCategory, time } from '../lib/format';
import { Icon } from '../lib/icons';
import { navigate } from '../lib/router';
import { groupFilter, groupsList, narrow, scanStatus, tasks, tileSize } from '../state/app';
import { ProgressBar } from '../components/Progress';
import { taskFraction } from '../lib/tasks';

const TILE: Record<string, number> = { s: 150, m: 210, l: 300 };
// A phone-width wall still gets three, two and one columns.
const NARROW_TILE: Record<string, number> = { s: 100, m: 150, l: 240 };
/** Target tile width for the current tile size; walls derive their columns from it. */
export const tileTarget = () => (narrow.value ? NARROW_TILE : TILE)[tileSize.value];

function GroupCard({ group, width }: { group: Group; width: number }) {
  const cover = group.cover_id;
  const edge = pickEdge(width * Math.min(2, window.devicePixelRatio || 1));
  return (
    <button class="card group-card" onClick={() => navigate({ library: group.library_id, group: group.id })} title={group.rel || '图库根目录中的散图'}>
      <div class="card-media">
        {cover ? <Thumb id={cover} edge={edge === 400 ? 400 : 800} />
          : <div class="card-placeholder"><Icon name="Folder" size={32} /></div>}
        <MarkBadge state={group.state} />
      </div>
      <div class="card-body">
        <span class="card-title">{stripCategory(group.name) || '（根目录散图）'}</span>
        <span class="card-meta">
          {group.category && group.category !== '其他' && <span class="badge category">{group.category}</span>}
          <span class="muted">{count(group.image_count)} 张 · {bytes(group.bytes)}</span>
        </span>
      </div>
    </button>
  );
}

function ScanProgress({ lib }: { lib: Library }) {
  const task = tasks.value.find((item) => item.kind === 'scan' && item.payload.library_id === lib.id && (item.state === 'running' || item.state === 'queued'));
  if (!task && !['scanning', 'pending'].includes(scanStatus(lib))) return null;
  return (
    <div class="scan-progress">
      <Icon name="LoaderCircle" spin size={16} />
      <span>正在建立索引{task?.current ? `：${task.current}` : '…'}</span>
      {task && <span class="muted num">{task.progress ? count(task.progress) : ''}{task.total ? ` / ${count(task.total)}` : ''}</span>}
      <ProgressBar fraction={task ? taskFraction(task) : null} />
    </div>
  );
}

export function LibraryHome({ lib }: { lib: Library }) {
  const filter = groupFilter.value;
  const list = groupsList(lib.id, filter);
  const total = list.total.value;
  const status = libraryStatus(lib);
  const tile = tileTarget();
  const scanning = ['scanning', 'pending'].includes(scanStatus(lib));
  return (
    <div class="page library-home">
      <section class="page-head">
        <div class="page-title">
          <h1>{lib.name}</h1>
          <span class="muted path" title={lib.path}>{lib.path}</span>
        </div>
        <div class="page-meta">
          <span class={`status ${status.tone}`}><span class={`dot ${status.tone}`} />{status.text}</span>
          {lib.last_scan && <span class="muted">上次扫描 {time(lib.last_scan)}</span>}
          {total !== null && <span class="muted">{count(total)} 个文件夹{filter.state || filter.category ? '（已筛选）' : ''}</span>}
          <button class="btn small" onClick={() => void rescanLibrary(lib)}><Icon name="RefreshCw" size={14} spin={scanStatus(lib) === 'scanning'} />重新扫描</button>
        </div>
        <FilterBar />
      </section>
      <ScanProgress lib={lib} />
      <VirtualGrid list={list} tile={tile} height={(width) => Math.round(width * 0.75) + 58} anchorKey={`home:${list.key}`}
        keyOf={(group) => group.id} label="文件夹" class="cards"
        empty={(
          <div class="empty">
            <Icon name={scanning ? 'LoaderCircle' : 'FolderOpen'} size={36} spin={scanning} />
            <p>{filter.state || filter.category ? '没有符合筛选条件的文件夹' : scanning ? '正在扫描，文件夹会陆续出现…' : '这个图库里还没有找到图片'}</p>
            {(filter.state || filter.category) && <button class="btn" onClick={() => { groupFilter.value = { state: '', category: '' }; }}>清除筛选</button>}
          </div>
        )}
        render={(group, _index, layout) => (group ? <GroupCard group={group} width={layout.tileWidth} /> : <div class="card skeleton" />)} />
    </div>
  );
}

export function Welcome() {
  return (
    <div class="page welcome">
      <div class="welcome-box">
        <Icon name="Images" size={40} />
        <h1>添加第一个图库</h1>
        <p class="muted">选择存放图片的文件夹。扫描在后台进行，扫描到的文件夹会立即可以浏览。</p>
        <AddLibraryForm />
      </div>
    </div>
  );
}
