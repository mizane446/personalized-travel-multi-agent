// Opt-in real Desktop showcase. No fixtures; shared ledger caps retries across reruns.
import fs from 'node:fs'
import path from 'node:path'
import http from 'node:http'
import { _electron } from '@playwright/test'
import { waitForChatReady } from '../../tests-js/scripts/desktop-chat-smoke.ts'
import { resolveElectronBinary } from '../../apps/desktop/e2e/electron-binary.ts'
const root = path.resolve(import.meta.dirname, '../..')
if (process.env.TRAVEL_LIVE_AUTHORIZED !== '100') throw new Error('Requires explicit 100-call authorization')
const ledgerPath = path.join(root, '.hermes-runtime/showcase-budget-v2.json')
const ledger = fs.existsSync(ledgerPath)
  ? JSON.parse(fs.readFileSync(ledgerPath, 'utf8'))
  : { models: [], searches: [] }
const persist = () => fs.writeFileSync(ledgerPath, JSON.stringify(ledger, null, 2))
const out = path.join(root, '.hermes-runtime', `showcase-real-${Date.now()}`)
const profile = path.join(out, 'profile')
fs.mkdirSync(profile, { recursive: true })
fs.writeFileSync(path.join(root, '.hermes-runtime/showcase-current.txt'), out)
function envFile(p: string) {
  return Object.fromEntries(
    fs
      .readFileSync(p, 'utf8')
      .split(/\r?\n/)
      .filter(l => l.includes('=') && !l.startsWith('#'))
      .map(l => {
        const i = l.indexOf('=')
        return [
          l.slice(0, i).trim(),
          l
            .slice(i + 1)
            .trim()
            .replace(/^["']|["']$/g, '')
        ]
      })
  )
}
const relay = envFile(path.join(root, '.hermes-runtime/relay-test.env'))
const local = envFile(path.join(root, '.hermes-runtime/profile/.env'))
if (!['localhost', '127.0.0.1'].includes(new URL(local.HERMES_LANGFUSE_BASE_URL).hostname))
  throw new Error('Local traces only')
const server = http.createServer(async (req, res) => {
  if (req.method === 'GET' && req.url?.endsWith('/models')) {
    res.setHeader('Content-Type', 'application/json')
    res.end(JSON.stringify({ data: [{ id: 'gpt-6-sol', object: 'model' }], object: 'list' }))
    return
  }
  const search = req.url === '/search'
  if (req.method !== 'POST' || (!search && req.url !== '/v1/chat/completions')) {
    res.writeHead(404)
    res.end()
    return
  }
  const calls = search ? ledger.searches : ledger.models
  if (calls.length >= 100) {
    res.writeHead(400)
    res.end('Authorized cumulative cap reached')
    return
  }
  const chunks = []
  for await (const chunk of req) chunks.push(chunk)
  const body = JSON.parse(Buffer.concat(chunks).toString())
  if (!search) {
    body.model = 'gpt-6-sol'
    if ('max_completion_tokens' in body) {
      body.max_completion_tokens = Math.min(3000, body.max_completion_tokens || 3000)
      delete body.max_tokens
    } else body.max_tokens = Math.min(3000, body.max_tokens || 3000)
  }
  const row: any = {
    index: calls.length + 1,
    run: path.basename(out),
    started: new Date().toISOString(),
    ...(search ? { query: body.Query } : { tools: (body.tools ?? []).map((t: any) => t.function.name) })
  }
  calls.push(row)
  persist()
  try {
    const response = await fetch(
      search
        ? 'https://open.feedcoopapi.com/search_api/web_search'
        : relay.TRAVEL_RELAY_BASE_URL.replace(/\/$/, '') + '/chat/completions',
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: 'Bearer ' + (search ? local.ASK_ECHO_SEARCH_INFINITY_API_KEY : relay.TRAVEL_RELAY_API_KEY)
        },
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(search ? 30000 : 90000)
      }
    )
    const text = await response.text()
    row.status = response.status
    row.ended = new Date().toISOString()
    if (search) {
      const data = JSON.parse(text)
      fs.writeFileSync(path.join(out, `search-${row.index}.json`), JSON.stringify(data, null, 2))
    } else {
      let packets: any[] = []
      if (body.stream) {
        for (const l of text.split('\n'))
          if (l.startsWith('data: ') && l.trim() !== 'data: [DONE]') {
            try {
              packets.push(JSON.parse(l.slice(6)))
            } catch {}
          }
      } else {
        try {
          packets = [JSON.parse(text)]
        } catch {}
      }
      row.usage = packets.filter(p => p.usage).at(-1)?.usage
      // Preserve visible answers and tool calls only, never reasoning fields.
      const visible = packets.flatMap(p =>
        (p.choices ?? []).map((c: any) => {
          const m = c.message ?? c.delta ?? {}
          return { content: m.content, tool_calls: m.tool_calls, finish_reason: c.finish_reason }
        })
      )
      fs.writeFileSync(path.join(out, `model-${row.index}.json`), JSON.stringify(visible, null, 2))
    }
    persist()
    res.writeHead(response.status, { 'Content-Type': response.headers.get('content-type') ?? 'application/json' })
    res.end(text)
  } catch (e) {
    row.error = (e as Error).name
    persist()
    res.writeHead(502)
    res.end('Upstream request failed')
  }
})
await new Promise<void>(r => server.listen(0, '127.0.0.1', r))
const base = `http://127.0.0.1:${(server.address() as any).port}`
for (const [src, dst] of [
  ['travel_extensions/travel', 'travel-enhancements'],
  ['travel_extensions/doubao_search', 'web-doubao'],
  ['.hermes-runtime/profile/plugins/langfuse', 'langfuse']
])
  fs.cpSync(path.join(root, src), path.join(profile, 'plugins', dst), {
    recursive: true,
    filter: p => !p.includes('__pycache__')
  })
