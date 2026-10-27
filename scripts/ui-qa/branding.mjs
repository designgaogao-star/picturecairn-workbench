import assert from 'node:assert/strict';
import { writeFile } from 'node:fs/promises';
import path from 'node:path';

const product = 'PictureCairn 影标图片工作台';

export async function brandingChecks(page, base, output, application) {
  const checks = [];
  const check = (name, result) => { assert.ok(result, name); checks.push(name); };
  check('网页标题使用完整产品名', await page.title() === product);
  check('查看器品牌锚点使用白色单色稿', await page.locator('.viewer-brand path').evaluateAll((paths) =>
    paths.length > 0 && paths.every((element) => getComputedStyle(element).fill === 'rgb(255, 255, 255)')));
  await page.setViewportSize({ width: 1440, height: 1000 });
  const library = (await (await fetch(base + '/api/v1/libraries')).json()).items[0];
  await page.goto(`${base}#/l/${library.id}`);
  await page.locator('.library-home').waitFor();
  if (!await page.locator('.sidebar').count()) await page.getByRole('button', { name: '切换侧栏', exact: true }).click();
  for (const [theme, system] of [['浅色', 'dark'], ['深色', 'light']]) {
    await page.emulateMedia({ colorScheme: system });
    await page.getByRole('button', { name: '外观', exact: true }).click();
    await page.getByRole('menuitemradio', { name: theme, exact: true }).click();
    const logo = page.locator('.sidebar .brand');
    check(`${theme}标志使用正文颜色`, await logo.locator('.brand-mark svg').evaluate((svg) =>
      getComputedStyle(svg.querySelector('path')).fill === getComputedStyle(svg).color));
    check(`${theme}标志保留朱色印`, await logo.locator('.brand-mark path').last().evaluate((element) =>
      getComputedStyle(element).fill === 'rgb(226, 83, 42)'));
    check(`${theme}字标使用确认的路径稿`, await logo.locator('.brand-wordmark path').count() > 0);
    await page.screenshot({ path: path.join(output, `brand-workbench-${theme === '浅色' ? 'light' : 'dark'}.png`), animations: 'disabled' });
  }
  const favicon = await page.locator('link[rel="icon"]').getAttribute('href');
  const response = await fetch(new URL(favicon, page.url()));
  check('正式 favicon 可读取', response.ok && (await response.text()).includes('PictureCairn'));

  // Hold only the isolated backend's library read so the otherwise brief startup state can be inspected.
  for (const mode of ['light', 'dark']) {
    await page.evaluate((value) => localStorage.setItem('gt.theme', value), mode);
    let release;
    const gate = new Promise((resolve) => { release = resolve; });
    const hold = async (route) => { await gate; await route.continue().catch(() => {}); };
    await page.route('**/api/v1/libraries?*', hold);
    try {
      await page.reload({ waitUntil: 'domcontentloaded' });
      await page.locator('.brand-splash').waitFor();
      check(`${mode}启动页使用转曲组合`, await page.locator('.brand-splash path').count() > 0);
      await page.screenshot({ path: path.join(output, `brand-startup-${mode}.png`), animations: 'disabled' });
    } finally { release(); await page.unroute('**/api/v1/libraries?*', hold); }
    await page.locator('.library-home').waitFor();
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator('.sidebar').waitFor({ state: 'detached' });
  await page.getByRole('button', { name: '切换侧栏', exact: true }).click();
  check('窄屏侧栏标志可见', await page.locator('.sidebar .brand').isVisible());
  check('窄屏品牌区无横向溢出', await page.locator('.side-head').evaluate((header) => header.scrollWidth <= header.clientWidth));
  await page.screenshot({ path: path.join(output, 'brand-sidebar-narrow.png'), animations: 'disabled' });
  await page.keyboard.press('Escape');
  await page.setViewportSize({ width: 1440, height: 1000 });

  if (application) {
    const native = await application.evaluate(({ app, nativeImage, nativeTheme, Tray }) => {
      const fs = process.getBuiltinModule('fs');
      const path = process.getBuiltinModule('path');
      const root = app.getAppPath();
      const load = process.getBuiltinModule('module').createRequire(path.join(root, 'package.json'));
      const helper = load(path.join(root, 'electron/brand.cjs'));
      const directory = app.isPackaged ? path.join(root, 'electron/brand') : path.join(root, 'output/brand/runtime');
      const variants = [];
      for (const dark of [false, true]) {
        const image = helper.trayImage(directory, dark);
        for (const [scale, suffix] of [[1, ''], [1.25, '@1.25x'], [1.5, '@1.5x'], [2, '@2x']]) {
          const expected = nativeImage.createFromBuffer(fs.readFileSync(path.join(directory, `tray${dark ? '-white' : ''}${suffix}.png`)));
          variants.push({ dark, scale, passed: image.toBitmap({ scaleFactor: scale }).equals(expected.toBitmap()) });
        }
      }
      let refreshed = false;
      const original = Tray.prototype.setImage;
      Tray.prototype.setImage = function(image) {
        const expected = helper.trayImage(directory, nativeTheme.shouldUseDarkColorsForSystemIntegratedUI);
        refreshed = image.toBitmap().equals(expected.toBitmap());
        return original.call(this, image);
      };
      try { nativeTheme.emit('updated'); }
      finally { Tray.prototype.setImage = original; }
      return { name: app.getName(), id: helper.APP_USER_MODEL_ID, variants, refreshed };
    });
    check('桌面应用使用完整产品名', native.name === product);
    check('Windows 应用标识有独立命名空间', native.id === 'GalleryTool.PictureCairnWorkbench');
    check('黑白托盘四种缩放像素正确', native.variants.length === 8 && native.variants.every((item) => item.passed));
    check('系统主题更新会刷新托盘', native.refreshed);
  }
  await writeFile(path.join(output, 'brand-verification.json'), JSON.stringify({ checks }, null, 2));
  console.log(`PASS brand integration: ${checks.length} checks; app theme, startup, favicon, narrow, ${application ? 'native tray variants/theme event' : 'browser'}`);
}
