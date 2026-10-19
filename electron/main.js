'use strict';
const { app, BrowserWindow, dialog, ipcMain, Tray, Menu, shell } = require('electron');
const { spawn } = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs');
const crypto = require('node:crypto');
const http = require('node:http');

app.setName('GalleryTool');
const data = path.resolve(process.env.GALLERY_DATA || path.join(process.env.LOCALAPPDATA || path.join(app.getPath('home'), 'AppData', 'Local'), 'GalleryTool'));
fs.mkdirSync(data, { recursive: true });
app.setPath('userData', data);
const token = crypto.randomBytes(32).toString('hex');
const readyFile = path.join(data, `desktop-${process.pid}.json`);
let backend, mainWindow, tray, base, quitting = false, quitStarted = false;

function request(url, method = 'GET', headers = {}) {
  return new Promise((resolve, reject) => {
    const req = http.request(url, { method, headers, timeout: 3000 }, (res) => {
      let body = ''; res.setEncoding('utf8'); res.on('data', (chunk) => { body += chunk; });
      res.on('end', () => res.statusCode < 400 ? resolve(body ? JSON.parse(body) : {}) : reject(new Error(`HTTP ${res.statusCode}`)));
    });
    req.on('error', reject); req.on('timeout', () => req.destroy(new Error('Backend timeout'))); req.end();
  });
}
async function startBackend() {
  const serviceFile = path.join(data, 'service.json');
  if (fs.existsSync(serviceFile)) {
    try {
      const descriptor = JSON.parse(fs.readFileSync(serviceFile, 'utf8'));
      const health = await request(descriptor.url + '/api/v1/health');
      if (health.api_version === '1' && health.instance_id === descriptor.instance_id) {
        base = descriptor.url;
        return;
      }
    } catch (error) { console.warn('Background service unavailable:', error.message); }
  }
  const project = path.join(__dirname, '..');
  const packed = path.join(process.resourcesPath, 'backend', 'gallery_server.exe');
  const python = process.env.GALLERY_PYTHON || path.join(project, '.venv', 'Scripts', 'python.exe');
  const command = app.isPackaged ? packed : python;
  const args = app.isPackaged ? [] : ['-m', 'gallery'];
  args.push('--port', '0', '--data', data, '--ready-file', readyFile, '--no-open');
  const log = fs.openSync(path.join(data, 'desktop-backend.log'), 'a');
  let spawnError;
  backend = spawn(command, args, { cwd: app.isPackaged ? path.dirname(packed) : project,
    env: { ...process.env, GALLERY_DATA: data, GALLERY_APPLICATION: app.isPackaged ? path.dirname(process.execPath) : project,
      GALLERY_DESKTOP_TOKEN: token, PYTHONIOENCODING: 'utf-8' },
    stdio: ['ignore', log, log], windowsHide: true });
  fs.closeSync(log);
  backend.on('error', (error) => { spawnError = error; });
  backend.on('exit', (code) => {
    if (!quitting && mainWindow && !mainWindow.isDestroyed()) {
      dialog.showErrorBox('图库服务已停止', `退出码：${code}\n日志：${path.join(data, 'server.log')}`);
    }
  });
  const until = Date.now() + 30000;
  while (Date.now() < until) {
    if (spawnError) throw spawnError;
    if (backend.exitCode !== null) throw new Error(`图库服务启动失败，退出码 ${backend.exitCode}`);
    if (fs.existsSync(readyFile)) {
      let descriptor;
      try { descriptor = JSON.parse(fs.readFileSync(readyFile, 'utf8')); }
      catch (error) {
        if (!['EACCES', 'EPERM', 'ENOENT'].includes(error.code)) throw error;
        await new Promise((resolve) => setTimeout(resolve, 50)); continue;
      }
      const health = await request(descriptor.url + '/api/v1/health');
      if (health.api_version !== '1' || health.instance_id !== descriptor.instance_id
          || descriptor.session_id !== crypto.createHash('sha256').update(token).digest('hex')) {
        throw new Error('图库服务版本或实例不匹配');
      }
      base = descriptor.url;
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  throw new Error(`图库服务启动超时\n日志：${path.join(data, 'server.log')}`);
}
function windowState() {
  try { return JSON.parse(fs.readFileSync(path.join(data, 'window-state.json'), 'utf8')); }
  catch { return { width: 1600, height: 1000 }; }
}
function createWindow() {
  const saved = windowState();
  mainWindow = new BrowserWindow({ width: Math.max(700, saved.width || 1600), height: Math.max(500, saved.height || 1000),
    minWidth: 700, minHeight: 500, backgroundColor: '#161718', show: false, title: '图库', autoHideMenuBar: true,
    webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true, preload: path.join(__dirname, 'preload.js') } });
  if (saved.maximized) mainWindow.maximize();
  mainWindow.loadURL(base);
  mainWindow.once('ready-to-show', () => mainWindow.show());
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//.test(url)) shell.openExternal(url);
    return { action: 'deny' };
  });
  mainWindow.webContents.on('will-navigate', (event, url) => {
    if (new URL(url).origin !== base) event.preventDefault();
  });
  mainWindow.on('close', (event) => {
    fs.writeFileSync(path.join(data, 'window-state.json'), JSON.stringify({ ...mainWindow.getNormalBounds(), maximized: mainWindow.isMaximized() }));
    if (!quitting && tray) { event.preventDefault(); mainWindow.hide(); }
  });
}
async function stopBackend() {
  if (!backend || backend.exitCode !== null) return;
  if (base) await request(base + '/api/v1/system/shutdown', 'POST', { 'X-Gallery-Desktop': token }).catch(() => {});
  const until = Date.now() + 25000;
  while (backend.exitCode === null && Date.now() < until) await new Promise((resolve) => setTimeout(resolve, 50));
  if (backend.exitCode === null) backend.kill();
  fs.rmSync(readyFile, { force: true });
}
ipcMain.handle('gallery:choose-directory', async (event) => {
  if (!mainWindow || event.sender !== mainWindow.webContents || !base || new URL(event.senderFrame.url).origin !== base) return null;
  const result = await dialog.showOpenDialog(mainWindow, { properties: ['openDirectory'], title: '添加图库' });
  return result.canceled ? null : result.filePaths[0];
});
if (!app.requestSingleInstanceLock()) app.quit();
else {
  app.on('second-instance', (_event, argv) => {
    if (argv.includes('--quit')) { app.quit(); return; }
    if (mainWindow) { mainWindow.show(); mainWindow.focus(); }
  });
  app.whenReady().then(async () => {
    try {
      await startBackend(); createWindow();
      tray = new Tray(path.join(__dirname, 'tray.png'));
      tray.setToolTip('图库');
      tray.setContextMenu(Menu.buildFromTemplate([{ label: '打开图库', click: () => mainWindow.show() }, { label: '退出', click: () => app.quit() }]));
      tray.on('double-click', () => mainWindow.show());
    } catch (error) { dialog.showErrorBox('无法启动图库', error.message); app.quit(); }
  });
  app.on('before-quit', (event) => {
    quitting = true;
    if (quitStarted) return;
    event.preventDefault(); quitStarted = true;
    stopBackend().finally(() => { tray?.destroy(); app.quit(); });
  });
}
