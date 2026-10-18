"""One explicitly authorized live canary, with a global HTTP request/token cap.

All profiles, transcripts and credentials remain under ignored .hermes-runtime.
This tests integration, not model quality comparisons or monetary cost.
"""
import argparse
from datetime import datetime, UTC
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
import time
import uuid

import httpx

from travel_extensions.configure import configure


def read_env(path):
    values = {}
    for line in path.read_text('utf-8').splitlines():
        if '=' in line and not line.startswith('#'):
            key, value = line.split('=', 1)
            values[key.strip()] = value.strip().strip('\x22\x27')
    return values


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true', required=True)
    parser.add_argument('--relay-env', type=Path, required=True)
    parser.add_argument('--search-env', type=Path, required=True)
    parser.add_argument('--model', choices=['gpt-6-sol'], default='gpt-6-sol')
    args = parser.parse_args()
    relay = read_env(args.relay_env)
    search = read_env(args.search_env)['ASK_ECHO_SEARCH_INFINITY_API_KEY']
    if not relay.get('TRAVEL_RELAY_API_KEY') or not search:
        raise ValueError('Missing test credentials')
    model = args.model
    root = Path(__file__).resolve().parents[2]
    out = root / '.hermes-runtime' / ('live-canary-' + datetime.now(UTC).strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6])
    profile = out / 'profile'
    configure(profile)
    calls = []
    lock = threading.Lock()
    search_requests = []
    direct_post = httpx.post

    def limited_post(url, **kwargs):
        if url == 'https://open.feedcoopapi.com/search_api/web_search':
            with lock:
                if len(search_requests) >= 5:
                    raise httpx.RequestError('Authorized global search limit reached')
                search_requests.append(time.monotonic())
        return direct_post(url, **kwargs)

    httpx.post = limited_post

    class Gate(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            if self.path != '/v1/chat/completions':
                self.send_error(400, 'Only chat completions is authorized')
                return
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            with lock:
                if len(calls) >= 12:
                    self.send_error(400, 'Authorized request limit reached; no upstream call')
                    return
                row = {'request': len(calls) + 1, 'tools': [t['function']['name'] for t in body.get('tools', [])]}
                calls.append(row)
            body['model'] = model
            # Old and new OpenAI-compatible token parameters cannot coexist.
            if 'max_completion_tokens' in body:
                body['max_completion_tokens'] = min(1600, body['max_completion_tokens'])
                body.pop('max_tokens', None)
            else:
                body['max_tokens'] = min(1600, body.get('max_tokens') or 1600)
            row['output_token_limit'] = 1600
            (out / 'calls.json').write_text(json.dumps(calls, ensure_ascii=False, indent=2), 'utf-8')
            started = time.monotonic()
            try:
                response = httpx.post(relay['TRAVEL_RELAY_BASE_URL'].rstrip('/') + '/chat/completions',
                    headers={'Authorization': 'Bearer ' + relay['TRAVEL_RELAY_API_KEY']}, json=body, timeout=90)
                row['status'] = response.status_code
                row['seconds'] = round(time.monotonic() - started, 3)
                payloads = []
                if body.get('stream'):
                    for line in response.text.splitlines():
                        if line.startswith('data: ') and line != 'data: [DONE]':
                            try:
                                payloads.append(json.loads(line[6:]))
                            except ValueError:
                                pass
                else:
                    try:
                        payloads.append(response.json())
                    except ValueError:
                        pass
                usages = [p['usage'] for p in payloads if p.get('usage')]
                if usages:
                    row['usage'] = usages[-1]
                self.send_response(response.status_code)
                self.send_header('Content-Type', response.headers.get('content-type', 'application/json'))
                self.end_headers()
                self.wfile.write(response.content)
            except Exception as exc:  # health: allow BLE001 -- Test gate records type only to avoid leaking relay credentials.
                row['error_type'] = type(exc).__name__
                self.send_error(502, 'Relay request failed')
            finally:
                (out / 'calls.json').write_text(json.dumps(calls, ensure_ascii=False, indent=2), 'utf-8')

    server = ThreadingHTTPServer(('127.0.0.1', 0), Gate)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base = f'http://127.0.0.1:{server.server_port}/v1'
    os.environ.update(HERMES_HOME=str(profile), CUSTOM_API_KEY='local-gate', OPENAI_API_KEY='local-gate',
                      OPENAI_BASE_URL=base, ASK_ECHO_SEARCH_INFINITY_API_KEY=search)
    import hermes_yaml as yaml
    config = yaml.safe_load((profile / 'config.yaml').read_text('utf-8'))
    config['model'] = {'provider': 'custom', 'default': model, 'base_url': base, 'context_length': 64000}
    config['delegation'].update(provider='custom', model=model, base_url=base)
    config['auxiliary']['travel_review'].update(provider='custom', model=model, base_url=base)
    (profile / 'config.yaml').write_text(yaml.safe_dump(config, allow_unicode=True), 'utf-8')
    (profile / '.env').write_text('CUSTOM_API_KEY=local-gate\nOPENAI_API_KEY=local-gate\nOPENAI_BASE_URL=' + base +
                                '\nASK_ECHO_SEARCH_INFINITY_API_KEY=' + search + '\n', 'utf-8')
    from hermes_cli.plugins import discover_plugins
    discover_plugins(force=True)
    from run_agent import AIAgent
    agent = AIAgent(model=model, provider='custom', base_url=base, api_key='local-gate',
        enabled_toolsets=['search', 'travel'], max_iterations=10, quiet_mode=True,
        skip_memory=True, skip_context_files=True, reasoning_config={'effort': 'none'},
        api_mode='chat_completions', max_tokens=1600)
    started = time.monotonic()
    result = {}
    failure = None
    try:
        result = agent.run_conversation('这是一次合成用户验收。我长期喜欢散步。目的地是杭州，只推荐一处适合散步的景点。'
            '请记录明确偏好，用 travel_research 启动 attraction 任务并 poll 取得有来源的审查结果；'
            '不要扩展到餐饮或住宿。将通过审查的结果保存为方案，导出 Markdown 和 PDF，最后给出来源 URL。'
            '资料不足就明确说缺口，不要编造。')
    except Exception as exc:  # health: allow BLE001 -- Persist a failure receipt without copying secrets from SDK exceptions.
        failure = type(exc).__name__
    finally:
        agent.close()
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)
        httpx.post = direct_post
    from travel_extensions.travel.wiki import WikiStore
    wiki = WikiStore(profile / 'travel/wiki')
    with wiki.connect() as db:
        jobs = [dict(row) for row in db.execute('SELECT direction,used,cancelled,result FROM jobs')]
        sources = db.execute('SELECT count(*) FROM evidence').fetchone()[0]
    files = list((profile / 'travel/exports').rglob('*'))
    formats = sorted({p.suffix[1:] for p in files if p.is_file() and p.suffix in ('.md', '.pdf')})
    receipt = {'mode': 'real ccgoai relay and real Doubao; synthetic user request', 'model': model,
        'seconds': round(time.monotonic() - started, 3), 'model_requests': len(calls),
        'request_limit': 12, 'output_tokens_per_request_limit': 1600, 'calls': calls,
        'search_calls': sum(job['used'] for job in jobs), 'search_http_requests': len(search_requests), 'evidence_urls': sources,
        'preference_count': len(wiki.facts()), 'exported_formats': formats, 'exception_type': failure,
        'cost': 'unknown; token usage is not a bill',
        'passed': bool(not failure and formats == ['md', 'pdf'] and wiki.facts() and sources)}
    (out / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), 'utf-8')
    (out / 'final-response.json').write_text(json.dumps(result.get('final_response'), ensure_ascii=False), 'utf-8')
    print(json.dumps({'run_directory': out.name, **{k: v for k, v in receipt.items() if k != 'calls'}}, ensure_ascii=False))
    return 0 if receipt['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
