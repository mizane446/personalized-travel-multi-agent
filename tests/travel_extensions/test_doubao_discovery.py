"""Installed directory plugin → native web_search, with a local HTTP fixture."""
import json
from pathlib import Path
import shutil

import httpx


def test_installed_plugin_routes_native_search(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    monkeypatch.setenv('ASK_ECHO_SEARCH_INFINITY_API_KEY', 'fixture-key')
    source = Path(__file__).resolve().parents[2] / 'travel_extensions/doubao_search'
    shutil.copytree(source, tmp_path / 'plugins/web/doubao_search')
    (tmp_path / 'config.yaml').write_text(
        'plugins:\n  enabled: [web-doubao]\nweb:\n  search_backend: doubao\n', encoding='utf-8')
    calls = []

    def post(url, **kwargs):
        calls.append(kwargs['json']['Query'])
        return httpx.Response(200, json={'Result': {'WebResults': [
            {'Title': 'West Lake', 'Url': 'https://example.org/lake', 'Summary': 'Fixture evidence'}
        ]}}, request=httpx.Request('POST', url))

    monkeypatch.setattr(httpx, 'post', post)
    from hermes_cli.plugins import discover_plugins
    discover_plugins(force=True)
    from agent.web_search_registry import get_active_search_provider
    assert get_active_search_provider().name == 'doubao'
    from tools.web_tools import web_search_tool
    result = json.loads(web_search_tool('isolated discovery query'))
    assert result['success']
    assert result['data']['web'][0]['url'] == 'https://example.org/lake'
    assert calls == ['isolated discovery query']
