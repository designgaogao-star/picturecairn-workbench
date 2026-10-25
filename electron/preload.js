'use strict';
const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('galleryApp', {
  isElectron: true,
  sessionId: process.argv.find((argument) => argument.startsWith('--gallery-ui-session='))?.slice('--gallery-ui-session='.length),
  theme: process.argv.find((argument) => argument.startsWith('--gallery-theme='))?.slice('--gallery-theme='.length),
  loadPreferences: () => ipcRenderer.invoke('gallery:preferences'),
  chooseDirectory: () => ipcRenderer.invoke('gallery:choose-directory'),
});