const provider = path.join(profile, 'plugins/web-doubao/provider.py')
fs.writeFileSync(
  provider,
  fs.readFileSync(provider, 'utf8').replace('https://open.feedcoopapi.com/search_api/web_search', base + '/search')
)
let config = fs
  .readFileSync(path.join(root, 'travel_extensions/config.travel.example.yaml'), 'utf8')
  .replaceAll('https://ccgoai.club/v1', base + '/v1')
  .replace('enabled: [web-doubao, travel-enhancements]', 'enabled: [web-doubao, travel-enhancements, langfuse]')
fs.writeFileSync(path.join(profile, 'config.yaml'), config + '\ndisplay:\n  language: en\n')
const trace = Object.entries(local).filter(([k]) => /^HERMES_LANGFUSE_(PUBLIC_KEY|SECRET_KEY|BASE_URL)$/.test(k))
fs.writeFileSync(
  path.join(profile, '.env'),
  [
    ['CUSTOM_API_KEY', 'local-gate'],
    ['OPENAI_API_KEY', 'local-gate'],
    ['OPENAI_BASE_URL', base + '/v1'],
    ['ASK_ECHO_SEARCH_INFINITY_API_KEY', 'local-gate'],
    ['HERMES_LANGFUSE_CAPTURE', 'sanitized'],
    ...trace
  ]
    .map(([k, v]) => `${k}=${v}`)
    .join('\n') + '\n'
)
const env = Object.fromEntries(
  Object.entries(process.env).filter(
    ([k, v]) =>
      v &&
      !/(_KEY|_TOKEN|_SECRET|_PASSWORD|_CREDENTIALS)$/.test(k) &&
      !k.startsWith('HERMES_') &&
      !/^(OPENAI|ANTHROPIC|CUSTOM)_/.test(k)
  )
) as Record<string, string>
Object.assign(env, {
  HERMES_HOME: profile,
  HERMES_RUNTIME_DIR: path.join(root, '.hermes-runtime/tools'),
  HERMES_DESKTOP_USER_DATA_DIR: path.join(out, 'electron'),
  HERMES_DESKTOP_IGNORE_EXISTING: '1',
  HERMES_DESKTOP_ISOLATED_BACKEND: '1',
  HERMES_DESKTOP_HERMES_ROOT: root,
  HERMES_DESKTOP_PYTHON: process.env.TRAVEL_TEST_PYTHON!,
  HERMES_TUI_TOOLSETS: 'search,travel',
  HERMES_DESKTOP_SKIP_QUIT_CONFIRM: '1',
  HERMES_DESKTOP_SKIP_PROTOCOL_REGISTRATION: '1',
  HERMES_DESKTOP_APP_NAME: `TravelShowcase-${Date.now()}`,
  PYTHONUTF8: '1'
})
delete env.ELECTRON_RUN_AS_NODE
const prompt =
  '请为两位成年人制定杭州两日慢旅行资料方案，不订票、不付款。这是用于公开展示的虚构用户需求：我长期喜欢湖边散步和博物馆，饮食偏好清淡。住宿目标每晚500元以内，餐饮目标人均100元以内，都只是预算目标，不要求你保证实时价格。请分别启动 attraction、food、hotel 三个方向的原生研究任务，每个方向先用2到3次聚焦搜索，优先官方网站或政府文旅资料。景点至少2个不同地点，餐饮给2种本地选择，住宿给1个适合慢旅行的区域及1家可核查的候选酒店；查询不到可靠价格就标注待核实。poll 取得各任务审查结果后，将三个方向一起保存为“杭州两日慢旅行：景点、餐饮与住宿”，导出Markdown和PDF。在最终回答给两天建议安排、候选依据、来源URL、预算假设及未确认事项。不要把未核实营业时间、交通用时和房价写成确定事实。只有长期偏好写入Wiki。无需追问出发日期，因为本次只做非实时资料方案。'
