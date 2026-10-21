const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { chromium } = require('playwright-core');

const root = path.resolve(__dirname, '../../..');
const output = path.join(root, 'output/playwright/workbench-design');
const base = pathToFileURL(path.join(__dirname, 'preview/index.html')).href;
const checks = [];
const errors = [];
const externalRequests = [];
const contrastResults = [];
const check = (name, condition) => { assert.ok(condition, name); checks.push(name); };

async function ready(page) {
  await page.locator('h1').waitFor();
  await page.evaluate(() => Promise.all([...document.images].filter((image) => image.getBoundingClientRect().height > 0).map((image) => image.decode().catch(() => {}))));
}

async function screenshot(page, name) {
  await ready(page);
  await page.mouse.move(0, 0);
  await page.screenshot({ path: path.join(output, `${name}.png`) });
}

async function layout(page, name) {
  const geometry = await page.evaluate(() => ({
    viewport: innerWidth,
    documentWidth: document.documentElement.scrollWidth,
    contentWidth: document.querySelector('#content').scrollWidth,
    contentClient: document.querySelector('#content').clientWidth,
    clippedLabels: [...document.querySelectorAll('.tile-body')].filter((item) => item.scrollHeight > item.clientHeight + 1).length,
    controls: [...document.querySelectorAll('button:not(:disabled), input, select')].filter((item) => {
      const r = item.getBoundingClientRect();
      return r.width > 0 && r.height > 0 && r.right > innerWidth + 1;
    }).map((item) => item.getAttribute('aria-label') || item.textContent.trim()),
  }));
  check(`${name}: 页面无横向溢出`, geometry.documentWidth <= geometry.viewport + 1);
  check(`${name}: 主内容无横向溢出`, geometry.contentWidth <= geometry.contentClient + 1);
  check(`${name}: 卡片文案无垂直溢出`, geometry.clippedLabels === 0);
  check(`${name}: 操作控件在视口内`, geometry.controls.length === 0);
}

async function contrast(page, theme) {
  const values = await page.evaluate(() => {
    const css = getComputedStyle(document.documentElement);
    const pairs = [
      ['正文', '--text', '--surface', 4.5], ['辅助文字', '--text-secondary', '--canvas', 4.5],
      ['弱文字', '--text-muted', '--canvas', 4.5], ['选中文字', '--accent-text', '--accent-soft', 4.5],
      ['主要按钮', '--on-accent', '--accent', 4.5], ['成功', '--success', '--success-soft', 4.5],
      ['警告', '--warning', '--warning-soft', 4.5], ['危险', '--danger', '--danger-soft', 4.5],
      ['控件边界', '--line-strong', '--surface', 3], ['焦点', '--accent', '--canvas', 3],
      ['查看器文字', '--viewer-secondary', '--viewer', 4.5],
    ];
    const luminance = (key) => {
      const color = css.getPropertyValue(key).trim().replace('#', '');
      const channels = [0, 2, 4].map((offset) => parseInt(color.slice(offset, offset + 2), 16) / 255).map((n) => n <= .04045 ? n / 12.92 : ((n + .055) / 1.055) ** 2.4);
      return channels[0] * .2126 + channels[1] * .7152 + channels[2] * .0722;
    };
    return pairs.map(([name, front, back, minimum]) => {
      const a = luminance(front), b = luminance(back);
      return { name, minimum, ratio: (Math.max(a, b) + .05) / (Math.min(a, b) + .05) };
    });
  });
  for (const item of values) check(`${theme}: ${item.name}对比 ≥ ${item.minimum}`, item.ratio >= item.minimum);
  contrastResults.push({ theme, values });
}

