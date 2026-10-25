import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const code = await readFile(fileURLToPath(new URL('../../electron/image-memory.js', import.meta.url)), 'utf8');
const MiB = 1024 * 1024;
function policy(privateMiB, liveMiB) {
  let exposed, trims = 0, reads = 0, now = 0;
  const timers = [];
  const electron = {
    contextBridge: { exposeInMainWorld(name, api) { assert.equal(name, 'galleryImageResources'); exposed = api; } },
    ipcRenderer: { async invoke(channel) { assert.equal(channel, 'gallery:renderer-memory'); reads++; return privateMiB * 1024; } },
    webFrame: { getResourceUsage: () => ({ images: { liveSize: liveMiB * MiB } }), clearCache: () => { trims++; } },
  };
  vm.runInNewContext(code, { require: (name) => { assert.equal(name, 'electron'); return electron; },
    setTimeout: (callback) => timers.push(callback), performance: { now: () => now }, console });
  return { release: () => exposed.release(), tick: async () => { const callback = timers.shift(); assert.ok(callback); await callback(); },
    counts: () => ({ trims, reads, pending: timers.length }), advance: (ms) => { now += ms; } };
}

const light = policy(96, 8);
for (let index = 0; index < 100; index++) light.release();
assert.deepEqual(light.counts(), { trims: 0, reads: 0, pending: 1 }, 'Scrolling releases share one pending check');
await light.tick();
assert.deepEqual(light.counts(), { trims: 0, reads: 1, pending: 0 }, 'A small renderer keeps its warm cache');

const heavy = policy(180, 8);
heavy.release(); await heavy.tick();
assert.equal(heavy.counts().trims, 1, 'Unused resources above the soft budget are reclaimed');
heavy.release(); await heavy.tick();
assert.equal(heavy.counts().reads, 1, 'A recent trim avoids another memory query');
heavy.advance(10000); heavy.release(); await heavy.tick();
assert.equal(heavy.counts().trims, 2, 'Later resource releases can reclaim again');

const active = policy(220, 160);
active.release(); await active.tick();
assert.equal(active.counts().trims, 0, 'Large active images retain their allowance');
console.log('PASS image memory policy: coalescing, soft budget, cooldown and active image allowance');
