import { useState } from 'preact/hooks';
import { describeError } from '../api';
import { Icon } from '../lib/icons';
import { addLibrary, dialog } from '../state/app';
import { Dialog } from './Dialog';

interface DesktopBridge { isElectron?: boolean; chooseDirectory?: () => Promise<string | null | undefined> }
const desktop = (window as unknown as { galleryApp?: DesktopBridge }).galleryApp;

export function AddLibraryForm({ onDone }: { onDone?: () => void }) {
  const [path, setPath] = useState('');
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const choose = async () => {
    const chosen = await desktop?.chooseDirectory?.();
    if (chosen) { setPath(chosen); setError(''); }
  };
  const submit = async (event: Event) => {
    event.preventDefault();
    if (!path.trim() || busy) return;
    setBusy(true); setError('');
    try {
      await addLibrary(path.trim(), name.trim() || null);
      onDone?.();
    } catch (failure) {
      setError(describeError(failure));
    } finally { setBusy(false); }
  };

  return (
    <form class="form" onSubmit={submit}>
      <label class="field">
        <span>图库文件夹</span>
        <div class="field-row">
          <input value={path} onInput={(event) => setPath(event.currentTarget.value)} required autoFocus
            placeholder="例如 D:\图片\收藏" spellcheck={false} />
          {desktop?.chooseDirectory && (
            <button type="button" class="btn" onClick={choose}><Icon name="FolderOpen" />选择…</button>
          )}
        </div>
      </label>
      <label class="field">
        <span>名称（可选）</span>
        <input value={name} onInput={(event) => setName(event.currentTarget.value)} placeholder="默认使用文件夹名" />
      </label>
      <p class="hint">只读取该文件夹中的图片；索引在后台建立，期间可以直接浏览已扫描的部分。</p>
      {error && <p class="form-error" role="alert"><Icon name="CircleAlert" size={16} />{error}</p>}
      <div class="form-actions">
        <button class="btn primary" type="submit" disabled={busy || !path.trim()}>
          {busy ? <Icon name="LoaderCircle" spin /> : <Icon name="FolderPlus" />}添加图库
        </button>
      </div>
    </form>
  );
}

export function AddLibraryDialog() {
  const close = () => { dialog.value = null; };
  return <Dialog title="添加图库" onClose={close}><AddLibraryForm onDone={close} /></Dialog>;
}
