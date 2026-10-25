import { Icon } from '../lib/icons';
import { reconnectNow } from '../state/events';
import { connection, currentLibrary, dismissToast, manageLibrary, scanStatus, toasts } from '../state/app';
import { rescanLibrary } from './Sidebar';

export function Toasts() {
  return (
    <div class="toasts" role="status" aria-live="polite">
      {toasts.value.map((item) => (
        <div key={item.id} class={`toast ${item.tone}`}>
          <Icon name={item.tone === 'error' ? 'CircleAlert' : item.tone === 'success' ? 'Check' : 'Info'} size={16} />
          <span class="toast-text">{item.text}</span>
          {item.action && (
            <button class="btn small" onClick={() => { item.action!.run(); dismissToast(item.id); }}>{item.action.label}</button>
          )}
          <button class="icon-btn small" title="关闭" aria-label="关闭提示" onClick={() => dismissToast(item.id)}><Icon name="X" size={14} /></button>
        </div>
      ))}
    </div>
  );
}

/** Service connection and library availability, shown above the content without covering it. */
export function StatusBanner() {
  const state = connection.value;
  const lib = currentLibrary.value;
  if (state === 'offline') {
    return (
      <div class="banner bad" role="alert">
        <Icon name="WifiOff" size={16} />
        <span>与图库服务的连接已断开。已显示的内容仍可查看，新的图片和列表会在恢复后自动加载。</span>
        <button class="btn small" onClick={reconnectNow}>立即重连</button>
      </div>
    );
  }
  if (state === 'reconnecting') {
    return <div class="banner warn"><Icon name="LoaderCircle" size={16} spin /><span>正在重新连接图库服务…</span></div>;
  }
  if (lib && !lib.online) {
    return (
      <div class="banner warn" role="alert">
        <Icon name="TriangleAlert" size={16} />
        <span>图库目录“{lib.path}”当前无法访问（磁盘未连接或已移动）。已索引的列表仍可浏览，图片可能无法加载。</span>
        <button class="btn small" onClick={() => void rescanLibrary(lib)}>重新检查</button>
        <button class="btn small" onClick={() => manageLibrary(lib, 'reconnect')}>重新定位目录…</button>
      </div>
    );
  }
  if (lib?.error && scanStatus(lib) !== 'scanning') {
    return (
      <div class="banner warn">
        <Icon name="TriangleAlert" size={16} />
        <span title={lib.error}>上次扫描未完全成功：{lib.error}</span>
        <button class="btn small" onClick={() => void rescanLibrary(lib)}>重新扫描</button>
      </div>
    );
  }
  return null;
}
