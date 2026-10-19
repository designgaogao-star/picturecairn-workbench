/**
 * Electron 主进程：把「一个 Python 脚本 + 浏览器标签页」变成「一个应用」。
 *
 * 职责：
 *   1. 单实例锁 —— 第二次双击把已有窗口提到前台，不起第二个进程
 *   2. 启动画面 —— 先出 Logo，Python 就绪后再切主界面，避免白屏干等
 *   3. Python sidecar —— 开发用系统 Python，打包后用 PyInstaller 产物；退出时一并杀掉
 *   4. 窗口状态记忆 —— 位置/大小/最大化，重启后还原
 *
 * 刻意没做的：不用无边框自绘标题栏。现有前端没有预留拖拽区，
 * 强行无边框会让窗口没法移动 —— 等阶段 3 重做 UI 时一起改。
 */
const { app, BrowserWindow, shell, dialog, Tray, Menu, nativeImage } = require('electron')
const path = require('node:path')
const fs = require('node:fs')
const http = require('node:http')
const { spawn } = require('node:child_process')

const PORT = Number(process.env.GALLERY_PORT || 8765)
const BASE = `http://127.0.0.1:${PORT}`
const IS_DEV = process.argv.includes('--dev')

// 【必须在任何 getPath('userData') 之前固定应用名】
// 否则 userData 会跟着 package.json 的 `name`（gallery-tool）走，
// 而用户/文档里看到的是产品名（GalleryTool）—— 配置写到哪个目录全靠猜。
// 打包后 electron-builder 会设成 productName，但目录形式（resources/app）不会。
app.setName('GalleryTool')
if (process.env.GALLERY_DATA) {
  fs.mkdirSync(process.env.GALLERY_DATA, { recursive: true })
  app.setPath('userData', path.resolve(process.env.GALLERY_DATA))
}

let mainWin = null
let splashWin = null
let tray = null
let pyProc = null
let quitting = false

// ---------------------------------------------------------------- 单实例
if (!app.requestSingleInstanceLock()) {
  app.quit()
} else {
  app.on('second-instance', () => {
    if (mainWin) {
      if (mainWin.isMinimized()) mainWin.restore()
      mainWin.show()
      mainWin.focus()
    }
  })
  app.whenReady().then(boot)
}

// ---------------------------------------------------------------- 窗口状态
function stateFile() {
  return path.join(app.getPath('userData'), 'window-state.json')
}

function loadWindowState() {
  const fallback = { width: 1600, height: 1000 }
  try {
    const s = JSON.parse(fs.readFileSync(stateFile(), 'utf8'))
    // 校验：上次可能停在已拔掉的副屏上，那种坐标会让窗口"消失"
    const ok = Number.isFinite(s.x) && Number.isFinite(s.y) &&
      s.width >= 900 && s.height >= 600
    return ok ? s : { ...fallback, ...s, x: undefined, y: undefined }
  } catch {
    return fallback
  }
}

function saveWindowState() {
  if (!mainWin || mainWin.isDestroyed()) return
  try {
    const b = mainWin.getNormalBounds ? mainWin.getNormalBounds() : mainWin.getBounds()
    fs.writeFileSync(stateFile(), JSON.stringify({ ...b, maximized: mainWin.isMaximized() }))
  } catch { /* 状态丢了不影响使用 */ }
}

// ---------------------------------------------------------------- HTTP 探活
function ping(timeout = 1200) {
  return new Promise((resolve) => {
    const req = http.get(`${BASE}/api/ping`, { timeout }, (res) => {
      res.resume()
      resolve(res.statusCode === 200)
    })
    req.on('error', () => resolve(false))
    req.on('timeout', () => { req.destroy(); resolve(false) })
  })
}

async function waitForServer(ms = 90000) {
  const t0 = Date.now()
  while (Date.now() - t0 < ms) {
    if (await ping()) return true
    await new Promise((r) => setTimeout(r, 400))
  }
  return false
}

