import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createWriteStream } from 'node:fs';
import { mkdir, mkdtemp, readFile, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { setTimeout as delay } from 'node:timers/promises';
import { chromium } from 'playwright-core';

const project = fileURLToPath(new URL('../../', import.meta.url));
const [baseline, current] = process.argv.slice(2).map((value) => path.resolve(value));
assert.ok(baseline && current, 'Usage: node performance.mjs <baseline gallery_server.exe> <current gallery_server.exe>');
const temporary = await mkdtemp(path.join(tmpdir(), 'gallery-ui-perf-'));
const output = path.join(project, 'output/ui-qa', `performance-${Date.now()}`);
await mkdir(output, { recursive: true });
const library = path.join(temporary, 'library');
const environment = { ...process.env, GALLERY_DESKTOP_TOKEN: 'isolated-ui-performance' };
for (const key of ['GALLERY_DATA', 'GALLERY_ROOT', 'GALLERY_LEGACY', 'GALLERY_APPLICATION', 'ELECTRON_RUN_AS_NODE']) delete environment[key];
const children = [];
let browser, running;
const distribution = (values) => {
  const ordered = [...values].sort((a, b) => a - b);
  return { p50_ms: Number(ordered[Math.floor(ordered.length / 2)].toFixed(2)), p95_ms: Number(ordered[Math.ceil(ordered.length * .95) - 1].toFixed(2)),
    samples: ordered.length, samples_ms: values.map((value) => Number(value.toFixed(2))) };
};
function launch(executable, args, name) {
  const stream = createWriteStream(path.join(output, name + '.log'));
  const child = spawn(executable, args, { cwd: project, env: environment, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
  child.stdout.pipe(stream, { end: false }); child.stderr.pipe(stream, { end: false });
  child.once('close', () => stream.end());
  children.push(child);
  return child;
}
async function exit(child) {
  if (child.exitCode !== null || child.signalCode !== null) return;
  await new Promise((resolve) => child.once('exit', resolve));
}
async function stop() {
  if (!running) return;
  await fetch(running.url + '/api/v1/system/shutdown', { method: 'POST', headers: { 'x-gallery-desktop': environment.GALLERY_DESKTOP_TOKEN }, signal: AbortSignal.timeout(5000) });
  await exit(running.child);
  running = null;
}
async function start(executable, label, data, attempt) {
  const ready = path.join(temporary, `${label}-${attempt}-ready.json`);
  const began = performance.now();
  const child = launch(executable, ['--data', data, '--port', '0', '--ready-file', ready, '--no-open', '--no-watch', '--no-scan'], `${label}-${attempt}`);
  for (let tries = 0; tries < 1000; tries++) {
    assert.equal(child.exitCode, null);
    try {
      const descriptor = JSON.parse(await readFile(ready, 'utf8'));
      running = { child, url: descriptor.url };
      return { ...running, ready_ms: performance.now() - began };
    } catch (error) { if (!['ENOENT', 'EACCES', 'EPERM'].includes(error.code)) throw error; }
    await delay(20);
  }
  throw new Error(`${label} startup timeout`);
}
async function request(url, route, body) {
  const response = await fetch(url + route, body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  assert.ok(response.ok, route);
  return response.json();
}
async function run(executable, label) {
  const data = path.join(temporary, label);
  let service = await start(executable, label, data, 1);
  const lib = await request(service.url, '/api/v1/libraries', { path: library });
  for (let attempt = 0; attempt < 500; attempt++) {
    const scan = (await request(service.url, '/api/v1/tasks')).items.find((item) => item.kind === 'scan');
    if (scan?.state === 'completed') break;
    assert.notEqual(scan?.state, 'failed');
    await delay(50);
  }
  await stop();
  service = await start(executable, label, data, 2);
  const groups = (await request(service.url, `/api/v1/libraries/${lib.id}/groups`)).items;
  const group = groups.find((item) => item.name === '山色');
  const packages = (await request(service.url, `/api/v1/groups/${group.id}/packages`)).items;
  const largeGroup = groups.find((item) => item.name.includes('大图包'));
  const largePackage = (await request(service.url, `/api/v1/groups/${largeGroup.id}/packages`)).items[0];
  const targets = [];
  const previews = new Map();
  for (const pkg of packages.slice(0, 4)) {
    const images = (await request(service.url, `/api/v1/packages/${pkg.id}/images`)).items;
    for (const image of images) previews.set(image.id, image);
    for (const image of images.slice(0, 4)) targets.push({ pkg, image });
  }
  // Both versions start with 400px derivatives and metadata ready, no originals cached by the browser.
  for (const image of previews.values()) assert.ok((await fetch(`${service.url}/api/v1/images/${image.id}/thumbnail?edge=400`)).ok);
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' });
  const page = await context.newPage();
  const session = await context.newCDPSession(page);
  let thumbnails = 0, maxCards = 0;
  page.on('request', (event) => { if (event.url().includes('/thumbnail')) thumbnails++; });
  const wall = `${service.url}#/l/${lib.id}/g/${group.id}/p/${packages[0].id}`;
  const walls = [];
  for (let index = 0; index < 16; index++) {
    await page.goto('about:blank');
    const began = performance.now();
    await page.goto(wall);
    await page.waitForFunction(() => {
      const cards = [...document.querySelectorAll('.image-card .thumb')];
      return cards.length === 8 && cards.every((item) => item.classList.contains('is-ready') && item.querySelector('img')?.naturalWidth > 0);
    });
    walls.push(performance.now() - began);
    maxCards = Math.max(maxCards, await page.locator('.image-card').count());
  }
  const render = async (items) => {
    const times = [];
    for (const { pkg, image } of items) {
      const began = performance.now();
      await page.goto(`${service.url}#/l/${lib.id}/g/${group.id}/p/${pkg.id}/i/${image.id}`);
      await page.waitForFunction((name) => {
        const image = document.querySelector('.viewer .frame:not(.pending):not(.placeholder):not(.stale) img');
        return image?.alt === name && image.complete && image.naturalWidth > 0 && !document.querySelector('.viewer-loading');
      }, image.name);
      times.push(performance.now() - began);
    }
    return distribution(times);
  };
  const cold = await render(targets);
  const warm = await render(targets);
  await session.send('HeapProfiler.collectGarbage');
  const heap = await session.send('Runtime.getHeapUsage');
  const apiTimes = async (route, count) => {
    const values = [];
    for (let index = 0; index < count; index++) {
      const began = performance.now();
      const response = await fetch(service.url + route);
      assert.ok(response.ok); await response.arrayBuffer();
      values.push(performance.now() - began);
    }
    return distribution(values);
  };
  const report = { indexed_ready_ms: Number(service.ready_ms.toFixed(2)), visible_wall: distribution(walls),
    viewer_resource_first: cold, viewer_resource_warm: warm, renderer_heap_mib: Number((heap.usedSize / 1024 / 1024).toFixed(2)),
    max_wall_cards: maxCards, thumbnail_requests: thumbnails,
    health: await apiTimes('/api/v1/health', 50), images_100: await apiTimes(`/api/v1/packages/${largePackage.id}/images?limit=100`, 40),
    warm_thumbnail: await apiTimes(`/api/v1/images/${targets[0].image.id}/thumbnail?edge=400`, 50) };
  await context.close();
  await stop();
  return report;
}
try {
  const generator = launch(path.join(project, '.venv/Scripts/python.exe'), ['scripts/demo_ui_library.py', library], 'fixture');
  await exit(generator);
  assert.equal(generator.exitCode, 0);
  browser = await chromium.launch({ channel: 'msedge', headless: true });
  const report = { notes: 'Same generated files, same viewport, independent empty data/cache directories and fresh browser contexts. 400px previews primed before UI measurement. Resource-first is a browser cache miss, not physical disk cold; OS cache is not flushed. Heap is post-GC renderer JS only. Electron RSS/physical disk IO are not inferred.',
    baseline: await run(baseline, 'baseline'), current: await run(current, 'current') };
  await writeFile(path.join(output, 'result.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
  console.log(`Reports: ${output}`);
} finally {
  await browser?.close();
  await stop().catch(() => undefined);
  for (const child of children) if (child.exitCode === null && child.signalCode === null) child.kill();
}
