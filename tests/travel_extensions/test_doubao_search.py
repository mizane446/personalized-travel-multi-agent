"""Direct API contract: credentials, semantic failures and source preservation."""
import importlib
import json

import httpx
import pytest


@pytest.fixture
def provider(monkeypatch):
    module = importlib.import_module('travel_extensions.doubao_search.provider')
    monkeypatch.setattr(module, 'get_provider_env', lambda name: 'synthetic-secret')
    return module, module.DoubaoSearchProvider()


def respond(monkeypatch, module, payload, status=200):
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(status, json=payload, request=httpx.Request('POST', url))

    monkeypatch.setattr(module.httpx, 'post', post)
    return calls


def test_preserves_sources_and_prefers_summary(provider, monkeypatch):
    module, search = provider
    calls = respond(monkeypatch, module, {'Result': {'WebResults': [
        {'Title': '', 'Url': 'https://example.org/a?q=1', 'Snippet': 'short', 'Summary': 'useful evidence'},
        {'Title': 'unsupported', 'Url': 'javascript:alert(1)'},
        {'Title': 'missing source'},
    ]}})
    result = search.search('杭州 西湖', 5)
    assert result['success'] is True
    assert result['data']['web'] == [{'title': '', 'url': 'https://example.org/a?q=1',
                                      'description': 'useful evidence', 'position': 1}]
    assert calls[0][1]['headers']['Authorization'] == 'Bearer synthetic-secret'
    assert calls[0][1]['json']['QueryControl'] == {'QueryRewrite': False}
    assert calls[0][1]['json']['Count'] == 5


@pytest.mark.parametrize('status', [301, 401, 403, 429, 500])
def test_http_errors_do_not_echo_remote_secrets(provider, monkeypatch, status):
    module, search = provider
    respond(monkeypatch, module, {'error': 'synthetic-secret'}, status)
    result = search.search('杭州')
    assert result['success'] is False
    assert str(status) in result['error']
    assert 'synthetic-secret' not in json.dumps(result)


@pytest.mark.parametrize('payload', [
    {'ResponseMetadata': {'Error': {'Code': '700429', 'Message': 'synthetic-secret'}}},
    {}, [], {'Result': {'WebResults': 'not a list'}},
    {'Result': {'WebResults': [{'Title': 'only unsourced result'}]}},
])
def test_semantic_errors_and_missing_protocol_fail_closed(provider, monkeypatch, payload):
    module, search = provider
    respond(monkeypatch, module, payload)
    result = search.search('杭州')
    assert not result['success']
    assert 'synthetic-secret' not in json.dumps(result)


def test_empty_results_are_a_valid_search(provider, monkeypatch):
    module, search = provider
    respond(monkeypatch, module, {'Result': {'WebResults': []}})
    assert search.search('杭州') == {'success': True, 'data': {'web': []}}


def test_timeout_is_safe_and_not_retried(provider, monkeypatch):
    module, search = provider
    calls = []

    def timeout(*args, **kwargs):
        calls.append(1)
        raise httpx.ReadTimeout('synthetic-secret')

    monkeypatch.setattr(module.httpx, 'post', timeout)
    assert search.search('杭州') == {'success': False, 'error': 'Doubao search timed out (30s); no automatic retry.'}
    assert len(calls) == 1


def test_missing_scoped_key_makes_no_network_request(provider, monkeypatch):
    module, search = provider
    monkeypatch.setattr(module, 'get_provider_env', lambda name: '')
    calls = respond(monkeypatch, module, {})
    assert not search.is_available()
    assert not search.search('杭州')['success']
    assert calls == []


@pytest.mark.parametrize('query,limit', [('', 5), ('a' * 101, 5), ('杭州', 0), ('杭州', 51)])
def test_invalid_input_rejected_before_billing(provider, monkeypatch, query, limit):
    module, search = provider
    calls = respond(monkeypatch, module, {})
    assert not search.search(query, limit)['success']
    assert calls == []
