"""Real Hermes parent, child, hooks, review, plan and export; network is synthetic."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import shutil
import threading

import httpx


def test_parent_to_child_review_wiki_plan_export(tmp_path, monkeypatch):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if not self.path.endswith('/chat/completions'):
                self.send_response(404)
                self.end_headers()
                return
            requests.append(body)
            try:
                message = respond(body)
            except Exception as exc:
                message = {'role': 'assistant', 'content': 'FIXTURE ERROR: ' + repr(exc)}
            finish = 'tool_calls' if message.get('tool_calls') else 'stop'
            response = {'id': 'fixture', 'object': 'chat.completion', 'created': 1, 'model': 'fixture-model',
                        'choices': [{'index': 0, 'message': message, 'finish_reason': finish}],
                        'usage': {'prompt_tokens': 20, 'completion_tokens': 20, 'total_tokens': 40}}
            self.send_response(200)
            if body.get('stream'):
                self.send_header('Content-Type', 'text/event-stream')
                self.end_headers()
                delta = dict(message)
                for i, call in enumerate(delta.get('tool_calls', [])):
                    call['index'] = i
                response['object'] = 'chat.completion.chunk'
                response['choices'] = [{'index': 0, 'delta': delta, 'finish_reason': None}]
                self.wfile.write(('data: ' + json.dumps(response) + '\n\n').encode())
                response['choices'] = [{'index': 0, 'delta': {}, 'finish_reason': finish}]
                self.wfile.write(('data: ' + json.dumps(response) + '\n\ndata: [DONE]\n\n').encode())
            else:
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(response).encode())

    def call(name, args):
        return {'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'call-' + str(len(requests)),
                'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args, ensure_ascii=False)}}]}

    def respond(body):
        names = {t['function']['name'] for t in body.get('tools', [])}
        results = []
        for m in body['messages']:
            if m['role'] != 'tool':
                continue
            content = m['content']
            try:
                results.append(json.JSONDecoder().raw_decode(content[content.index('{'):])[0])
            except (ValueError, TypeError):
                results.append({'error': content})
        if names == {'web_search'}:
            if results:
                return {'role': 'assistant', 'content': '西湖散步 https://example.org/westlake'}
            return call('web_search', {'query': '杭州西湖散步', 'limit': 5})
        if not names:
            return {'role': 'assistant', 'content': json.dumps({'accepted': [{'text': '西湖散步；开放时间待核实',
                    'sources': [1]}], 'complete': True, 'feedback': ''}, ensure_ascii=False)}
        if not results:
            return call('web_search', {'query': 'unauthorized parent search'})
        if len(results) == 1:
            assert '没有活动旅行子任务' in str(results[0]), results[0]
            source = re.search(r'source_id=([a-f0-9]{24})', json.dumps(body['messages'], ensure_ascii=False))[1]
            return call('travel_preferences', {'action': 'propose', 'source_id': source, 'key': 'attraction.style', 'quote': '喜欢散步'})
        if 'fact_id' in results[-1]:
            return call('travel_research', {'action': 'start', 'direction': 'attraction', 'destination': '杭州', 'requirements': '喜欢散步，一个景点'})
        jobs = [r['job_id'] for r in results if 'job_id' in r]
        if 'job_id' in results[-1] or results[-1].get('state') in ('RUNNING', 'PENDING', 'STARTING', 'REVIEWING'):
            return call('travel_research', {'action': 'poll', 'job_id': jobs[0]})
        if results[-1].get('reviewed'):
            return call('travel_plan', {'action': 'save', 'title': '杭州散步方案', 'job_ids': [jobs[0]]})
        if 'version' in results[-1]:
            return call('travel_plan', {'action': 'export', 'format': 'markdown'})
        if 'markdown' in results[-1]:
            return {'role': 'assistant', 'content': '完成方案与导出，来源 https://example.org/westlake'}
        return {'role': 'assistant', 'content': 'FAILED: ' + json.dumps(results[-1], ensure_ascii=False)}

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    monkeypatch.setenv('ASK_ECHO_SEARCH_INFINITY_API_KEY', 'fixture-key')
    monkeypatch.setenv('CUSTOM_API_KEY', 'fixture-key')
    monkeypatch.setenv('OPENAI_API_KEY', 'fixture-key')
    base = f'http://127.0.0.1:{server.server_port}/v1'
    root = Path(__file__).resolve().parents[2]
    for folder in ('doubao_search', 'travel'):
        shutil.copytree(root / 'travel_extensions' / folder, tmp_path / 'plugins' / folder)
    (tmp_path / 'config.yaml').write_text(
        f'_config_version: 51\nmodel:\n  default: fixture-model\n  provider: custom\n  base_url: {base}\n  context_length: 64000\n'
        'tools:\n  tool_search:\n    enabled: "off"\n'
        'plugins:\n  enabled: [web-doubao, travel-enhancements]\nweb:\n  search_backend: doubao\n'
        'delegation:\n  max_spawn_depth: 1\n  inherit_mcp_toolsets: false\n', encoding='utf-8')
    def search_post(url, **kwargs):
        assert url == 'https://open.feedcoopapi.com/search_api/web_search'
        return httpx.Response(200, json={'Result': {'WebResults': [{'Title': '西湖',
            'Url': 'https://example.org/westlake', 'Summary': '合成景点散步资料'}]}}, request=httpx.Request('POST', url))
    monkeypatch.setattr(httpx, 'post', search_post)
    from hermes_cli.plugins import discover_plugins
    discover_plugins(force=True)
    from run_agent import AIAgent
    from hermes_cli import lifecycle
    observed_searches = []
    invoke = lifecycle.invoke_hook
    has_hook = lifecycle.has_hook
    monkeypatch.setattr(lifecycle, 'has_hook', lambda name: name == 'post_tool_call' or has_hook(name))
    def observe(name, **event):
        if name == 'post_tool_call' and event.get('tool_name') == 'web_search':
            observed_searches.append(event)
        return invoke(name, **event)
    monkeypatch.setattr(lifecycle, 'invoke_hook', observe)
    parent = AIAgent(model='fixture-model', provider='custom', base_url=base, api_key='fixture-key',
                     enabled_toolsets=['search', 'travel'], max_iterations=25,
                     quiet_mode=True, skip_memory=True, skip_context_files=True)
    try:
        result = parent.run_conversation('去杭州，喜欢散步，推荐一个景点并保存导出。')
        from travel_extensions.travel.wiki import WikiStore
        with WikiStore(tmp_path / 'travel/wiki').connect() as db:
            evidence_debug = {table: [dict(row) for row in db.execute('SELECT * FROM ' + table)]
                              for table in ('jobs', 'children', 'evidence')}
        if '完成方案与导出' not in result['final_response']:
            print(json.dumps(evidence_debug, ensure_ascii=False, default=str))
        assert '完成方案与导出' in result['final_response'], (result['final_response'], evidence_debug,
            [m['content'] for r in requests for m in r['messages'] if m['role'] == 'tool'])
        files = list((tmp_path / 'travel/exports').rglob('*.md'))
        assert len(files) == 1
        assert 'https://example.org/westlake' in files[0].read_text('utf-8')
        assert any(not r.get('tools') for r in requests), 'review must use the host LLM with no tools'
        from travel_extensions.travel.wiki import WikiStore
        assert WikiStore(tmp_path / 'travel/wiki').facts()[0]['quote'] == '喜欢散步'
        successful_searches = [event for event in observed_searches if event.get('status') == 'ok']
        assert len(successful_searches) == 1, observed_searches
    finally:
        parent.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
