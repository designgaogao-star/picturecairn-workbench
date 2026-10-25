import assert from 'node:assert/strict';
import { access, readFile } from 'node:fs/promises';
import path from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';

export async function decisions(page, { base, lib, groups, library, temporary, project, launch, get, check, snapshot }) {
  const group = groups.find((item) => item.name.includes('重复样本'));
  const packages = (await get(`/api/v1/groups/${group.id}/packages`)).items;
  const hash = `#/l/${lib.id}/g/${group.id}/organize/t/compare`;
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(base + hash);
  const choose = async (left, right) => {
    await page.waitForFunction(() => document.querySelectorAll('datalist option').length >= 4);
    await page.getByLabel('左侧图包').fill(packages.find((pkg) => pkg.name.startsWith(left)).name);
    await page.getByLabel('右侧图包').fill(packages.find((pkg) => pkg.name.startsWith(right)).name);
    const accepted = page.waitForResponse((response) => new URL(response.url()).pathname === '/api/v1/tasks' && response.request().method() === 'POST');
    await page.getByRole('button', { name: '开始核验', exact: true }).click();
    const task = await (await accepted).json();
    await page.locator(`.verdict[data-task-id="${task.id}"]`).waitFor();
  };
  await choose('A', 'B');
  check('全文件核验包含说明文件', await page.locator('.verdict').textContent().then((text) => text.includes('两侧完全一致') && text.includes('11 个文件')));
  check('相同两侧均可由用户选择保留', await page.locator('.side-delete .btn').count() === 2);
  await snapshot(page, 'D-compare-equal');
  const resultBefore = await page.locator('.verdict').textContent();
  await page.getByRole('button', { name: '后台任务', exact: true }).click();
  check('桌面任务非模态且360px', await page.locator('.drawer').evaluate((el) => !el.matches(':modal') && Math.round(el.getBoundingClientRect().width) === 360));
  await page.getByLabel('左侧图包').click();
  check('任务打开仍可操作工作区', await page.getByLabel('左侧图包').evaluate((el) => el === document.activeElement));
  await snapshot(page, 'D-tasks-desktop');
  await page.keyboard.press('Escape');
  await page.locator('.drawer').waitFor({ state: 'detached' });
  check('关闭任务保留核验结果', await page.locator('.verdict').textContent().then((text) => text === resultBefore));
  const revision = (await get('/api/v1/libraries')).items.find((item) => item.id === lib.id).revision;
  const libraryRoute = '**/api/v1/libraries?*';
  const staleLibraries = async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    data.items = data.items.map((item) => item.id === lib.id ? { ...item, revision: revision + 1 } : item);
    await route.fulfill({ response, json: data });
  };
  // A revision change uses a contract-valid snapshot; it never mutates indexed data.
  await page.route(libraryRoute, staleLibraries);
  await page.evaluate(async () => { const app = await import('/src/state/app.ts'); await app.loadLibraries(); });
  await page.getByText('核验结果已过期', { exact: true }).waitFor();
  check('过期核验撤除快捷删除入口', await page.locator('.side-delete').count() === 0);
  await snapshot(page, 'D-compare-stale');
  // This is the only installed route. Finish in-flight snapshots before restoring the real API.
  await page.unrouteAll({ behavior: 'wait' });
  await page.evaluate(async () => { const app = await import('/src/state/app.ts'); await app.loadLibraries(); });
  await choose('A', 'D');
  check('非图片差异阻止重复结论', await page.locator('.verdict').textContent().then((text) => text.includes('各有独有文件')));
  check('独有非图片文件保持可见', await page.locator('.file-row').filter({ hasText: '说明.txt' }).count() === 2);
  check('各有独有内容没有核验删除入口', await page.locator('.side-delete').count() === 0);
  await choose('C', 'A');
  check('包含关系只允许被包含侧快捷删除', await page.locator('.compare-side[aria-label="左侧"] .side-delete .btn').count() === 1
    && await page.locator('.compare-side[aria-label="右侧"] .side-delete').count() === 0);
  await page.getByRole('button', { name: '相似图包', exact: true }).click();
  await page.getByRole('button', { name: '开始分析', exact: true }).click();
  await page.locator('.pair-row').first().waitFor();
  check('相似候选各自展示匹配率与覆盖率', await page.locator('.pair-row .rate').first().textContent().then((text) => text.includes('指纹覆盖')));
  check('相似候选不能直接删除', await page.locator('.pair-row .danger').count() === 0);
  await snapshot(page, 'D-similar');
  await page.getByRole('button', { name: '清理检查', exact: true }).click();
  await page.getByRole('button', { name: '开始检查', exact: true }).click();
  await page.getByRole('heading', { name: '空壳包' }).waitFor();
  check('清理检查读取真实任务结果', await page.getByRole('heading', { name: '疑似不完整' }).count() === 1);

  await page.getByRole('button', { name: '后台任务', exact: true }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator('.drawer:modal').waitFor();
  check('窄屏任务原生模态', await page.locator('.drawer').evaluate((el) => el.matches(':modal')));
  await snapshot(page, 'D-tasks-narrow');
  for (let index = 0; index < 12; index++) await page.keyboard.press('Tab');
  check('窄屏任务限制背景焦点', await page.evaluate(() => Boolean(document.activeElement?.closest('.drawer'))));
  await page.keyboard.press('Escape');
  await page.locator('.drawer').waitFor({ state: 'detached' });
  await page.getByRole('button', { name: '切换侧栏', exact: true }).click();
  await page.locator('.sidebar:modal').waitFor();
  check('窄屏侧栏原生模态', await page.locator('.sidebar').evaluate((el) => el.matches(':modal')));
  await page.keyboard.press('Escape');
  await page.locator('.sidebar').waitFor({ state: 'detached' });
  await page.setViewportSize({ width: 1440, height: 1000 });

  const large = groups.find((item) => item.name.includes('大图包'));
  const created = await fetch(new URL('/api/v1/tasks', base), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ kind: 'prewarm', group_id: large.id, edge: 800 }) });
  assert.equal(created.status, 202);
  const task = await created.json();
  await page.getByRole('button', { name: '后台任务', exact: true }).click();
  const row = page.locator('.task-row').filter({ hasText: '大图包' });
  await row.getByRole('button', { name: '暂停', exact: true }).waitFor();
  const controlPattern = `**/api/v1/tasks/${task.id}/control`;
  let controlRequests = 0;
  await page.route(controlPattern, async (route) => { controlRequests++; await delay(350); await route.continue(); });
  await row.getByRole('button', { name: '暂停', exact: true }).click();
  check('控制待回应禁用重复请求', await row.getByRole('button', { name: '暂停中…', exact: true }).isDisabled());
  await row.getByRole('button', { name: '继续', exact: true }).waitFor();
  check('暂停请求只提交一次', controlRequests === 1);
  await row.getByRole('button', { name: '取消', exact: true }).click();
  await row.getByText('已取消', { exact: true }).waitFor();
  check('任务取消以服务端终态为准', (await get(`/api/v1/tasks/${task.id}`)).state === 'cancelled');
  await page.unroute(controlPattern);
  await page.keyboard.press('Escape');

  const disposable = groups.find((item) => item.name.includes('删除测试'));
  const pkg = (await get(`/api/v1/groups/${disposable.id}/packages`)).items[0];
  const images = (await get(`/api/v1/packages/${pkg.id}/images`)).items;
  await page.goto(`${base}#/l/${lib.id}/g/${disposable.id}/p/${pkg.id}`);
  await page.getByRole('button', { name: images[0].name, exact: true }).waitFor();
  await page.getByRole('button', { name: '选择', exact: true }).click();
  for (const image of images.slice(0, 2)) await page.getByRole('button', { name: image.name, exact: true }).click();
  await page.getByRole('button', { name: '删除…', exact: true }).click();
  const confirmation = page.getByRole('dialog', { name: '确认删除', exact: true });
  const permanent = confirmation.getByRole('checkbox', { name: '永久删除，不经过回收站', exact: true });
  check('默认回收且目标路径完整', !await permanent.isChecked() && await confirmation.locator('.delete-targets li').count() === 2
    && await confirmation.locator('.delete-targets').textContent().then((text) => text.includes(disposable.name)));
  await permanent.check();
  check('永久删除还需第二次勾选', await confirmation.getByRole('button', { name: '永久删除', exact: true }).isDisabled());
  await confirmation.getByRole('checkbox', { name: '我确认永久删除这些文件，且无法恢复', exact: true }).check();
  const lockedPath = path.join(library, images[1].rel);
  const marker = path.join(temporary, 'file-locked');
  const locked = launch(path.join(project, '.venv/Scripts/python.exe'), ['scripts/ui-qa/lock_file.py', lockedPath, marker], 'locked-file');
  for (let attempt = 0; attempt < 100; attempt++) {
    assert.equal(locked.exitCode, null);
    try { if (await readFile(marker, 'utf8') === 'locked') break; } catch (error) { if (error.code !== 'ENOENT') throw error; }
    await delay(50);
  }
  await access(marker);
  await confirmation.getByRole('button', { name: '永久删除', exact: true }).click();
  await page.locator('.report-row.completed').waitFor();
  await page.locator('.report-row.failed').waitFor();
  check('真实临时删除逐项成功与失败', await page.locator('.report-row.completed').count() === 1 && await page.locator('.report-row.failed').count() === 1);
  await snapshot(page, 'D-delete-partial');
  await page.setViewportSize({ width: 390, height: 844 });
  await snapshot(page, 'D-delete-partial-narrow');
  await page.getByRole('button', { name: '只重试失败项', exact: true }).click();
  await confirmation.waitFor();
  check('重试只包含失败项并重置危险选项', await confirmation.locator('.delete-targets li').count() === 1 && !await permanent.isChecked());
  locked.kill();
  if (locked.exitCode === null) await new Promise((resolve) => locked.once('exit', resolve));
  await permanent.check();
  await confirmation.getByRole('checkbox', { name: '我确认永久删除这些文件，且无法恢复', exact: true }).check();
  await confirmation.getByRole('button', { name: '永久删除', exact: true }).click();
  await page.locator('.report-row.completed').waitFor();
  check('只重试失败项最终成功', await page.locator('.report-row.completed').count() === 1 && await page.locator('.report-row.failed').count() === 0);
  for (const image of images.slice(0, 2)) await assert.rejects(access(path.join(library, image.rel)), { code: 'ENOENT' });
  await page.getByRole('dialog', { name: '删除结果', exact: true }).getByRole('button', { name: '完成', exact: true }).click();
  await page.waitForFunction(() => document.querySelector('.toolbar.selecting strong')?.textContent === '0');
  check('成功项从选择中移除', await page.locator('.toolbar.selecting strong').textContent().then((text) => text === '0'));
  await page.getByRole('button', { name: images[2].name, exact: true }).click();
  await page.getByRole('button', { name: '删除…', exact: true }).click();
  const failedId = `qa-recycle-failure-${Date.now()}`;
  const failedTask = { ...task, id: failedId, kind: 'delete', state: 'completed', error: null,
    payload: { targets: [{ kind: 'image', id: images[2].id }], permanent: false },
    result: { items: [{ task_id: failedId, id: 'qa-operation', target_id: images[2].id, kind: 'image', path: path.join(library, images[2].rel),
      mode: 'recycle', state: 'failed', error: '模拟：回收不可用', time: Date.now() / 1000 }], failed: 1, skipped: 0 } };
  const deleteBodies = [];
  const deletionPattern = '**/api/v1/operations/delete';
  await page.route(deletionPattern, async (route) => {
    deleteBodies.push(route.request().postDataJSON());
    await route.fulfill({ status: 202, json: failedTask });
  });
  const failurePattern = `**/api/v1/tasks/${failedId}`;
  await page.route(failurePattern, (route) => route.fulfill({ json: failedTask }));
  // The default recycle branch is simulated at HTTP; no request reaches IFileOperation.
  await confirmation.getByRole('button', { name: '移到回收站', exact: true }).click();
  await page.locator('.report-row.failed').waitFor();
  check('模拟回收失败逐项呈现且不自动永久删除', deleteBodies.length === 1 && deleteBodies[0].permanent === false
    && await page.locator('.report-error').textContent().then((text) => text.includes('回收不可用')));
  await access(path.join(library, images[2].rel));
  await page.getByRole('button', { name: '只重试失败项', exact: true }).click();
  await confirmation.waitFor();
  check('模拟回收失败重试仍默认回收', !await permanent.isChecked());
  await confirmation.getByRole('button', { name: '取消', exact: true }).click();
  await page.unroute(deletionPattern);
  await page.unroute(failurePattern);
  check('页面没有嵌套按钮', await page.locator('button button').count() === 0);
}