async function main() {
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const newPage = async (viewport = { width: 1440, height: 1000 }) => {
    const context = await browser.newContext({ viewport, reducedMotion: 'reduce' });
    const page = await context.newPage();
    page.on('pageerror', (error) => errors.push(error.message));
    page.on('console', (message) => { if (message.type() === 'error' || message.type() === 'warning') errors.push(message.text()); });
    page.on('request', (request) => { if (/^https?:/.test(request.url())) externalRequests.push(request.url()); });
    return page;
  };
  try {
    const page = await newPage();
    await page.goto(base);
    await ready(page);
    check('默认图包墙为 12 项', await page.locator('#app .tile').count() === 12);
    check('图标来自 Lucide', await page.locator('#app svg').count() > 20);
    check('可见图片均解码成功', await page.locator('#app .tile img').evaluateAll((items) => items.every((item) => item.complete && item.naturalWidth > 0)));
    await layout(page, '1440 桌面');
    await contrast(page, '浅色');
    await screenshot(page, 'browse-desktop');
    for (const viewport of [{ width: 1280, height: 800 }, { width: 1920, height: 1080 }]) {
      await page.setViewportSize(viewport);
      await page.waitForFunction((width) => innerWidth === width && document.querySelector('.grid').style.getPropertyValue('--tile-min') === '230px', viewport.width);
      await layout(page, `${viewport.width} 桌面`);
    }
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.locator('#app [data-action="open-package"][data-id="travel-lake"]').click();
    await page.waitForURL(/\/p\/travel-lake$/);
    check('图包单击先打开图片墙', await page.locator('#app .image-grid').count() === 1 && !await page.locator('#viewer').evaluate((item) => item.open));
    check('图片墙完整显示', await page.locator('#app .image-grid img').first().evaluate((item) => getComputedStyle(item).objectFit) === 'contain');
    await screenshot(page, 'images-desktop');
    await page.locator('#app [data-action="open-image"][data-index="3"]').click();
    await page.locator('#viewer[open]').waitFor();
    await screenshot(page, 'viewer-desktop');
    await page.keyboard.press('ArrowRight');
    await page.waitForURL(/\/i\/4$/);
    check('查看器方向键切图', await page.locator('.viewer-counter').textContent() === '5 / 8');
    for (let index = 0; index < 5; index++) await page.keyboard.press('ArrowRight');
    await page.waitForURL(/\/i\/7$/);
    check('包末停止导航', await page.locator('#viewer [data-action="next"]').isDisabled());
    check('包末有明确状态', await page.locator('.boundary').textContent() === '已到当前图包末尾');
    await page.keyboard.press('Escape');
    await page.locator('#viewer').waitFor({ state: 'hidden' });
    check('关闭后焦点回到刚看的图片', await page.evaluate(() => document.activeElement.dataset.index === '7'));
    check('关闭后图片墙标记刚看的图片', await page.locator('#app [data-tile-id="travel-lake-8"]').getAttribute('class').then((value) => value.includes('last-viewed')));
    await page.locator('#app [data-action="resume"]').click();
    await page.waitForURL(/\/i\/7$/);
    await page.reload();
    await page.locator('#viewer[open]').waitFor();
    check('刷新恢复同一图片', await page.locator('.viewer-counter').textContent() === '8 / 8');
    await page.keyboard.press('Escape');
    await page.locator('#viewer').waitFor({ state: 'hidden' });
    await page.locator('#app [data-action="appearance"]').click();
    await page.getByRole('menuitemradio', { name: '深色', exact: true }).click();
    check('深色外观切换', await page.locator('html').getAttribute('data-theme') === 'dark');
    await contrast(page, '深色');
    await screenshot(page, 'images-dark');
    await page.locator('#app [data-action="appearance"]').click();
    await page.getByRole('menuitemradio', { name: '浅色', exact: true }).click();
    await page.locator('#app .task-button').click();
    await page.locator('#panel[open]').waitFor();
    await screenshot(page, 'tasks-desktop');
    await page.locator('#panel [data-action="task-pause"][data-id="warm"]').click();
    await page.locator('#panel [data-action="task-resume"][data-id="warm"]').waitFor();
    check('任务暂停有最终状态', await page.locator('#panel').textContent().then((value) => value.includes('已暂停')));
    await page.locator('#panel [data-action="task-resume"][data-id="warm"]').click();
    await page.locator('#panel [data-action="task-cancel"][data-id="warm"]').click();
    await page.waitForFunction(() => document.querySelector('#panel').textContent.includes('停止于 48 / 96'));
    checks.push('任务取消保留已完成数量');
    await page.locator('#panel [data-action="close-panel"]').click();
    await page.locator('#app [data-action="organize"]').click();
    await page.waitForURL(/\/organize\/compare$/);
    check('未核验不提供核验删除命令', await page.locator('[data-action="delete-verified"]').count() === 0);
    await page.locator('[data-action="verify"]').click();
    await page.waitForFunction(() => document.querySelector('.verdict').textContent.includes('左侧被右侧完整包含'));
    check('核验结论包含非图片文件', await page.locator('.file-list').first().textContent().then((value) => value.includes('README.txt')));
    await page.locator('.toast').waitFor({ state: 'hidden' });
    await screenshot(page, 'organize-desktop');
    await page.locator('[data-action="org-tab"][data-id="similar"]').click();
    await page.waitForURL(/\/similar$/);
    check('相似候选展示覆盖率', await page.locator('.similar-row').first().textContent().then((value) => value.includes('指纹覆盖')));
    check('相似候选没有删除捷径', await page.locator('.similar-row [data-action*="delete"]').count() === 0);
    await page.locator('[data-action="org-tab"][data-id="sample"]').click();
    await page.waitForURL(/\/sample$/);
    check('抽样显示有界数量', await page.locator('.sample-grid .tile').count() === 20);
    await page.locator('[data-action="org-tab"][data-id="audit"]').click();
    await page.waitForURL(/\/audit$/);
    await page.locator('[data-action="audit-detail"]').click();
    check('空壳详情保留文本文件', await page.locator('#modal').textContent().then((value) => value.includes('说明.txt')));
    await page.locator('#modal [data-action="close-modal"]').last().click();

    const mixed = await newPage();
    await mixed.goto(`${base}?scene=mixed&view=images`);
    await ready(mixed);
    await mixed.locator('#app [data-action="selection-start"]').click();
    await mixed.locator('#app .tile-check input').nth(0).check();
    await mixed.locator('#app .tile-check input').nth(1).check();
    await mixed.locator('#app [data-action="delete-selected"]').click();
    check('默认使用回收站', await mixed.locator('#modal [data-action="delete-confirm"]').textContent().then((value) => value.includes('移到回收站')));
    await mixed.locator('#modal [data-change="permanent"]').check();
    check('永久删除未确认不可提交', await mixed.locator('#modal [data-action="delete-confirm"]').isDisabled());
    await mixed.locator('#modal [data-change="confirm-permanent"]').check();
    check('永久删除明确确认后可提交', await mixed.locator('#modal [data-action="delete-confirm"]').isEnabled());
    await mixed.locator('#modal [data-change="permanent"]').uncheck();
    await mixed.locator('#modal [data-action="delete-confirm"]').click();
    check('删除展示逐项结果', await mixed.locator('.report-items li').count() === 2);
    check('回收失败保持失败状态', await mixed.locator('.report-items .failed').count() === 1);
    check('失败项仍保留在选择范围', await mixed.locator('#app .toolbar.selecting').count() === 1);
    check('回收失败没有转为永久删除', await mixed.locator('.report-items').textContent().then((value) => !value.includes('永久')));
    await screenshot(mixed, 'delete-result');
    await mixed.locator('#modal [data-action="retry-delete"]').click();
    check('可以只重试失败项', await mixed.locator('.report-items .failed').count() === 0);
    await mixed.locator('#modal [data-action="close-modal"]').last().click();
    check('成功项目才移出清单', await mixed.locator('#app .tile').count() === 6);

    for (const scene of ['offline', 'error', 'empty', 'stale', 'unique']) {
      const scenePage = await newPage();
      await scenePage.goto(`${base}?scene=${scene}${['stale', 'unique'].includes(scene) ? '&view=organize' : ''}`);
      await ready(scenePage);
      await layout(scenePage, scene);
      if (scene === 'offline') check('离线保留索引', await scenePage.locator('.notice').count() === 1 && await scenePage.locator('#app .tile').count() === 12);
      if (scene === 'error') {
        check('坏图只有单项错误', await scenePage.locator('.bad-media').count() === 1);
        await scenePage.locator('.bad-media [data-action="retry-image"]').click();
        check('坏图可以局部重试', await scenePage.locator('.bad-media').count() === 0);
      }
      if (scene === 'empty') check('空目录有明确状态', await scenePage.locator('.empty h2').textContent().then((value) => value.includes('还没有图片')));
      if (scene === 'stale') check('过期核验不能快捷删除', await scenePage.locator('[data-action="delete-verified"]').count() === 0);
      if (scene === 'unique') check('各有独有内容不能快捷删除', await scenePage.locator('[data-action="delete-verified"]').count() === 0);
      await scenePage.context().close();
    }

    const mobile = await newPage({ width: 390, height: 844 });
    await mobile.goto(base);
    await ready(mobile);
    await layout(mobile, '390 窄屏');
    check('窄屏默认两列', await mobile.locator('.grid').evaluate((item) => getComputedStyle(item).gridTemplateColumns.split(' ').length) === 2);
    await screenshot(mobile, 'browse-mobile');
    await mobile.locator('.mobile-menu').click();
    check('窄屏导航使用模态抽屉', await mobile.locator('#navigation').evaluate((item) => item.open && item.matches(':modal')));
    await mobile.locator('#navigation [data-action="folder"][data-id="buildings"]').click();
    await mobile.waitForURL(/\/buildings$/);
    await mobile.locator('#app [data-action="open-package"]').click();
    await mobile.waitForURL(/\/p\/buildings-architecture$/);
    await screenshot(mobile, 'images-mobile');
    await mobile.locator('#app [data-action="open-image"]').first().click();
    await mobile.locator('#viewer[open]').waitFor();
    await screenshot(mobile, 'viewer-mobile');
    check('竖图查看完整显示', await mobile.locator('.viewer-image').evaluate((item) => item.naturalHeight > item.naturalWidth && getComputedStyle(item).objectFit === 'contain'));
    await mobile.keyboard.press('Escape');
    await mobile.locator('#viewer').waitFor({ state: 'hidden' });
    await mobile.locator('#app .task-button').click();
    check('窄屏任务抽屉限制背景焦点', await mobile.locator('#panel').evaluate((item) => item.open && item.matches(':modal')));
    await screenshot(mobile, 'tasks-mobile');
    await mobile.keyboard.press('Escape');
    await mobile.locator('#panel').waitFor({ state: 'hidden' });
    await mobile.locator('.mobile-menu').click();
    await mobile.locator('#navigation [data-action="folder"][data-id="travel"]').click();
    await mobile.locator('#app [data-action="organize"]').click();
    await mobile.locator('[data-action="verify"]').click();
    await mobile.waitForFunction(() => document.querySelector('.verdict').textContent.includes('左侧被右侧完整包含'));
    await layout(mobile, '390 核验');
    await screenshot(mobile, 'organize-mobile');

    const longName = await newPage({ width: 390, height: 844 });
    await longName.goto(base);
    await ready(longName);
    await longName.evaluate(() => {
      window.WORKBENCH_DATA.groups[0].name = '这是一个很长的文件夹名称_' + 'LongUnbrokenDirectoryName'.repeat(8);
      window.WORKBENCH_DATA.photos[0].name = 'LongUnbrokenImagePackageName'.repeat(10);
      document.querySelector('#app [data-action="organize"]').click();
    });
    await longName.waitForURL(/\/organize\/compare$/);
    await layout(longName, '390 超长名称');
    await longName.locator('[data-action="org-tab"][data-id="similar"]').click();
    await longName.waitForURL(/\/similar$/);
    await layout(longName, '390 超长候选');

    check('无浏览器错误或图标缺失警告', errors.length === 0);
    check('样机没有 HTTP 请求', externalRequests.length === 0);
    const result = { checkedAt: new Date().toISOString(), browser: await browser.version(), checks: checks.length, passed: checks, contrastResults, errors, externalRequests };
    fs.writeFileSync(path.join(output, 'verification.json'), `${JSON.stringify(result, null, 2)}\n`);
    console.log(JSON.stringify({ checks: checks.length, browser: result.browser, output, errors, externalRequests }, null, 2));
  } finally { await browser.close(); }
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
