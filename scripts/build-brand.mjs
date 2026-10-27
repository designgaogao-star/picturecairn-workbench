import { execFileSync } from 'node:child_process';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const project = fileURLToPath(new URL('../', import.meta.url));
const source = path.join(project, 'docs/brand/picturecairn');
const output = path.join(project, 'output/brand/runtime');
await mkdir(output, { recursive: true });
const jobs = [];
for (const size of [16, 24, 32, 48, 64, 128, 256]) jobs.push({ size, file: `app-${size}.png`,
  source: size === 24 ? 'extra/picturecairn-app-icon-24.svg' : size <= 32 ? 'picturecairn-favicon.svg' : 'picturecairn-app-icon.svg' });
for (const [size, suffix] of [[16, ''], [20, '@1.25x'], [24, '@1.5x'], [32, '@2x']]) {
  for (const white of [false, true]) jobs.push({ size, file: `tray${white ? '-white' : ''}${suffix}.png`,
    source: size === 20 || size === 24 ? `extra/picturecairn-tray-${size}${white ? '-white' : ''}.svg`
      : white ? 'extra/picturecairn-tray-white.svg' : 'picturecairn-tray.svg' });
}
jobs.push({ size: 512, file: 'github-avatar.png', source: 'extra/picturecairn-avatar.svg' });
const browser = await chromium.launch({ channel: 'msedge', headless: true });
try {
  const page = await browser.newPage({ deviceScaleFactor: 1 });
  for (const job of jobs) {
    await page.setViewportSize({ width: job.size, height: job.size });
    const svg = await readFile(path.join(source, job.source));
    await page.setContent(`<style>html,body{margin:0;background:transparent}img{display:block;width:${job.size}px;height:${job.size}px}</style><img src="data:image/svg+xml;base64,${svg.toString('base64')}">`);
    await page.locator('img').evaluate((image) => image.decode());
    await page.screenshot({ path: path.join(output, job.file), omitBackground: true });
  }
} finally { await browser.close(); }
await writeFile(path.join(output, 'renders.json'), JSON.stringify(jobs, null, 2) + '\n');
execFileSync(path.join(project, '.venv/Scripts/python.exe'), ['scripts/brand_assets.py', '--output', output],
  { cwd: project, stdio: 'inherit', windowsHide: true });
console.log(`Brand assets: ${output}`);
