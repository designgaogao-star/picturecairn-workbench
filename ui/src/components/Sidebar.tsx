import type { Group, Library } from '../api';
import { bytes, count, stripCategory, time } from '../lib/format';
import { Icon } from '../lib/icons';
import { navigate, route } from '../lib/router';
import {
  currentLibrary, dialog, groupFilter, groupsList, libraries, narrow, reportError, scanStatus, sidebarOpen, submitTask, toast,
  type GroupFilter,
} from '../state/app';
import { MarkBadge } from './Marks';
import { VirtualGrid } from './VirtualGrid';
import { SidePanel } from './SidePanel';
import { LibraryMenu } from './LibraryDialog';
import { Brand } from './Brand';

export const CATEGORIES: GroupFilter['category'][] = ['', 'R16', 'R18', '非R18', '其他'];
export const SCAN_LABEL: Record<string, string> = {
  pending: '等待扫描', scanning: '正在扫描', ready: '索引完成', partial: '部分目录读取失败', offline: '目录离线', interrupted: '扫描中断', unscanned: '尚未扫描',
};

export function libraryStatus(lib: Library): { tone: 'ok' | 'busy' | 'warn' | 'bad'; text: string } {
  if (!lib.online) return { tone: 'bad', text: '目录离线' };
  const status = scanStatus(lib);
  if (status === 'scanning' || status === 'pending') return { tone: 'busy', text: SCAN_LABEL[status] };
  if (status === 'partial' || status === 'interrupted' || status === 'unscanned') return { tone: 'warn', text: SCAN_LABEL[status] };
  return { tone: 'ok', text: SCAN_LABEL[status] || status };
}

export async function rescanLibrary(lib: Library, directoryId?: string) {
  try {
    await submitTask({ kind: 'scan', library_id: lib.id, directory_id: directoryId ?? null, force: true });
    toast(directoryId ? '已开始重新扫描此文件夹' : `已开始重新扫描“${lib.name}”`, 'info');
  } catch (error) { reportError(error, '无法开始扫描：'); }
}

function closeOnNarrow() { if (narrow.value) sidebarOpen.value = false; }

export function FilterBar({ compact }: { compact?: boolean }) {
  const filter = groupFilter.value;
  const set = (patch: Partial<GroupFilter>) => { groupFilter.value = { ...filter, ...patch }; };
  return (
    <div class={`filters ${compact ? 'compact' : ''}`}>
      <select aria-label="文件夹状态" value={filter.state} onChange={(event) => set({ state: event.currentTarget.value as GroupFilter['state'] })}>
        <option value="">全部状态</option>
        <option value="none">未标记</option>
        <option value="kept">保留</option>
        <option value="marked">待整理</option>
      </select>
      <select aria-label="分类" value={filter.category} onChange={(event) => set({ category: event.currentTarget.value as GroupFilter['category'] })}>
        {CATEGORIES.map((category) => <option key={category} value={category}>{category || '全部分类'}</option>)}
      </select>
    </div>
  );
}

function GroupRow({ group, active }: { group: Group; active: boolean }) {
  return (
    <button class={`group-row ${active ? 'active' : ''}`} aria-current={active ? 'true' : undefined}
      onClick={() => { navigate({ library: group.library_id, group: group.id }); closeOnNarrow(); }}>
      <span class="group-row-name" title={group.name}>{stripCategory(group.name) || '（根目录）'}</span>
      <span class="group-row-meta">
        {group.category && group.category !== '其他' && <span class="badge category">{group.category}</span>}
        <MarkBadge state={group.state} />
        <span class="muted">{count(group.image_count)} 张 · {bytes(group.bytes)}</span>
      </span>
    </button>
  );
}

function GroupList({ lib }: { lib: Library }) {
  const filter = groupFilter.value;
  const list = groupsList(lib.id, filter);
  const active = route.value.group;
  const index = active ? list.indexOf((group) => group.id === active) : -1;
  return (
    <VirtualGrid list={list} tile={100000} height={() => 50} gap={2} pad={6} class="group-list" label="文件夹"
      anchorKey={`side:${list.key}`} reveal={index >= 0 ? index : null} keyOf={(group) => group.id}
      empty={<p class="muted pad">{filter.state || filter.category ? '没有符合筛选的文件夹' : ['scanning', 'pending'].includes(scanStatus(lib)) ? '正在扫描，文件夹会陆续出现…' : '没有文件夹'}</p>}
      render={(group) => (group ? <GroupRow group={group} active={group.id === active} /> : <div class="group-row skeleton" />)} />
  );
}

export function Sidebar() {
  const lib = currentLibrary.value;
  const all = libraries.value;
  const open = sidebarOpen.value;
  if (!open) return null;
  return (
      <SidePanel class="sidebar open" label="图库与文件夹" desktopEscape={false} closeOnNarrow onClose={() => { sidebarOpen.value = false; }}>
        <div class="side-head">
          <Brand />
          {narrow.value && <button class="icon-btn" title="关闭侧栏" aria-label="关闭侧栏" onClick={() => { sidebarOpen.value = false; }}><Icon name="X" /></button>}
          <button class="icon-btn" title="添加图库" aria-label="添加图库" onClick={() => { dialog.value = { kind: 'add-library' }; }}>
            <Icon name="FolderPlus" />
          </button>
        </div>
        <nav class="library-list" aria-label="图库">
          {all.map((item) => {
            const status = libraryStatus(item);
            return (
              <button key={item.id} class={`library-row ${item.id === lib?.id ? 'active' : ''}`} title={`${item.path}\n${status.text}`}
                aria-current={item.id === lib?.id ? 'true' : undefined}
                onClick={() => { navigate({ library: item.id }); closeOnNarrow(); }}>
                <span class={`dot ${status.tone}`} />
                <span class="library-row-name">{item.name}</span>
                {status.tone !== 'ok' && <span class="library-row-status">{status.text}</span>}
              </button>
            );
          })}
        </nav>
        {lib && (
          <>
            <div class="side-section">
              <span>文件夹</span>
              <div class="side-actions">
                <button class="icon-btn small" title="重新扫描图库" aria-label="重新扫描图库" onClick={() => void rescanLibrary(lib)}>
                  <Icon name="RefreshCw" size={16} spin={scanStatus(lib) === 'scanning'} />
                </button>
                <LibraryMenu library={lib} />
              </div>
            </div>
            <FilterBar compact />
            <GroupList lib={lib} />
            <footer class="side-foot" title={lib.path}>
              <span class={`dot ${libraryStatus(lib).tone}`} />
              <span>{libraryStatus(lib).text}</span>
              {lib.last_scan && <span class="muted">· {time(lib.last_scan)}</span>}
            </footer>
          </>
        )}
      </SidePanel>
  );
}
