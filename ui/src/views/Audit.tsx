import type { ComponentChildren } from 'preact';
import { isActive, type AuditImage, type AuditPackage, type AuditResult, type Group, type IncompletePackage, type ShellPackage, type Task } from '../api';
import { Thumb } from '../components/Thumb';
import { bytes, count } from '../lib/format';
import { Icon } from '../lib/icons';
import { reportError, requestDelete, submitTask, trackTask } from '../state/app';
import {
  completed, ListState, openImage, openPackage, PackageRef, Pager, TaskBlock, useFindings, usePackageNames, useTracked, type Names,
} from './organizeParts';

type Kind = 'shell' | 'advertisement' | 'incomplete';

export function Audit({ group }: { group: Group }) {
  const scope = `audit:${group.id}`;
  const { id, task, gone } = useTracked(scope);
  const names = usePackageNames(group.id);
  const result = completed<AuditResult>(task);
  const running = task ? isActive(task) : false;
  const start = async () => {
    try {
      const created = await submitTask({ kind: 'audit', group_id: group.id });
      trackTask(scope, created.id);
    } catch (error) { reportError(error, '无法开始清理检查：'); }
  };
  return (
    <section class="org-section">
      <p class="org-intro">
        根据常见的小尺寸广告图（在多个图包中反复出现的同一画面，或已知的广告文件名），以及图包名称里声明的张数和大小做启发式检查。结果只是线索，请打开图包确认后再处理。先做一次相似分析，可以让广告图的判断更可靠。
      </p>
      <div class="org-controls">
        <button class="btn primary" disabled={running} onClick={() => void start()}>
          <Icon name="ShieldAlert" size={16} />{result ? '重新检查' : '开始检查'}
        </button>
      </div>
      {!id && <div class="empty small"><Icon name="ShieldAlert" size={30} /><p>还没有检查过此文件夹</p></div>}
      {gone && <p class="note">之前的检查记录已不存在，请重新检查。</p>}
      {task && <TaskBlock task={task} label="清理检查" onRestart={() => void start()} />}
      {result && task && (
        <>
          {names.error && <ListState error={`图包名称读取失败：${names.error}`} retry={names.retry} loading={false} />}
          <Findings<ShellPackage> task={task} kind="shell" title="空壳包" preview={result.shells} total={result.shells_total}
            hint="图包里只有广告图（总共不超过 20 MB），没有正文内容。"
            render={(item) => <ShellRow key={item.package_id} item={item} group={group} names={names} />} />
          <Findings<AuditPackage> task={task} kind="advertisement" title="含广告图" preview={result.advertisements}
            total={result.advertisements_total} hint="图包里混有疑似广告图；可以只删除这些图片，保留其余内容。"
            render={(item) => <AdRow key={item.package_id} item={item} group={group} names={names} />} />
          <Findings<IncompletePackage> task={task} kind="incomplete" title="疑似不完整" preview={result.incomplete}
            total={result.incomplete_total} hint="名称里声明的张数或大小远多于实际内容，可能下载或解压不完整。"
            render={(item) => <IncompleteRow key={item.package_id} item={item} group={group} names={names} />} />
        </>
      )}
    </section>
  );
}

const PAGE = 50;

function Findings<T>({ task, kind, title, hint, preview, total, render }: {
  task: Task; kind: Kind; title: string; hint: string; preview: T[]; total: number; render: (item: T) => ComponentChildren;
}) {
  const findings = useFindings<T>(task.id, kind, preview, total, PAGE);
  return (
    <section class="org-block">
      <header class="org-block-head">
        <h2>{title}</h2>
        <span class={`count-badge ${total ? 'some' : ''}`}>{count(total)}</span>
        <span class="spacer" />
        <Pager page={findings.page} pages={findings.pages} onPage={findings.setPage} />
      </header>
      <p class="muted block-hint">{hint}</p>
      {!total && <p class="muted none"><Icon name="Check" size={14} />没有发现</p>}
      {total > 0 && <ListState error={findings.error} retry={findings.retry} loading={!findings.items && !findings.error} />}
      {total > 0 && findings.items && <ul class="finding-list">{findings.items.map(render)}</ul>}
    </section>
  );
}

