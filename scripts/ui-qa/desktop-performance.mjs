import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createWriteStream } from 'node:fs';
import { mkdir, mkdtemp, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import { fileURLToPath } from 'node:url';
import { _electron } from 'playwright-core';

const project = fileURLToPath(new URL('../../', import.meta.url));
const [baseline, current] = process.argv.slice(2);
assert.ok(baseline && current, 'Usage: node desktop-performance.mjs <baseline GalleryTool.exe> <current GalleryTool.exe>');
const temporary = await mkdtemp(path.join(tmpdir(), 'gallery-desktop-perf-'));
const output = path.join(project, 'output/ui-qa', `desktop-performance-${Date.now()}`);
await mkdir(output, { recursive: true });
const libraryPath = path.join(temporary, 'generated-library');
const environment = { ...process.env };
for (const key of ['ELECTRON_RUN_AS_NODE', 'GALLERY_ROOT', 'GALLERY_DATA', 'GALLERY_LEGACY',
  'GALLERY_APPLICATION', 'GALLERY_DESKTOP_TOKEN', 'GALLERY_TEST_BACKEND']) delete environment[key];
let application, page, generator;

const distribution = (times) => {
  const ordered = [...times].sort((a, b) => a - b);
  return { p50_ms: Number(ordered[Math.floor(ordered.length / 2)].toFixed(2)),
    p95_ms: Number(ordered[Math.ceil(ordered.length * .95) - 1].toFixed(2)), samples: ordered.length };
};

async function run(executable, label) {
  const data = path.join(temporary, label);
  application = await _electron.launch({ executablePath: path.resolve(executable),
    env: { ...environment, GALLERY_DATA: data }, timeout: 60000 });
  page = await application.firstWindow();
  page.setDefaultTimeout(30000);
  const errors = [], budgetWarnings = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('crash', () => errors.push('Renderer crashed'));
  page.on('console', (message) => {
    if (message.text().includes('Image memory budget check failed:')) budgetWarnings.push(message.text());
  });
  await page.getByRole('button', { name: '选择文件夹…', exact: true }).waitFor();
  await application.evaluate(({ app, BrowserWindow }, filePath) => {
    const originalMetrics = app.getAppMetrics.bind(app);
    let policyQueries = 0;
    app.getAppMetrics = () => { policyQueries++; return originalMetrics(); };
    app.__stillmarkMetrics = () => ({ items: originalMetrics(), policyQueries });
    BrowserWindow.getAllWindows()[0].webContents.session.registerPreloadScript({
      id: 'stillmark-perf-resources', type: 'frame', filePath,
    });
  }, path.join(project, 'scripts/ui-qa/resource-stats.cjs'));
  await page.reload();
  await page.getByRole('button', { name: '选择文件夹…', exact: true }).waitFor();
  const base = new URL(page.url()).origin;
  const api = async (route, body) => {
    const response = await fetch(base + '/api/v1' + route, { method: body ? 'POST' : 'GET',
      headers: body ? { 'Content-Type': 'application/json' } : {},
      body: body ? JSON.stringify(body) : undefined, signal: AbortSignal.timeout(30000) });
    assert.ok(response.ok, `${route}: ${response.status}`);
    return response.json();
  };
  const library = await api('/libraries', { path: libraryPath });
  const scanDeadline = Date.now() + 120000;
  while (true) {
    const scans = (await api('/tasks?kind=scan')).items;
    assert.ok(scans.length && scans.every((task) => !['failed', 'interrupted'].includes(task.state)));
    if (scans.every((task) => task.state === 'completed')) break;
    assert.ok(Date.now() < scanDeadline, 'Fixture scan did not finish');
    await delay(100);
  }
  const groups = (await api(`/libraries/${library.id}/groups?limit=500`)).items;
  const mountain = groups.find((group) => group.name === '山色');
  const motion = groups.find((group) => group.name.includes('动图'));
  assert.ok(mountain && motion);
  const packages = (await api(`/groups/${mountain.id}/packages`)).items;
  const targets = [];
  for (const pkg of packages.slice(0, 4)) {
    const images = (await api(`/packages/${pkg.id}/images`)).items;
    for (const image of images.slice(0, 4)) targets.push({ group: mountain, pkg, image });
  }
  assert.equal(targets.length, 16);
  const motionPackage = (await api(`/groups/${motion.id}/packages`)).items[0];
  const animations = (await api(`/packages/${motionPackage.id}/images`)).items
    .filter((image) => /01-gif|02-webp/.test(image.name))
    .map((image) => ({ group: motion, pkg: motionPackage, image, expectAnimated: true }));
  assert.equal(animations.length, 2);
  // Same derivatives and metadata are ready in both independent application profiles.
  for (const { image } of targets) {
    const response = await fetch(`${base}/api/v1/images/${image.id}/thumbnail?edge=400`);
    assert.ok(response.ok); await response.arrayBuffer();
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  const nativeMemory = async () => {
    const memory = await application.evaluate(({ app, BrowserWindow }) => {
      const pid = BrowserWindow.getAllWindows()[0].webContents.getOSProcessId();
      const metrics = app.__stillmarkMetrics();
      const value = metrics.items.find((item) => item.pid === pid).memory;
      return { private_mib: value.privateBytes / 1024, working_set_mib: value.workingSetSize / 1024,
        policy_queries: metrics.policyQueries };
    });
    assert.ok(Number.isFinite(memory.private_mib) && Number.isFinite(memory.working_set_mib),
      'The Windows renderer memory measurements must be available');
    const resources = await page.evaluate(() => ({ blink_images: window.__stillmarkResourceUsage.read().images,
      dom_images: document.querySelectorAll('img').length }));
    return { ...memory, ...resources };
  };
  const show = async ({ group, pkg, image, expectAnimated = false }) => {
    const hash = `#/l/${library.id}/g/${group.id}/p/${pkg.id}/i/${image.id}`;
    const started = performance.now();
    await page.evaluate((value) => { location.hash = value; }, hash);
    await page.waitForFunction(({ id, name, expectAnimated }) => {
      const element = document.querySelector('.viewer .frame:not(.pending):not(.placeholder):not(.stale) img');
      return element?.alt === name && element.complete && element.naturalWidth > 0
        && element.currentSrc.includes(`/images/${id}/`) && (!expectAnimated || element.currentSrc.includes('/original'))
        && !document.querySelector('.viewer-loading, .viewer .frame.pending');
    }, { id: image.id, name: image.name, expectAnimated });
    assert.deepEqual(errors, []);
    return performance.now() - started;
  };
  const measure = async () => {
    const timings = [];
    for (const target of targets) timings.push({ id: target.image.id, name: target.image.name,
      package: target.pkg.name, ms: Number((await show(target)).toFixed(2)) });
    return { ...distribution(timings.map((item) => item.ms)), timings };
  };
  const report = { executable: path.resolve(executable), data,
    image_release_bridge: await page.evaluate(() => typeof window.galleryImageResources?.release === 'function'),
    viewer_resource_first: await measure(), viewer_resource_warm: await measure(),
    memory_before_animation_workload: await nativeMemory(), animation_workload: [] };
  for (let cycle = 0; cycle < 90; cycle++) {
    for (const target of animations) {
      await show(target); await delay(360);
      await page.keyboard.press('Escape');
      await page.locator('.viewer').waitFor({ state: 'detached' });
    }
    if (cycle % 15 === 14) {
      const sample = { cycle: cycle + 1, ...await nativeMemory() };
      report.animation_workload.push(sample);
      console.log(`${label}: ${sample.cycle}/90 GIF/WebP pairs, renderer ${sample.private_mib.toFixed(1)} MiB`);
    }
  }
  report.viewer_resource_warm_after_animation_workload = await measure();
  report.viewer_resource_reheated_after_animation_workload = await measure();
  report.memory_after_animation_workload = await nativeMemory();
  report.errors = errors;
  report.budget_warnings = budgetWarnings;
  assert.deepEqual(errors, []); assert.deepEqual(budgetWarnings, []);
  if (report.image_release_bridge) assert.ok(report.memory_after_animation_workload.policy_queries > 0,
    'Real image cleanup must reach the production native-memory policy');
  await application.close(); application = null; page = null;
  await assert.rejects(fetch(base + '/api/v1/health', { signal: AbortSignal.timeout(1000) }),
    'The owned backend must exit with its desktop');
  report.owned_backend_exited = true;
  return report;
}

try {
  const stream = createWriteStream(path.join(output, 'fixture.log'));
  generator = spawn(path.join(project, '.venv/Scripts/python.exe'), ['scripts/demo_ui_library.py', libraryPath],
    { cwd: project, env: environment, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
  generator.stdout.pipe(stream, { end: false }); generator.stderr.pipe(stream, { end: false });
  await new Promise((resolve, reject) => {
    generator.once('error', reject);
    generator.once('exit', (code) => { stream.end(); code === 0 ? resolve() : reject(new Error(`Fixture generation exited ${code}`)); });
  });
  const report = { notes: 'Actual packaged Electron, same generated files and 1440x1000 viewport, independent temporary profiles. '
    + 'A separate read-only sandbox preload samples Blink resource statistics; it cannot clear resources. '
    + '400px derivatives primed first; resource-first is not physical disk cold. 90 GIF/WebP pairs use normal UI navigation and production resource policy. '
    + 'The first revisit after animations can require decoded images to be rebuilt; the reheated pass repeats the same targets immediately. '
    + 'No diagnostic cache clear, explicit GC or injected memory-pressure notification; the production policy uses Electron public resource reclamation. '
    + 'Native memory is sampled without an extra GC. This short workload does not replace a 60-minute soak.',
    baseline: await run(baseline, 'baseline'), current: await run(current, 'current') };
  await writeFile(path.join(output, 'result.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
  console.log(`Reports: ${output}`);
} catch (error) {
  await writeFile(path.join(output, 'failure.txt'), error.stack ?? String(error));
  await page?.screenshot({ path: path.join(output, 'failure.png') }).catch(() => {});
  throw error;
} finally {
  await application?.close().catch(() => {});
  if (generator && generator.exitCode === null && generator.signalCode === null) generator.kill();
}
