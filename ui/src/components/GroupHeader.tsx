import { useEffect, useState } from 'preact/hooks';
import { client, isAbort, statusOf, type Group, type ImageContext } from '../api';
import { bytes, count, stripCategory } from '../lib/format';
import { Icon } from '../lib/icons';
import { navigate, route, type GroupView } from '../lib/router';
import {
  cachedPackage, currentGroup, currentLibrary, currentReview, reportError, requestDelete, submitTask, toast,
} from '../state/app';
import { wallEdge } from '../views/ImageWall';
import { MarkSegment } from './Marks';
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

const VIEWS: { value: GroupView; label: string; icon: 'LayoutGrid' | 'Dices' | 'ScanSearch' }[] = [
  { value: 'packages', label: '图包', icon: 'LayoutGrid' },
  { value: 'samples', label: '抽样', icon: 'Dices' },
  { value: 'organize', label: '整理', icon: 'ScanSearch' },
];

async function prewarm(group: Group) {
  try {
    await submitTask({ kind: 'prewarm', group_id: group.id, edge: wallEdge() });
    toast('已开始为此文件夹的全部图片生成缩略图', 'info');
  } catch (error) { reportError(error, '无法开始生成缩略图：'); }
}

export function GroupHeader({ group }: { group: Group | null }) {
  const r = route.value;
  const lib = currentLibrary.value;
  const resume = useResume(group?.id);
  const [menu, setMenu] = useState(false);
  const resumePackage = resume ? cachedPackage(resume.packageId) : undefined;
  return (
    <section class="group-head">
      <div class="group-title">
        <h1 title={group?.rel || group?.name}>
          {group ? stripCategory(group.name) || '（根目录散图）' : <span class="skeleton-text" />}
        </h1>
        {group?.category && group.category !== '其他' && <span class="badge category">{group.category}</span>}
        {group && <span class="muted stats">{count(group.image_count)} 张 · {bytes(group.bytes)}</span>}
      </div>
      <div class="group-tools">
        <div class="segment views" role="tablist" aria-label="视图">
          {VIEWS.map((view) => (
            <button key={view.value} role="tab" aria-selected={r.view === view.value && !r.package}
              class={r.view === view.value && !r.package ? 'active' : ''}
              onClick={() => navigate({ library: r.library, group: r.group, view: view.value, tab: view.value === 'organize' ? r.tab : undefined })}>
              <Icon name={view.icon} size={16} /><span>{view.label}</span>
            </button>
          ))}
        </div>
        {group && <MarkSegment groupId={group.id} value={group.state as 'none' | 'kept' | 'marked'} />}
        {resume && (
          <button class="btn resume" title={`上次看到：${resumePackage ? (resumePackage.loose ? '散图' : resumePackage.name) + ' · ' : ''}${resume.name}`}
            onClick={() => navigate({ library: r.library, group: r.group, package: resume.packageId, image: resume.imageId })}>
            <Icon name="History" size={16} /><span>继续浏览</span>
            <span class="muted">第 {resume.index + 1} 张</span>
          </button>
        )}
        {group && lib && (
          <div class="menu-wrap">
            <button class="icon-btn" title="更多操作" aria-label="更多操作" aria-expanded={menu} onClick={() => setMenu(!menu)}>
              <Icon name="ChevronDown" />
            </button>
            {menu && (
              <>
                <div class="menu-scrim" onClick={() => setMenu(false)} />
                <div class="menu" role="menu">
                  <button role="menuitem" onClick={() => { setMenu(false); void rescanLibrary(lib, group.id); }}>
                    <Icon name="RefreshCw" size={16} />重新扫描此文件夹
                  </button>
                  <button role="menuitem" onClick={() => { setMenu(false); void prewarm(group); }}>
                    <Icon name="Sparkles" size={16} />预先生成缩略图
                  </button>
                  {group.rel && (
                    <button role="menuitem" class="danger" onClick={() => {
                      setMenu(false);
                      requestDelete({
                        targets: [{ kind: 'group', id: group.id }], title: `整个文件夹“${stripCategory(group.name)}”（${count(group.image_count)} 张）`,
                        names: { [group.id]: group.rel }, includesFolders: true,
                        onDone: (done) => { if (done.has(group.id)) navigate({ library: group.library_id }, { replace: true }); },
                      });
                    }}>
                      <Icon name="Trash2" size={16} />删除整个文件夹…
                    </button>
                  )}
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

export const groupOf = (id: string | undefined) => (currentGroup.value && currentGroup.value.id === id ? currentGroup.value : null);
