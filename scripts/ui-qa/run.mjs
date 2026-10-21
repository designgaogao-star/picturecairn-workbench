import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createWriteStream } from 'node:fs';
import { access, mkdir, mkdtemp, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import { fileURLToPath } from 'node:url';
import { _electron, chromium } from 'playwright-core';
import { createServer } from 'vite';
import { readonlyApiChecks, readonlyChecks } from './readonly.mjs';
import { directoryChecks, workflows } from './workflows.mjs';

const project = fileURLToPath(new URL('../../', import.meta.url));
const temporary = await mkdtemp(path.join(tmpdir(), 'gallery-ui-qa-'));
const output = path.join(project, 'output', 'ui-qa', `integration-${Date.now()}`);
await mkdir(output, { recursive: true });
const children = [];
const applications = [];
let server;
const option = (name) => {
  const index = process.argv.indexOf(name);
  if (index < 0) return null;
  assert.ok(process.argv[index + 1] && !process.argv[index + 1].startsWith('--'), `${name} needs a path`);
  return path.resolve(process.argv[index + 1]);
};
const packedDesktop = option('--desktop');
const packedBackend = option('--backend');
assert.ok(!(packedDesktop && packedBackend), '--desktop and --backend are mutually exclusive');

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
  if (child.exitCode !== null) return;
  child.kill();
  if (child.exitCode === null) await new Promise((resolve) => child.once('exit', resolve));
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
  if (packedDesktop) {
    const data = path.join(temporary, 'desktop');
    const application = await _electron.launch({
      executablePath: packedDesktop, env: { ...environment, GALLERY_DATA: data },
    });
    applications.push(application);
    const page = await application.firstWindow();
    await page.getByRole('button', { name: '选择文件夹…', exact: true }).waitFor();
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
    const { restoreHash } = await workflows(page, url, library, output);
    await page.goto(url + restoreHash);
    await page.waitForFunction(() => document.querySelector('.viewer img.layer')?.naturalWidth > 0);
    await application.close();
    applications.pop();
    await assert.rejects(access(ready), { code: 'ENOENT' });
    await assert.rejects(fetch(`${url}/api/v1/health`, { signal: AbortSignal.timeout(1000) }));
    console.log('PASS packaged Electron, preload IPC, owned backend shutdown');
    assert.equal(JSON.parse(await readFile(path.join(data, 'window-state.json'), 'utf8')).route, restoreHash);
    const restarted = await _electron.launch({ executablePath: packedDesktop, env: { ...environment, GALLERY_DATA: data } });
    applications.push(restarted);
    const restored = await restarted.firstWindow();
    await restored.waitForFunction(() => document.querySelector('.viewer img.layer')?.naturalWidth > 0);
    assert.equal(new URL(restored.url()).hash, restoreHash, 'Desktop restart should restore the route across dynamic ports');
    await restarted.close();
    applications.pop();
    console.log('PASS desktop restart: persisted image route and original library data');
  } else {
    const ready = path.join(temporary, 'ready.json');
    const token = 'isolated-ui-qa';
    const backend = launch(packedBackend || path.join(project, '.venv', 'Scripts', 'python.exe'), [
      ...(packedBackend ? [] : ['-m', 'gallery']), '--data', path.join(temporary, 'data'), '--port', '0',
      '--ready-file', ready, '--no-watch', '--no-scan', '--no-open',
    ], 'backend', { ...environment, GALLERY_DESKTOP_TOKEN: token });
    const descriptor = await readyFile(ready, backend);
    process.env.GALLERY_BACKEND = descriptor.url;
    process.env.GALLERY_UI_PORT = '0';
    server = await createServer({ configFile: path.join(project, 'ui', 'vite.config.ts') });
    await server.listen();
    const base = server.resolvedUrls.local[0];
    await readonlyApiChecks(server, base);
    if (!process.argv.includes('--api-only')) {
      const application = await chromium.launch({ channel: 'msedge', headless: true });
      applications.push(application);
      const page = await application.newPage({ viewport: { width: 1440, height: 1000 } });
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
      await workflows(page, descriptor.url, library, output);
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
} finally {
  for (const application of applications.reverse()) await application.close().catch(() => {});
  await server?.close();
  for (const child of children.reverse()) await stop(child);
}
