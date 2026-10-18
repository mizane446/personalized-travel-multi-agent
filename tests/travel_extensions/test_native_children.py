"""Real Hermes child construction + two model rounds + native search dispatch.

Only network responses are fixtures. No paid calls or replacement agent runner.
"""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import threading

import httpx
import pytest


@pytest.mark.parametrize('public_lifecycle', [False, True])
def test_three_native_children_only_search_and_return_sources(tmp_path, monkeypatch, public_lifecycle):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if self.path != '/v1/chat/completions':
                self.send_response(404)
                self.end_headers()
                return
            requests.append(body)
            has_result = any(m['role'] == 'tool' for m in body['messages'])
            message = {'role': 'assistant', 'content': 'Found https://example.org/evidence'} if has_result else {
                'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'search-1', 'type': 'function',
                    'function': {'name': 'web_search', 'arguments': '{"query":"synthetic travel evidence","limit":5}'}}]}
            finish = 'stop' if has_result else 'tool_calls'
            response = {'id': 'fixture', 'object': 'chat.completion', 'created': 1, 'model': 'fixture-model',
                        'choices': [{'index': 0, 'message': message, 'finish_reason': finish}],
                        'usage': {'prompt_tokens': 10, 'completion_tokens': 10, 'total_tokens': 20}}
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

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    monkeypatch.setenv('ASK_ECHO_SEARCH_INFINITY_API_KEY', 'fixture-key')
    source = Path(__file__).resolve().parents[2] / 'travel_extensions/doubao_search'
    shutil.copytree(source, tmp_path / 'plugins/web/doubao_search')
    (tmp_path / 'config.yaml').write_text(
        'plugins:\n  enabled: [web-doubao]\nweb:\n  search_backend: doubao\n'
        'delegation:\n  max_concurrent_children: 3\n  max_spawn_depth: 1\n'
        '  inherit_mcp_toolsets: false\n  oneshot_max_children: 3\n', encoding='utf-8')

    def search_post(url, **kwargs):
        assert url == 'https://open.feedcoopapi.com/search_api/web_search'
        return httpx.Response(200, json={'Result': {'WebResults': [
            {'Title': 'Fixture', 'Url': 'https://example.org/evidence', 'Summary': 'Public fixture'}
        ]}}, request=httpx.Request('POST', url))

    monkeypatch.setattr(httpx, 'post', search_post)
    from hermes_cli.plugins import discover_plugins
    discover_plugins(force=True)
    from run_agent import AIAgent
    from tools.delegate_tool import delegate_task
    from tools.registry import registry
    registry.register(name='private_write', toolset='private_test',
                      schema={'name': 'private_write', 'description': 'Parent-only fixture write',
                              'parameters': {'type': 'object', 'properties': {}}}, handler=lambda args: '{}')
    parent = AIAgent(model='fixture-model', provider='custom',
                     base_url=f'http://127.0.0.1:{server.server_port}/v1', api_key='fixture-key',
                     enabled_toolsets=['search', 'delegation'] + (['private_test'] if public_lifecycle else []), max_iterations=4,
                     quiet_mode=True, skip_memory=True, skip_context_files=True)
    try:
        if public_lifecycle:
            from agent.subagent_lifecycle import SubagentLifecycleService, SubagentLaunchRequest
            service = SubagentLifecycleService(lambda: parent)
            handles = [service.launch(SubagentLaunchRequest(goal=f'Search {role}', allowed_toolsets=('search',)))
                       for role in ('food', 'hotel', 'attraction')]
            for handle in handles:
                assert service.wait(handle, timeout_seconds=60).completed
                assert 'https://example.org/evidence' in service.result(handle).summary
        else:
            result = json.loads(delegate_task(tasks=[{'goal': f'Search {role}'} for role in ('food', 'hotel', 'attraction')],
                                              max_iterations=3, parent_agent=parent))
            assert len(result['results']) == 3, result
            assert all(r['status'] == 'completed' and 'https://example.org/evidence' in r['summary']
                       for r in result['results']), result
        assert len(requests) == 6
        for request in requests:
            assert {t['function']['name'] for t in request.get('tools', [])} == {'web_search'}
    finally:
        parent.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
