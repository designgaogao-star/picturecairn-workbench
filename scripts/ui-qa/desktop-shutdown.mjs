import assert from 'node:assert/strict';
import { mkdir, mkdtemp, readFile, writeFile, access } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { setTimeout as delay } from 'node:timers/promises';
import { _electron } from 'playwright-core';

// An empty generated library exposes the real size controls without loading images.
// Exercise the renderer and desktop lifecycle using isolated data; no deletion is requested.
const project = fileURLToPath(new URL('../../', import.meta.url));
const index = process.argv.indexOf('--desktop');
if (index >= 0) assert.ok(process.argv[index + 1], '--desktop needs an executable path');
const executable = index >= 0 ? path.resolve(process.argv[index + 1]) : path.join(project, 'node_modules/electron/dist/electron.exe');
const data = await mkdtemp(path.join(tmpdir(), 'gallery-shutdown-'));
const library = await mkdtemp(path.join(tmpdir(), 'gallery-shutdown-library-'));
const output = path.join(project, 'output/ui-qa', `shutdown-${Date.now()}`);
await mkdir(output, { recursive: true });
const lifecycle = path.join(output, 'lifecycle.jsonl');
const env = { ...process.env, GALLERY_DATA: data };
for (const name of ['ELECTRON_RUN_AS_NODE', 'GALLERY_ROOT', 'GALLERY_LEGACY',
  'GALLERY_DESKTOP_TOKEN', 'GALLERY_APPLICATION', 'GALLERY_TEST_BACKEND']) delete env[name];
let application, child, descriptor, page;
const preferences = path.join(data, 'ui-preferences.json');
const report = { executable, temporary: data, library, checks: [], preference_warnings: [] };

async function exitWithin(process, milliseconds) {
  if (process.exitCode !== null || process.signalCode !== null) return;
  let timer;
  try {
    await Promise.race([
      new Promise((resolve) => process.once('exit', resolve)),
      new Promise((_resolve, reject) => { timer = setTimeout(() => reject(new Error('Desktop did not exit in time')), milliseconds); }),
    ]);
  } finally { clearTimeout(timer); }
}

async function waitForSavedSize(size) {
  // Windows runners can schedule the close event after a delayed window show.
  // Keep checking the exact persisted value, but allow the 1.5s save timeout and
  // the runner's process scheduling to complete before declaring a failure.
  for (let attempt = 0; attempt < 200; attempt++) {
    try { if (JSON.parse(await readFile(path.join(data, 'ui-preferences.json'), 'utf8'))['gt.tileSize'] === size) return; }
    catch (error) { if (!['ENOENT', 'EACCES', 'EPERM'].includes(error.code)) throw error; }
    await delay(50);
  }
  throw new Error(`Desktop did not save tile size ${size}`);
}

async function waitForWindowVisibility(visible) {
  const actual = await application.evaluate(async ({ BrowserWindow }, expected) => {
    const window = BrowserWindow.getAllWindows()[0];
    const deadline = Date.now() + 5000;
    while (window && window.isVisible() !== expected && Date.now() < deadline) {
      await new Promise((resolve) => setTimeout(resolve, 25));
    }
    return window?.isVisible() ?? false;
  }, visible);
  assert.equal(actual, visible, `Desktop window did not become ${visible ? 'visible' : 'hidden'}`);
}
async function show() {
  await application.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].show());
  await waitForWindowVisibility(true);
}
async function hide() {
  await application.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].close());
  await waitForWindowVisibility(false);
}
async function blockRenderer(page, milliseconds) {
  // Return to the driver first; only the renderer thread will be busy, not Electron's main thread.
  await page.evaluate((duration) => {
    setTimeout(() => { const until = performance.now() + duration; while (performance.now() < until) { /* simulated renderer stall */ } }, 0);
  }, milliseconds);
  await delay(150);
}

async function chooseSize(size) {
  await page.getByRole('radio', { name: { s: '小', m: '中', l: '大' }[size], exact: true }).click();
  await page.waitForFunction((value) => localStorage.getItem('gt.tileSize') === value, size);
}

