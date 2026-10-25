import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { setTimeout as delay } from 'node:timers/promises';
import { chromium } from 'playwright-core';
import { createServer } from 'vite';

const project = fileURLToPath(new URL('../../', import.meta.url));
const output = path.join(project, 'output/ui-qa', `review-${Date.now()}`);
await mkdir(output, { recursive: true });
const server = await createServer({ configFile: path.join(project, 'ui/vite.config.mts'), server: { port: 0 }, plugins: [{
  name: 'isolated-mock-api',
  configureServer(server) {
    // Requests racing context disposal must never fall through to a locally configured backend.
    server.middlewares.use('/api', (_request, response) => {
      response.writeHead(503, { 'Content-Type': 'application/json' });
      response.end(JSON.stringify({ error: { code: 'mock_only', message: 'Mock API only' } }));
    });
  },
}] });
let browser;
const results = [];
const total = 8120;
const savedImage = 7900;
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII=', 'base64');
const library = { id: 'review-lib', name: 'Review library', path: 'C:\\synthetic-review', online: true, scan_status: 'ready', revision: 1, last_scan: null };
const group = { id: 'review-group', library_id: library.id, name: 'Review group', rel: 'group', state: 'none', category: '其他', image_count: total, bytes: total * 100, cover_id: null };
const pkg = { id: 'review-package', library_id: library.id, group_id: group.id, name: 'Review package', rel: 'group/package', loose: false, image_count: total, cover_id: null };
const anchorKey = `images:${pkg.id}`;
const wallHash = `#/l/${library.id}/g/${group.id}/p/${pkg.id}`;
const image = (index) => ({ id: `review-image-${index}`, library_id: library.id, group_id: group.id, package_id: pkg.id,
  name: `image-${String(index).padStart(5, '0')}.png`, rel: `group/package/image-${index}.png`, size: 100, width: 1, height: 1,
  animated: false, error: null, version: 'v1' });
const paged = (items, count = items.length, offset = 0, limit = 100) => ({ items, total: count, offset, limit, revision: 1 });

