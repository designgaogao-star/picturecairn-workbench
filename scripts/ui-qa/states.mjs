import { setTimeout as delay } from 'node:timers/promises';

export async function states(page, { base, lib, groups, get, check, snapshot }) {
  const group = groups.find((item) => item.name.includes('长名称与同名路径'));
  const packages = (await get(`/api/v1/groups/${group.id}/packages`)).items;
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(`${base}#/l/${lib.id}/g/${group.id}`);
  await page.locator('.package-card').first().waitFor();
  check('真实目录图包名称保持归属', await page.locator('.package-card .card-title').allTextContents().then((items) => items.includes('2025') && items.includes('2026')));
  const pkg = packages[0];
  const images = (await get(`/api/v1/packages/${pkg.id}/images`)).items;
  const image = images[0];
  const imagesPattern = `**/api/v1/packages/${pkg.id}/images?*`;
  await page.route(imagesPattern, async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    await route.fulfill({ response, json: { ...data, items: data.items.map((item) => ({ ...item, width: null, height: null })) } });
  });
  await page.locator('.package-card .card-hit').first().click();
  await page.getByRole('button', { name: image.name, exact: true }).first().waitFor();
  check('未知尺寸只显示已有大小', await page.locator('.image-card .card-sub').first().textContent().then((text) => !text.includes('null') && !text.includes('×') && text.includes('KB')));
  check('长文件名保留完整可访问名称', await page.locator('.image-card .card-title').first().getAttribute('title') === image.name);
  await page.getByRole('button', { name: '信息', exact: true }).click();
  await page.getByRole('button', { name: image.name, exact: true }).first().focus();
  await page.waitForFunction((name) => document.querySelector('.inspector-body h3')?.textContent === name, image.name);
  check('长路径详情可复制换行', await page.locator('.inspector-body').evaluate((el) => getComputedStyle(el).userSelect === 'text' && el.scrollWidth <= el.clientWidth));
  await page.getByRole('button', { name: image.name, exact: true }).nth(1).focus();
  await page.waitForFunction((rel) => document.querySelector('.inspector-body')?.textContent.includes(rel), images[1].rel);
  check('同名图片以完整相对路径消歧', images[0].name === images[1].name && images[0].rel !== images[1].rel);
  await snapshot(page, 'E-long-name-desktop');
  await page.unroute(imagesPattern);
  await page.setViewportSize({ width: 390, height: 844 });
  await snapshot(page, 'E-long-name-narrow');
  await page.keyboard.press('Escape');
  await page.locator('.inspector').waitFor({ state: 'detached' });

  const librariesPattern = '**/api/v1/libraries?*';
  await page.route(librariesPattern, async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    await route.fulfill({ response, json: { ...data, items: data.items.map((item) => item.id === lib.id ? { ...item, online: false, scan_status: 'offline' } : item) } });
  });
  await page.evaluate(async () => { const app = await import('/src/state/app.ts'); await app.loadLibraries(); });
  await page.locator('.banner').filter({ hasText: '当前无法访问' }).waitFor();
  check('离线快照保留图片清单', await page.locator('.image-card').count() === images.length);
  await snapshot(page, 'E-offline-narrow');
  await page.unroute(librariesPattern);
  const reads = [];
  const track = (request) => { if (/\/api\/v1\/(libraries|tasks)\?/.test(request.url())) reads.push(request.url()); };
  page.on('request', track);
  const snapshots = Promise.all([
    page.waitForRequest((request) => new URL(request.url()).pathname === '/api/v1/libraries'),
    page.waitForRequest((request) => new URL(request.url()).pathname === '/api/v1/tasks'),
  ]);
  await page.evaluate(async () => { const events = await import('/src/state/events.ts'); events.reconnectNow(); });
  await snapshots;
  await page.waitForFunction(async () => {
    const app = await import('/src/state/app.ts');
    return app.connection.value === 'online' && app.currentLibrary.value?.online;
  });
  check('SSE重连读取图库与任务快照', reads.some((url) => url.includes('/libraries?')) && reads.some((url) => url.includes('/tasks?')));
  page.off('request', track);

  const mountain = groups.find((item) => item.name === '山色');
  const mountainPackage = (await get(`/api/v1/groups/${mountain.id}/packages`)).items[0];
  const mountainImages = (await get(`/api/v1/packages/${mountainPackage.id}/images`)).items;
  const wall = `${base}#/l/${lib.id}/g/${mountain.id}/p/${mountainPackage.id}`;
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(wall);
  await page.getByRole('button', { name: mountainImages[0].name, exact: true }).waitFor();
  await page.locator('.image-card .card-hit').first().click();
  for (let index = 1; index < 6; index++) {
    await page.keyboard.press('ArrowRight');
    await page.waitForFunction((id) => location.hash.endsWith(`/i/${id}`), mountainImages[index].id);
  }
  await page.waitForFunction((name) => {
    const img = document.querySelector('.frame:not(.pending):not(.stale):not(.placeholder) img');
    return img?.alt === name && img.complete && img.naturalWidth > 0;
  }, mountainImages[5].name);
  check('连续快切只展示最终图片', await page.locator('.viewer-name').textContent() === mountainImages[5].name);
  check('胶片条节点有界', await page.locator('.film-cell').count() < 40);
  await page.keyboard.press('Escape');
  await page.locator('.viewer').waitFor({ state: 'detached' });
  const targetPage = `**/api/v1/packages/${mountainPackage.id}/images?*`;
  let failedPages = 0, exhausted;
  const retriesExhausted = new Promise((resolve) => { exhausted = resolve; });
  await page.route(targetPage, (route) => {
    if (++failedPages === 3) exhausted();
    return route.fulfill({ status: 503, json: { detail: '模拟分页读取失败' } });
  });
  await page.evaluate(async () => {
    const app = await import('/src/state/app.ts');
    const router = await import('/src/lib/router.ts');
    app.imagesList(router.route.value.package).invalidate();
  });
  await page.locator('.images .vgrid-error').waitFor();
  check('分页失败保留已有内容', await page.locator('.image-card').count() > 0);
  await snapshot(page, 'E-page-failure');
  await retriesExhausted;
  await page.waitForFunction(() => document.querySelector('.images .vgrid-space')?.getAttribute('aria-busy') === 'false'
    && document.querySelector('.images .vgrid-error'));
  await page.unroute(targetPage);
  await page.locator('.images .vgrid-error').getByRole('button', { name: '重试', exact: true }).click();
  await page.locator('.images .vgrid-error').waitFor({ state: 'detached' });
  check('分页可原位恢复', await page.locator('.image-card').count() === mountainImages.length);
  await delay(100);
  check('最终页面无嵌套按钮或横向溢出', await page.locator('button button').count() === 0 && await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
}
