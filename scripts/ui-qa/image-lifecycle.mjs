import assert from 'node:assert/strict';
import { writeFile } from 'node:fs/promises';
import path from 'node:path';

export async function imageLifecycleChecks(page, base, output) {
  const saved = page.url();
  const get = async (route) => {
    const response = await fetch(base + '/api/v1' + route);
    assert.ok(response.ok, route);
    return response.json();
  };
  const library = (await get('/libraries')).items[0];
  const group = (await get(`/libraries/${library.id}/groups?limit=500`)).items.find((item) => item.name.includes('动图'));
  assert.ok(group);
  const pkg = (await get(`/groups/${group.id}/packages`)).items[0];
  const image = (await get(`/packages/${pkg.id}/images`)).items.find((item) => item.name.includes('01-gif'));
  assert.ok(image);
  const packageHash = `#/l/${library.id}/g/${group.id}/p/${pkg.id}`;
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(base + packageHash);
  await page.locator('.image-card').filter({ has: page.getByRole('button', { name: image.name, exact: true }) })
    .locator('.thumb.is-ready img').waitFor();
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  const originalPath = `/api/v1/images/${image.id}/original`;
  const pattern = `**${originalPath}*`;
  const hold = async (route) => { await gate; await route.continue().catch(() => {}); };
  await page.route(pattern, hold);
  try {
    const request = page.waitForRequest((item) => new URL(item.url()).pathname === originalPath);
    await page.evaluate((hash) => { location.hash = hash; }, `${packageHash}/i/${image.id}`);
    await request;
    await page.locator('.viewer .placeholder img').waitFor();
    const before = await page.evaluate(() => {
      // Retain the DOM nodes so this checks eager release, independently of the browser's next GC.
      window.__qaImageNodes = [...document.querySelectorAll('.viewer img.layer')];
      return window.__qaImageNodes.map((element) => ({ placeholder: Boolean(element.closest('.placeholder')), src: element.getAttribute('src') }));
    });
    assert.ok(before.some((item) => item.placeholder && item.src));
    await page.keyboard.press('Escape');
    await page.locator('.viewer').waitFor({ state: 'detached' });
    const after = await page.evaluate(() => window.__qaImageNodes.map((element) => element.getAttribute('src')));
    const passed = after.every((src) => src === null);
    await writeFile(path.join(output, 'image-lifecycle-verification.json'), JSON.stringify({
      before, after, no_forced_gc: true, passed,
    }, null, 2));
    console.log(`Image lifecycle evidence: ${output}`);
    assert.ok(passed, 'Every detached viewer image, including the static placeholder, must release its source before GC');
    console.log('PASS image lifecycle: detached static placeholder and pending animation release their sources before GC');
  } finally {
    release();
    await page.unroute(pattern, hold);
    await page.evaluate(() => { delete window.__qaImageNodes; });
    await page.goto(saved);
    await page.waitForFunction(() => document.querySelector('.viewer img.layer')?.naturalWidth > 0);
  }
}
