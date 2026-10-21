import assert from 'node:assert/strict';
import path from 'node:path';

async function snapshot(page, output, name) {
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${name}: horizontal overflow`);
  await page.screenshot({ path: path.join(output, `${name}.png`) });
}

async function viewReady(page) {
  await page.waitForFunction(() => {
    const image = document.querySelector('.viewer .frame:not(.stale):not(.placeholder):not(.pending) img.layer');
    return image?.complete && image.naturalWidth > 0 && !document.querySelector('.viewer-loading');
  });
}

export async function directoryChecks(page, setChoice, library, output) {
  const picker = page.getByRole('button', { name: '选择文件夹…', exact: true });
  const input = page.getByPlaceholder('例如 D:\\图片\\收藏');
  await picker.waitFor();
  await input.fill('cancel keeps this path');
  await setChoice({ canceled: true, filePaths: [] });
  await picker.click();
  await page.waitForFunction(() => ![...document.querySelectorAll('button')].find((button) => button.textContent.includes('选择文件夹'))?.disabled);
  assert.equal(await input.inputValue(), 'cancel keeps this path');

  await setChoice({ error: 'QA directory selection failure' });
  await picker.click();
  await page.getByRole('alert').filter({ hasText: '无法选择文件夹' }).waitFor();
  assert.ok(await picker.isEnabled());

  await setChoice({ canceled: false, filePaths: [library] });
  await picker.click();
  await page.waitForFunction((value) => document.querySelector('.field-row input')?.value === value, library);
  assert.equal(await page.getByRole('alert').count(), 0);
  await page.setViewportSize({ width: 390, height: 844 });
  await snapshot(page, output, 'directory-picker-narrow');
  await page.setViewportSize({ width: 1440, height: 1000 });
  console.log('PASS directory selection: success, cancellation, failure, narrow layout');
}

export async function workflows(page, base, library, output) {
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  const get = async (route) => {
    const response = await fetch(`${base}${route}`);
    assert.equal(response.status, 200, route);
    return response.json();
  };
  await page.getByPlaceholder('例如 D:\\图片\\收藏').fill(library);
  const added = page.waitForResponse((response) => new URL(response.url()).pathname === '/api/v1/libraries'
    && response.request().method() === 'POST');
  await page.getByRole('button', { name: '添加图库', exact: true }).click();
  const created = await added;
  assert.equal(created.status(), 201);
  const registered = await created.json();
  let scan;
  for (let attempt = 0; attempt < 300; attempt++) {
    const tasks = await get('/api/v1/tasks');
    scan = tasks.items.find((task) => task.kind === 'scan' && task.payload.library_id === registered.id);
    if (scan?.state === 'completed') break;
    if (scan?.state === 'failed') throw new Error(scan.error);
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  assert.equal(scan?.state, 'completed', 'Initial scan did not finish');
  const groups = (await get(`/api/v1/libraries/${registered.id}/groups`)).items;
  const group = groups.find((item) => item.name === '山色');
  assert.ok(group, 'Generated library did not finish scanning');
  const packages = (await get(`/api/v1/groups/${group.id}/packages`)).items;
  const images = (await get(`/api/v1/packages/${packages[0].id}/images`)).items;
  const route = `#/l/${registered.id}/g/${group.id}/p/${packages[0].id}`;

  await page.locator('.group-card').filter({ hasText: '山色' }).click();
  await page.getByRole('button', { name: '打开图片墙', exact: true }).first().click();
  await page.locator('.image-card img').first().waitFor();
  await snapshot(page, output, 'images-desktop');
  await page.locator('.image-card').first().click();
  await viewReady(page);
  await page.keyboard.press('ArrowRight');
  await page.waitForFunction((id) => location.hash.endsWith(`/i/${id}`), images[1].id);
  await viewReady(page);
  await snapshot(page, output, 'viewer-desktop');
  let review;
  for (let attempt = 0; attempt < 100; attempt++) {
    review = await get(`/api/v1/groups/${group.id}/review`);
    if (review.image_id === images[1].id) break;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  assert.equal(review.image_id, images[1].id);
  const before = page.url();
  await page.reload();
  await viewReady(page);
  assert.equal(page.url(), before, 'Refresh must preserve the viewer route');
  await page.keyboard.press('End');
  await page.waitForFunction((id) => location.hash.endsWith(`/i/${id}`), images.at(-1).id);
  await viewReady(page);
  await page.keyboard.press('ArrowRight');
  assert.ok(page.url().endsWith(`/i/${images.at(-1).id}`), 'Viewer crossed a package boundary');
  await page.keyboard.press('Escape');
  await page.locator('.viewer').waitFor({ state: 'detached' });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${base}${route}`);
  await page.locator('.image-card img').first().waitFor();
  await snapshot(page, output, 'images-narrow');
  await page.locator('.image-card').first().click();
  await viewReady(page);
  await snapshot(page, output, 'viewer-narrow');

  const animationGroup = groups.find((item) => item.name.includes('动图'));
  const animationPackage = (await get(`/api/v1/groups/${animationGroup.id}/packages`)).items[0];
  const animationImages = (await get(`/api/v1/packages/${animationPackage.id}/images`)).items;
  for (const name of ['01-gif.gif', '02-webp.webp']) {
    const image = animationImages.find((item) => item.name === name);
    await page.goto(`${base}#/l/${registered.id}/g/${animationGroup.id}/p/${animationPackage.id}/i/${image.id}`);
    await viewReady(page);
    assert.ok(await page.locator('.viewer img.layer').last().getAttribute('src').then((src) => src.includes('/original')));
    await page.waitForFunction(async () => {
      const image = document.querySelector('.viewer .frame:not(.stale):not(.placeholder):not(.pending) img.layer');
      const canvas = document.createElement('canvas');
      canvas.width = canvas.height = 1;
      const context = canvas.getContext('2d');
      context.drawImage(image, 0, 0, 1, 1);
      const first = String(context.getImageData(0, 0, 1, 1).data);
      await new Promise((resolve) => setTimeout(resolve, 300));
      context.drawImage(image, 0, 0, 1, 1);
      return first !== String(context.getImageData(0, 0, 1, 1).data);
    });
  }
  await snapshot(page, output, 'animation-narrow');

  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(`${base}#/l/${registered.id}/g/${group.id}`);
  await page.getByRole('button', { name: '更多操作', exact: true }).click();
  await page.getByRole('menuitem', { name: '预先生成缩略图' }).click();
  await page.getByRole('button', { name: '后台任务', exact: true }).click();
  await page.locator('.task-row').filter({ hasText: '缩略图' }).first().waitFor();
  await snapshot(page, output, 'tasks-desktop');
  let prewarm;
  for (let attempt = 0; attempt < 300; attempt++) {
    prewarm = (await get('/api/v1/tasks')).items.find((task) => task.kind === 'prewarm' && task.payload.group_id === group.id);
    if (prewarm?.state === 'completed' || prewarm?.state === 'failed') break;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  assert.equal(prewarm?.state, 'completed', prewarm?.error || 'Prewarm did not finish');
  assert.equal(prewarm.result.generated_or_cached, group.image_count);
  assert.equal(prewarm.result.failed, 0);
  await page.locator('.drawer').getByRole('button', { name: '关闭', exact: true }).click();

  const deleteGroup = groups.find((item) => item.name.includes('删除测试'));
  const deletePackage = (await get(`/api/v1/groups/${deleteGroup.id}/packages`)).items[0];
  const victim = (await get(`/api/v1/packages/${deletePackage.id}/images`)).items[0];
  await page.goto(`${base}#/l/${registered.id}/g/${deleteGroup.id}/p/${deletePackage.id}/i/${victim.id}`);
  await viewReady(page);
  await page.getByRole('button', { name: '删除这张图片', exact: true }).click();
  const confirmation = page.getByRole('dialog', { name: '确认删除' });
  const radios = confirmation.getByRole('radio');
  assert.ok(await radios.nth(0).isChecked(), 'Recycle must remain the default');
  await radios.nth(1).check();
  const remove = confirmation.getByRole('button', { name: '永久删除', exact: true });
  assert.ok(await remove.isDisabled());
  await confirmation.getByRole('checkbox').check();
  await remove.click();
  await page.getByRole('dialog', { name: '删除结果' }).waitFor();
  await page.locator('.report-row.completed').waitFor();
  assert.equal(await page.locator('.report-row.failed').count(), 0);
  await snapshot(page, output, 'delete-result-desktop');
  const missing = await fetch(`${base}/api/v1/images/${victim.id}/original`);
  assert.equal(missing.status, 404);
  assert.deepEqual(errors, []);
  console.log('PASS production UI: register, browse, view, boundary, position/reload, GIF/WebP pixels, tasks, confirmed temporary delete');
}