const SHOWN = 24;

function AdThumbs({ images, group, packageId }: { images: AuditImage[]; group: Group; packageId: string }) {
  return (
    <div class="ad-thumbs">
      {images.slice(0, SHOWN).map((image) => (
        <button key={image.id} class="ad-thumb" onClick={() => void openImage(group, 'audit', image.id, packageId)}
          title={image.verified ? '画面与常见广告图一致' : '仅凭文件名判断（指纹尚未计算或已过期）'} aria-label="查看广告图">
          <Thumb id={image.id} edge={400} retryButton={false} />
          {!image.verified && <span class="badge warn">仅文件名</span>}
        </button>
      ))}
      {images.length > SHOWN && <span class="muted more">另有 {count(images.length - SHOWN)} 张</span>}
    </div>
  );
}

function ShellRow({ item, group, names }: { item: ShellPackage; group: Group; names: Names }) {
  const pkg = names.get(item.package_id);
  return (
    <li class="finding">
      <PackageRef id={item.package_id} names={names} group={group}>
        <span class="muted">{count(item.images.length)} 张疑似广告图 · {bytes(item.bytes)}</span>
        {!item.verified && <span class="warn-text">部分图片仅凭文件名判断</span>}
      </PackageRef>
      <AdThumbs images={item.images} group={group} packageId={item.package_id} />
      <div class="finding-actions">
        <button class="btn small" onClick={() => openPackage(group, item.package_id)}><Icon name="LayoutGrid" size={14} />查看</button>
        <button class="btn small danger" disabled={!pkg} onClick={() => pkg && requestDelete({
          targets: [{ kind: 'package', id: item.package_id }], title: `空壳图包“${pkg.name}”（${count(item.images.length)} 个文件）`,
          names: { [item.package_id]: pkg.rel }, includesFolders: true,
        })}>
          <Icon name="Trash2" size={14} />删除图包…
        </button>
      </div>
    </li>
  );
}

function AdRow({ item, group, names }: { item: AuditPackage; group: Group; names: Names }) {
  const pkg = names.get(item.package_id);
  const unverified = item.images.filter((image) => !image.verified).length;
  const where = pkg ? `“${pkg.loose ? '散图' : pkg.name}”中的` : '';
  return (
    <li class="finding">
      <PackageRef id={item.package_id} names={names} group={group}>
        <span class="muted">{count(item.images.length)} 张疑似广告图{unverified ? `，其中 ${count(unverified)} 张仅凭文件名判断` : ''}</span>
      </PackageRef>
      <AdThumbs images={item.images} group={group} packageId={item.package_id} />
      <div class="finding-actions">
        <button class="btn small" onClick={() => openPackage(group, item.package_id)}><Icon name="LayoutGrid" size={14} />查看</button>
        <button class="btn small danger" onClick={() => requestDelete({
          targets: item.images.map((image) => ({ kind: 'image' as const, id: image.id })),
          title: `${where}${count(item.images.length)} 张疑似广告图`,
        })}>
          <Icon name="Trash2" size={14} />删除这 {count(item.images.length)} 张…
        </button>
      </div>
    </li>
  );
}

function IncompleteRow({ item, group, names }: { item: IncompletePackage; group: Group; names: Names }) {
  const declared = [item.declared_images ? `${count(item.declared_images)} 张` : '', item.declared_bytes ? bytes(item.declared_bytes) : '']
    .filter(Boolean).join(' / ');
  return (
    <li class="finding">
      <PackageRef id={item.package_id} names={names} group={group}>
        <span class="muted">名称声明 {declared}，实际 {count(item.images)} 张 / {bytes(item.bytes)}</span>
      </PackageRef>
      <div class="finding-actions">
        <button class="btn small" onClick={() => openPackage(group, item.package_id)}><Icon name="LayoutGrid" size={14} />查看</button>
      </div>
    </li>
  );
}
