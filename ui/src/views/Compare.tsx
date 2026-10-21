import { useEffect, useId, useMemo, useState } from 'preact/hooks';
import { isActive, type CompareResult, type ComparedFile, type Group, type Task } from '../api';
import { Thumb } from '../components/Thumb';
import { bytes, count } from '../lib/format';
import { Icon, type IconName } from '../lib/icons';
import { currentLibrary, reportError, requestDelete, submitTask, trackTask } from '../state/app';
import {
  completed, ListState, openImage, PackageRef, Pager, pickerLabel, TaskBlock, useFindings, usePackageNames, useTracked, type Names,
} from './organizeParts';

const idOf = (value: unknown) => (typeof value === 'string' ? value : null);

export function Compare({ group }: { group: Group }) {
  const scope = `compare:${group.id}`;
  const { id, task, gone } = useTracked(scope);
  const names = usePackageNames(group.id);
  const [left, setLeft] = useState<string | null>(null);
  const [right, setRight] = useState<string | null>(null);
  const listId = useId();
  // The pickers start from the comparison on screen, e.g. one started from the similar-packages list.
  useEffect(() => {
    const l = idOf(task?.payload.left_id), r = idOf(task?.payload.right_id);
    if (l && r) { setLeft(l); setRight(r); }
  }, [task?.id]);
  const byLabel = useMemo(() => new Map(names.all.map((pkg) => [pickerLabel(pkg, group), pkg.id])), [names.all, group]);
  const result = completed<CompareResult>(task);
  const running = task ? isActive(task) : false;
  const valid = Boolean(left && right && left !== right);
  const start = async (l: string | null, r: string | null) => {
    if (!l || !r || l === r) return;
    try {
      const created = await submitTask({ kind: 'compare', left_id: l, right_id: r });
      trackTask(scope, created.id);
    } catch (error) { reportError(error, '无法开始整包核验：'); }
  };
  const restart = () => void start(idOf(task?.payload.left_id), idOf(task?.payload.right_id));
  return (
    <section class="org-section">
      <p class="org-intro">
        选择同一文件夹中的两个图包，用 SHA-256 逐字节比较两侧的<b>全部文件</b>（包括非图片文件）。只有一侧被另一侧完整包含时，删除这一侧才不会丢失内容。
      </p>
      <div class="compare-pick">
        <PackagePicker label="左侧图包" value={left} onChange={setLeft} names={names} group={group} listId={listId} byLabel={byLabel} />
        <button class="icon-btn swap" title="交换左右" aria-label="交换左右" onClick={() => { setLeft(right); setRight(left); }}>
          <Icon name="ArrowLeftRight" />
        </button>
        <PackagePicker label="右侧图包" value={right} onChange={setRight} names={names} group={group} listId={listId} byLabel={byLabel} />
        <button class="btn primary" disabled={!valid || running} onClick={() => void start(left, right)}>
          <Icon name="GitCompare" size={16} />开始核验
        </button>
      </div>
      <datalist id={listId}>
        {[...byLabel.keys()].map((label) => <option key={label} value={label} />)}
      </datalist>
      {left && left === right && <p class="form-error"><Icon name="CircleAlert" size={16} />请选择两个不同的图包</p>}
      {names.error && <ListState error={`图包列表读取失败：${names.error}`} retry={names.retry} loading={false} />}
      {!id && <div class="empty small"><Icon name="GitCompare" size={30} /><p>还没有核验过此文件夹中的图包</p></div>}
      {gone && <p class="note">之前的核验记录已不存在，请重新核验。</p>}
      {task && <TaskBlock task={task} label="整包核验" onRestart={restart} />}
      {result && task && <CompareView group={group} task={task} result={result} names={names} onRecheck={restart} />}
    </section>
  );
}

function PackagePicker({ label, value, onChange, names, group, listId, byLabel }: {
  label: string; value: string | null; onChange: (id: string | null) => void; names: Names; group: Group; listId: string;
  byLabel: Map<string, string>;
}) {
  const current = value ? names.get(value) : undefined;
  const [text, setText] = useState('');
  useEffect(() => { if (current) setText(pickerLabel(current, group)); }, [current?.id]);
  return (
    <label class="picker">
      <span>{label}</span>
      <input list={listId} value={text} spellcheck={false} placeholder={names.loading ? '正在读取图包…' : '输入名称并从列表中选择'}
        aria-invalid={Boolean(text) && !value}
        onInput={(event) => { const next = event.currentTarget.value; setText(next); onChange(byLabel.get(next) ?? null); }} />
    </label>
  );
}

interface Verdict { tone: 'ok' | 'warn' | ''; icon: IconName; title: string; text: string }

