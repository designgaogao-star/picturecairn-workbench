import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createWriteStream } from 'node:fs';
import { appendFile, mkdir, mkdtemp, readFile, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import { fileURLToPath } from 'node:url';
import { _electron } from 'playwright-core';

const project = fileURLToPath(new URL('../../', import.meta.url));
const option = (name, fallback) => {
  const index = process.argv.indexOf(name);
  return index < 0 ? fallback : process.argv[index + 1];
};
const executable = option('--desktop');
const minutes = Number(option('--minutes', '60'));
const preflight = process.argv.includes('--preflight');
assert.ok(executable && Number.isFinite(minutes) && minutes >= 60, '--desktop and --minutes >= 60 are required');
const output = path.join(project, 'output/quality', `soak-${Date.now()}`);
await mkdir(output, { recursive: true });
const temporary = await mkdtemp(path.join(tmpdir(), 'gallery-soak-data-'));
const source = path.join(temporary, 'generated-library');
const python = path.join(project, '.venv/Scripts/python.exe');
const env = { ...process.env, GALLERY_DATA: temporary };
for (const key of ['ELECTRON_RUN_AS_NODE', 'GALLERY_ROOT', 'GALLERY_LEGACY', 'GALLERY_APPLICATION', 'GALLERY_DESKTOP_TOKEN', 'GALLERY_TEST_BACKEND']) delete env[key];
const children = [];
let application, page, backendUrl, sampler;
const errors = [];
const inflight = new Map();
const controls = [];
const samples = [];
const processFile = path.join(output, 'processes.jsonl');
const rendererFile = path.join(output, 'renderer.jsonl');
let closing = false;

function launch(args, name) {
  const stream = createWriteStream(path.join(output, `${name}.log`));
  const child = spawn(python, args, { cwd: project, env, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
  child.stdout.pipe(stream, { end: false });
  child.stderr.pipe(stream, { end: false });
  child.once('close', () => stream.end());
  children.push(child);
  return child;
}
const exited = (child) => child.exitCode !== null || child.signalCode !== null ? Promise.resolve(child.exitCode) : new Promise((resolve, reject) => {
  child.once('error', reject);
  child.once('exit', resolve);
});
async function api(route, method = 'GET', body) {
  const response = await fetch(backendUrl + '/api/v1' + route, { method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined, signal: AbortSignal.timeout(30000) });
  const value = await response.json();
  assert.ok(response.ok, `${method} ${route}: ${response.status} ${JSON.stringify(value)}`);
  return value;
}
async function taskDone(id) {
  const deadline = Date.now() + 120000;
  while (Date.now() < deadline) {
    const task = await api(`/tasks/${id}`);
    if (!['queued', 'running', 'paused', 'cancelling'].includes(task.state)) {
      assert.ok(['completed', 'cancelled'].includes(task.state), JSON.stringify(task));
      return task;
    }
    await delay(100);
  }
  throw new Error(`Task did not settle: ${id}`);
}
async function wall(hash) {
  await page.evaluate((value) => { location.hash = value; }, hash);
  await page.locator('.content .card-hit').first().waitFor();
}
async function visiblePreview() {
  await page.waitForFunction(() => {
    const layer = document.querySelector('.viewer img.layer');
    return layer?.naturalWidth > 0;
  });
}
async function controlPrewarm(packageId, edge) {
  const task = await api('/tasks', 'POST', { kind: 'prewarm', package_id: packageId, edge });
  for (const action of ['pause', 'resume', 'cancel']) {
    const current = await api(`/tasks/${task.id}`);
    if (!['queued', 'running', 'paused'].includes(current.state)) break;
    const response = await fetch(`${backendUrl}/api/v1/tasks/${task.id}/control`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action }),
      signal: AbortSignal.timeout(30000),
    });
    if (response.status === 409) continue; // Completion can race the control request.
    assert.ok(response.ok, `Task ${action}: ${response.status}`);
    controls.push({ id: task.id, action, at: Date.now() });
    await delay(150);
  }
  await taskDone(task.id);
}
const median = (values) => [...values].sort((a, b) => a - b)[Math.floor(values.length / 2)];
function trend(records, valueOf) {
  const points = records.map((row) => [row.elapsed_seconds / 60, valueOf(row)]);
  const x = points.reduce((sum, point) => sum + point[0], 0) / points.length;
  const y = points.reduce((sum, point) => sum + point[1], 0) / points.length;
  const slope = points.reduce((sum, point) => sum + (point[0] - x) * (point[1] - y), 0)
    / points.reduce((sum, point) => sum + (point[0] - x) ** 2, 0);
  const half = Math.floor(points.length / 2);
  return { slope_per_minute: slope, median_change: median(points.slice(half).map((point) => point[1])) - median(points.slice(0, half).map((point) => point[1])) };
}

