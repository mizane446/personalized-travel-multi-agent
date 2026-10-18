// Test harness only: keep the real upstream Desktop off the user's foreground.
const electron = require('electron');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
electron.app.on('browser-window-created', (_event, window) => {
  window.webContents.setBackgroundThrottling(false);
});
for (const method of ['show', 'showInactive', 'focus', 'moveTop']) {
  electron.BrowserWindow.prototype[method] = function () {};
}
const desktop = path.resolve(__dirname, '../../apps/desktop');
electron.app.setAppPath(desktop);
import(pathToFileURL(path.join(desktop, 'dist/electron-main.mjs')).href);
