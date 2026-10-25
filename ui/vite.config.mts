import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';

// Explicit ESM keeps the config compatible with Vite's native loader and CommonJS Electron.
// The dev server proxies /api to a running backend on the same origin, so the backend's
// Origin check never sees the dev port. GALLERY_BACKEND selects a temporary QA backend.
const backend = process.env.GALLERY_BACKEND || 'http://127.0.0.1:8765';

export default defineConfig({
  root: fileURLToPath(new URL('.', import.meta.url)),
  base: '/',
  oxc: { jsx: { runtime: 'automatic', importSource: 'preact' } },
  server: {
    host: '127.0.0.1',
    port: Number(process.env.GALLERY_UI_PORT || 5173),
    strictPort: true,
    proxy: {
      '/api': {
        target: backend,
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on('proxyReq', (request) => request.removeHeader('origin'));
          // An upstream that dies mid-response (the SSE stream when the backend stops) must drop the browser side
          // too; otherwise EventSource keeps a silent stream open and never notices the backend went away.
          proxy.on('proxyRes', (upstream, _request, response) => {
            upstream.on('close', () => { if (!upstream.complete) response.destroy(); });
          });
        },
      },
    },
  },
  build: { outDir: 'dist', emptyOutDir: true, target: 'chrome130', assetsInlineLimit: 0, chunkSizeWarningLimit: 400 },
});
