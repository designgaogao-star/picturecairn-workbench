import { stripCategory } from '../lib/format';
import { Icon } from '../lib/icons';
import { navigate, route } from '../lib/router';
import {
  activeTaskCount, connection, currentGroup, currentLibrary, currentPackage, narrow, sidebarOpen, taskDrawer, theme,
} from '../state/app';
import { Menu } from './Menu';
import { inspectorOpen } from '../state/inspection';

export function Topbar() {
  const r = route.value;
  const lib = currentLibrary.value;
  const group = currentGroup.value?.id === r.group ? currentGroup.value : null;
  const pkg = r.package && currentPackage.value?.id === r.package ? currentPackage.value : null;
  const showPackage = Boolean(r.package && r.view === 'packages');
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
          r.group ? <button class="crumb" title={lib.name} onClick={() => navigate({ library: lib.id })}>{lib.name}</button>
            : <span class="crumb" aria-current="page" title={lib.name}>{lib.name}</span>
        )}
        {r.group && (
          <>
            {lib && showLibrary && <Icon name="ChevronRight" size={14} class="crumb-sep" />}
            {showPackage ? <button class="crumb" onClick={() => navigate({ library: r.library, group: r.group })} title={group?.name}>
              {group ? stripCategory(group.name) || '（根目录）' : '…'}</button>
              : <span class="crumb" aria-current="page" title={group?.name}>{group ? stripCategory(group.name) || '（根目录）' : '…'}</span>}
          </>
        )}
        {showPackage && (
          <>
            <Icon name="ChevronRight" size={14} class="crumb-sep" />
            <span class="crumb" aria-current="page" title={pkg?.rel || pkg?.name}>{pkg ? (pkg.loose ? '散图' : pkg.name) : '图包'}</span>
          </>
        )}
      </nav>
      {group?.category && group.category !== '其他' && <span class="badge category">{group.category}</span>}
      <div class="spacer" />
      {state !== 'online' && (
        <span class={`conn ${state}`} title={state === 'offline' ? '与图库服务断开' : '正在连接'}>
          <Icon name={state === 'offline' ? 'WifiOff' : 'LoaderCircle'} size={16} spin={state !== 'offline'} />
        </span>
      )}
      {r.group && <button class="icon-btn" aria-label="信息" title="信息" aria-pressed={inspectorOpen.value}
        onClick={() => { taskDrawer.value = false; inspectorOpen.value = !inspectorOpen.value; }}><Icon name="PanelRight" /></button>}
      <Menu label="外观" icon={theme.value === 'system' ? 'Monitor' : theme.value === 'light' ? 'Sun' : 'Moon'}>
        <div class="menu-label" aria-hidden="true">外观</div>
        {(['system', 'light', 'dark'] as const).map((value) => <button key={value} role="menuitemradio" aria-checked={theme.value === value}
          onClick={() => { theme.value = value; }}><Icon name={value === 'system' ? 'Monitor' : value === 'light' ? 'Sun' : 'Moon'} size={16} />
          <span>{value === 'system' ? '跟随系统' : value === 'light' ? '浅色' : '深色'}</span>
          {theme.value === value && <Icon name="Check" size={14} class="menu-check" />}</button>)}
      </Menu>
      <button class="btn subtle tasks-btn" title="后台任务" aria-label="后台任务"
        aria-expanded={taskDrawer.value} onClick={() => { taskDrawer.value = !taskDrawer.value; }}>
        <Icon name="ListChecks" size={16} /><span class="tasks-label">任务</span>
        {active > 0 && <span class="count-badge">{active}</span>}
      </button>
    </header>
  );
}
