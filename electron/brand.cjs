'use strict';
const fs = require('node:fs');
const path = require('node:path');
const { nativeImage } = require('electron');

const PRODUCT_NAME = 'Stillmark 影迹图片工作台';
const APP_USER_MODEL_ID = 'GalleryTool.StillmarkWorkbench';

function trayImage(directory, dark) {
  const image = nativeImage.createEmpty();
  for (const [scaleFactor, suffix] of [[1, ''], [1.25, '@1.25x'], [1.5, '@1.5x'], [2, '@2x']]) {
    image.addRepresentation({ scaleFactor, buffer: fs.readFileSync(path.join(directory, `tray${dark ? '-white' : ''}${suffix}.png`)) });
  }
  return image;
}

module.exports = { PRODUCT_NAME, APP_USER_MODEL_ID, trayImage };
