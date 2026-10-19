'use strict';
const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('galleryApp', {
  isElectron: true,
  chooseDirectory: () => ipcRenderer.invoke('gallery:choose-directory'),
});
