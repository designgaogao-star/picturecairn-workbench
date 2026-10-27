'use strict';
const { contextBridge, webFrame } = require('electron');

// Read-only benchmark instrumentation; never packaged with the application.
contextBridge.exposeInMainWorld('__picturecairnResourceUsage', {
  read: () => webFrame.getResourceUsage(),
});
