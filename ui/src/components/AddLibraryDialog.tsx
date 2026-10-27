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
  const [choosing, setChoosing] = useState(false);
  const [error, setError] = useState('');

  const choose = async () => {
    if (busy || choosing) return;
    setChoosing(true); setError('');
    try {
      const chosen = await desktop?.chooseDirectory?.();
      if (chosen) setPath(chosen);
    } catch (failure) {
      setError(`无法选择文件夹：${describeError(failure)}`);
    } finally { setChoosing(false); }
  };
  const submit = async (event: Event) => {
    event.preventDefault();
    if (!path.trim() || busy || choosing) return;
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
            <button type="button" class="btn" onClick={choose} disabled={busy || choosing}>
              <Icon name={choosing ? 'LoaderCircle' : 'FolderOpen'} spin={choosing} />选择文件夹…
            </button>
          )}
        </div>
      </label>
      <label class="field">
        <span>名称（可选）</span>
        <input value={name} onInput={(event) => setName(event.currentTarget.value)} placeholder="默认使用文件夹名" />
      </label>
      <p class="hint"><Icon name="Info" size={15} />只读取这个文件夹中的图片；不会复制或移动原图。索引在后台建立，期间可以直接浏览已扫描的部分。</p>
      {error && <p class="form-error" role="alert"><Icon name="CircleAlert" size={16} />{error}</p>}
      <div class="form-actions">
        <button class="btn primary" type="submit" disabled={busy || choosing || !path.trim()}>
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
