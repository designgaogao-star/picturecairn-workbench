import { useEffect, useState } from 'preact/hooks';
import { client, describeError, isAbort, isActive, type AnalyzeResult, type Group, type PackageSimilarity, type Pair } from '../api';
import { Thumb } from '../components/Thumb';
import { GroupMenu, ModeTabs, NarrowMarks } from '../components/GroupHeader';
import { MarkSegment } from '../components/Marks';
import { count, percent } from '../lib/format';
import { Icon, type IconName } from '../lib/icons';
import { lastOrganizeTab, navigate, route, type OrganizeTab } from '../lib/router';
import { currentLibrary, reportError, submitTask, trackTask } from '../state/app';
import { Audit } from './Audit';
import { Compare } from './Compare';
import { Samples } from './Samples';
import {
  completed, ListState, openImage, PackageRef, Pager, Stat, startCompare, TaskBlock, useFindings, usePackageNames, useTracked, type Names,
} from './organizeParts';

const TABS: { id: OrganizeTab; label: string; icon: IconName }[] = [
  { id: 'samples', label: '抽样', icon: 'Dices' },
  { id: 'similar', label: '相似图包', icon: 'Images' },
  { id: 'compare', label: '整包核验', icon: 'GitCompare' },
  { id: 'audit', label: '清理检查', icon: 'ShieldAlert' },
];

export function Organize({ group }: { group: Group }) {
  const tab = route.value.tab ?? lastOrganizeTab();
  useEffect(() => { sessionStorage.setItem('gt.organizeTab', tab); }, [tab]);
  return (
    <div class="organize">
      <div class="toolbar"><ModeTabs /><span class="toolbar-sep" />
      <nav class="segment tool-tabs" aria-label="整理功能">
        {TABS.map((item) => (
          <button key={item.id} title={item.label} class={item.id === tab ? 'active' : ''} aria-current={item.id === tab ? 'page' : undefined}
            onClick={() => navigate({ library: group.library_id, group: group.id, view: 'organize', tab: item.id }, { replace: true })}>
            <Icon name={item.icon} size={16} /><span>{item.label}</span>
          </button>
        ))}
      </nav>
      <span class="spacer" /><MarkSegment class="at-wide" groupId={group.id} value={group.state} />
      {currentLibrary.value && <GroupMenu group={group} lib={currentLibrary.value}><NarrowMarks group={group} /></GroupMenu>}
      </div>
      {tab === 'samples' ? <Samples groupId={group.id} group={group} /> : <div class="org-scroll">
        {tab === 'similar' && <Similar group={group} />}
        {tab === 'compare' && <Compare group={group} />}
        {tab === 'audit' && <Audit group={group} />}
      </div>}
    </div>
  );
}

// ---------------------------------------------------------------- similar packages

const THRESHOLD = 'gt.threshold';
function savedThreshold(): number {
  const value = Number(localStorage.getItem(THRESHOLD) ?? 8);
  return Number.isInteger(value) && value >= 0 && value <= 16 ? value : 8;
}
const strictness = (value: number) => (value <= 4 ? '严格' : value <= 10 ? '适中' : '宽松');

function Similar({ group }: { group: Group }) {
  const scope = `analyze:${group.id}`;
  const { id, task, gone } = useTracked(scope);
  const names = usePackageNames(group.id);
  const [threshold, setThreshold] = useState(savedThreshold);
  const result = completed<AnalyzeResult>(task);
  const running = task ? isActive(task) : false;
  const start = async () => {
    try {
      localStorage.setItem(THRESHOLD, String(threshold));
      const created = await submitTask({ kind: 'analyze', group_id: group.id, threshold });
      trackTask(scope, created.id);
    } catch (error) { reportError(error, '无法开始相似分析：'); }
  };
  const used = typeof task?.payload.threshold === 'number' ? task.payload.threshold : null;
  return (
    <section class="org-section">
      <p class="org-intro">
        相似度是画面线索，不能证明文件内容相同。删除依据为整包内容核验或用户自己的选择。
      </p>
      <div class="org-controls">
        <label class="threshold">
          <span>相似阈值</span>
          <input type="range" min={0} max={16} step={1} value={threshold} disabled={running}
            onInput={(event) => setThreshold(Number(event.currentTarget.value))} aria-valuetext={`${threshold}，${strictness(threshold)}`} />
          <span class="num">{threshold}</span>
          <span class="muted">{strictness(threshold)}</span>
        </label>
        <button class="btn primary" disabled={running} onClick={() => void start()}>
          <Icon name="ScanSearch" size={16} />{result ? '重新分析' : '开始分析'}
        </button>
        <span class="muted hint">分析会先重新扫描此文件夹，再为新图片计算指纹；机械硬盘上可能需要较长时间。</span>
      </div>
      {!id && <div class="empty small"><Icon name="Images" size={30} /><p>还没有分析过此文件夹</p></div>}
      {gone && <p class="note">之前的分析记录已不存在，请重新分析。</p>}
      {task && <TaskBlock task={task} label={`相似分析${used !== null ? `（阈值 ${used}）` : ''}`} onRestart={() => void start()} />}
      {result && task && <AnalyzeView group={group} result={result} names={names} />}
    </section>
  );
}