async function openPage(base, { desktop = false, anchor, latency = 0, contextDelay = 0, groupCount = 1, packageCount = 1 } = {}) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' });
  const page = await context.newPage();
  page.setDefaultTimeout(15000);
  const errors = [];
  const listRequests = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.addInitScript(({ desktop, anchor, anchorKey }) => {
    window.EventSource = class { static CLOSED = 2; readyState = 1; addEventListener() {} close() {} };
    window.__qaThemeChanges = [];
    new MutationObserver(() => window.__qaThemeChanges.push(document.documentElement.dataset.theme ?? null))
      .observe(document, { subtree: true, attributes: true, attributeFilter: ['data-theme'] });
    if (!sessionStorage.getItem('qa.seeded')) {
      if (anchor !== undefined) localStorage.setItem('gt.anchors', JSON.stringify([[anchorKey, anchor]]));
      sessionStorage.setItem('qa.seeded', '1');
    }
    if (desktop) {
      window.galleryApp = {
        isElectron: true,
        sessionId: sessionStorage.getItem('qa.hostSession') || 'desktop-a',
        theme: 'dark',
        loadPreferences: async () => {
          sessionStorage.setItem('qa.preferenceLoads', String(Number(sessionStorage.getItem('qa.preferenceLoads') || 0) + 1));
          return { 'gt.theme': 'dark', 'gt.tileSize': 'm', 'gt.inspector': '0' };
        },
      };
    }
  }, { desktop, anchor, anchorKey });
  let position = image(savedImage).id;
  let imageOrder = Array.from({ length: total }, (_, index) => index);
  let imageRevision = 1;
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const endpoint = url.pathname;
    let data;
    if (endpoint === '/api/v1/libraries') data = paged([library]);
    else if (endpoint === '/api/v1/tasks') data = paged([]);
    else if (endpoint === '/api/v1/cache') data = { bytes: 0, limit: 12 * 1024 ** 3 };
    else if (endpoint === `/api/v1/libraries/${library.id}/groups`) {
      const offset = Number(url.searchParams.get('offset') || 0), limit = Number(url.searchParams.get('limit') || 100);
      data = paged(Array.from({ length: Math.min(limit, groupCount - offset) }, (_, at) => offset + at === 0 ? group
        : { ...group, id: `group-${offset + at}`, name: `Group ${offset + at}` }), groupCount, offset, limit);
    }
    else if (endpoint === `/api/v1/groups/${group.id}`) data = group;
    else if (endpoint === `/api/v1/groups/${group.id}/review`) data = { group_id: group.id, state: 'none', image_id: position };
    else if (endpoint === `/api/v1/groups/${group.id}/position` && request.method() === 'PUT') {
      position = request.postDataJSON().image_id;
      data = { group_id: group.id, state: 'none', image_id: position };
    } else if (endpoint === `/api/v1/groups/${group.id}/packages`) {
      const offset = Number(url.searchParams.get('offset') || 0), limit = Number(url.searchParams.get('limit') || 100);
      data = paged(Array.from({ length: Math.min(limit, packageCount - offset) }, (_, at) => offset + at === 0 ? pkg
        : { ...pkg, id: `package-${offset + at}`, name: `Package ${offset + at}` }), packageCount, offset, limit);
    }
    else if (endpoint === `/api/v1/packages/${pkg.id}`) data = pkg;
    else if (endpoint === `/api/v1/packages/${pkg.id}/images`) {
      const offset = Number(url.searchParams.get('offset') || 0), limit = Number(url.searchParams.get('limit') || 100);
      listRequests.push(offset);
      if (latency) await delay(latency);
      data = { ...paged(imageOrder.slice(offset, offset + limit).map(image), imageOrder.length, offset, limit), revision: imageRevision };
    } else {
      const match = endpoint.match(/^\/api\/v1\/images\/review-image-(\d+)\/(context|thumbnail|original)$/);
      if (match) {
        const index = Number(match[1]);
        if (match[2] !== 'context') return route.fulfill({ contentType: 'image/png', body: png });
        if (contextDelay) await delay(contextDelay);
        data = { image: image(index), index, total, previous_id: index ? image(index - 1).id : null, next_id: index < total - 1 ? image(index + 1).id : null };
      }
    }
    if (data === undefined) {
      errors.push(`Unexpected API request: ${request.method()} ${endpoint}`);
      return route.fulfill({ status: 500, json: { detail: 'Unexpected review API request' } });
    }
    await route.fulfill({ json: data });
  });
  await page.goto(base + wallHash);
  await page.locator('.image-card').first().waitFor();
  const reorderImages = async (update) => {
    imageOrder = update(imageOrder);
    imageRevision++;
    await page.evaluate(async (packageId) => {
      const app = await import('/src/state/app.ts');
      app.imagesList(packageId).invalidate();
    }, pkg.id);
  };
  return { context, page, errors, listRequests, reorderImages };
}

async function test(name, options, run) {
  const { context, page, errors, listRequests, reorderImages } = await openPage(server.resolvedUrls.local[0], options);
  try {
    await run(page, { listRequests, reorderImages });
    assert.deepEqual(errors, [], 'No browser errors or unexpected API requests');
    results.push({ name, passed: true });
    console.log(`PASS ${name}`);
  } catch (error) {
    results.push({ name, passed: false, error: error.stack ?? String(error) });
    await page.screenshot({ path: path.join(output, `${name}-failure.png`) });
    console.error(`FAIL ${name}: ${error.stack ?? error}`);
  } finally { await context.close(); }
}

async function visibleIndices(page) {
  return page.locator('.images .vgrid').evaluate((grid) => {
    const bounds = grid.getBoundingClientRect();
    return [...grid.querySelectorAll('[aria-posinset]')].filter((cell) => {
      const rect = cell.getBoundingClientRect();
      return rect.bottom > bounds.top && rect.top < bounds.bottom;
    }).map((cell) => Number(cell.getAttribute('aria-posinset')) - 1);
  });
}

