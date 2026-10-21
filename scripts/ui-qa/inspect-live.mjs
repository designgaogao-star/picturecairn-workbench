import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { chromium } from 'playwright-core';

const [base, packageId, output = 'output/playwright/live'] = process.argv.slice(2);
assert.ok(base && packageId, 'Usage: node scripts/ui-qa/inspect-live.mjs <base URL> <non-R18 package ID> [output]');
assert.equal(new URL(base).hostname, '127.0.0.1');
const get = async (route) => {
  const response = await fetch(base + route);
  assert.ok(response.ok, route);
  return response.json();
};
const pkg = await get('/api/v1/packages/' + packageId);
const group = await get('/api/v1/groups/' + pkg.group_id);
assert.equal(group.category, '非R18', 'Real-library inspection only opens explicitly non-R18 folders');
const tail = await get(`/api/v1/packages/${packageId}/images?offset=${pkg.image_count - 1}&limit=1`);
assert.equal(tail.total, pkg.image_count);
const last = tail.items[0];
const context = await get(`/api/v1/images/${last.id}/context`);
assert.equal(context.index, pkg.image_count - 1);
assert.equal(context.next_id, null);
await mkdir(output, { recursive: true });

const browser = await chromium.launch({ channel: 'msedge', headless: true });
const errors = [], writes = [], pages = [], measurements = [];
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  page.on('pageerror', (error) => errors.push(error.message));
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    if (request.method() !== 'GET') { writes.push(request.method()); await route.abort(); return; }
    if (new URL(request.url()).pathname.endsWith('/images')) {
      const query = new URL(request.url()).searchParams;
      const limit = Number(query.get('limit') || 100);
      assert.ok(limit <= 500);
      pages.push({ offset: Number(query.get('offset') || 0), limit });
    }
    await route.continue();
  });
  await page.addInitScript(() => {
    localStorage.setItem('gt.groupFilter', JSON.stringify({ state: '', category: '非R18' }));
  });
  await page.goto(`${base}#/l/${pkg.library_id}/g/${pkg.group_id}/p/${pkg.id}`);
  const ready = () => page.waitForFunction(() => {
    const bounds = document.querySelector('.image-wall .vgrid')?.getBoundingClientRect();
    if (!bounds) return false;
    const visible = [...document.querySelectorAll('.image-card')].filter((card) => {
      const rect = card.getBoundingClientRect();
      return rect.bottom > bounds.top && rect.top < bounds.bottom;
    });
    return visible.length > 0 && visible.every((card) => {
      const image = card.querySelector('.is-ready img');
      return image?.complete && image.naturalWidth > 0 || card.querySelector('.thumb-error');
    });
  });
  const capture = async (name) => {
    await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await ready();
    const measured = await page.evaluate(() => {
      const grid = document.querySelector('.image-wall .vgrid');
      return { cards: document.querySelectorAll('.image-card').length,
        nodes: document.querySelectorAll('*').length, overflow: document.documentElement.scrollWidth > innerWidth,
        scroll_ratio: grid.scrollTop / (grid.scrollHeight - grid.clientHeight) };
    });
    assert.equal(measured.overflow, false);
    assert.ok(measured.cards > 0 && measured.cards < 160, 'Wall DOM must stay bounded');
    measurements.push({ name, ...measured });
    console.log(JSON.stringify({ stage: name, ...measured }));
    await page.addStyleTag({ content: 'img { filter: blur(32px) !important; transition: none !important; }' });
    assert.match(await page.locator('.image-card img').first().evaluate((image) => getComputedStyle(image).filter), /blur\(32px\)/);
    await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await page.screenshot({ path: path.join(output, name + '.png'), animations: 'disabled' });
  };
  const scroll = (fraction) => page.locator('.image-wall .vgrid').evaluate((element, value) => {
    element.scrollTop = (element.scrollHeight - element.clientHeight) * value;
  }, fraction);
  await capture('live-desktop-top');
  await scroll(.5);
  await page.waitForFunction(() => document.querySelector('.image-wall .vgrid')?.scrollTop > 1000);
  await capture('live-desktop-middle');
  await scroll(1);
  await page.getByRole('button', { name: last.name, exact: true }).waitFor();
  await capture('live-desktop-end');
  await page.waitForFunction((id) => JSON.parse(localStorage.getItem('gt.anchors') || '[]')
    .some(([key, index]) => key === `images:${id}` && index > 1000), pkg.id);
  await page.reload();
  await page.getByRole('button', { name: last.name, exact: true }).waitFor();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  await page.waitForFunction(() => {
    const grid = document.querySelector('.image-wall .vgrid');
    return grid && grid.scrollTop / (grid.scrollHeight - grid.clientHeight) > .99;
  });
  await capture('live-narrow-anchor');
  await scroll(1);
  await page.getByRole('button', { name: last.name, exact: true }).waitFor();
  await capture('live-narrow-end');
  assert.ok(pages.every((item) => item.offset < pkg.image_count), 'Resize must not request beyond the package');
  assert.deepEqual(writes, []);
  assert.deepEqual(errors, []);
  const report = { images: pkg.image_count, context_index: context.index, bounded_pages: pages,
    measurements, writes, errors, screenshots_blurred: true };
  await writeFile(path.join(output, 'report.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
} finally {
  await browser.close();
}
