/**
 * preload：渲染进程与主进程之间唯一的通道。
 *
 * 现在前端还是直接 loadURL('http://127.0.0.1:8765')，走 HTTP，用不到 IPC。
 * 这个文件的用途是**先占住位置**：等阶段 3 把前端迁到 React 后，
 * 这里会暴露有限的白名单方法（打开文件夹、选择目录、显示通知等），
 * 而不是给渲染进程 nodeIntegration。保持 contextIsolation: true 不要动。
 */
const { contextBridge } = require('electron')

contextBridge.exposeInMainWorld('galleryApp', {
  isElectron: true,
  platform: process.platform,
  versions: {
    electron: process.versions.electron,
    chrome: process.versions.chrome,
  },
})