function AnalyzeView({ group, result, names }: { group: Group; result: AnalyzeResult; names: Names }) {
  const unhashed = result.images - Math.round(result.coverage * result.images);
  return (
    <>
      <div class="org-stats">
        <Stat label="图片" value={count(result.images)} />
        <Stat label="指纹覆盖" value={percent(result.coverage)} tone={result.coverage < 1 ? 'warn' : ''} />
        {result.failed > 0 && <Stat label="无法计算指纹" value={count(result.failed)} tone="bad" />}
        <Stat label="相似图片对" value={count(result.pairs)} />
        <Stat label="相似图包对" value={count(result.package_pairs_total)} />
      </div>
      {unhashed > 0 && (
        <p class="note warn"><Icon name="TriangleAlert" size={16} />
          <span>有 {count(unhashed)} 张图片没有指纹（无法解码或分析期间发生变化），不参与比较，相关图包的匹配率会偏低。</span>
        </p>
      )}
      <PackagePairs group={group} result={result} names={names} />
      <ImagePairs group={group} taskId={result.pair_task_id} />
    </>
  );
}

const full = (rate: number) => rate >= 1;
function pairVerdict(pair: PackageSimilarity): { text: string; tone: string } {
  if (full(pair.left_match_rate) && full(pair.right_match_rate)) return { text: '疑似完全重复', tone: 'bad' };
  if (full(pair.left_match_rate)) return { text: '左侧疑似被包含', tone: 'warn' };
  if (full(pair.right_match_rate)) return { text: '右侧疑似被包含', tone: 'warn' };
  return { text: '部分相似', tone: '' };
}

function Rate({ rate, coverage }: { rate: number; coverage: number }) {
  return (
    <span class="rate">
      <b class="num">{percent(rate)}</b> 的图片在另一侧有相似图
      <span class={coverage < 1 ? 'warn-text' : 'muted'}>（指纹覆盖 {percent(coverage)}）</span>
    </span>
  );
}

const PAIR_PAGE = 30;

function PackagePairs({ group, result, names }: { group: Group; result: AnalyzeResult; names: Names }) {
  const total = result.package_pairs_total;
  const findings = useFindings<PackageSimilarity>(result.pair_task_id, 'package_pair', result.package_pairs, total, PAIR_PAGE);
  const { page, pages, setPage } = findings;
  const shown = findings.items ?? [];
  return (
    <section class="org-block">
      <header class="org-block-head">
        <h2>相似图包</h2>
        <span class="muted">{count(total)} 对</span>
        <span class="spacer" />
        <Pager page={page} pages={pages} onPage={setPage} />
      </header>
      {names.error && <ListState error={`图包名称读取失败：${names.error}`} retry={names.retry} loading={false} />}
      <ListState error={findings.error} retry={findings.retry} loading={!findings.items && !findings.error} />
      {total === 0 && <p class="muted">没有发现相似的图包。</p>}
      <ul class="pair-list">
        {shown.map((pair) => {
          const verdict = pairVerdict(pair);
          return (
            <li key={`${pair.left_id}:${pair.right_id}`} class="pair-row">
              <PackageRef id={pair.left_id} names={names} group={group}>
                <Rate rate={pair.left_match_rate} coverage={pair.left_coverage} />
              </PackageRef>
              <div class="pair-mid">
                <span class={`chip ${verdict.tone}`}>{verdict.text}</span>
                <button class="btn small" title="内容核验两个图包的全部文件" onClick={() => void startCompare(group, pair.left_id, pair.right_id)}>
                  <Icon name="GitCompare" size={14} />整包核验
                </button>
              </div>
              <PackageRef id={pair.right_id} names={names} group={group}>
                <Rate rate={pair.right_match_rate} coverage={pair.right_coverage} />
              </PackageRef>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

const IMAGE_PAGE = 40;

/** Similar image pairs, read page by page from the analysis task (they are not embedded in its result). */
function ImagePairs({ group, taskId }: { group: Group; taskId: string }) {
  const [page, setPage] = useState(0);
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<{ key: string; items?: Pair[]; total?: number; error?: string }>({ key: '' });
  const key = `${taskId}:${page}`;
  useEffect(() => { setPage(0); }, [taskId]);
  useEffect(() => {
    const controller = new AbortController();
    client.request('get', '/api/v1/tasks/{task_id}/pairs', {
      params: { path: { task_id: taskId }, query: { offset: page * IMAGE_PAGE, limit: IMAGE_PAGE } }, signal: controller.signal,
    }).then((result) => setState({ key, items: result.items, total: result.total }))
      .catch((error) => { if (!isAbort(error)) setState((old) => ({ key, total: old.total, error: describeError(error) })); });
    return () => controller.abort();
  }, [key, attempt]);
  const current = state.key === key ? state : null;
  const total = state.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / IMAGE_PAGE));
  return (
    <section class="org-block">
      <header class="org-block-head">
        <h2>相似图片</h2>
        {state.total !== undefined && <span class="muted">{count(total)} 对，按差异从小到大</span>}
        <span class="spacer" />
        <Pager page={page} pages={pages} onPage={setPage} />
      </header>
      <ListState error={current?.error ?? null} retry={() => setAttempt((n) => n + 1)} loading={!current?.items && !current?.error} />
      {current?.items && !current.items.length && <p class="muted">没有相似的图片。</p>}
      {current?.items && current.items.length > 0 && (
        <ul class="image-pairs">
          {current.items.map((pair) => (
            <li key={`${pair.left_id}:${pair.right_id}`} class="image-pair">
              <button class="pair-thumb" onClick={() => void openImage(group, 'similar', pair.left_id, pair.left_package_id)} aria-label="查看左图">
                <Thumb id={pair.left_id} edge={400} retryButton={false} />
              </button>
              <span class="pair-distance" title="指纹差异（0 表示几乎相同，最大 64）">
                <Icon name="ArrowLeftRight" size={14} /><span class="num">{pair.distance}</span>
              </span>
              <button class="pair-thumb" onClick={() => void openImage(group, 'similar', pair.right_id, pair.right_package_id)} aria-label="查看右图">
                <Thumb id={pair.right_id} edge={400} retryButton={false} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
