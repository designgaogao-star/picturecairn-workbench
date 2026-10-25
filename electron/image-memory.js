'use strict';
const { contextBridge, ipcRenderer, webFrame } = require('electron');

const MiB = 1024 * 1024;
const idleBudget = 128 * MiB;
const activeOverhead = 96 * MiB;
let scheduled = false;
let lastTrim = -Infinity;

// A release hint follows a real image leaving the UI. Keep one check in flight;
// active images retain their allowance, and HTTP/disk caches remain intact.
function release() {
  if (scheduled) return;
  scheduled = true;
  setTimeout(async () => {
    try {
      if (performance.now() - lastTrim < 10000) return;
      const privateKiB = await ipcRenderer.invoke('gallery:renderer-memory');
      const liveImages = webFrame.getResourceUsage().images.liveSize;
      if (privateKiB * 1024 > Math.max(idleBudget, liveImages + activeOverhead)) {
        webFrame.clearCache();
        lastTrim = performance.now();
      }
    } catch (error) {
      console.warn('Image memory budget check failed:', error.message);
    } finally {
      scheduled = false;
    }
  }, 1000);
}

contextBridge.exposeInMainWorld('galleryImageResources', { release });