async function waitVisible(page, index) {
  await page.waitForFunction((at) => {
    const grid = document.querySelector('.images .vgrid');
    const cell = grid?.querySelector(`[aria-posinset="${at + 1}"] .card-hit`);
    if (!cell) return false;
    const rect = cell.getBoundingClientRect(), bounds = grid.getBoundingClientRect();
    return rect.bottom > bounds.top && rect.top < bounds.bottom;
  }, index);
}

async function scrollTo(page, index) {
  await page.locator('.images .vgrid').evaluate((grid, at) => {
    const cells = [...grid.querySelectorAll('.vgrid-cell')];
    const first = cells[0].getBoundingClientRect();
    const columns = cells.filter((cell) => Math.abs(cell.getBoundingClientRect().top - first.top) < 1).length;
    const next = cells.find((cell) => cell.getBoundingClientRect().top > first.top + 1);
    grid.scrollTop = Math.floor(at / columns) * (next.getBoundingClientRect().top - first.top);
  }, index);
  await waitVisible(page, index);
  await page.waitForFunction(({ key, at }) => {
    const anchor = new Map(JSON.parse(localStorage.getItem('gt.anchors') || '[]')).get(key);
    return anchor !== undefined && Math.abs(anchor - at) < 10;
  }, { key: anchorKey, at: index });
}

