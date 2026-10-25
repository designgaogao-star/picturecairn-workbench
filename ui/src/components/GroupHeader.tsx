import type { ComponentChildren } from 'preact';
import { useEffect, useState } from 'preact/hooks';
import { client, isAbort, statusOf, type Group, type ImageContext, type Library } from '../api';
import { count, stripCategory } from '../lib/format';
import { Icon } from '../lib/icons';
import { lastOrganizeTab, navigate, route } from '../lib/router';
import {
  cachedPackage, currentGroup, currentReview, imageFit, reportError, requestDelete, submitTask, tileSize, toast, type TileSize,
} from '../state/app';
import { wallEdge } from '../views/ImageWall';
import { applyMark, MARKS } from './Marks';
import { Menu } from './Menu';
import { rescanLibrary } from './Sidebar';

export interface Resume { imageId: string; packageId: string; index: number; name: string }

/** Where the user left this group: the saved image ID resolved through its context. */
export function useResume(groupId: string | undefined): Resume | null {
  const imageId = currentReview.value?.group_id === groupId ? currentReview.value?.image_id ?? null : null;
  const [resume, setResume] = useState<Resume | null>(null);
  useEffect(() => {
    setResume(null);
    if (!imageId) return;
    const controller = new AbortController();
    client.request('get', '/api/v1/images/{image_id}/context', { params: { path: { image_id: imageId } }, signal: controller.signal })
      .then((context: ImageContext) => setResume({
        imageId, packageId: context.image.package_id, index: context.index, name: context.image.name,
      }))
      .catch((error) => { if (!isAbort(error) && statusOf(error) !== 404) console.warn('resume', error); });
    return () => controller.abort();
  }, [imageId]);
  return resume;
}

export async function prewarm(group: Group) {
  try {
    await submitTask({ kind: 'prewarm', group_id: group.id, edge: wallEdge() });
    toast('已开始为此文件夹的全部图片生成缩略图', 'info');
  } catch (error) { reportError(error, '无法开始生成缩略图：'); }
}

export function ModeTabs() {
  const r = route.value;
  return <nav class="tabs" aria-label="模式">
    <button class={r.view === 'packages' ? 'active' : ''} aria-current={r.view === 'packages' ? 'page' : undefined}
      onClick={() => { if (r.view !== 'packages') navigate({ library: r.library, group: r.group }); }}>
      <Icon name="LayoutGrid" size={16} /><span>浏览</span></button>
    <button class={r.view === 'organize' ? 'active' : ''} aria-current={r.view === 'organize' ? 'page' : undefined}
      onClick={() => { if (r.view !== 'organize') navigate({ library: r.library, group: r.group, view: 'organize', tab: lastOrganizeTab() }); }}>
      <Icon name="ScanSearch" size={16} /><span>整理</span></button>
  </nav>;
}

export function ResumeButton({ resume }: { resume?: Resume | null }) {
  const r = route.value;
  if (!resume) return null;
  const pkg = cachedPackage(resume.packageId);
  return <button class="btn subtle small" title={`上次看到：${pkg ? (pkg.loose ? '散图' : pkg.name) + ' · ' : ''}${resume.name}`}
    onClick={() => navigate({ library: r.library, group: r.group, package: resume.packageId, image: resume.imageId })}>
    <Icon name="History" size={14} /><span class="label-wide">继续浏览</span><span class="muted resume-pos">第 {resume.index + 1} 张</span>
  </button>;
}

const SIZES: { value: TileSize; label: string }[] = [{ value: 's', label: '小' }, { value: 'm', label: '中' }, { value: 'l', label: '大' }];

export function SizeSegment({ class: className = '' }: { class?: string }) {
  return <div class={`segment tile-size ${className}`} role="radiogroup" aria-label="缩略图大小">
    {SIZES.map((size) => <button key={size.value} role="radio" aria-checked={tileSize.value === size.value}
      class={tileSize.value === size.value ? 'active' : ''} title={`${size.label}缩略图`}
      onClick={() => { tileSize.value = size.value; }}>{size.label}</button>)}
  </div>;
}

export function NarrowMarks({ group }: { group: Group }) {
  return <div class="at-narrow" role="group" aria-label="文件夹状态">
    <div class="menu-label" aria-hidden="true">文件夹状态</div>
    {MARKS.map((mark) => <button key={mark.value} role="menuitemradio" aria-checked={group.state === mark.value}
      onClick={() => applyMark(group.id, mark.value)}><Icon name={mark.icon} size={16} /><span>{mark.label}</span>
      {group.state === mark.value && <Icon name="Check" size={14} class="menu-check" />}</button>)}
    <div class="menu-sep" role="separator" />
  </div>;
}

export function NarrowSizes() {
  return <div class="at-narrow" role="group" aria-label="缩略图大小">
    <div class="menu-label" aria-hidden="true">缩略图大小</div>
    {SIZES.map((size) => <button key={size.value} role="menuitemradio" aria-checked={tileSize.value === size.value}
      onClick={() => { tileSize.value = size.value; }}><span>{size.label}缩略图</span>
      {tileSize.value === size.value && <Icon name="Check" size={14} class="menu-check" />}</button>)}
    <div class="menu-sep" role="separator" />
  </div>;
}

export function ImageFitOptions() {
  return <div role="group" aria-label="图片显示方式"><div class="menu-label" aria-hidden="true">图片显示方式</div>
    {(['contain', 'cover'] as const).map((value) => <button key={value} role="menuitemradio" aria-checked={imageFit.value === value}
      onClick={() => { imageFit.value = value; }}><Icon name={value === 'contain' ? 'Maximize' : 'Scan'} size={16} />
      <span>{value === 'contain' ? '完整显示' : '填充裁切'}</span>{imageFit.value === value && <Icon name="Check" size={14} class="menu-check" />}</button>)}
    <div class="menu-sep" role="separator" /></div>;
}

export function GroupMenu({ group, lib, children }: { group: Group; lib: Library; children?: ComponentChildren }) {
  return <Menu label="更多操作">
    {children}
    <button role="menuitem" onClick={() => void rescanLibrary(lib, group.id)}><Icon name="RefreshCw" size={16} />重新扫描此文件夹</button>
    <button role="menuitem" onClick={() => void prewarm(group)}><Icon name="Sparkles" size={16} />预先生成缩略图</button>
    {group.rel && <><div class="menu-sep" role="separator" /><button role="menuitem" class="danger" onClick={() => requestDelete({
      targets: [{ kind: 'group', id: group.id }], title: `整个文件夹“${stripCategory(group.name)}”（${count(group.image_count)} 张）`,
      names: { [group.id]: group.rel }, includesFolders: true,
      onDone: (done) => { if (done.has(group.id)) navigate({ library: group.library_id }, { replace: true }); },
    })}><Icon name="Trash2" size={16} />删除整个文件夹…</button></>}
  </Menu>;
}

export const groupOf = (id: string | undefined) => (currentGroup.value && currentGroup.value.id === id ? currentGroup.value : null);
