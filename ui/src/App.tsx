import { useEffect, useRef } from 'preact/hooks';
import { AddLibraryDialog } from './components/AddLibraryDialog';
import { DeleteDialog, DeleteReportDialog } from './components/DeleteDialog';
import { GroupHeader, groupOf, useResume } from './components/GroupHeader';
import { Sidebar } from './components/Sidebar';
import { TasksDrawer } from './components/TasksDrawer';
import { StatusBanner, Toasts } from './components/Toasts';
import { Topbar } from './components/Topbar';
import { Icon } from './lib/icons';
import { route, type Route } from './lib/router';
import {
  connection, currentLibrary, dialog, groupError, libraries, librariesError, librariesLoaded, loadLibraries, narrow,
  refreshCurrentGroup, refreshCurrentPackage, sidebarOpen,
} from './state/app';
import { ImageWall } from './views/ImageWall';
import { LibraryHome, Welcome } from './views/LibraryHome';
import { Organize } from './views/Organize';
import { PackageWall } from './views/PackageWall';
import { Samples } from './views/Samples';
import { Viewer } from './views/Viewer';

function Splash() {
  return (
    <div class="splash" role="status">
      <Icon name="LoaderCircle" size={28} spin />
      <p class="muted">正在连接图库服务…</p>
    </div>
  );
}

function Unreachable({ error }: { error: string }) {
  // The event stream can be up while the list itself fails, e.g. on a database error.
  const online = connection.value === 'online';
  const title = online ? '无法读取图库列表' : '无法连接图库服务';
  return (
    <div class="splash">
      <div class="welcome-box" role="alert">
        <Icon name={online ? 'CircleAlert' : 'WifiOff'} size={36} />
        <h1>{title}</h1>
        {error !== title && <p class="muted">{error}</p>}
        <p class="muted">{online ? '图库服务已连接，但读取图库列表失败，请稍后重试。' : '请确认 GalleryTool 正在运行。服务恢复后会自动重新连接。'}</p>
        <button class="btn primary" onClick={() => void loadLibraries()}><Icon name="RefreshCw" size={16} />重试</button>
      </div>
    </div>
  );
}

function GroupSkeleton({ groupId }: { groupId: string }) {
  const error = groupError.value?.id === groupId ? groupError.value.text : null;
  return (
    <div class="wall">
      <div class="wall-hold">
        {error ? (
          <div class="hold-error" role="alert">
            <Icon name="CircleAlert" size={24} />
            <strong>无法读取文件夹信息</strong>
            <span class="muted">{error}</span>
            <button class="btn" onClick={() => void refreshCurrentGroup()}><Icon name="RotateCw" size={16} />重试</button>
          </div>
        ) : <Icon name="LoaderCircle" size={22} spin />}
      </div>
    </div>
  );
}

/** The page under the viewer; organize and samples keep their own page while an image is open. */
function GroupBody({ base }: { base: Route }) {
  const groupId = base.group!;
  const group = groupOf(groupId);
  const resume = useResume(groupId);
  if (base.view === 'organize') return group ? <Organize group={group} /> : <GroupSkeleton groupId={groupId} />;
  if (base.package) return <ImageWall groupId={groupId} group={group} packageId={base.package} resume={resume} />;
  if (base.view === 'samples') return <Samples groupId={groupId} group={group} />;
  return group ? <PackageWall group={group} resume={resume} /> : <GroupSkeleton groupId={groupId} />;
}

function Content({ base }: { base: Route | null }) {
  const lib = currentLibrary.value;
  // A viewer opened straight from a link has no page under it yet; it is built when the viewer closes,
  // so its thumbnails never compete with the image being viewed.
  if (!base) return <div class="wall-hold" />;
  if (!lib) return <div class="wall-hold"><Icon name="LoaderCircle" size={22} spin /></div>;
  if (!base.group) return <LibraryHome lib={lib} />;
  return (
    <>
      <GroupHeader group={groupOf(base.group)} />
      <GroupBody base={base} />
    </>
  );
}

// Each delete request gets a fresh dialog, even if a new one replaces another without closing in between.
const requestKeys = new WeakMap<object, number>();
let requestCount = 0;
function requestKey(request: object) {
  let key = requestKeys.get(request);
  if (key === undefined) requestKeys.set(request, key = ++requestCount);
  return key;
}

function Dialogs() {
  const current = dialog.value;
  if (!current) return null;
  if (current.kind === 'add-library') return <AddLibraryDialog />;
  if (current.kind === 'delete') return <DeleteDialog key={requestKey(current)} request={current} />;
  return <DeleteReportDialog key={current.taskId} taskId={current.taskId} />;
}

export function App() {
  const r = route.value;
  const viewing = Boolean(r.image);

  useEffect(() => { void refreshCurrentGroup(); }, [r.library, r.group]);
  useEffect(() => { void refreshCurrentPackage(); }, [r.group, r.package]);
  // The narrow layout opens the sidebar as an overlay, so it starts closed there.
  useEffect(() => {
    sidebarOpen.value = narrow.value ? false : localStorage.getItem('gt.sidebar') !== '0';
  }, [narrow.value]);

  // While the viewer is open, the page it was opened from stays mounted underneath (scroll position,
  // loaded thumbnails) as long as it belongs to the same folder.
  const held = useRef<Route | null>(null);
  if (!viewing) held.current = r;
  const base = !viewing ? r : held.current && held.current.library === r.library && held.current.group === r.group ? held.current : null;

  if (!librariesLoaded.value && !librariesError.value) return <><Splash /><Toasts /></>;
  if (librariesError.value && !libraries.value.length) return <><Unreachable error={librariesError.value} /><Toasts /></>;
  if (!libraries.value.length) return <><Welcome /><Dialogs /><Toasts /></>;

  return (
    <div class={`app ${sidebarOpen.value ? 'sidebar-open' : 'sidebar-closed'} ${narrow.value ? 'narrow' : ''}`}>
      <div class="shell" inert={viewing}>
        <Sidebar />
        <main class="main">
          <Topbar />
          <StatusBanner />
          <div class="content">
            <Content base={base} />
          </div>
        </main>
      </div>
      {viewing && <Viewer key="viewer" />}
      <TasksDrawer />
      <Dialogs />
      <Toasts />
    </div>
  );
}
