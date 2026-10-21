import { stripCategory } from '../lib/format';
import { Icon } from '../lib/icons';
import { navigate, route } from '../lib/router';
import {
  activeTaskCount, connection, currentGroup, currentLibrary, currentPackage, narrow, sidebarOpen, taskDrawer, tileSize, type TileSize,
} from '../state/app';

const SIZES: { value: TileSize; label: string }[] = [{ value: 's', label: '小' }, { value: 'm', label: '中' }, { value: 'l', label: '大' }];

export function Topbar() {
  const r = route.value;
  const lib = currentLibrary.value;
  const group = currentGroup.value?.id === r.group ? currentGroup.value : null;
  const pkg = r.package && currentPackage.value?.id === r.package ? currentPackage.value : null;
  const wall = !r.group || r.view === 'packages' || r.view === 'samples';
  // On a phone the library is one tap away in the sidebar, so the crumbs keep their room for the folder and package.
  const showLibrary = !(narrow.value && r.group);
  const active = activeTaskCount.value;
  const state = connection.value;
  return (
    <header class="topbar">
      <button class="icon-btn" title={sidebarOpen.value ? '收起侧栏' : '展开侧栏'} aria-label="切换侧栏"
        aria-expanded={sidebarOpen.value} onClick={() => { sidebarOpen.value = !sidebarOpen.value; }}>
        <Icon name="Menu" />
      </button>
      <nav class="crumbs" aria-label="位置">
        {lib && showLibrary && (
          <button class="crumb" onClick={() => navigate({ library: lib.id })} aria-current={!r.group ? 'page' : undefined}>
            {lib.name}
          </button>
        )}
        {r.group && (
          <>
            {lib && showLibrary && <Icon name="ChevronRight" size={14} class="crumb-sep" />}
            <button class="crumb" onClick={() => navigate({ library: r.library, group: r.group })}
              aria-current={!r.package && r.view === 'packages' ? 'page' : undefined} title={group?.name}>
              {group ? stripCategory(group.name) || '（根目录）' : '…'}
            </button>
          </>
        )}
        {r.package && (
          <>
            <Icon name="ChevronRight" size={14} class="crumb-sep" />
            <span class="crumb current" title={pkg?.rel}>{pkg ? (pkg.loose ? '散图' : pkg.name) : '图包'}</span>
          </>
        )}
      </nav>
      <div class="spacer" />
      {wall && (
        <div class="segment tile-size" role="radiogroup" aria-label="缩略图大小">
          {SIZES.map((size) => (
            <button key={size.value} role="radio" aria-checked={tileSize.value === size.value}
              class={tileSize.value === size.value ? 'active' : ''} title={`${size.label}缩略图`}
              onClick={() => { tileSize.value = size.value; }}>{size.label}</button>
          ))}
        </div>
      )}
      {state !== 'online' && (
        <span class={`conn ${state}`} title={state === 'offline' ? '与图库服务断开' : '正在连接'}>
          <Icon name={state === 'offline' ? 'WifiOff' : 'LoaderCircle'} size={16} spin={state !== 'offline'} />
        </span>
      )}
      <button class={`icon-btn tasks-btn ${taskDrawer.value ? 'active' : ''}`} title="后台任务" aria-label="后台任务"
        aria-expanded={taskDrawer.value} onClick={() => { taskDrawer.value = !taskDrawer.value; }}>
        <Icon name="ListChecks" spin={false} />
        {active > 0 && <span class="count-badge">{active}</span>}
      </button>
    </header>
  );
}