console.log(`Soak evidence: ${output}`);
console.log(`Temporary data: ${temporary}`);
try {
  assert.equal(await exited(launch(['scripts/demo_ui_library.py', source, '--large-count', '8120'], 'generate')), 0);
  application = await _electron.launch({ executablePath: path.resolve(executable), env, timeout: 60000 });
  application.on('close', () => { if (!closing) errors.push('Electron closed unexpectedly'); });
  page = await application.firstWindow();
  page.setDefaultTimeout(20000);
  page.on('pageerror', (error) => errors.push(error.stack ?? error.message));
  page.on('crash', () => errors.push('Renderer crashed'));
  page.on('request', (request) => inflight.set(request, { url: request.url(), at: Date.now() }));
  page.on('requestfinished', (request) => inflight.delete(request));
  page.on('requestfailed', (request) => inflight.delete(request));
  await page.getByRole('button', { name: '选择文件夹…', exact: true }).waitFor();
  backendUrl = new URL(page.url()).origin;
  const rootPid = await application.evaluate(() => process.pid);
  const ready = JSON.parse(await readFile(path.join(temporary, `desktop-${rootPid}.json`), 'utf8'));
  sampler = launch(['scripts/ui-qa/process_metrics.py', '--root', String(rootPid), '--backend', String(ready.pid),
    '--output', processFile, '--interval', '30'], 'sampler');
  const library = await api('/libraries', 'POST', { path: source, name: 'Soak generated library' });
  for (const task of (await api('/tasks?active=true')).items) await taskDone(task.id);
  const groups = (await api(`/libraries/${library.id}/groups?limit=500`)).items;
  const big = groups.find((group) => group.name.includes('大图包'));
  const mountain = groups.find((group) => group.name === '山色');
  const motion = groups.find((group) => group.name.includes('动图'));
  const duplicates = groups.find((group) => group.name.includes('重复样本'));
  assert.ok(big && mountain && motion && duplicates);
  const bigPackage = (await api(`/groups/${big.id}/packages`)).items[0];
  const mountainPackages = (await api(`/groups/${mountain.id}/packages`)).items;
  const motionPackage = (await api(`/groups/${motion.id}/packages`)).items[0];
  const animations = (await api(`/packages/${motionPackage.id}/images`)).items.filter((item) => /01-gif|02-webp/.test(item.name));
  const duplicatePackages = (await api(`/groups/${duplicates.id}/packages`)).items;
  const groupHash = (group) => `#/l/${library.id}/g/${group.id}`;
  const packageHash = (group, pkg) => `${groupHash(group)}/p/${pkg.id}`;
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Performance.enable');
  const started = Date.now(), deadline = started + minutes * 60000;
  await writeFile(path.join(output, 'run.json'), JSON.stringify({ executable: path.resolve(executable), temporary, source,
    rootPid, backendPid: ready.pid, started: new Date(started).toISOString(), minutes, preflight }, null, 2));
  let cycle = 0;
  while (preflight ? cycle < 6 : Date.now() < deadline) {
    const cycleStart = Date.now();
    assert.deepEqual(errors, []);
    assert.equal(sampler.exitCode, null, 'Process sampler stopped before Electron');
    const phase = cycle % 6;
    if (phase === 0 || phase === 4) {
      await wall(packageHash(big, bigPackage));
      await page.locator('.images .vgrid').evaluate((grid, index) => {
        const cells = [...grid.querySelectorAll('.vgrid-cell')];
        const top = cells[0].getBoundingClientRect().top;
        const columns = cells.filter((cell) => Math.abs(cell.getBoundingClientRect().top - top) < 1).length;
        const next = cells.find((cell) => cell.getBoundingClientRect().top > top + 1);
        grid.scrollTop = Math.floor(index / columns) * (next.getBoundingClientRect().top - top);
      }, (cycle * 137) % 7900);
      await delay(400);
      const entry = page.locator('.images .card-hit[tabindex="0"]');
      await entry.focus();
      await page.keyboard.press(phase === 4 ? 'End' : 'PageDown');
      await page.waitForFunction(() => document.activeElement?.matches('.images .card-hit'));
      if (phase === 4) {
        await page.keyboard.press('Home');
        await page.waitForFunction(() => document.activeElement?.closest('[aria-posinset]')?.getAttribute('aria-posinset') === '1');
        await page.keyboard.press('Space');
        await page.keyboard.press('Escape');
        await page.getByRole('button', { name: '信息', exact: true }).click();
        await page.getByRole('button', { name: '信息', exact: true }).click();
      } else {
        await page.keyboard.press('Enter');
        await visiblePreview();
        for (let index = 0; index < 15; index++) { await page.keyboard.press('ArrowRight'); await delay(25); }
        await visiblePreview();
        await page.keyboard.press('Escape');
        await page.locator('.viewer').waitFor({ state: 'detached' });
      }
    } else if (phase === 1) {
      await wall(packageHash(mountain, mountainPackages[Math.floor(cycle / 6) % mountainPackages.length]));
      await page.locator('.images .card-hit').first().focus();
      await page.keyboard.press('Enter');
      await visiblePreview();
      await page.keyboard.press('ArrowRight');
      await visiblePreview();
      await page.keyboard.press('Escape');
      await page.locator('.viewer').waitFor({ state: 'detached' });
    } else if (phase === 2) {
      for (const animation of animations) {
        await page.evaluate((hash) => { location.hash = hash; }, `${packageHash(motion, motionPackage)}/i/${animation.id}`);
        await visiblePreview();
        await delay(1200);
        await page.keyboard.press('Escape');
        await page.locator('.viewer').waitFor({ state: 'detached' });
      }
    } else if (phase === 3) {
      await page.evaluate((hash) => { location.hash = hash; }, `${groupHash(mountain)}/organize/t/samples`);
      await page.locator('.sample-controls').waitFor();
      await page.locator('.sample-grid .card-hit').first().waitFor();
      await page.getByRole('button', { name: '后台任务', exact: true }).click();
      await page.locator('.drawer[open]').waitFor();
      await page.keyboard.press('Escape');
      await page.locator('.drawer').waitFor({ state: 'detached' });
    } else {
      await wall(groupHash(duplicates));
      const analyze = await api('/tasks', 'POST', { kind: 'analyze', group_id: duplicates.id, threshold: 8 });
      await taskDone(analyze.id);
      const compare = await api('/tasks', 'POST', { kind: 'compare', left_id: duplicatePackages[0].id, right_id: duplicatePackages[1].id });
      await taskDone(compare.id);
    }
    if (cycle % 18 === 0) await controlPrewarm(bigPackage.id, [400, 800, 1600, 2560, 4200][Math.floor(cycle / 18) % 5]);
    if (cycle % 12 === 6) await taskDone((await api('/tasks', 'POST', { kind: 'scan', library_id: library.id })).id);
    await delay(400);
    const cache = await api('/cache');
    assert.ok(cache.bytes <= cache.limit, 'Derivative cache exceeded its configured budget');
    const active = (await api('/tasks?active=true')).items;
    assert.ok(active.length <= 6 && active.every((task) => task.state !== 'queued' || Date.now() / 1000 - task.created < 30),
      `Background jobs accumulated: ${JSON.stringify(active.map(({ kind, state, trigger }) => ({ kind, state, trigger })))}`);
    const requests = [...inflight.values()].filter((item) => !item.url.endsWith('/events'));
    assert.ok(requests.length <= 16 && requests.every((item) => Date.now() - item.at < 30000), 'Image requests accumulated');
    const performance = Object.fromEntries((await cdp.send('Performance.getMetrics')).metrics.map((item) => [item.name, item.value]));
    const dom = await cdp.send('Memory.getDOMCounters');
    const record = { elapsed_seconds: (Date.now() - started) / 1000, cycle, phase, performance, dom, errors: [...errors], controls: [...controls],
      liveDom: await page.locator('*').count(), requests: requests.length, activeTasks: active.length, cache };
    samples.push(record);
    await appendFile(rendererFile, JSON.stringify(record) + '\n');
    if (cycle % 15 === 0) {
      await page.screenshot({ path: path.join(output, `minute-${Math.floor(record.elapsed_seconds / 60)}.png`) });
      console.log(`Soak ${record.elapsed_seconds.toFixed(0)}s: cycle=${cycle}, DOM=${record.liveDom}, requests=${requests.length}, tasks=${active.length}`);
    }
    cycle++;
    if (!preflight) await delay(Math.max(0, Math.min(20000 - (Date.now() - cycleStart), deadline - Date.now())));
  }
  for (const task of (await api('/tasks?active=true')).items) await taskDone(task.id);
  assert.deepEqual(errors, []);
  assert.ok(['pause', 'resume', 'cancel'].every((action) => controls.some((control) => control.action === action)));
  if (!preflight) assert.ok(Date.now() - started >= minutes * 60000);
  const processes = (await readFile(processFile, 'utf8')).trim().split('\n').map(JSON.parse);
  const latter = processes.filter((row) => row.elapsed_seconds >= processes.at(-1).elapsed_seconds - 1800);
  const processTrend = preflight ? null : trend(latter, (row) => row.processes.reduce((sum, item) => sum + item.private, 0) / 1024 ** 2);
  const handleTrend = preflight ? null : trend(latter, (row) => row.processes.reduce((sum, item) => sum + item.handles, 0));
  const rendererTrend = preflight ? null : trend(samples.filter((row) => row.elapsed_seconds >= minutes * 60 - 1800), (row) => row.performance.JSHeapUsedSize / 1024 ** 2);
  const summary = { preflight, elapsed_seconds: (Date.now() - started) / 1000, cycles: cycle, errors, controls,
    samples: { renderer: samples.length, processes: processes.length }, process_private_mib: processTrend,
    handles: handleTrend, renderer_heap_mib: rendererTrend, cache: await api('/cache'),
    passed: preflight || processTrend.slope_per_minute < 2 && processTrend.median_change < 96
      && handleTrend.slope_per_minute < 2 && handleTrend.median_change < 100
      && rendererTrend.slope_per_minute < 1 && rendererTrend.median_change < 32 };
  await writeFile(path.join(output, 'result.json'), JSON.stringify(summary, null, 2));
  assert.ok(summary.passed, 'Sustained growth exceeded acceptance thresholds; inspect the recorded trends');
  // Persist the completed workload and trend checks before a separate screenshot capture can fail.
  await page.screenshot({ path: path.join(output, 'final-desktop.png'), timeout: 60000 });
  closing = true;
  await application.close();
  application = null;
  assert.equal(await exited(sampler), 0);
  assert.equal(await exited(launch(['scripts/ui-qa/process_metrics.py', '--check-exited', processFile], 'exit-check')), 0);
  summary.owned_processes_exited = true;
  await writeFile(path.join(output, 'result.json'), JSON.stringify(summary, null, 2));
  console.log(`PASS ${preflight ? 'preflight only' : 'long run'}: ${summary.elapsed_seconds.toFixed(1)} seconds, ${cycle} cycles; all owned desktop/backend processes exited`);
} catch (error) {
  await appendFile(path.join(output, 'failure.txt'), (error.stack ?? String(error)) + '\n');
  await page?.screenshot({ path: path.join(output, 'failure.png') }).catch(() => {});
  throw error;
} finally {
  closing = true;
  await application?.close().catch(() => {});
  for (const child of children.reverse()) if (child.exitCode === null && child.signalCode === null) {
    child.kill();
    await exited(child);
  }
}