function verdictOf(result: CompareResult): Verdict {
  const l = result.left_files, r = result.right_files;
  if (result.exact_equal) {
    return { tone: 'ok', icon: 'CopyCheck', title: '两侧完全一致', text: `两个图包的 ${count(l)} 个文件逐字节相同（包括非图片文件），保留其中一个即可。` };
  }
  if (result.left_contained) {
    return { tone: 'ok', icon: 'CopyCheck', title: '左侧被右侧完整包含',
      text: `左侧全部 ${count(l)} 个文件在右侧都有逐字节相同的副本；右侧另有 ${count(result.right_unique_total)} 个独有文件。删除左侧不会丢失内容。` };
  }
  if (result.right_contained) {
    return { tone: 'ok', icon: 'CopyCheck', title: '右侧被左侧完整包含',
      text: `右侧全部 ${count(r)} 个文件在左侧都有逐字节相同的副本；左侧另有 ${count(result.left_unique_total)} 个独有文件。删除右侧不会丢失内容。` };
  }
  if (!l && !r) return { tone: 'warn', icon: 'CircleAlert', title: '两侧都没有文件', text: '两个图包当前都没有文件，无法判断是否重复。' };
  if (!l || !r) {
    return { tone: 'warn', icon: 'CircleAlert', title: `${l ? '右' : '左'}侧图包当前没有文件`, text: '空图包不算被包含，没有可以比较的内容。' };
  }
  return { tone: '', icon: 'Files', title: '两侧各有独有文件',
    text: `左侧独有 ${count(result.left_unique_total)} 个、右侧独有 ${count(result.right_unique_total)} 个文件。两侧不是重复关系，删除任何一侧都会丢失内容。` };
}

function CompareView({ group, task, result, names, onRecheck }: {
  group: Group; task: Task; result: CompareResult; names: Names; onRecheck: () => void;
}) {
  const lib = currentLibrary.value;
  // The revision covers the whole library, so any scan or delete after the check makes it stale.
  const stale = Boolean(lib && lib.id === group.library_id && lib.revision > result.revision);
  const verdict = verdictOf(result);
  return (
    <>
      <div class={`verdict ${verdict.tone}`} role="status">
        <Icon name={verdict.icon} size={22} />
        <div><strong>{verdict.title}</strong><p>{verdict.text}</p></div>
      </div>
      {stale && (
        <div class="note warn">
          <Icon name="TriangleAlert" size={16} />
          <span>核验之后图库有过扫描或删除，结果可能已过期；删除前需要重新核验。</span>
          <button class="btn small" onClick={onRecheck}><Icon name="RotateCcw" size={14} />重新核验</button>
        </div>
      )}
      <div class="compare-sides">
        <Side which="left" group={group} task={task} result={result} names={names} stale={stale} />
        <Side which="right" group={group} task={task} result={result} names={names} stale={stale} />
      </div>
    </>
  );
}

const FILE_PAGE = 100;

function Side({ which, group, task, result, names, stale }: {
  which: 'left' | 'right'; group: Group; task: Task; result: CompareResult; names: Names; stale: boolean;
}) {
  const left = which === 'left';
  const id = left ? result.left_id : result.right_id;
  const files = left ? result.left_files : result.right_files;
  const uniqueTotal = left ? result.left_unique_total : result.right_unique_total;
  const contained = left ? result.left_contained : result.right_contained;
  const pkg = names.get(id);
  const findings = useFindings<ComparedFile>(task.id, left ? 'left_unique' : 'right_unique',
    left ? result.left_unique : result.right_unique, uniqueTotal, FILE_PAGE);
  const remove = () => {
    if (!pkg) return;
    requestDelete({
      targets: [{ kind: 'package', id }], title: `图包“${pkg.name}”（${count(files)} 个文件）`,
      names: { [id]: pkg.rel }, includesFolders: true,
    });
  };
  return (
    <section class={`compare-side ${contained ? 'contained' : ''}`} aria-label={left ? '左侧' : '右侧'}>
      <h3>{left ? '左侧' : '右侧'}</h3>
      <PackageRef id={id} names={names} group={group}>
        <span class="muted">{count(files)} 个文件 · 独有 {count(uniqueTotal)} 个</span>
      </PackageRef>
      {contained && (
        <div class="side-delete">
          <p class="hint"><Icon name="CopyCheck" size={14} />此图包的全部文件在{left ? '右' : '左'}侧都有逐字节相同的副本。</p>
          {pkg?.loose
            ? <p class="muted">散图不是独立的图包，不能整包删除；请进入图片墙逐张处理。</p>
            : (
              <button class="btn danger" disabled={!pkg || stale} onClick={remove}
                title={stale ? '结果可能已过期，请先重新核验' : '删除整个图包文件夹（默认移到回收站）'}>
                <Icon name="Trash2" size={16} />删除此图包…
              </button>
            )}
        </div>
      )}
      {uniqueTotal > 0 && (
        <div class="unique">
          <header class="org-block-head">
            <h4>独有文件</h4>
            <span class="muted">{count(uniqueTotal)} 个</span>
            <span class="spacer" />
            <Pager page={findings.page} pages={findings.pages} onPage={findings.setPage} />
          </header>
          <ListState error={findings.error} retry={findings.retry} loading={!findings.items && !findings.error} />
          {findings.items && (
            <ul class="file-list">
              {findings.items.map((file) => (
                <li key={file.id} class="file-row">
                  {file.is_image
                    ? <button class="file-thumb" aria-label={`查看 ${file.name}`} onClick={() => void openImage(group, 'compare', file.id, id)}><Thumb id={file.id} edge={400} /></button>
                    : <span class="file-icon" title="非图片文件"><Icon name="FileText" size={18} /></span>}
                  <span class="file-name" title={file.name}>{file.name}</span>
                  <span class="muted num">{bytes(file.size)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
