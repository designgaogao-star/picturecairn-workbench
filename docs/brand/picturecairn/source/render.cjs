// Render PictureCairn preview pages to PNG with headless Edge.
// usage: node render.cjs <manifest.json>
// manifest: [{ "html": "...", "png": "...", "width": 1600, "scale": 1 }]
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(path.resolve(__dirname, '../../../../node_modules/playwright-core'));

(async () => {
  const manifest = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  for (const job of manifest) {
    const page = await browser.newPage({
      viewport: { width: job.width, height: 200 },
      deviceScaleFactor: job.scale || 1,
      colorScheme: 'light',
    });
    await page.goto('file:///' + path.resolve(job.html).replace(/\\/g, '/'));
    await page.evaluate(() => window.__ready);
    await page.evaluate(() => document.fonts.ready);
    fs.mkdirSync(path.dirname(job.png), { recursive: true });
    await page.screenshot({ path: job.png, fullPage: true });
    await page.close();
    console.log(path.basename(job.png));
  }
  await browser.close();
})().catch((error) => { console.error(error); process.exit(1); });