// ---------------------------------------------------------------- Python sidecar
function readGalleryRoot() {
  /** 打包版从 userData/config.json 读图库根目录；没配就返回空串。 */
  try {
    const cfgPath = path.join(app.getPath('userData'), 'config.json')
    let raw = fs.readFileSync(cfgPath, 'utf8')
    // 【必须剥 BOM】PowerShell 的 `Set-Content -Encoding UTF8` 会写入 BOM，
    // 而 JSON.parse 遇到 BOM 直接抛 SyntaxError —— 表现是"配置明明写了却没生效"。
    // 让人去查编码问题太难，这里主动兼容。
    if (raw.charCodeAt(0) === 0xFEFF) raw = raw.slice(1)
    const cfg = JSON.parse(raw)
    if (cfg.root && fs.existsSync(cfg.root)) return cfg.root
    if (cfg.root) console.warn('[config] 配置的 root 不存在:', cfg.root)
  } catch (e) {
    console.warn('[config] 读取失败:', e.message)
  }
  return ''
}

function resolvePython() {
  // 打包后：resources/backend/gallery_server.exe（PyInstaller --onedir 产物）
  const packed = path.join(process.resourcesPath, 'backend', 'gallery_server.exe')
  if (app.isPackaged && fs.existsSync(packed)) {
    return { cmd: packed, args: ['--no-open', '--port', String(PORT)], cwd: path.dirname(packed) }
  }
  // 开发态：优先环境变量，其次 pythonw（无控制台），最后 python
  const toolDir = path.join(__dirname, '..')
  const localPython = path.join(process.env.LOCALAPPDATA || '', 'Programs', 'Python', 'Python312', 'pythonw.exe')
  const cmd = process.env.GALLERY_PYTHON || (fs.existsSync(localPython) ? localPython : 'pythonw.exe')
  return { cmd, args: [path.join(toolDir, 'gallery_server.py'), '--no-open', '--port', String(PORT)], cwd: toolDir }
}

async function startBackend() {
  // 已经在跑（用户之前用 vbs 起过）就直接复用，不重复绑端口
  if (await ping()) {
    console.log('[sidecar] 已有实例在跑，复用')
    return true
  }
  const { cmd, args, cwd } = resolvePython()
  console.log('[sidecar] 启动:', cmd, args.join(' '))
  try {
    // 【打包后数据必须写到用户目录】
    // exe 装在 C:\Program Files\ 下时，它自己所在的目录是只读的 —— 数据库、
    // 缩略图、审查状态全都写不进去，表现是"能打开但什么都记不住"。
    // 开发态不设 GALLERY_DATA，仍写在工具目录（行为不变）。
    const env = { ...process.env, PYTHONIOENCODING: 'utf-8' }
    if (app.isPackaged) {
      env.GALLERY_DATA = env.GALLERY_DATA || app.getPath('userData')
      // 图库根目录从 userData/config.json 读（{"root": "F:\\图库"}）。
      // 不猜默认值 —— 猜错了会静默指向一个空目录，用户看到"125 组不见了"却不知道为什么。
      const root = env.GALLERY_ROOT || readGalleryRoot()
      if (root) env.GALLERY_ROOT = root
    }
    pyProc = spawn(cmd, args, {
      cwd,
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true,
      env,
    })
  } catch (e) {
    console.error('[sidecar] spawn 失败', e)
    return false
  }
  pyProc.stdout.on('data', (d) => IS_DEV && process.stdout.write(`[py] ${d}`))
  pyProc.stderr.on('data', (d) => process.stderr.write(`[py:err] ${d}`))
  pyProc.on('error', (error) => {
    console.error('[sidecar] 无法启动:', error.message)
    pyProc = null
  })
  pyProc.on('exit', (code) => {
    console.log('[sidecar] 退出，code =', code)
    pyProc = null
    // 非主动退出且主窗口还开着 → 说明后端崩了，要告诉用户而不是白屏
    if (!quitting && mainWin && !mainWin.isDestroyed()) {
      dialog.showErrorBox('后端已停止',
        `图库服务异常退出（code=${code}）。\n\n请查看日志：${path.join(app.isPackaged ? app.getPath('userData') : cwd, 'cache', 'server.log')}`)
    }
  })
  return waitForServer()
}

function stopBackend() {
  if (!pyProc) return
  try {
    // Windows 上 kill 不会带走子进程树，用 taskkill /T 才干净
    if (process.platform === 'win32') {
      spawn('taskkill', ['/pid', String(pyProc.pid), '/T', '/F'], { windowsHide: true })
    } else {
      pyProc.kill('SIGTERM')
    }
  } catch { /* 进程可能已退出 */ }
  pyProc = null
}