try {
  await server.listen();
  browser = await chromium.launch({ channel: 'msedge', headless: true });
  for (const eventName of ['load', 'error']) {
    await test(`thumbnail-stale-${eventName}`, { anchor: 0 }, async (page) => {
      await page.getByRole('radio', { name: '大', exact: true }).click();
      await page.setViewportSize({ width: 390, height: 844 });
      const thumbnail = page.locator(`.images [data-resource-id="${image(0).id}"] .thumb`);
      await page.waitForFunction(() => document.querySelector('.images [data-resource-id="review-image-0"] .thumb')?.classList.contains('is-ready'));
      await page.evaluate(() => { window.__qaPreviousThumb = document.querySelector('.images [data-resource-id="review-image-0"] .thumb img'); });
      const oldSource = await thumbnail.locator('img').getAttribute('src');
      // This layout changes the same card from a 400px to an 800px resource.
      await page.setViewportSize({ width: 870, height: 1000 });
      await page.waitForFunction((previous) => {
        const thumb = document.querySelector('.images [data-resource-id="review-image-0"] .thumb');
        const image = thumb?.querySelector('img');
        return thumb?.classList.contains('is-ready') && image?.getAttribute('src') !== previous && image?.naturalWidth > 0;
      }, oldSource);
      const currentSource = await thumbnail.locator('img').getAttribute('src');
      // A queued event from the previous resource must not overwrite the current card.
      await page.evaluate((name) => window.__qaPreviousThumb.dispatchEvent(new Event(name)), eventName);
      await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
      assert.ok(await thumbnail.evaluate((element) => element.classList.contains('is-ready')));
      assert.equal(await thumbnail.locator('img').getAttribute('src'), currentSource);
      await page.evaluate(() => { window.__qaPreviousThumb = null; });
    });
  }
  await test('desktop-preferences', { desktop: true }, async (page) => {
    await page.getByRole('button', { name: '外观', exact: true }).click();
    await page.getByRole('menuitemradio', { name: '浅色', exact: true }).click();
    await page.getByRole('radio', { name: '小', exact: true }).click();
    await page.reload();
    await page.locator('.image-card').first().waitFor();
    assert.deepEqual(await page.evaluate(() => [document.documentElement.dataset.theme, localStorage.getItem('gt.tileSize')]), ['light', 's']);
    assert.equal(await page.evaluate(() => window.__qaThemeChanges[0]), 'light', 'Reload must apply the current theme before bootstrap');
    assert.equal(await page.evaluate(() => sessionStorage.getItem('qa.preferenceLoads')), '1');
    await page.getByRole('button', { name: '外观', exact: true }).click();
    await page.getByRole('menuitemradio', { name: '跟随系统', exact: true }).click();
    await page.reload();
    await page.locator('.image-card').first().waitFor();
    assert.equal(await page.evaluate(() => document.documentElement.dataset.theme ?? null), null);
    await page.evaluate(() => sessionStorage.setItem('qa.hostSession', 'desktop-b'));
    await page.reload();
    await page.locator('.image-card').first().waitFor();
    assert.deepEqual(await page.evaluate(() => [document.documentElement.dataset.theme, localStorage.getItem('gt.tileSize')]), ['dark', 'm']);
    assert.equal(await page.evaluate(() => window.__qaThemeChanges[0]), 'dark', 'A new desktop session must apply its saved theme before bootstrap');
    assert.equal(await page.evaluate(() => sessionStorage.getItem('qa.preferenceLoads')), '2');
  });
  await test('escape-layers', { anchor: 0 }, async (page) => {
    const select = async () => {
      await page.getByRole('button', { name: '选择', exact: true }).click();
      await page.locator('.image-card .card-hit').first().click();
    };
    const selected = async () => assert.equal(await page.locator('.toolbar.selecting strong').textContent(), '1');
    await select();
    await page.getByRole('button', { name: '后台任务', exact: true }).click();
    await page.locator('.drawer[open]').waitFor();
    await page.getByRole('button', { name: '外观', exact: true }).focus();
    await page.keyboard.press('Enter');
    await page.keyboard.press('Escape');
    assert.equal(await page.getByRole('menu').count(), 0);
    assert.equal(await page.locator('.drawer[open]').count(), 1);
    await selected();
    await page.keyboard.press('Escape');
    await page.locator('.drawer').waitFor({ state: 'detached' });
    await selected();
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('.toolbar.selecting').count(), 0);
    await select();
    await page.getByRole('button', { name: '信息', exact: true }).click();
    await page.locator('.inspector[open]').waitFor();
    await page.keyboard.press('Escape');
    await page.locator('.inspector').waitFor({ state: 'detached' });
    await selected();
    await page.getByRole('button', { name: '删除…', exact: true }).click();
    await page.getByRole('dialog', { name: '确认删除', exact: true }).waitFor();
    await page.keyboard.press('Escape');
    assert.equal(await page.getByRole('dialog', { name: '确认删除', exact: true }).count(), 0);
    await selected();
    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByRole('button', { name: '后台任务', exact: true }).click();
    await page.locator('.drawer:modal').waitFor();
    await page.keyboard.press('Escape');
    await page.locator('.drawer').waitFor({ state: 'detached' });
    await selected();
    await page.screenshot({ path: path.join(output, 'selection-narrow.png') });
  });
  await test('wall-anchor', { anchor: 1000 }, async (page) => {
    await waitVisible(page, 1000);
    assert.ok(!(await visibleIndices(page)).includes(savedImage));
    await page.reload();
    await waitVisible(page, 1000);
    await page.goto(new URL(wallHash + `/i/${image(savedImage).id}`, page.url()).href);
    await page.waitForFunction(() => document.querySelector('.viewer img.layer')?.naturalWidth > 0);
    await page.keyboard.press('Escape');
    await page.locator('.viewer').waitFor({ state: 'detached' });
    await waitVisible(page, savedImage);
    await page.waitForFunction((id) => document.activeElement?.closest('[data-resource-id]')?.getAttribute('data-resource-id') === id, image(savedImage).id);
    await scrollTo(page, 1000);
    const before = (await visibleIndices(page))[0];
    await page.setViewportSize({ width: 390, height: 844 });
    await waitVisible(page, before);
    await page.screenshot({ path: path.join(output, 'anchor-narrow.png') });
    await page.setViewportSize({ width: 1440, height: 1000 });
    await waitVisible(page, before);
    await page.getByRole('button', { name: library.name, exact: true }).first().click();
    await page.locator('.group-card .card-hit').click();
    await waitVisible(page, before);
    await page.reload();
    await waitVisible(page, before);
    await page.screenshot({ path: path.join(output, 'anchor-desktop.png') });
  });
  await test('initial-resume', {}, async (page) => { await waitVisible(page, savedImage); });
  await test('quick-return-after-history', { anchor: 0, contextDelay: 400 }, async (page) => {
    await page.locator('.images [aria-posinset="1"] .card-hit').focus();
    await page.keyboard.press('Enter');
    await page.waitForFunction(() => document.querySelector('.viewer-name')?.textContent === 'image-00000.png');
    await page.keyboard.press('Escape');
    await page.locator('.viewer').waitFor({ state: 'detached' });
    await page.locator('.images [aria-posinset="8"] .card-hit').focus();
    await page.keyboard.press('Enter');
    await page.locator('.viewer').waitFor();
    await page.keyboard.press('Escape');
    await page.locator('.viewer').waitFor({ state: 'detached' });
    await page.waitForFunction(() => document.activeElement?.closest('[aria-posinset]')?.getAttribute('aria-posinset') === '8');
  });
  for (const width of [1440, 390]) {
    await test(`keyboard-wall-${width}`, { anchor: 0, latency: 80 }, async (page, { listRequests }) => {
      await page.setViewportSize({ width, height: 844 });
      const focusAt = async (index) => page.locator(`.images [aria-posinset="${index + 1}"] .card-hit`).focus();
      const focusedAt = async (index) => {
        try {
          await page.waitForFunction((at) => document.activeElement?.closest('[aria-posinset]')?.getAttribute('aria-posinset') === String(at + 1), index);
        } catch (error) {
          const active = await page.evaluate(() => document.activeElement?.outerHTML.slice(0, 350));
          throw new Error(`Expected keyboard focus at ${index}; active=${active}`, { cause: error });
        }
      };
      await focusAt(0);
      assert.equal(await page.locator('.images .card-hit[tabindex="0"]').count(), 1);
      const tracks = await page.locator('.images .vgrid').evaluate((grid) => {
        const cells = [...grid.querySelectorAll('.vgrid-cell')];
        const top = cells[0].getBoundingClientRect().top;
        const columns = cells.filter((cell) => Math.abs(cell.getBoundingClientRect().top - top) < 1).length;
        const next = cells.find((cell) => cell.getBoundingClientRect().top > top + 1);
        const rowHeight = next.getBoundingClientRect().top - top;
        return { columns, page: columns * Math.max(1, Math.floor(grid.clientHeight / rowHeight)) };
      });
      for (const [key, index] of [['ArrowDown', tracks.columns], ['ArrowUp', 0], ['PageDown', tracks.page], ['PageUp', 0]]) {
        await page.keyboard.press(key);
        await focusedAt(index);
      }
      const before = listRequests.length;
      await page.keyboard.press('End');
      await focusedAt(total - 1);
      assert.ok(listRequests.slice(before).every((offset) => offset >= 8000), 'End must fetch the destination directly');
      for (const key of ['ArrowRight', 'ArrowDown', 'PageDown']) {
        await page.keyboard.press(key);
        await focusedAt(total - 1);
      }
      await page.keyboard.press('Home');
      await focusedAt(0);
      for (let index = 0; index < 125; index++) await page.keyboard.press('ArrowRight');
      await focusedAt(125);
      assert.ok(await page.locator('.images .vgrid-cell').count() < 100, 'Keyboard navigation must keep DOM bounded');
      await page.setViewportSize({ width: width === 390 ? 1440 : 390, height: 844 });
      await focusedAt(125);
      await page.keyboard.press('Home');
      await focusedAt(0);
      await page.keyboard.press('Space');
      await page.keyboard.press('ArrowRight');
      await focusedAt(1);
      await page.keyboard.press('ArrowRight');
      await focusedAt(2);
      await page.keyboard.press('Shift+Space');
      assert.equal(await page.locator('.toolbar.selecting strong').textContent(), '3');
      await page.keyboard.press('Enter');
      await page.locator('.viewer').waitFor();
      await page.keyboard.press('Escape');
      await page.locator('.viewer').waitFor({ state: 'detached' });
      await focusedAt(2);
      await page.keyboard.press('Escape');
      await page.locator('.toolbar.selecting').waitFor({ state: 'detached' });
      await page.getByRole('button', { name: '更多操作', exact: true }).click();
      await page.keyboard.press('End');
      assert.ok(await page.getByRole('menu').evaluate((menu) => menu.contains(document.activeElement)));
      await page.keyboard.press('Escape');
      await page.screenshot({ path: path.join(output, `keyboard-${width}.png`) });
    });
    await test(`keyboard-revision-${width}`, { anchor: 0 }, async (page, { reorderImages }) => {
      await page.setViewportSize({ width, height: 844 });
      const target = page.locator(`.images [data-resource-id="${image(10).id}"] .card-hit`);
      await target.focus();
      // A scan inserts ahead of the focused resource without replacing its keyed DOM node.
      await reorderImages((order) => [total, ...order]);
      await page.waitForFunction((id) => {
        const cell = document.activeElement?.closest('[data-grid-index]');
        return cell?.getAttribute('data-resource-id') === id && cell.getAttribute('data-grid-index') === '11';
      }, image(10).id);
      await page.keyboard.press('ArrowRight');
      await page.waitForFunction((id) => document.activeElement?.closest('[data-resource-id]')?.getAttribute('data-resource-id') === id, image(11).id);
      // Removing two preceding entries moves the focused resource back; Left must use its new index.
      await reorderImages((order) => order.slice(2));
      await page.waitForFunction((id) => {
        const cell = document.activeElement?.closest('[data-grid-index]');
        return cell?.getAttribute('data-resource-id') === id && cell.getAttribute('data-grid-index') === '10';
      }, image(11).id);
      await page.keyboard.press('ArrowLeft');
      await page.waitForFunction((id) => document.activeElement?.closest('[data-resource-id]')?.getAttribute('data-resource-id') === id, image(10).id);
      // A reorder crosses rendered row boundaries, then a column change must retain the same ID.
      await reorderImages((order) => [...order.slice(0, 30).reverse(), ...order.slice(30)]);
      await page.waitForFunction((id) => {
        const cell = document.activeElement?.closest('[data-grid-index]');
        return cell?.getAttribute('data-resource-id') === id && cell.getAttribute('data-grid-index') === '20';
      }, image(10).id);
      await page.setViewportSize({ width: width === 390 ? 1440 : 390, height: 844 });
      await page.waitForFunction((id) => document.activeElement?.closest('[data-resource-id]')?.getAttribute('data-resource-id') === id, image(10).id);
      await page.keyboard.press('ArrowRight');
      await page.waitForFunction((id) => document.activeElement?.closest('[data-resource-id]')?.getAttribute('data-resource-id') === id, image(9).id);
      assert.equal(await page.locator('.images .card-hit[tabindex="0"]').count(), 1);
      assert.ok(await page.locator('.images .vgrid-cell').count() < 100);
    });
  }
  await test('keyboard-resources', { anchor: 0, groupCount: 106, packageCount: 106 }, async (page) => {
    await page.goto(new URL(`#/l/${library.id}`, page.url()).href);
    await page.locator('.content .group-card .card-hit').first().focus();
    await page.keyboard.press('End');
    await page.waitForFunction(() => document.activeElement?.closest('[aria-posinset]')?.getAttribute('aria-posinset') === '106');
    assert.equal(await page.locator('.content .card-hit[tabindex="0"]').count(), 1);
    await page.locator('.group-list .group-row').first().focus();
    await page.keyboard.press('End');
    await page.waitForFunction(() => document.activeElement?.closest('.group-list [aria-posinset]')?.getAttribute('aria-posinset') === '106');
    await page.keyboard.press('ArrowUp');
    await page.waitForFunction(() => document.activeElement?.closest('.group-list [aria-posinset]')?.getAttribute('aria-posinset') === '105');
    await page.goto(new URL(`#/l/${library.id}/g/${group.id}`, page.url()).href);
    await page.locator('.package-card .card-hit').first().focus();
    await page.keyboard.press('End');
    await page.waitForFunction(() => document.activeElement?.closest('[aria-posinset]')?.getAttribute('aria-posinset') === '106');
    assert.equal(await page.locator('.content .card-hit[tabindex="0"]').count(), 1);
  });
  await writeFile(path.join(output, 'result.json'), JSON.stringify(results, null, 2));
  assert.ok(results.every((result) => result.passed), `${results.filter((result) => !result.passed).length} regression scenarios failed`);
  console.log(`Reports: ${output}`);
} finally {
  await browser?.close();
  await server.close();
}
