import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile, realpath, rename, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';

/** Real library lifecycle checks. The caller owns an isolated backend and a generated temporary library. */
export async function libraryChecks(page, base, libraryPath, output, setChoice) {
  // Python resolves Windows short names and junctions when registering a library.
  // Compare physical paths, and apply the temporary-directory guard to that same path.
  libraryPath = await realpath(libraryPath);
  const insideTemp = path.relative(await realpath(tmpdir()), libraryPath);
  assert.ok(insideTemp && !insideTemp.startsWith('..') && !path.isAbsolute(insideTemp), 'Only a generated temporary library may be moved');
  const checks = [];
  const failures = [];
  const operations = [];
  const check = (name, condition) => { assert.ok(condition, name); checks.push(name); };
  const onError = (error) => failures.push(error.message);
  const onRequest = (request) => {
    if (request.method() !== 'GET' && new URL(request.url()).pathname === '/api/v1/operations/delete') operations.push(request.url());
  };
  page.on('pageerror', onError);
  page.on('request', onRequest);
  const request = async (route, method = 'GET', body) => {
    const response = await fetch(base + route, { method, headers: { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(10000) });
    assert.ok(response.ok, `${method} ${route}: ${response.status} ${await response.clone().text()}`);
    return response.status === 204 ? null : response.json();
  };
  const waitFor = async (read, accept, name) => {
    for (let i = 0; i < 200; i++) {
      const result = await read();
      if (accept(result)) return result;
      await delay(100);
    }
    throw new Error(`Timed out: ${name}`);
  };
  const idle = (id) => waitFor(() => request(`/api/v1/tasks?library_id=${id}&active=true`),
    (result) => result.total === 0, 'library tasks to settle');
  const completed = (id) => waitFor(() => request(`/api/v1/tasks/${id}`),
    (task) => { if (['failed', 'interrupted'].includes(task.state)) throw new Error(task.error); return task.state === 'completed'; }, 'scan to finish');
  const snapshot = async (name) => {
    check(`${name}: 页面无横向溢出`, await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    const still = await page.addStyleTag({ content: '*,*::before,*::after{transition:none!important;animation:none!important}' });
    try {
      await page.waitForFunction(() => [...document.querySelectorAll('.thumb')].filter((element) => {
        const r = element.getBoundingClientRect();
        return r.width && r.height && r.top < innerHeight && r.bottom > 0 && r.left < innerWidth && r.right > 0;
      }).every((element) => !element.classList.contains('is-loading') && !element.classList.contains('is-pending')));
      await page.screenshot({ path: path.join(output, `${name}.png`), animations: 'disabled' });
    }
    finally { await still.evaluate((element) => element.remove()); }
  };
  const menu = async (action) => {
    await page.locator('.library-home .toolbar').getByRole('button', { name: '管理图库', exact: true }).click();
    await page.getByRole('menuitem', { name: action, exact: true }).click();
  };
  let lib;
  try {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(base);
    const libraries = await request('/api/v1/libraries');
    for (const item of libraries.items) {
      if (await realpath(item.path) === libraryPath) { lib = item; break; }
    }
    if (!lib) {
      await page.getByPlaceholder('例如 D:\\图片\\收藏').fill(libraryPath);
      const created = page.waitForResponse((response) => new URL(response.url()).pathname === '/api/v1/libraries'
        && response.request().method() === 'POST');
      await page.getByRole('button', { name: '添加图库', exact: true }).click();
      assert.equal((await created).status(), 201);
      lib = await (await created).json();
    }
    await idle(lib.id);
    const groups = (await request(`/api/v1/libraries/${lib.id}/groups`)).items;
    const group = groups.find((item) => item.name === '山色');
    const pkg = (await request(`/api/v1/groups/${group.id}/packages`)).items[0];
    const image = (await request(`/api/v1/packages/${pkg.id}/images`)).items[1];
    const restoreHash = `#/l/${lib.id}/g/${group.id}/p/${pkg.id}/i/${image.id}`;
    const digest = (buffer) => createHash('sha256').update(buffer).digest('hex');
    const originalDigest = digest(await readFile(path.join(libraryPath, image.rel)));
    await page.goto(base + restoreHash);
    await page.waitForFunction(() => document.querySelector('.viewer img.layer')?.naturalWidth > 0);
    await page.keyboard.press('k');
    await waitFor(() => request(`/api/v1/groups/${group.id}/review`),
      (review) => review.image_id === image.id && review.state === 'kept', 'viewer position and kept mark');
    await page.goto(`${base}#/l/${lib.id}`);
    await page.locator('.library-home .group-card').first().waitFor();

    await menu('修改名称…');
    let modal = page.getByRole('dialog', { name: '修改图库名称', exact: true });
    const name = modal.getByLabel('图库显示名称');
    await name.fill('   ');
    check('空白名称不能提交', await modal.getByRole('button', { name: '保存名称', exact: true }).isDisabled());
    await name.fill('临时图库 · 山色档案');
    await snapshot('library-rename-desktop');
    await modal.getByRole('button', { name: '保存名称', exact: true }).click();
    await modal.waitFor({ state: 'detached' });
    const renamed = await request(`/api/v1/libraries/${lib.id}`);
    check('改名保留图库 ID 和磁盘路径', renamed.name === '临时图库 · 山色档案' && renamed.path === lib.path);
    if (!await page.locator('.sidebar').count()) await page.getByRole('button', { name: '切换侧栏', exact: true }).click();
    check('侧栏使用修改后的显示名称', await page.locator('.library-row.active').textContent().then((text) => text.includes(renamed.name)));

    // Hold a real generated-library prewarm task, so reconnect must respect its paused state.
    const large = groups.reduce((left, right) => left.image_count > right.image_count ? left : right);
    const prewarm = await request('/api/v1/tasks', 'POST', { kind: 'prewarm', group_id: large.id, edge: 4200 });
    await request(`/api/v1/tasks/${prewarm.id}/control`, 'POST', { action: 'pause' });
    const relocated = path.join(path.dirname(libraryPath), 'library-relocated');
    await menu('重新连接目录…');
    modal = page.getByRole('dialog', { name: '重新连接图库目录', exact: true });
    await modal.getByLabel('图库文件夹的新位置').fill(relocated);
    await modal.getByRole('button', { name: '确认并连接', exact: true }).click();
    await modal.getByRole('alert').filter({ hasText: '未结束的任务' }).waitFor();
    await snapshot('library-busy-desktop');
    check('忙碌时不改变根路径', (await request(`/api/v1/libraries/${lib.id}`)).path === lib.path);
    await modal.getByRole('button', { name: '查看后台任务', exact: true }).click();
    const drawer = page.getByRole('dialog', { name: '后台任务', exact: true });
    await drawer.getByRole('combobox', { name: '任务类型', exact: true }).selectOption('prewarm');
    await drawer.getByRole('combobox', { name: '任务状态', exact: true }).selectOption('paused');
    await drawer.getByRole('combobox', { name: '任务图库', exact: true }).selectOption(lib.id);
    await drawer.getByRole('button', { name: '取消', exact: true }).click();
    await idle(lib.id);
    await drawer.getByRole('button', { name: '关闭', exact: true }).click();
    await page.getByRole('button', { name: '返回图库操作', exact: true }).click();
    modal = page.getByRole('dialog', { name: '重新连接图库目录', exact: true });
    check('查看任务后保留重连输入', await modal.getByLabel('图库文件夹的新位置').inputValue() === relocated);
    await modal.getByRole('button', { name: '确认并连接', exact: true }).click();
    await modal.getByRole('alert').waitFor();
    check('不存在的目录不会替换原根路径', (await request(`/api/v1/libraries/${lib.id}`)).path === lib.path);
    await modal.getByRole('button', { name: '取消', exact: true }).click();

    await rename(libraryPath, relocated);
    const offline = await request('/api/v1/tasks', 'POST', { kind: 'scan', library_id: lib.id, force: true });
    await completed(offline.id);
    await idle(lib.id);
    await page.reload();
    await page.getByRole('button', { name: '重新定位目录…', exact: true }).click();
    modal = page.getByRole('dialog', { name: '重新连接图库目录', exact: true });
    if (setChoice) {
      await setChoice({ canceled: true, filePaths: [] });
      await modal.getByRole('button', { name: '选择文件夹…', exact: true }).click();
      await page.waitForFunction(() => !document.querySelector('.dialog .field-row input')?.disabled);
      check('取消目录选择保留当前根路径', await modal.getByLabel('图库文件夹的新位置').inputValue() === libraryPath);
      await setChoice({ error: 'isolated reconnect picker error' });
      await modal.getByRole('button', { name: '选择文件夹…', exact: true }).click();
      await modal.getByRole('alert').filter({ hasText: '无法选择文件夹' }).waitFor();
      await setChoice({ canceled: false, filePaths: [relocated] });
      await modal.getByRole('button', { name: '选择文件夹…', exact: true }).click();
      await page.waitForFunction((value) => document.querySelector('.dialog .field-row input')?.value === value, relocated);
    } else {
      check('普通浏览器没有目录选择桥接按钮', await modal.getByRole('button', { name: '选择文件夹…', exact: true }).count() === 0);
      await modal.getByLabel('图库文件夹的新位置').fill(relocated);
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await snapshot('library-reconnect-narrow');
    const accepted = page.waitForResponse((response) => new URL(response.url()).pathname === `/api/v1/libraries/${lib.id}/reconnect`);
    await modal.getByRole('button', { name: '确认并连接', exact: true }).click();
    const response = await accepted;
    assert.equal(response.status(), 202);
    await completed((await response.json()).id);
    await modal.waitFor({ state: 'detached' });
    check('重连后图库沿用原 ID', (await request(`/api/v1/libraries/${lib.id}`)).path === relocated);
    const review = await request(`/api/v1/groups/${group.id}/review`);
    check('重连保留浏览位置和标记', review.image_id === image.id && review.state === 'kept');
    check('重连后从新目录读取原图', digest(Buffer.from(await (await fetch(base + `/api/v1/images/${image.id}/original`)).arrayBuffer())) === originalDigest);

    await idle(lib.id);
    await menu('移出管理…');
    modal = page.getByRole('dialog', { name: '移出图库管理', exact: true });
    check('移出说明明确保留磁盘图片和记录', await modal.textContent().then((text) => text.includes('磁盘图片') && text.includes('保留')));
    await snapshot('library-remove-narrow');
    await modal.getByRole('button', { name: '移出管理', exact: true }).click();
    await page.getByRole('heading', { name: '添加第一个图库', exact: true }).waitFor();
    check('移出最后一个图库清除旧路由', new URL(page.url()).hash === '#/');
    check('移出管理后原图字节保持不变', digest(await readFile(path.join(relocated, image.rel))) === originalDigest);
    check('移出管理后原图片 ID 暂不可访问', (await fetch(base + `/api/v1/images/${image.id}/original`)).status === 404);
    await page.reload();
    await page.getByRole('heading', { name: '添加第一个图库', exact: true }).waitFor();
    await page.getByPlaceholder('例如 D:\\图片\\收藏').fill(relocated);
    const readded = page.waitForResponse((result) => new URL(result.url()).pathname === '/api/v1/libraries'
      && result.request().method() === 'POST');
    await page.getByRole('button', { name: '添加图库', exact: true }).click();
    check('重新添加恢复原图库 ID', (await (await readded).json()).id === lib.id);
    await idle(lib.id);
    const restored = await request(`/api/v1/groups/${group.id}/review`);
    check('移出再添加后恢复原位置和标记', restored.image_id === image.id && restored.state === 'kept');
    await page.goto(base + restoreHash);
    await page.waitForFunction(() => document.querySelector('.viewer img.layer')?.naturalWidth > 0);
    await snapshot('library-restored-viewer-narrow');
    check('图库管理未发起文件删除请求', operations.length === 0);
    assert.deepEqual(failures, []);
    await writeFile(path.join(output, 'library-lifecycle.json'), JSON.stringify({ checks, libraryId: lib.id,
      imageId: image.id, originalPath: libraryPath, reconnectedPath: relocated }, null, 2));
    console.log(`PASS library lifecycle: ${checks.length} checks; rename, busy/cancel, offline/reconnect, remove/readd, preserved IDs/position/files`);
    return { restoreHash };
  } catch (error) {
    await page.screenshot({ path: path.join(output, 'library-failure.png') }).catch(() => {});
    await writeFile(path.join(output, 'library-lifecycle.json'), JSON.stringify({ checks, failures, error: error.stack }, null, 2));
    throw error;
  } finally {
    page.off('pageerror', onError);
    page.off('request', onRequest);
  }
}
