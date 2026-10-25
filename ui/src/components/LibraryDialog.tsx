import { useState } from 'preact/hooks';
import { describeError, GalleryError, type Library } from '../api';
import { Icon } from '../lib/icons';
import {
  dialog, manageLibrary, reconnectLibrary, removeLibrary, renameLibrary, taskDrawer, toast,
  type LibraryRequestState,
} from '../state/app';
import { Dialog } from './Dialog';
import { Menu } from './Menu';

const TITLES = { rename: '修改图库名称', reconnect: '重新连接图库目录', remove: '移出图库管理' };
const desktop = (window as unknown as {
  galleryApp?: { chooseDirectory?: () => Promise<string | null | undefined> };
}).galleryApp;

export function LibraryMenu({ library, class: className }: { library: Library; class?: string }) {
  return (
    <Menu label="管理图库" class={className}>
      <span class="menu-label">管理当前图库</span>
      <button role="menuitem" onClick={() => manageLibrary(library, 'rename')}>修改名称…</button>
      <button role="menuitem" onClick={() => manageLibrary(library, 'reconnect')}>重新连接目录…</button>
      <div class="menu-sep" role="separator" />
      <button role="menuitem" onClick={() => manageLibrary(library, 'remove')}>移出管理…</button>
    </Menu>
  );
}

export function LibraryDialog({ request }: { request: LibraryRequestState }) {
  const { library, action } = request;
  const [value, setValue] = useState(request.draft ?? (action === 'rename' ? library.name : library.path));
  const [busy, setBusy] = useState(false);
  const [choosing, setChoosing] = useState(false);
  const [error, setError] = useState('');
  const [blockedByTask, setBlockedByTask] = useState(false);
  const close = () => { dialog.value = null; };

  const choose = async () => {
    if (busy || choosing) return;
    setChoosing(true); setError(''); setBlockedByTask(false);
    try {
      const chosen = await desktop?.chooseDirectory?.();
      if (chosen) setValue(chosen);
    } catch (failure) { setError(`无法选择文件夹：${describeError(failure)}`); }
    finally { setChoosing(false); }
  };
  const submit = async (event: Event) => {
    event.preventDefault();
    if (busy || choosing || (action !== 'remove' && !value.trim())) return;
    setBusy(true); setError(''); setBlockedByTask(false);
    try {
      if (action === 'rename') await renameLibrary(library.id, value.trim());
      else if (action === 'reconnect') await reconnectLibrary(library.id, value.trim());
      else await removeLibrary(library.id);
      close();
    } catch (failure) {
      const detail = failure instanceof GalleryError ? failure.detail as { error?: { code?: string } } : null;
      setBlockedByTask(detail?.error?.code === 'library_busy');
      setError(describeError(failure));
    } finally { setBusy(false); }
  };

  return (
    <Dialog title={TITLES[action]} onClose={close} locked={busy || choosing}>
      <form class="form" onSubmit={submit}>
        <p class="library-manage-name">{library.name}</p>
        {action === 'rename' && <>
          <label class="field"><span>图库显示名称</span>
            <input value={value} maxLength={120} required autoFocus disabled={busy}
              onInput={(event) => setValue(event.currentTarget.value)} />
          </label>
          <p class="hint">只修改工作台中的显示名称，磁盘上的文件夹名称不变。</p>
        </>}
        {action === 'reconnect' && <>
          <label class="field"><span>图库文件夹的新位置</span>
            <div class="field-row">
              <input value={value} required autoFocus disabled={busy || choosing} spellcheck={false}
                onInput={(event) => setValue(event.currentTarget.value)} />
              {desktop?.chooseDirectory && <button type="button" class="btn" onClick={choose} disabled={busy || choosing}>
                <Icon name={choosing ? 'LoaderCircle' : 'FolderOpen'} spin={choosing} />选择文件夹…
              </button>}
            </div>
          </label>
          <p class="hint">选择原图库搬迁后的根目录。后台会重新核对文件，相对路径相同的图片保留原有浏览位置和标记。</p>
          <p class="hint">此操作不会移动磁盘文件。请确认选择的是同一个图库的新位置。</p>
        </>}
        {action === 'remove' && <>
          <p>将此图库从工作台中移出？</p>
          <p class="hint">磁盘图片、索引、缩略图、浏览位置、标记和操作日志都会保留。以后重新添加原目录，可恢复这份图库记录。</p>
          <p class="hint library-manage-path">{library.path}</p>
        </>}
        {error && <div class="library-manage-error">
          <p class="form-error" role="alert"><Icon name="CircleAlert" size={16} />{error}</p>
          {blockedByTask && <button type="button" class="btn small" onClick={() => {
            close(); taskDrawer.value = true;
            toast('处理完后台任务后，可继续刚才的图库操作', 'info', {
              label: '返回图库操作', run: () => { taskDrawer.value = false; dialog.value = { ...request, draft: value }; },
            }, 0);
          }}>查看后台任务</button>}
        </div>}
        <div class="form-actions">
          <button type="button" class="btn" onClick={close} disabled={busy || choosing}>取消</button>
          <button type="submit" class="btn primary" disabled={busy || choosing || (action !== 'remove' && !value.trim())}>
            {busy && <Icon name="LoaderCircle" spin />}
            {action === 'rename' ? '保存名称' : action === 'reconnect' ? '确认并连接' : '移出管理'}
          </button>
        </div>
      </form>
    </Dialog>
  );
}
