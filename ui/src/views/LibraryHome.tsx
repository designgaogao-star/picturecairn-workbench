import { pickEdge, type Group, type Library } from '../api';
import { AddLibraryForm } from '../components/AddLibraryDialog';
import { LibraryMenu } from '../components/LibraryDialog';
import { Brand } from '../components/Brand';
import { SizeSegment } from '../components/GroupHeader';
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

const TILE: Record<string, number> = { s: 180, m: 230, l: 310 };
// A phone-width wall still gets three, two and one columns.
const NARROW_TILE: Record<string, number> = { s: 100, m: 150, l: 240 };
/** Target tile width for the current tile size; walls derive their columns from it. */
export const tileTarget = () => (narrow.value ? NARROW_TILE : TILE)[tileSize.value];

function GroupCard({ group, width }: { group: Group; width: number }) {
  const cover = group.cover_id;
  const edge = pickEdge(width * Math.min(2, window.devicePixelRatio || 1));
  return (
    <div class="card group-card">
      <button class="card-hit" onClick={() => navigate({ library: group.library_id, group: group.id })} title={group.rel || '图库根目录中的散图'} aria-label={stripCategory(group.name) || '图库根目录中的散图'} />
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
    </div>
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
      <section class="library-context" aria-labelledby="library-context-title">
        <div class="library-context-copy">
          <div class="library-context-kicker">
            <span class={`status ${status.tone}`}><span class={`dot ${status.tone}`} />{status.text}</span>
            <span class="context-divider" aria-hidden="true" />
            <span class="muted">本地图库</span>
          </div>
          <h1 id="library-context-title">图库概览</h1>
          <p class="library-path" title={lib.path}><Icon name="FolderOpen" size={14} />{lib.path}</p>
        </div>
        <dl class="library-context-stats">
          <div><dt>文件夹</dt><dd class="num">{total === null ? '—' : count(total)}</dd></div>
          <div><dt>上次扫描</dt><dd>{lib.last_scan ? time(lib.last_scan) : '尚未扫描'}</dd></div>
        </dl>
      </section>
      <section class="toolbar wrap" aria-label="图库工具">
        <FilterBar /><SizeSegment />
        <span class="spacer" />
        <button class="btn subtle small" title="重新扫描" onClick={() => void rescanLibrary(lib)}><Icon name="RefreshCw" size={14} spin={scanStatus(lib) === 'scanning'} /><span class="label-wide">重新扫描</span></button>
        <LibraryMenu library={lib} />
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
      <div class="welcome-layout">
        <section class="welcome-copy" aria-labelledby="welcome-title">
          <Brand />
          <p class="welcome-kicker">PictureCairn · 影标图片工作台</p>
          <h1 id="welcome-title">从你熟悉的文件夹开始</h1>
          <p class="welcome-lede">选择一个本地图片目录。原图留在原处，图库只记录索引和浏览位置。</p>
          <ul class="welcome-points">
            <li><Icon name="FolderOpen" size={16} /><span>按真实目录和图包浏览</span></li>
            <li><Icon name="History" size={16} /><span>关掉再开，回到上次看到的位置</span></li>
            <li><Icon name="CopyCheck" size={16} /><span>整理前先核实，删除逐项反馈</span></li>
          </ul>
        </section>
        <section class="welcome-box" aria-labelledby="welcome-form-title">
          <div class="welcome-box-head">
            <span class="welcome-box-mark"><Icon name="FolderPlus" size={18} /></span>
            <div><h2 id="welcome-form-title">添加第一个图库</h2><p>索引会在后台建立，扫描到的内容可以立即浏览。</p></div>
          </div>
          <AddLibraryForm />
        </section>
      </div>
    </div>
  );
}