// ---------------------------------------------------------------- 窗口
function createSplash() {
  splashWin = new BrowserWindow({
    width: 420, height: 300, frame: false, resizable: false,
    transparent: false, backgroundColor: '#16171b', show: true,
    alwaysOnTop: true, skipTaskbar: true, center: true,
    webPreferences: { contextIsolation: true },
  })
  splashWin.loadFile(path.join(__dirname, 'splash.html'))
}

function createMain() {
  const st = loadWindowState()
  mainWin = new BrowserWindow({
    width: st.width || 1600,
    height: st.height || 1000,
    x: st.x, y: st.y,
    minWidth: 1100, minHeight: 700,
    backgroundColor: '#16171b',
    show: false,
    title: 'GalleryTool',
    autoHideMenuBar: true,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      preload: path.join(__dirname, 'preload.js'),
    },
  })
  if (st.maximized) mainWin.maximize()

  mainWin.loadURL(BASE)

  mainWin.once('ready-to-show', () => {
    mainWin.show()
    if (splashWin && !splashWin.isDestroyed()) {
      splashWin.close()
      splashWin = null
    }
  })

  // 外链走系统浏览器，不要在应用里开新窗口
  mainWin.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url)
    return { action: 'deny' }
  })

  mainWin.on('close', (e) => {
    saveWindowState()
    // 点 X = 收进托盘，不退出。缩略图预热和去重索引都在后台继续跑，
    // 下次点托盘图标是秒回，而不是重新等一遍索引。
    if (!quitting && tray) {
      e.preventDefault()
      mainWin.hide()
    }
  })
  mainWin.on('closed', () => { mainWin = null })
}

// ---------------------------------------------------------------- 托盘
function showMain() {
  if (!mainWin) { createMain(); return }
  if (mainWin.isMinimized()) mainWin.restore()
  mainWin.show()
  mainWin.focus()
}

function createTray() {
  const iconPath = path.join(__dirname, 'tray.png')
  let img = nativeImage.createFromPath(iconPath)
  if (img.isEmpty()) {
    // 图标丢了也不能让应用起不来 —— 用 16x16 的纯色块兜底
    img = nativeImage.createEmpty()
  }
  tray = new Tray(img.resize({ width: 16, height: 16 }))
  tray.setToolTip('GalleryTool · 图片库')
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: '显示主窗口', click: showMain },
    { label: '在浏览器中打开', click: () => shell.openExternal(BASE) },
    { type: 'separator' },
    {
      label: '打开日志目录',
      click: () => shell.openPath(path.join(app.isPackaged ? app.getPath('userData') : path.join(__dirname, '..'), 'cache')),
    },
    {
      label: '打开图库根目录',
      click: () => shell.openPath(process.env.GALLERY_ROOT || readGalleryRoot() || path.join(__dirname, '..', '..')),
    },
    { type: 'separator' },
    {
      label: '退出（同时停止后端）',
      click: () => { quitting = true; app.quit() },
    },
  ]))
  tray.on('click', showMain)          // 左键单击 = 显示/聚焦
  tray.on('double-click', showMain)
}

// ---------------------------------------------------------------- 启动
async function boot() {
  createSplash()

  const ok = await startBackend()

  if (!ok) {
    if (splashWin && !splashWin.isDestroyed()) splashWin.close()
    dialog.showErrorBox('无法启动图库服务',
      'Python 后端没能在 90 秒内就绪。\n\n' +
      '常见原因：\n' +
      '· 缺少 Pillow / numpy\n' +
      '· 8765 端口被别的程序占用\n' +
      '· 图库根目录不可访问\n\n' +
      '可以先用「启动图库预览.bat」看看具体报错。')
    app.quit()
    return
  }

  createTray()          // 必须在 createMain 之前：close 事件里要判断 tray 是否存在
  createMain()
}

app.on('window-all-closed', () => {
  // 有托盘时关窗只是 hide()，根本不会走到这里。
  // 能走到这里说明托盘也没了（或没建起来），该退出并带走后端。
  if (tray) return
  quitting = true
  stopBackend()
  if (process.platform !== 'darwin') app.quit()
})

app.on('before-quit', () => {
  quitting = true
  saveWindowState()
  stopBackend()
})
