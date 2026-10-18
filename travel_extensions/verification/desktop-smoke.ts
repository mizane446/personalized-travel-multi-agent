import fs from 'node:fs';
import path from 'node:path';
import { _electron } from '@playwright/test';
import { startMockServer } from '../../tests-js/scripts/mock-server.ts';
import { writeMockProviderConfig, writeEnvFile } from '../../tests-js/scripts/mock-provider-config.ts';
import { runDesktopChatSmoke } from '../../tests-js/scripts/desktop-chat-smoke.ts';
import { resolveElectronBinary } from '../../apps/desktop/e2e/electron-binary.ts';

const root = path.resolve(import.meta.dirname, '../..');
const outDir = path.join(root, '.hermes-runtime', `desktop-smoke-${Date.now()}`);
const profile = path.join(outDir, 'profile');
fs.mkdirSync(profile, { recursive: true });
const server = await startMockServer();
writeMockProviderConfig(profile, server.url, 'language: en', '_config_version: 12');
writeEnvFile(profile, 'e2e-mock-key', server.url);
const env = Object.fromEntries(Object.entries(process.env).filter(([key, value]) =>
  value && !/(_KEY|_TOKEN|_SECRET|_PASSWORD|_CREDENTIALS)$/.test(key)
  && !key.startsWith('HERMES_') && !/^(OPENAI|ANTHROPIC|CUSTOM)_/.test(key))) as Record<string, string>;
Object.assign(env, {
  HERMES_HOME: profile,
  HERMES_RUNTIME_DIR: path.join(root, '.hermes-runtime/tools'),
  HERMES_DESKTOP_USER_DATA_DIR: path.join(outDir, 'electron'),
  HERMES_DESKTOP_IGNORE_EXISTING: '1',
  HERMES_DESKTOP_ISOLATED_BACKEND: '1',
  HERMES_DESKTOP_HERMES_ROOT: root,
  HERMES_DESKTOP_PYTHON: process.env.TRAVEL_TEST_PYTHON!,
  HERMES_DESKTOP_SKIP_QUIT_CONFIRM: '1',
  HERMES_DESKTOP_SKIP_PROTOCOL_REGISTRATION: '1',
  HERMES_DESKTOP_APP_NAME: `TravelBaseline-${Date.now()}`,
  PYTHONUTF8: '1',
});
delete env.ELECTRON_RUN_AS_NODE;
const app = await _electron.launch({
  executablePath: resolveElectronBinary([path.join(root, 'apps/desktop'), root]),
  args: [path.join(import.meta.dirname, 'desktop-hidden.cjs'), '--disable-gpu', '--no-sandbox'],
  env, timeout: 120000,
});
try {
  const page = await app.firstWindow();
  console.log('Desktop renderer connected');
  const receipt = await runDesktopChatSmoke(page, {
    phase: 'installed', outDir, mockUrl: server.url,
    observePrompts: async () => server.receivedPrompts,
  });
  const visible = await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows().some(w => w.isVisible()));
  if (visible) throw new Error('Test window unexpectedly visible');
  fs.mkdirSync(path.join(root, 'docs/travel/images'), { recursive: true });
  // Crop the OS user-name footer from the public evidence, keeping the chat unchanged.
  const size = await page.evaluate(() => ({ width: innerWidth, height: innerHeight }));
  await page.screenshot({ path: path.join(root, 'docs/travel/images/desktop-baseline.png'),
    clip: { x: 0, y: 0, width: size.width, height: size.height - 48 } });
  console.log(JSON.stringify({ status: receipt.status, hidden: !visible, screenshot: receipt.screenshot }));
} finally {
  await app.close();
  await server.close();
}
