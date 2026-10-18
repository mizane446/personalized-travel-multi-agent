// Real hidden Desktop/Gateway; only model and web evidence are synthetic fixtures.
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import { _electron, expect } from '@playwright/test';
import { waitForChatReady } from '../../tests-js/scripts/desktop-chat-smoke.ts';
import { writeEnvFile } from '../../tests-js/scripts/mock-provider-config.ts';
import { resolveElectronBinary } from '../../apps/desktop/e2e/electron-binary.ts';

const root = path.resolve(import.meta.dirname, '../..');
const outDir = path.join(root, '.hermes-runtime', `desktop-travel-${Date.now()}`);
const profile = path.join(outDir, 'profile');
fs.mkdirSync(profile, { recursive: true });
let modelCalls = 0;
let childCalls = 0;
let reviews = 0;
function tool(name: string, args: object) {
  return { role: 'assistant', content: null, tool_calls: [{ id: `call-${modelCalls}`, type: 'function',
    function: { name, arguments: JSON.stringify(args) } }] };
}
function response(body: any): any {
  const names = new Set((body.tools ?? []).map((t: any) => t.function.name));
  const results = body.messages.filter((m: any) => m.role === 'tool').map((m: any) => {
    const text = m.content as string;
    try { return JSON.parse(text.slice(text.indexOf('{'), text.lastIndexOf('}') + 1)); }
    catch { return { error: text }; }
  });
  if (names.size === 1 && names.has('web_search')) {
    childCalls++;
    return results.length ? { role: 'assistant', content: '西湖散步 https://example.org/westlake' }
      : tool('web_search', { query: '杭州西湖散步', limit: 5 });
  }
  if (!names.size) {
    reviews++;
    return { role: 'assistant', content: JSON.stringify({ accepted: [{ text: '西湖散步；开放时间与天气待核实（合成资料）',
      sources: [1] }], complete: true, feedback: '' }) };
  }
  const last = results.at(-1);
  if (!last) {
    const source = JSON.stringify(body.messages).match(/source_id=([a-f0-9]{24})/)?.[1];
    if (!source) throw new Error('Missing Wiki source context');
    return tool('travel_preferences', { action: 'propose', source_id: source, key: 'attraction.style', quote: '喜欢散步' });
  }
  if (last.fact_id) return tool('travel_research', { action: 'start', direction: 'attraction', destination: '杭州', requirements: '喜欢散步，推荐一个景点' });
  const job = results.find((r: any) => r.job_id)?.job_id;
  if (last.job_id || ['RUNNING', 'PENDING', 'STARTING', 'REVIEWING'].includes(last.state)) return tool('travel_research', { action: 'poll', job_id: job });
  if (last.reviewed && last.accepted?.length) return tool('travel_plan', { action: 'save', title: '杭州散步方案（合成验收）', job_ids: [job] });
  if (last.version) return tool('travel_plan', { action: 'export', format: 'both' });
  if (last.pdf) return { role: 'assistant', content: `旅行方案已保存并导出。\n\n推荐：西湖散步。开放时间与天气待核实。\n\n来源：https://example.org/westlake\n\n已记录偏好“喜欢散步”。Markdown 与 PDF 已保留在当前人物的导出目录。\n\n本次是合成资料验收，不是真实旅行建议。` };
  return { role: 'assistant', content: '验收失败：' + JSON.stringify(last) };
}
const server = http.createServer(async (req, res) => {
  if (req.method === 'GET' && req.url?.endsWith('/models')) {
    res.setHeader('Content-Type', 'application/json');
    res.end(JSON.stringify({ object: 'list', data: [{ id: 'mock-model', object: 'model' }] }));
    return;
  }
  if (!req.url?.endsWith('/chat/completions')) { res.writeHead(404); res.end(); return; }
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  const body = JSON.parse(Buffer.concat(chunks).toString());
  modelCalls++;
  let message;
  try { message = response(body); }
  catch (error) { message = { role: 'assistant', content: 'Fixture error: ' + String(error) }; }
  const finish = message.tool_calls ? 'tool_calls' : 'stop';
  const base = { id: `mock-${modelCalls}`, created: 1, model: 'mock-model', usage: { prompt_tokens: 20, completion_tokens: 20, total_tokens: 40 } };
  if (body.stream) {
    res.setHeader('Content-Type', 'text/event-stream');
    message.tool_calls?.forEach((call: any, index: number) => { call.index = index; });
    res.write('data: ' + JSON.stringify({ ...base, object: 'chat.completion.chunk', choices: [{ index: 0, delta: message, finish_reason: null }] }) + '\n\n');
    res.end('data: ' + JSON.stringify({ ...base, object: 'chat.completion.chunk', choices: [{ index: 0, delta: {}, finish_reason: finish }] }) + '\n\ndata: [DONE]\n\n');
  } else {
    res.setHeader('Content-Type', 'application/json');
    res.end(JSON.stringify({ ...base, object: 'chat.completion', choices: [{ index: 0, message, finish_reason: finish }] }));
  }
});
await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
const url = `http://127.0.0.1:${(server.address() as any).port}`;
fs.cpSync(path.join(root, 'travel_extensions/travel'), path.join(profile, 'plugins/travel'), { recursive: true, filter: source => !source.includes('__pycache__') });
const fixturePlugin = path.join(profile, 'plugins/fixture-web');
fs.mkdirSync(fixturePlugin, { recursive: true });
fs.writeFileSync(path.join(fixturePlugin, 'plugin.yaml'), 'name: fixture-web\nversion: 1.0.0\ndescription: Synthetic test evidence only\n');
fs.writeFileSync(path.join(fixturePlugin, '__init__.py'), `from agent.web_search_provider import WebSearchProvider
class Fixture(WebSearchProvider):
    name = 'fixture'
    display_name = 'Synthetic fixture'
    def is_available(self): return True
    def search(self, query, limit=5):
        return {'success': True, 'data': {'web': [{'title': '西湖', 'url': 'https://example.org/westlake', 'description': '合成散步资料'}]}}
def register(ctx): ctx.register_web_search_provider(Fixture())
`);
fs.writeFileSync(path.join(profile, 'config.yaml'), `_config_version: 51
display:
  language: en
model:
  provider: custom
  default: mock-model
  base_url: ${url}/v1
  context_length: 64000
plugins:
  enabled: [travel-enhancements, fixture-web]
web:
  search_backend: fixture
platform_toolsets:
  cli: [search, travel]
tools:
  tool_search:
    enabled: "off"
auxiliary:
  title_generation:
    enabled: false
delegation:
  max_spawn_depth: 1
  inherit_mcp_toolsets: false
`);
writeEnvFile(profile, 'fixture-key', url);
const env = Object.fromEntries(Object.entries(process.env).filter(([key, value]) => value && !/(_KEY|_TOKEN|_SECRET|_PASSWORD|_CREDENTIALS)$/.test(key)
  && !key.startsWith('HERMES_') && !/^(OPENAI|ANTHROPIC|CUSTOM)_/.test(key))) as Record<string, string>;
