// Private visual review only. Downloaded third-party marks stay in ignored output, outside the portable package.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const project = fileURLToPath(new URL('../', import.meta.url));
const output = path.join(project, 'output/brand/comparison');
await mkdir(output, { recursive: true });
const entries = [
  { name: 'Stillmark', file: 'docs/brand/stillmark/stillmark-app-icon.svg', note: 'D · 压角印，256px 母版' },
  { name: 'ImageGlass', url: 'https://raw.githubusercontent.com/d2phap/ImageGlass/develop/source/ImageGlass.Win32/icon256.ico',
    api: 'https://api.github.com/repos/d2phap/ImageGlass/contents/source/ImageGlass.Win32/icon256.ico?ref=develop', note: '项目官方仓库 Windows 图标' },
  { name: 'digiKam', url: 'https://www.digikam.org/favicon-32x32.png', note: '官方网站 32px 图标' },
  { name: 'XnView', url: 'https://www.xnview.com/ico/apple-touch-icon-144-precomposed.png', note: '官方网站 144px 图标' },
  { name: 'FastStone', url: 'https://ninite.com/static/app_icons2/L7R6BPJMEA2I5T2BHFY5PQMTYE.png',
    note: 'Ninite 的 FastStone 8.5 图标缓存；16px 放大', page: 'https://ninite.com/' },
  { name: 'Adobe Bridge', url: 'https://www.adobe.com/cc-shared/assets/img/product-icons/svg/bridge.svg', note: 'Adobe 官方 Bridge SVG' },
  { name: 'Eagle', url: 'https://eagle.cool/images/favicon.png', note: '官方网站图标' },
];
const outcomes = await Promise.allSettled(entries.map(async (entry, index) => {
  let data, mime;
  if (entry.file) { data = await readFile(path.join(project, entry.file)); mime = 'image/svg+xml'; }
  else {
    if (!process.argv.includes('--refresh')) {
      try { data = await readFile(path.join(output, `source-${index}`)); }
      catch (error) { if (error.code !== 'ENOENT') throw error; }
    }
    if (data) mime = entry.url.endsWith('.ico') ? 'image/x-icon' : entry.url.endsWith('.svg') ? 'image/svg+xml' : 'image/png';
    else {
      const response = await fetch(entry.api || entry.url, { signal: AbortSignal.timeout(20000) });
      assert.ok(response.ok, `${entry.name}: HTTP ${response.status}`);
      if (entry.api) {
        const file = await response.json();
        assert.equal(file.encoding, 'base64');
        data = Buffer.from(file.content, 'base64');
        mime = 'image/x-icon';
      } else {
        mime = response.headers.get('content-type').split(';')[0];
        assert.ok(mime.startsWith('image/'), `${entry.name}: expected an actual image`);
        data = Buffer.from(await response.arrayBuffer());
      }
    }
  }
  await writeFile(path.join(output, `source-${index}`), data);
  return { ...entry, sha256: createHash('sha256').update(data).digest('hex'), mime,
    data: `data:${mime};base64,${data.toString('base64')}` };
}));
const failures = outcomes.flatMap((result, index) => result.status === 'rejected' ? [`${entries[index].name}: ${result.reason.message}`] : []);
assert.deepEqual(failures, [], `Sources unavailable; partial downloads retained for the next run: ${failures.join('; ')}`);
const records = outcomes.map((result) => result.value);
const cards = records.map((entry, index) => `<section><h2>${entry.name}</h2><div class="large ${index === 4 ? 'pixels' : ''}"><img src="${entry.data}" width="80" height="80"></div><div class="sizes">${[16, 24, 32].map((size) => `<div><img src="${entry.data}" width="${size}" height="${size}"><span>${size}px</span></div>`).join('')}</div><p>${entry.note}</p></section>`).join('');
const html = `<!doctype html><meta charset="utf-8"><title>Stillmark 图标对照</title><style>*{box-sizing:border-box}body{margin:0;padding:40px;background:#f3f2ee;color:#1e2225;font:16px 'Segoe UI','Microsoft YaHei UI',sans-serif}h1{margin:0 0 12px;font-size:28px}header p{margin:0 0 28px;color:#5e676b}main{display:grid;grid-template-columns:repeat(7,1fr);gap:14px}section{padding:18px 12px;background:#fff;border:1px solid #d8dcde;border-radius:8px;text-align:center;min-width:0}h2{font-size:17px;margin:0 0 24px}.large{height:100px;display:grid;place-items:center}.pixels img{image-rendering:pixelated}.sizes{display:flex;justify-content:center;align-items:flex-start;gap:16px;height:72px;margin-top:22px}.sizes div{width:36px;display:flex;flex-direction:column;align-items:center;gap:6px}.sizes span{font-size:11px;color:#5e676b}.sizes div img{object-fit:contain}.large img{object-fit:contain}section p{font-size:11px;line-height:1.6;color:#5e676b;min-height:54px}.dark{background:#1e2225;padding:18px;margin-top:22px;border-radius:8px;display:flex;justify-content:space-around}.dark div{text-align:center;color:#f3f2ee;font-size:12px;display:flex;align-items:center;gap:10px}.dark img{object-fit:contain}footer{margin-top:26px;line-height:1.7;font-size:13px;color:#5e676b}</style><header><h1>Stillmark · D「压角印」与同类工具图标</h1><p>构形、色彩与实际小尺寸对照；第三方图标归各自权利人，仅用于本机设计复核。</p></header><main>${cards}</main><div class="dark">${records.map((entry) => `<div><img src="${entry.data}" width="32" height="32">${entry.name}</div>`).join('')}</div><footer>Stillmark 由大画面、小印与切缝构成。此页验证视觉区分，不能代替名称或商标检索。<br>FastStone 官网本轮无法访问，图标来自 Ninite 对其 8.5 版本的缓存，已单独注明；其余来源与文件摘要保存于 sources.json。</footer>`;
await writeFile(path.join(output, 'index.html'), html);
const browser = await chromium.launch({ channel: 'msedge', headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1600, height: 700 }, deviceScaleFactor: 1 });
  await page.goto(new URL('file:///' + path.join(output, 'index.html').replaceAll('\\', '/')).href);
  await page.locator('img').evaluateAll((images) => Promise.all(images.map((image) => image.decode())));
  await page.screenshot({ path: path.join(output, 'comparison.png'), fullPage: true });
} finally { await browser.close(); }
await writeFile(path.join(output, 'sources.json'), JSON.stringify({ created: new Date().toISOString(),
  icons: records.map(({ data: _data, ...entry }) => entry) }, null, 2));
console.log(`Comparison: ${path.join(output, 'comparison.png')}`);
