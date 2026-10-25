import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createWriteStream } from 'node:fs';
import { mkdir, mkdtemp, readFile, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { setTimeout as delay } from 'node:timers/promises';
import { chromium } from 'playwright-core';
import { createServer } from 'vite';
import { decisions } from './decisions.mjs';
import { states } from './states.mjs';

const project = fileURLToPath(new URL('../../', import.meta.url));
const output = path.join(project, 'output/ui-qa', `workbench-${Date.now()}`);
const temporary = await mkdtemp(path.join(tmpdir(), 'gallery-workbench-'));
await mkdir(output, { recursive: true });
const environment = { ...process.env };
for (const key of ['ELECTRON_RUN_AS_NODE', 'GALLERY_ROOT', 'GALLERY_DATA', 'GALLERY_LEGACY', 'GALLERY_APPLICATION', 'GALLERY_TEST_BACKEND']) delete environment[key];
const desktopToken = 'isolated-workbench-qa';
environment.GALLERY_DESKTOP_TOKEN = desktopToken;
const children = [];
const checks = [];
const check = (name, condition) => { assert.ok(condition, name); checks.push(name); };
let browser, server, backendUrl, page;
const stageIndex = process.argv.indexOf('--stage');
const stage = stageIndex < 0 ? 'all' : process.argv[stageIndex + 1];
const only = process.argv.includes('--only');

function launch(command, args, name) {
  const log = createWriteStream(path.join(output, `${name}.log`));
  const child = spawn(command, args, { cwd: project, env: environment, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
  child.stdout.pipe(log, { end: false });
  child.stderr.pipe(log, { end: false });
  child.once('close', () => log.end());
  children.push(child);
  return child;
}

async function get(route) {
  const response = await fetch(backendUrl + route);
  assert.equal(response.status, 200, route);
  return response.json();
}

async function settled(page) {
  await page.waitForFunction(() => document.querySelector('.toolbar'));
  await page.waitForFunction(() => {
    const visible = [...document.querySelectorAll('.card, .thumb')].filter((item) => {
      const rect = item.getBoundingClientRect();
      return rect.width && rect.height && rect.bottom > 100 && rect.top < innerHeight;
    });
    return visible.length && visible.every((item) => !item.classList.contains('skeleton') && !item.classList.contains('is-loading'));
  });
}

async function snapshot(page, name) {
  await page.addStyleTag({ content: '*,*::before,*::after{transition:none!important;animation:none!important}' });
  await page.mouse.move(0, 0);
  await page.screenshot({ path: path.join(output, `${name}.png`), animations: 'disabled' });
}

async function toolbarFits(page, name) {
  const result = await page.locator('.content > .wall > .toolbar, .organize > .toolbar, .library-home > .toolbar').first().evaluate((toolbar) => {
    const bounds = toolbar.getBoundingClientRect();
    const overflow = [...toolbar.children].filter((item) => {
      const r = item.getBoundingClientRect();
      return r.width && r.height && (r.left < bounds.left - 1 || r.right > bounds.right + 1);
    }).map((item) => ({ class: item.className, text: item.textContent }));
    return { width: bounds.width, overflow };
  });
  check(`${name}: 工具栏无溢出 ${JSON.stringify(result.overflow)}`, !result.overflow.length);
  check(`${name}: 页面无横向溢出`, await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
}

async function scrollToImage(page, index) {
  await page.locator('.images .vgrid').evaluate((grid, target) => {
    const cells = [...grid.querySelectorAll('.vgrid-cell')];
    const first = cells[0].getBoundingClientRect();
    const columns = cells.filter((cell) => Math.abs(cell.getBoundingClientRect().top - first.top) < 1).length;
    const nextRow = cells.find((cell) => cell.getBoundingClientRect().top > first.top + 1);
    const rowHeight = nextRow.getBoundingClientRect().top - first.top;
    grid.scrollTop = Math.floor(target / columns) * rowHeight;
  }, index);
  await page.locator(`.images [aria-posinset="${index + 1}"] .card-hit`).waitFor();
}

async function framework(page, base, lib, group) {
  const groupHash = `#/l/${lib.id}/g/${group.id}`;
  const packageRoute = base + groupHash;
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto(packageRoute);
  await settled(page);
  for (const width of [1440, 1280, 1920, 1024, 720, 390]) {
    await page.setViewportSize({ width, height: ({ 390: 844, 1280: 800, 1920: 1080 })[width] ?? 1000 });
    await page.waitForFunction((w) => innerWidth === w, width);
    await delay(150);
    for (const theme of ['浅色', '深色']) {
      await page.getByRole('button', { name: '外观', exact: true }).click();
      await page.getByRole('menuitemradio', { name: theme, exact: true }).click();
      await toolbarFits(page, `${width}-${theme}`);
      await snapshot(page, `A1-packages-${width}-${theme === '浅色' ? 'light' : 'dark'}`);
    }
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
  await settled(page);
  const packageCount = (await get(`/api/v1/groups/${group.id}/packages`)).total;
  await page.waitForFunction((count) => {
    const cards = [...document.querySelectorAll('.package-card')];
    return cards.length === count && cards.every((card) => card.querySelector('.thumb.is-ready img')?.naturalWidth > 0);
  }, packageCount);
  const beforeTheme = await page.locator('.package-card').evaluateAll((cards) => cards.map((card) => ({
    id: card.closest('[data-resource-id]')?.getAttribute('data-resource-id'), ready: card.querySelector('.thumb')?.className,
    src: card.querySelector('.thumb img')?.getAttribute('src'), width: card.getBoundingClientRect().width,
  })));
  const thumbnails = [];
  const observe = (request) => { if (request.url().includes('/thumbnail')) thumbnails.push(request.url()); };
  page.on('request', observe);
  await page.getByRole('button', { name: '外观', exact: true }).click();
  await page.getByRole('menuitemradio', { name: '浅色', exact: true }).click();
  await delay(350);
  check(`切换主题不重新请求缩略图${thumbnails.length ? ` ${JSON.stringify({ thumbnails, beforeTheme })}` : ''}`, thumbnails.length === 0);
  check('切换主题保留已解码图片', JSON.stringify(await page.locator('.package-card .thumb img').evaluateAll((images) => images.map((image) => image.src)))
    === JSON.stringify(beforeTheme.map((card) => card.src)));
  page.off('request', observe);
  await page.getByRole('button', { name: '外观', exact: true }).click();
  await page.keyboard.press('End');
  check('菜单 End 到最后一项', await page.evaluate(() => document.activeElement.textContent.includes('深色')));
  await page.keyboard.press('Home');
  check('菜单 Home 到第一项', await page.evaluate(() => document.activeElement.textContent.includes('跟随系统')));
  await page.keyboard.press('ArrowDown');
  check('菜单方向键切换', await page.evaluate(() => document.activeElement.textContent.includes('浅色')));
  await page.keyboard.press('Escape');
  check('关闭菜单返回触发按钮', await page.evaluate(() => document.activeElement.getAttribute('aria-label') === '外观'));
  await page.getByRole('button', { name: '选择', exact: true }).click();
  await page.getByRole('button', { name: '外观', exact: true }).click();
  await page.keyboard.press('Escape');
  check('Escape 先关闭菜单', await page.locator('.toolbar.selecting').count() === 1 && !await page.getByRole('menu').count());
  await page.keyboard.press('Escape');
  check('第二次 Escape 退出选择', await page.locator('.toolbar.selecting').count() === 0);
  await page.goto(base + groupHash + '/samples');
  await page.waitForFunction(() => location.hash.includes('/organize/t/samples'));
  check('旧抽样深链改写', await page.locator('.sample-controls').count() === 1);
  for (const width of [1440, 1024, 720, 390]) {
    await page.setViewportSize({ width, height: 844 });
    await delay(150);
    await toolbarFits(page, `整理-${width}`);
  }
  check('框架无浏览器异常', errors.length === 0);
  return groupHash;
}

async function browsing(page, base, lib, groups) {
  const group = groups.find((item) => item.name === '山色');
  const packages = (await get(`/api/v1/groups/${group.id}/packages`)).items;
  const pkg = packages[0];
  const hash = `#/l/${lib.id}/g/${group.id}`;
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(base + hash);
  await settled(page);
  await page.locator('.package-card .card-hit').first().click();
  await page.waitForFunction((id) => location.hash.endsWith(`/p/${id}`), pkg.id);
  await settled(page);
  check('图包单击进入图片墙', await page.locator('.viewer').count() === 0);
  check('图片默认完整显示', await page.locator('.image-card .thumb > img').first().evaluate((img) => getComputedStyle(img).objectFit === 'contain'));
  check('图片说明常驻且高度准确', await page.locator('.image-card .card-body').first().evaluate((body) => Math.abs(body.getBoundingClientRect().height - 56) < 1 && body.textContent.includes('.jpg')));
  const requests = [];
  const track = (request) => { if (request.url().includes('/thumbnail')) requests.push(request.url()); };
  page.on('request', track);
  await page.getByRole('button', { name: '信息', exact: true }).click();
  await page.locator('.inspector[open]').waitFor();
  await delay(300);
  check('信息面板桌面非模态', await page.locator('.inspector').evaluate((el) => !el.matches(':modal') && Math.round(el.getBoundingClientRect().width) === 280));
  check('无选择显示当前图包', await page.locator('.inspector-head').textContent().then((text) => text.includes('图包信息')));
  check('开启信息面板不重复请求图片', requests.length === 0);
  page.off('request', track);
  await page.locator('.image-card .card-hit').first().focus();
  await page.locator('.inspector-head h2').filter({ hasText: '图片信息' }).waitFor();
  check('焦点项驱动图片信息', await page.locator('.inspector-head').textContent().then((text) => text.includes('图片信息')));
  await page.getByRole('button', { name: '选择', exact: true }).click();
  await page.locator('.image-card .card-hit').nth(0).click();
  await page.locator('.image-card .card-hit').nth(3).click({ modifiers: ['Shift'] });
  await page.waitForFunction(() => document.querySelectorAll('.image-card.selected').length === 4);
  check('Shift 选择连续已载入范围', await page.locator('.image-card.selected').count() === 4);
  check('多选显示数量', await page.locator('.inspector-body h3').textContent().then((text) => text.includes('已选 4 项')));
  await page.keyboard.press('Enter');
  await page.locator('.viewer').waitFor();
  check('选择模式Enter打开当前图片', true);
  await page.keyboard.press('Escape');
  await page.locator('.viewer').waitFor({ state: 'detached' });
  check('查看后选择保持不变', await page.locator('.toolbar.selecting strong').textContent().then((text) => text === '4'));
  await page.getByRole('button', { name: '清空', exact: true }).click();
  await page.getByRole('button', { name: '选中可见项', exact: true }).click();
  check('选中可见项有边界', await page.locator('.image-card.selected').count() > 0 && await page.locator('.image-card.selected').count() <= 8);
  await page.getByRole('button', { name: '完成', exact: true }).click();
  await snapshot(page, 'B-images-inspector-desktop');
  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator('.inspector').waitFor();
  check('窄屏信息抽屉为原生模态', await page.locator('.inspector').evaluate((el) => el.matches(':modal')));
  await snapshot(page, 'B-inspector-narrow');
  await page.keyboard.press('Escape');
  await page.locator('.inspector').waitFor({ state: 'detached' });
  await toolbarFits(page, '图片墙-390');
  const large = groups.find((item) => item.name.includes('大图包'));
  const largePackage = (await get(`/api/v1/groups/${large.id}/packages`)).items[0];
  const images = await get(`/api/v1/packages/${largePackage.id}/images?offset=7900&limit=1`);
  const target = images.items[0];
  await page.goto(`${base}#/l/${lib.id}/g/${large.id}/p/${largePackage.id}/i/${target.id}`);
  await page.waitForFunction(() => document.querySelector('.viewer .frame:not(.pending) img')?.naturalWidth > 0);
  await page.keyboard.press('Escape');
  await page.locator('.viewer').waitFor({ state: 'detached' });
  await settled(page);
  check('8000+ 图包恢复深页图片', await page.locator('.image-card.recent .card-title').textContent().then((text) => text.includes(target.name)));
  check('8000+ 图包 DOM 有界', await page.locator('.image-card').count() < 50);
  await snapshot(page, 'B-large-anchor-narrow');
  await page.setViewportSize({ width: 1440, height: 1000 });
  await delay(200);
  check('改变列数后仍能看到恢复项', await page.locator('.image-card.recent').count() === 1);
  await scrollToImage(page, 0);
  await page.getByRole('button', { name: '选择', exact: true }).click();
  await page.locator('.images [aria-posinset="1"] .card-hit').click();
  for (const index of [100, 200, 300, 400, 520]) await scrollToImage(page, index);
  await page.locator('.images [aria-posinset="521"] .card-hit').click({ modifiers: ['Shift'] });
  check('范围选择限制为500项', (await page.locator('.toolbar.selecting strong').textContent()) === '500');
  check('超出500项给出提示', await page.getByText('每批最多选择 500 项', { exact: true }).count() > 0);
  await page.getByRole('button', { name: '清空', exact: true }).click();
  await scrollToImage(page, 2000);
  const listRequests = [];
  const trackList = (request) => { if (/\/packages\/[^/]+\/images\?/.test(request.url())) listRequests.push(request.url()); };
  page.on('request', trackList);
  await page.locator('.images [aria-posinset="2001"] .card-hit').click({ modifiers: ['Shift'] });
  await delay(150);
  check('跨缺页只选连续已缓存项', Number(await page.locator('.toolbar.selecting strong').textContent()) < 100);
  check('范围选择不枚举未载入页', listRequests.length === 0);
  page.off('request', trackList);
  await page.getByRole('button', { name: '完成', exact: true }).click();
  const motion = groups.find((item) => item.name.includes('动图'));
  await page.goto(`${base}#/l/${lib.id}/g/${motion.id}`);
  await settled(page);
  await page.locator('.thumb-error').waitFor();
  check('坏图原因与重试在原格显示', await page.locator('.thumb-error button').count() === 1 && await page.locator('.image-card').filter({ hasText: '06-broken.jpg' }).count() === 1);
  check('墙内图片只使用静态缩略图', await page.locator('.image-card img').evaluateAll((items) => items.every((item) => item.src.startsWith('blob:'))));
  await snapshot(page, 'B-images-errors');
}

async function viewReady(page) {
  await page.waitForFunction(() => {
    const img = document.querySelector('.viewer .frame:not(.pending):not(.stale):not(.placeholder) img');
    return img?.complete && img.naturalWidth > 0 && !document.querySelector('.viewer-loading');
  });
}

async function viewing(page, base, lib, groups) {
  const group = groups.find((item) => item.name.includes('动图'));
  const pkg = (await get(`/api/v1/groups/${group.id}/packages`)).items[0];
  const images = (await get(`/api/v1/packages/${pkg.id}/images`)).items;
  const hash = `#/l/${lib.id}/g/${group.id}/p/${pkg.id}`;
  for (const name of ['01-gif.gif', '02-webp.webp']) {
    const image = images.find((item) => item.name === name);
    await page.goto(`${base}${hash}/i/${image.id}`);
    await viewReady(page);
    check(`${name} 使用原图`, await page.locator('.viewer .frame:not(.pending):not(.placeholder):not(.stale) img').getAttribute('src').then((src) => src.includes('/original')));
    await page.waitForFunction(async () => {
      const img = document.querySelector('.viewer .frame:not(.pending):not(.placeholder):not(.stale) img');
      const canvas = document.createElement('canvas');
      canvas.width = canvas.height = 1;
      const context = canvas.getContext('2d');
      context.drawImage(img, 0, 0, 1, 1);
      const first = String(context.getImageData(0, 0, 1, 1).data);
      await new Promise((resolve) => setTimeout(resolve, 300));
      context.drawImage(img, 0, 0, 1, 1);
      return first !== String(context.getImageData(0, 0, 1, 1).data);
    });
    check(`${name} 实际像素变化`, true);
  }
  const alpha = images.find((item) => item.name === '03-alpha.png');
  await page.goto(`${base}${hash}/i/${alpha.id}`);
  await viewReady(page);
  check('查看器顶栏52px', await page.locator('.viewer-bar').evaluate((el) => Math.round(el.getBoundingClientRect().height) === 52));
  check('查看器包含图包和第N/M张', await page.locator('.viewer-sub').textContent().then((text) => text.includes('动图合集') && text.includes('第 3 / 7 张')));
  check('透明图棋盘仅在图像区域', await page.locator('.frame.checker:not(.pending)').evaluate((el) => {
    const rect = el.getBoundingClientRect(), img = el.querySelector('img').getBoundingClientRect();
    return getComputedStyle(el).backgroundImage.includes('conic-gradient') && rect.width === img.width && rect.height === img.height;
  }));
  await page.getByRole('button', { name: '图片信息', exact: true }).click();
  check('图片信息图标统一', await page.getByRole('button', { name: '图片信息', exact: true }).getAttribute('aria-pressed') === 'true');
  const strip = page.getByRole('button', { name: '胶片条', exact: true });
  if (await strip.getAttribute('aria-pressed') !== 'true') await strip.click();
  await page.locator('.film-cell[aria-current="true"]').waitFor();
  check('胶片条当前项有2px描边', await page.locator('.film-cell.active').evaluate((el) => getComputedStyle(el, '::after').boxShadow.includes('2px')));
  await snapshot(page, 'C-alpha-desktop');
  await page.setViewportSize({ width: 390, height: 844 });
  await viewReady(page);
  await snapshot(page, 'C-alpha-narrow');
  check('窄屏查看器无横向溢出', await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.keyboard.press('Escape');
  await page.locator('.viewer').waitFor({ state: 'detached' });
  await settled(page);
  await page.waitForFunction((id) => document.activeElement?.closest('[data-resource-id]')?.getAttribute('data-resource-id') === id, alpha.id);
  check('退出查看器焦点回到刚看图片', true);
  await page.setViewportSize({ width: 1440, height: 1000 });
  const wide = images.find((item) => item.name === '04-wide.jpg');
  await page.getByRole('button', { name: wide.name, exact: true }).click();
  await viewReady(page);
  check('JPEG没有棋盘', await page.locator('.frame.checker').count() === 0);
  await page.keyboard.press('1');
  check('100%按CSS像素显示', await page.locator('.zoom-level').textContent().then((text) => text === '100%'));
  await page.keyboard.press('r');
  check('临时旋转保留', await page.locator('.frame:not(.pending)').last().getAttribute('style').then((style) => style.includes('rotate(90deg)')));
  await page.keyboard.press('0');
  await page.keyboard.press('Home');
  await page.waitForFunction((id) => location.hash.endsWith(`/i/${id}`), images[0].id);
  await viewReady(page);
  await page.keyboard.press('ArrowLeft');
  check('包头不跨包', page.url().endsWith(`/i/${images[0].id}`));
  await page.keyboard.press('End');
  await page.waitForFunction((id) => location.hash.endsWith(`/i/${id}`), images.at(-1).id);
  await viewReady(page);
  await page.keyboard.press('ArrowRight');
  check('包尾不跨包', page.url().endsWith(`/i/${images.at(-1).id}`));
  await page.reload();
  await viewReady(page);
  check('刷新恢复同一图片', page.url().endsWith(`/i/${images.at(-1).id}`));
  const broken = images.find((item) => item.name === '06-broken.jpg');
  await page.goto(`${base}${hash}/i/${broken.id}`);
  await page.locator('.viewer-failure').waitFor();
  check('坏图查看器可原地重试', await page.locator('.viewer-failure').getByRole('button', { name: '重试', exact: true }).count() === 1);
  await page.keyboard.press('ArrowRight');
  await viewReady(page);
  check('坏图后仍可包内导航', page.url().endsWith(`/i/${images.at(-1).id}`));
  await page.keyboard.press('Escape');
  await page.locator('.viewer').waitFor({ state: 'detached' });
  await page.getByRole('button', { name: images.at(-1).name, exact: true }).click();
  await viewReady(page);
  await page.keyboard.press('Escape');
  await page.locator('.viewer').waitFor({ state: 'detached' });
  await page.goForward();
  await viewReady(page);
  await page.keyboard.press('Escape');
  await page.locator('.viewer').waitFor({ state: 'detached' });
  check('前进后关闭仍返回正确图片墙', page.url().endsWith(`/p/${pkg.id}`));
}

try {
  const library = path.join(temporary, 'library');
  const generator = launch(path.join(project, '.venv/Scripts/python.exe'), ['scripts/demo_ui_library.py', library, '--large-count', only && ['C', 'E'].includes(stage) ? '620' : '8120'], 'fixture');
  await new Promise((resolve, reject) => { generator.once('error', reject); generator.once('exit', (code) => code ? reject(new Error(`Fixture exited ${code}`)) : resolve()); });
  const ready = path.join(temporary, 'ready.json');
  const backend = launch(path.join(project, '.venv/Scripts/python.exe'), ['-m', 'gallery', '--data', path.join(temporary, 'data'), '--port', '0', '--ready-file', ready, '--no-watch', '--no-scan', '--no-open'], 'backend');
  for (let attempt = 0; attempt < 300; attempt++) {
    assert.equal(backend.exitCode, null, 'Backend exited');
    try { backendUrl = JSON.parse(await readFile(ready, 'utf8')).url; break; }
    catch (error) { if (!['ENOENT', 'EACCES', 'EPERM'].includes(error.code)) throw error; }
    await delay(100);
  }
  assert.ok(backendUrl, 'Backend handshake');
  const response = await fetch(backendUrl + '/api/v1/libraries', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: library, name: '临时工作台验收' }) });
  assert.equal(response.status, 201);
  const lib = await response.json();
  for (let attempt = 0; attempt < 400; attempt++) {
    const tasks = await get('/api/v1/tasks');
    const scan = tasks.items.find((task) => task.kind === 'scan' && task.payload.library_id === lib.id);
    if (scan?.state === 'completed') break;
    if (scan?.state === 'failed') throw new Error(scan.error);
    await delay(100);
  }
  process.env.GALLERY_BACKEND = backendUrl;
  process.env.GALLERY_UI_PORT = '0';
  server = await createServer({ configFile: path.join(project, 'ui/vite.config.mts') });
  await server.listen();
  const base = server.resolvedUrls.local[0];
  browser = await chromium.launch({ channel: 'msedge', headless: true });
  page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' });
  const groups = (await get(`/api/v1/libraries/${lib.id}/groups`)).items;
  const group = groups.find((item) => item.name === '山色');
  assert.ok(group);
  if (!only || stage === 'A1') await framework(page, base, lib, group);
  if ((!only && stage !== 'A1') || stage === 'B') await browsing(page, base, lib, groups);
  if ((!only && !['A1', 'B'].includes(stage)) || stage === 'C') await viewing(page, base, lib, groups);
  if ((!only && !['A1', 'B', 'C'].includes(stage)) || stage === 'D') await decisions(page, { base, lib, groups, library, temporary, project, launch, get, check, snapshot: (page, name) => snapshot(page, name) });
  if (!['A1', 'B', 'C', 'D'].includes(stage)) await states(page, { base, lib, groups, get, check, snapshot: (page, name) => snapshot(page, name) });
  await writeFile(path.join(output, 'result.json'), JSON.stringify({ checks, count: checks.length, temporary }, null, 2));
  console.log(`PASS ${checks.length} checks; screenshots ${output}; temporary ${temporary}`);
} catch (error) {
  if (page) {
    await snapshot(page, 'failure');
    const state = await page.evaluate(async () => {
      const app = await import('/src/state/app.ts');
      const router = await import('/src/lib/router.ts');
      return {
        route: router.route.value, lastViewed: app.lastViewed.value,
        cards: [...document.querySelectorAll('.image-card')].map((card) => ({ name: card.textContent, class: card.className })),
        grids: [...document.querySelectorAll('.vgrid')].map((grid) => ({ top: grid.scrollTop, height: grid.clientHeight, scrollHeight: grid.scrollHeight })),
      };
    });
    await writeFile(path.join(output, 'failure.json'), JSON.stringify({ error: String(error), checks, state }, null, 2));
  }
  throw error;
} finally {
  await browser?.close();
  if (backendUrl) await fetch(backendUrl + '/api/v1/system/shutdown', { method: 'POST', headers: { 'x-gallery-desktop': desktopToken }, signal: AbortSignal.timeout(5000) }).catch(() => undefined);
  await server?.close();
  for (const child of children.reverse()) {
    if (child.exitCode === null && child.signalCode === null) {
      const exited = new Promise((resolve) => child.once('exit', resolve));
      child.kill();
      await exited;
    }
  }
}