Object.assign(env, { HERMES_HOME: profile, HERMES_RUNTIME_DIR: path.join(root, '.hermes-runtime/tools'),
  HERMES_DESKTOP_USER_DATA_DIR: path.join(outDir, 'electron'), HERMES_DESKTOP_IGNORE_EXISTING: '1',
  HERMES_DESKTOP_ISOLATED_BACKEND: '1', HERMES_DESKTOP_HERMES_ROOT: root,
  HERMES_DESKTOP_PYTHON: process.env.TRAVEL_TEST_PYTHON!, HERMES_TUI_TOOLSETS: 'search,travel',
  HERMES_DESKTOP_SKIP_QUIT_CONFIRM: '1', HERMES_DESKTOP_SKIP_PROTOCOL_REGISTRATION: '1',
  HERMES_DESKTOP_APP_NAME: `TravelEvidence-${Date.now()}`, PYTHONUTF8: '1' });
delete env.ELECTRON_RUN_AS_NODE;
const app = await _electron.launch({ executablePath: resolveElectronBinary([path.join(root, 'apps/desktop'), root]),
  args: [path.join(import.meta.dirname, 'desktop-hidden.cjs'), '--disable-gpu', '--no-sandbox'], env, timeout: 120000 });
try {
  const page = await app.firstWindow();
  const composer = await waitForChatReady(page);
  await composer.fill('去杭州，喜欢散步，推荐一个景点，保存方案并导出 Markdown 和 PDF。');
  await composer.press('Enter');
  await expect(page.getByText('旅行方案已保存并导出。', { exact: false }).last()).toBeVisible({ timeout: 150000 });
  const exportsDir = path.join(profile, 'travel/exports');
  const files = fs.readdirSync(exportsDir, { recursive: true }).map(String).filter(name => /\.(pdf|md)$/.test(name));
  if (files.length !== 2 || childCalls !== 2 || reviews !== 1) throw new Error(JSON.stringify({ files, childCalls, reviews }));
  const visible = await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows().some(w => w.isVisible()));
  if (visible) throw new Error('Window unexpectedly visible');
  const size = await page.evaluate(() => ({ width: innerWidth, height: innerHeight }));
  const screenshotVersion = process.env.TRAVEL_SCREENSHOT_VERSION ?? '1';
  if (!/^\d+$/.test(screenshotVersion)) throw new Error('Screenshot version must be numeric');
  const screenshot = path.join(root, `docs/travel/images/desktop-travel-v${screenshotVersion}.png`);
  if (fs.existsSync(screenshot)) throw new Error('Use a new screenshot version');
  await page.screenshot({ path: screenshot, clip: { x: 0, y: 0, width: size.width, height: size.height - 48 } });
  const receipt = { status: 'passed', mode: 'real Desktop/Gateway; synthetic model/search', modelCalls, childCalls, reviews, exportedFormats: ['markdown', 'pdf'], hidden: !visible };
  fs.writeFileSync(path.join(outDir, 'receipt.json'), JSON.stringify(receipt, null, 2));
  console.log(JSON.stringify(receipt));
} catch (error) {
  const page = await app.firstWindow();
  console.log((await page.locator('body').innerText()).slice(-5000));
  throw error;
} finally {
  await app.close();
  await new Promise<void>(resolve => server.close(() => resolve()));
}