try {
  application = await _electron.launch({ executablePath: executable, args: index >= 0 ? [] : ['.'], cwd: project, env, timeout: 30000 });
  child = application.process();
  application.on('console', (message) => {
    if (message.text().startsWith('Unable to save UI preferences:')) {
      report.preference_warnings.push({ at: new Date().toISOString(), text: message.text() });
    }
  });
  page = await application.firstWindow();
  // These main-process events distinguish application shutdown from native process exit.
  // Write them immediately so a closed inspector connection cannot lose the final phase.
  await application.evaluate(({ app, BrowserWindow }, destination) => {
    const fs = process.getBuiltinModule('fs');
    const record = (event) => fs.appendFileSync(destination, JSON.stringify({ at: Date.now(), event }) + '\n');
    for (const event of ['before-quit', 'will-quit', 'quit', 'window-all-closed']) app.on(event, () => record(event));
    const window = BrowserWindow.getAllWindows()[0];
    for (const event of ['close', 'closed', 'unresponsive']) window.on(event, () => record(`window-${event}`));
    window.webContents.on('destroyed', () => record('renderer-destroyed'));
  }, lifecycle);
  child.once('exit', (code, signal) => { report.process_exit = { at: Date.now(), code, signal }; });
  await page.getByRole('button', { name: '选择文件夹…', exact: true }).waitFor();
  const pid = await application.evaluate(() => process.pid);
  const ready = path.join(data, `desktop-${pid}.json`);
  descriptor = JSON.parse(await readFile(ready, 'utf8'));
  const registered = await fetch(descriptor.url + '/api/v1/libraries', { method: 'POST',
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: library, name: '退出验证（空图库）' }) });
  assert.equal(registered.status, 201);
  const lib = await registered.json();
  await page.goto(`${descriptor.url}/#/l/${lib.id}`);
  await application.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].setContentSize(1100, 800));
  await page.getByRole('radio', { name: '中', exact: true }).waitFor();

  await chooseSize('s');
  await hide();
  await waitForSavedSize('s');
  const baseline = await readFile(preferences, 'utf8');
  report.checks.push('responsive renderer saves current preferences');

  await show();
  await chooseSize('l');
  await blockRenderer(page, 4000);
  await hide();
  // Wait for the same renderer to recover so its late read can actually resolve.
  await page.evaluate(() => localStorage.getItem('gt.tileSize'));
  await show();
  // Use the same Electron execution queue as the save; CDP evaluation alone can overtake it.
  assert.equal(await application.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].webContents
    .executeJavaScript('localStorage.getItem("gt.tileSize")')), 'l');
  assert.equal(await readFile(preferences, 'utf8'), baseline, 'A timed-out read must not overwrite saved preferences when the renderer recovers');
  report.checks.push('late preference result cannot overwrite the previous file');

  // A layout change must preserve the actual UI choice. Raw storage writes bypassed this state.
  await application.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].setContentSize(700, 600));
  await page.waitForFunction(() => innerWidth <= 860 && localStorage.getItem('gt.tileSize') === 'l');
  await hide();
  await waitForSavedSize('l');
  const beforeQuit = await readFile(preferences, 'utf8');
  report.checks.push('saving resumes normally after a timed-out read');

  await show();
  await application.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].setContentSize(1100, 800));
  await chooseSize('m');
  await blockRenderer(page, 8000);
  const started = performance.now();
  report.quit_started_at = Date.now();
  await application.evaluate(({ app }) => { setImmediate(() => app.quit()); });
  await exitWithin(child, 6500);
  report.quit_ms = Math.round(performance.now() - started);
  assert.equal(child.exitCode, 0);
  assert.equal(await readFile(preferences, 'utf8'), beforeQuit, 'Quitting with a blocked renderer preserves previously saved preferences');
  await assert.rejects(access(ready), { code: 'ENOENT' });
  await assert.rejects(fetch(descriptor.url + '/api/v1/health', { signal: AbortSignal.timeout(1000) }));
  report.checks.push('desktop and owned backend exit before the blocked renderer recovers');
  report.passed = true;
} catch (error) {
  report.passed = false;
  report.error = error.stack ?? String(error);
  report.saved_preferences = await readFile(preferences, 'utf8').catch((failure) => ({ error: failure.message }));
  if (page && !page.isClosed()) {
    report.renderer = await Promise.race([
      page.evaluate(() => ({ size: localStorage.getItem('gt.tileSize'), visibility: document.visibilityState, width: innerWidth })),
      delay(1000).then(() => ({ timeout: true })),
    ]).catch((failure) => ({ error: failure.message }));
  }
  throw error;
} finally {
  // Only close processes launched above. Destroying the test window also unblocks a failed test's save.
  if (child && child.exitCode === null && child.signalCode === null) {
    await application.evaluate(({ app, BrowserWindow }) => {
      for (const window of BrowserWindow.getAllWindows()) window.destroy();
      app.quit();
    }).catch(() => {});
    await exitWithin(child, 10000).catch(() => child.kill());
  }
  if (descriptor) {
    try {
      const response = await fetch(descriptor.url + '/api/v1/health', { signal: AbortSignal.timeout(500) });
      const health = await response.json();
      if (health.instance_id === descriptor.instance_id) {
        process.kill(descriptor.pid);
        report.forced_backend_cleanup = true;
      }
    } catch { /* already stopped */ }
  }
  report.lifecycle = (await readFile(lifecycle, 'utf8').catch(() => '')).split('\n').filter(Boolean).map((line) => JSON.parse(line));
  await writeFile(path.join(output, 'result.json'), JSON.stringify(report, null, 2));
}
console.log(`PASS ${report.checks.length} desktop lifecycle checks; blocked quit ${report.quit_ms}ms; ${output}`);
