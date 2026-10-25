import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createWriteStream } from 'node:fs';
import { access, mkdir, mkdtemp, readFile, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import { fileURLToPath } from 'node:url';
import { _electron, chromium } from 'playwright-core';
import { createServer } from 'vite';
import { readonlyApiChecks, readonlyChecks } from './readonly.mjs';
import { directoryChecks, workflows } from './workflows.mjs';
import { libraryChecks } from './libraries.mjs';
import { brandingChecks } from './branding.mjs';
import { imageLifecycleChecks } from './image-lifecycle.mjs';

const project = fileURLToPath(new URL('../../', import.meta.url));
const temporary = await mkdtemp(path.join(tmpdir(), 'gallery-ui-qa-'));
const output = path.join(project, 'output', 'ui-qa', `integration-${Date.now()}`);
await mkdir(output, { recursive: true });
const children = [];
const applications = [];
const ownedServers = [];
let server, activePage;
const option = (name) => {
  const index = process.argv.indexOf(name);
  if (index < 0) return null;
  assert.ok(process.argv[index + 1] && !process.argv[index + 1].startsWith('--'), `${name} needs a path`);
  return path.resolve(process.argv[index + 1]);
};
const packedDesktop = option('--desktop');
const packedBackend = option('--backend');
const sourceDesktop = process.argv.includes('--source-desktop');
const traceBackend = process.argv.includes('--trace-backend');
assert.ok(Number(Boolean(packedDesktop)) + Number(Boolean(packedBackend)) + Number(sourceDesktop) <= 1,
  '--desktop, --backend and --source-desktop are mutually exclusive');
const desktopExecutable = packedDesktop || (sourceDesktop ? path.join(project, 'node_modules/electron/dist/electron.exe') : null);
assert.ok(!traceBackend || !desktopExecutable && !packedBackend, '--trace-backend only diagnoses the isolated source backend');
const desktopArguments = sourceDesktop ? ['.'] : [];

const environment = { ...process.env };
for (const name of ['ELECTRON_RUN_AS_NODE', 'GALLERY_ROOT', 'GALLERY_DATA', 'GALLERY_LEGACY',
  'GALLERY_DESKTOP_TOKEN', 'GALLERY_APPLICATION', 'GALLERY_TEST_BACKEND']) delete environment[name];

function launch(command, args, name, env = environment) {
  const log = createWriteStream(path.join(output, `${name}.log`));
  const child = spawn(command, args, { cwd: project, env, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
  child.stdout.pipe(log, { end: false });
  child.stderr.pipe(log, { end: false });
  child.once('close', () => log.end());
  children.push(child);
  return child;
}

async function readyFile(file, process) {
  for (let attempt = 0; attempt < 300; attempt++) {
    assert.equal(process.exitCode, null, 'Backend exited before its handshake');
    try { return JSON.parse(await readFile(file, 'utf8')); }
    catch (error) { if (!['ENOENT', 'EACCES', 'EPERM'].includes(error.code)) throw error; }
    await delay(100);
  }
  throw new Error('Backend handshake timed out');
}

async function stop(child) {
  if (child.exitCode !== null || child.signalCode !== null) return;
  const exited = new Promise((resolve) => child.once('exit', resolve));
  child.kill();
  await exited;
}

try {
  const library = path.join(temporary, 'library');
  const generate = launch(path.join(project, '.venv', 'Scripts', 'python.exe'), [
    'scripts/demo_ui_library.py', library,
  ], 'generate');
  await new Promise((resolve, reject) => {
    generate.once('error', reject);
    generate.once('exit', (code) => code === 0 ? resolve() : reject(new Error(`Fixture generation exited ${code}`)));
  });
  if (desktopExecutable) {
    const data = path.join(temporary, 'desktop');
    const application = await _electron.launch({
      executablePath: desktopExecutable, args: desktopArguments, env: { ...environment, GALLERY_DATA: data },
    });
    applications.push(application);
    const page = activePage = await application.firstWindow();
    const imageMemoryWarnings = [];
    page.on('console', (message) => {
      if (message.text().includes('Image memory budget check failed:')) imageMemoryWarnings.push(message.text());
    });
    await page.getByRole('button', { name: '选择文件夹…', exact: true }).waitFor();
    assert.equal(await page.evaluate(() => typeof window.galleryImageResources?.release), 'function',
      'The real sandboxed image-memory preload must be available');
    const choose = (choice) => application.evaluate(({ dialog }, result) => {
      dialog.showOpenDialog = async () => {
        if (result.error) throw new Error(result.error);
        return result;
      };
    }, choice);
    await directoryChecks(page, choose, library, output);
    const url = new URL(page.url()).origin;
    const pid = await application.evaluate(() => process.pid);
    const ready = path.join(data, `desktop-${pid}.json`);
    assert.ok(JSON.parse(await readFile(ready, 'utf8')).pid > 0);
    const onlyLibraries = process.argv.includes('--libraries-only');
    if (!onlyLibraries) await workflows(page, url, library, output);
    const { restoreHash } = await libraryChecks(page, url, library, output, choose);
    await imageLifecycleChecks(page, url, output);
    await brandingChecks(page, url, output, application);
    await page.evaluate(() => window.galleryImageResources.release());
    await delay(1500);
    assert.deepEqual(imageMemoryWarnings, [], 'No renderer-memory IPC errors may appear during the desktop workflows');
    await writeFile(path.join(output, 'image-memory-verification.json'), JSON.stringify({
      sandboxed_preload_available: true, release_hint_requested: true, observed_budget_warnings: imageMemoryWarnings,
    }, null, 2));
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(url + restoreHash);
    await page.waitForFunction(() => document.querySelector('.viewer img.layer')?.naturalWidth > 0);
    await page.evaluate(() => {
      localStorage.setItem('gt.theme', 'dark');
      localStorage.setItem('gt.tileSize', 's');
      localStorage.setItem('gt.inspector', '1');
    });
    await application.close();
    applications.pop();
    await assert.rejects(access(ready), { code: 'ENOENT' });
    await assert.rejects(fetch(`${url}/api/v1/health`, { signal: AbortSignal.timeout(1000) }));
    console.log(`PASS ${sourceDesktop ? 'source' : 'packaged'} Electron, preload IPC, owned backend shutdown`);
    assert.equal(JSON.parse(await readFile(path.join(data, 'window-state.json'), 'utf8')).route, restoreHash);
    const restarted = await _electron.launch({ executablePath: desktopExecutable, args: desktopArguments, env: { ...environment, GALLERY_DATA: data } });
    applications.push(restarted);
    const restored = activePage = await restarted.firstWindow();
    await restored.waitForFunction(() => document.querySelector('.viewer img.layer')?.naturalWidth > 0);
    assert.equal(await restored.evaluate(() => typeof window.galleryImageResources?.release), 'function',
      'The resource policy must be registered again after desktop restart');
    assert.equal(new URL(restored.url()).hash, restoreHash, 'Desktop restart should restore the route across dynamic ports');
    assert.deepEqual(await restored.evaluate(() => [document.documentElement.dataset.theme,
      localStorage.getItem('gt.tileSize'), localStorage.getItem('gt.inspector')]), ['dark', 's', '1']);
    await restored.keyboard.press('Escape');
    await restored.locator('.viewer').waitFor({ state: 'detached' });
    await restored.getByRole('button', { name: '外观', exact: true }).click();
    await restored.getByRole('menuitemradio', { name: '浅色', exact: true }).click();
    await restored.getByRole('radio', { name: '大', exact: true }).click();
    const wallHash = new URL(restored.url()).hash;
    await restored.addInitScript(() => {
      window.__qaThemeChanges = [];
      new MutationObserver(() => window.__qaThemeChanges.push(document.documentElement.dataset.theme ?? null))
        .observe(document, { subtree: true, attributes: true, attributeFilter: ['data-theme'] });
    });
    await restored.reload();
    await restored.locator('.image-card').first().waitFor();
    assert.equal(new URL(restored.url()).hash, wallHash);
    assert.deepEqual(await restored.evaluate(() => [document.documentElement.dataset.theme,
      localStorage.getItem('gt.tileSize'), localStorage.getItem('gt.inspector')]), ['light', 'l', '1']);
    assert.equal(await restored.evaluate(() => window.__qaThemeChanges[0]), 'light', 'Reload must not flash the previous desktop theme');
    assert.ok(await restored.evaluate(() => window.galleryApp.sessionId && sessionStorage.getItem('gt.desktopSession') === window.galleryApp.sessionId));
    await restored.getByRole('button', { name: '外观', exact: true }).click();
    await restored.getByRole('menuitemradio', { name: '跟随系统', exact: true }).click();
    await restored.reload();
    await restored.locator('.image-card').first().waitFor();
    assert.equal(await restored.evaluate(() => document.documentElement.dataset.theme ?? null), null);
    await restarted.close();
    applications.pop();
    const savedPreferences = JSON.parse(await readFile(path.join(data, 'ui-preferences.json'), 'utf8'));
    assert.equal(savedPreferences['gt.theme'], undefined);
    assert.equal(savedPreferences['gt.tileSize'], 'l');
    console.log('PASS desktop restart and reload: dynamic-port migration, current preferences, first-frame theme, system theme');
  } else {
    const ready = path.join(temporary, 'ready.json');
    const token = 'isolated-ui-qa';
    const sourceEntry = traceBackend ? ['-c', [
      'import faulthandler, runpy, sys',
      'trace = open(sys.argv.pop(1), "w")',
      'faulthandler.dump_traceback_later(2, repeat=True, file=trace)',
      'sys.argv[0] = "gallery"',
      'try:',
      '    runpy.run_module("gallery", run_name="__main__")',
      'finally:',
      '    faulthandler.cancel_dump_traceback_later()',
      '    trace.close()',
    ].join('\n'), path.join(output, 'backend-threads.log')] : ['-m', 'gallery'];
    const backend = launch(packedBackend || path.join(project, '.venv', 'Scripts', 'python.exe'), [
      ...(packedBackend ? [] : sourceEntry), '--data', path.join(temporary, 'data'), '--port', '0',
      '--ready-file', ready, '--no-watch', '--no-scan', '--no-open',
    ], 'backend', { ...environment, GALLERY_DESKTOP_TOKEN: token });
    const descriptor = await readyFile(ready, backend);
    ownedServers.push({ url: descriptor.url, token });
    process.env.GALLERY_BACKEND = descriptor.url;
    process.env.GALLERY_UI_PORT = '0';
    server = await createServer({ configFile: path.join(project, 'ui', 'vite.config.mts') });
    await server.listen();
    const base = server.resolvedUrls.local[0];
    await readonlyApiChecks(server, base);
    if (!process.argv.includes('--api-only')) {
      const application = await chromium.launch({ channel: 'msedge', headless: true });
      applications.push(application);
      const page = activePage = await application.newPage({ viewport: { width: 1440, height: 1000 } });
      await readonlyChecks(page, base, library, output);
      await page.unrouteAll({ behavior: 'wait' });
      // Browser QA supplies the bridge contract; desktop QA exercises the real preload/IPC.
      await page.context().addInitScript(() => {
        window.galleryApp = { chooseDirectory: async () => {
          const choice = window.__qaDirectory;
          if (choice.error) throw new Error(choice.error);
          return choice.canceled ? null : choice.filePaths[0];
        } };
      });
      await page.goto(descriptor.url + '?readonly');
      await directoryChecks(page, (choice) => page.evaluate((value) => { window.__qaDirectory = value; }, choice), library, output);
      if (!process.argv.includes('--libraries-only')) await workflows(page, descriptor.url, library, output);
      await libraryChecks(page, descriptor.url, library, output,
        (choice) => page.evaluate((value) => { window.__qaDirectory = value; }, choice));
      await imageLifecycleChecks(page, descriptor.url, output);
      await brandingChecks(page, descriptor.url, output);
      await application.close();
      applications.pop();
    }
    await fetch(`${descriptor.url}/api/v1/system/shutdown`, {
      method: 'POST', headers: { 'X-Gallery-Desktop': token },
    });
    for (let attempt = 0; attempt < 100 && backend.exitCode === null; attempt++) await delay(100);
    assert.equal(backend.exitCode, 0, 'Backend should exit gracefully');
  }
  console.log(`Screenshots/logs: ${output}`);
  console.log(`Temporary data: ${temporary}`);
} catch (error) {
  const diagnostic = { error: error.stack, temporary };
  if (activePage && !activePage.isClosed()) {
    const read = activePage.evaluate(() => ({
      url: location.href, title: document.title, ready: document.readyState, visibility: document.visibilityState,
      width: innerWidth, height: innerHeight, ratio: devicePixelRatio, text: document.body?.innerText.slice(0, 6000),
      images: [...document.querySelectorAll('img')].slice(0, 100).map((image) => ({
        src: image.getAttribute('src'), complete: image.complete, width: image.naturalWidth, className: image.className,
      })),
    }));
    diagnostic.page = await Promise.race([read, delay(2000).then(() => ({ diagnostic_timeout: true }))])
      .catch((failure) => ({ diagnostic_error: failure.message }));
    await activePage.screenshot({ path: path.join(output, 'failure.png'), timeout: 5000 }).catch(() => {});
  }
  await writeFile(path.join(output, 'failure.json'), JSON.stringify(diagnostic, null, 2));
  throw error;
} finally {
  for (const application of applications.reverse()) await application.close().catch(() => {});
  for (const service of ownedServers) await fetch(service.url + '/api/v1/system/shutdown', {
    method: 'POST', headers: { 'X-Gallery-Desktop': service.token }, signal: AbortSignal.timeout(1000),
  }).catch(() => undefined);
  await server?.close();
  for (const child of children.reverse()) await stop(child);
  for (const name of ['data', 'desktop']) {
    try {
      await writeFile(path.join(output, `${name}-server.log`), await readFile(path.join(temporary, name, 'server.log')));
    } catch (error) {
      if (error.code !== 'ENOENT') console.warn(`Unable to retain ${name} service log: ${error.message}`);
    }
  }
}