fs.writeFileSync(path.join(out, 'request.txt'), prompt)
console.log(
  JSON.stringify({
    out,
    mode: 'real Desktop/model/search/local Langfuse',
    caps: { models: 100, searches: 100, output: 3000 }
  })
)
const app = await _electron.launch({
  executablePath: resolveElectronBinary([path.join(root, 'apps/desktop'), root]),
  args: [path.join(import.meta.dirname, 'desktop-hidden.cjs'), '--disable-gpu', '--no-sandbox'],
  env,
  timeout: 120000
})
try {
  const page = await app.firstWindow()
  await page.setViewportSize({ width: 1440, height: 1050 })
  const composer = await waitForChatReady(page)
  await composer.fill(prompt)
  await composer.press('Enter')
  const deadline = Date.now() + 900000
  let done = false
  while (Date.now() < deadline) {
    await page.waitForTimeout(3000)
    fs.writeFileSync(path.join(out, 'visible.txt'), await page.locator('body').innerText())
    const exports = path.join(profile, 'travel/exports')
    if (fs.existsSync(exports) && fs.readdirSync(exports, { recursive: true }).some(p => String(p).endsWith('.pdf'))) {
      done = true
      break
    }
  }
  await page.waitForTimeout(18000)
  fs.writeFileSync(path.join(out, 'visible.txt'), await page.locator('body').innerText())
  await page.screenshot({ path: path.join(out, 'desktop-result.png') })
  fs.writeFileSync(
    path.join(out, 'receipt.json'),
    JSON.stringify(
      {
        exportExists: done,
        run: path.basename(out),
        models: ledger.models.filter((r: any) => r.run === path.basename(out)).length,
        searches: ledger.searches.filter((r: any) => r.run === path.basename(out)).length,
        hidden: !(await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows().some(w => w.isVisible())))
      },
      null,
      2
    )
  )
  console.log('Capture ready: ' + out)
  // Keep the independent hidden window available for inspection, without extra requests.
  while (!fs.existsSync(path.join(out, 'close'))) {
    await page.waitForTimeout(1000)
    if (fs.existsSync(path.join(out, 'capture-tools'))) {
      fs.unlinkSync(path.join(out, 'capture-tools'))
      const buttons = await page.locator('button').all()
      fs.writeFileSync(
        path.join(out, 'buttons.json'),
        JSON.stringify(
          await Promise.all(
            buttons.map(async b => ({ text: await b.innerText(), label: await b.getAttribute('aria-label') }))
          ),
          null,
          2
        )
      )
    }
  }
} finally {
  await app.close()
  await new Promise<void>(r => server.close(() => r()))
}
