import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from travel_extensions.travel.research import Research, validate_review
from travel_extensions.travel.wiki import WikiStore


def test_budget_scope_late_results_and_retry_limit(tmp_path):
    research = Research(WikiStore(tmp_path))
    research.begin('a', 'r1')
    job = research.create('a', 'food', '杭州', '不吃辣')
    research.child('a', job, 'child-1')
    with ThreadPoolExecutor(max_workers=8) as pool:
        allowed = list(pool.map(lambda _: research.reserve('child-1'), range(12)))
    assert sum(allowed) == 5
    with pytest.raises(ValueError):
        research.get('b', job)
    research.finish(job, {'complete': False, 'accepted': []})
    assert research.create('a', 'food', '杭州', '再试') == job
    assert research.reserve('child-1') is False
    research.finish(job, {'complete': False, 'accepted': []})
    research.create('a', 'food', '杭州', '第三轮')
    research.finish(job, {'complete': False, 'accepted': []})
    with pytest.raises(ValueError, match='轮'):
        research.create('a', 'food', '杭州', '第四轮')
    research.begin('a', 'r2')
    assert not research.finish(job, {'complete': True}, expected_revision='r1')
    with pytest.raises(ValueError, match='过期'):
        research.get('a', job)
    assert research.reserve('child-1') is False


@pytest.mark.parametrize('answer', [
    {'accepted': [{'text': 'x', 'sources': ['https://invented.test']}], 'complete': True, 'feedback': ''},
    {'accepted': [{'text': 'x', 'sources': []}], 'complete': True, 'feedback': ''},
    {'accepted': [], 'complete': True, 'feedback': ''},
    {'accepted': [], 'complete': 'yes', 'feedback': ''},
])
def test_review_refuses_unsupported_results(answer):
    with pytest.raises(ValueError):
        validate_review(answer, ['https://example.org/source'])


def test_review_source_resolution_and_duplicate_removal():
    item = {'text': '西湖，门票待确认', 'sources': [1]}
    result = validate_review({'accepted': [item, item], 'complete': True, 'feedback': ''}, ['https://example.org/source'])
    assert len(result['accepted']) == 1
    assert result['accepted'][0]['sources'] == ['https://example.org/source']


def test_native_adapter_launch_poll_cancellation_and_restart(tmp_path):
    from travel_extensions.travel.research import ResearchTools
    class Lifecycle:
        def wait(self, handle, timeout_seconds):
            assert timeout_seconds == 15
        def launch(self, request):
            assert request.allowed_toolsets == ('search',)
            return SimpleNamespace(to_dict=lambda: {'id': 'fixture'})
        def result(self, handle):
            return SimpleNamespace(ready=True, terminal_state=SimpleNamespace(value='SUCCEEDED'), summary='sample')
        def cancel(self, handle, reason):
            return SimpleNamespace(accepted=True)
    calls = []
    def review(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(parsed={'accepted': [{'text': '杭州景点', 'sources': [1]}], 'complete': True, 'feedback': ''})
    ctx = SimpleNamespace(subagent_lifecycle=Lifecycle(), llm=SimpleNamespace(complete_structured=review))
    state = Research(WikiStore(tmp_path))
    state.begin('a', 'r1')
    api = ResearchTools(ctx, lambda: state)
    result = json.loads(api.tool({'action': 'start', 'direction': 'food', 'destination': '杭州', 'requirements': '不吃辣'}, session_id='a'))
    job = result['job_id']
    state.child('a', job, 'child')
    state.evidence('child', {'data': {'web': [{'url': 'https://example.org/source', 'description': 'sample'}]}})
    accepted = json.loads(api.tool({'action': 'poll', 'job_id': job}, session_id='a'))
    assert accepted['complete'] is True
    assert json.loads(api.tool({'action': 'poll', 'job_id': job}, session_id='a')) == accepted
    assert len(calls) == 1
    assert 'error' in json.loads(api.tool({'action': 'poll', 'job_id': job}, session_id='b'))
    second = json.loads(api.tool({'action': 'start', 'direction': 'hotel', 'destination': '杭州', 'requirements': '安静'}, session_id='a'))['job_id']
    assert json.loads(api.tool({'action': 'cancel', 'job_id': second}, session_id='a'))['cancelled']
    assert json.loads(api.tool({'action': 'poll', 'job_id': second}, session_id='a'))['state'] == 'CANCELLED'
    state.begin('a', 'r2')
    restarted = json.loads(api.tool({'action': 'start', 'direction': 'food', 'destination': '杭州', 'requirements': '素食'}, session_id='a'))['job_id']
    ctx.subagent_lifecycle.result = lambda handle: SimpleNamespace(ready=False, terminal_state=SimpleNamespace(value='UNKNOWN'))
    assert json.loads(api.tool({'action': 'poll', 'job_id': restarted}, session_id='a'))['state'] == 'UNKNOWN'


def test_cancel_during_review_never_delivers(tmp_path):
    from travel_extensions.travel.research import ResearchTools
    state = Research(WikiStore(tmp_path))
    state.begin('a', 'r')
    job = state.create('a', 'food', '杭州', '清淡')
    state.child('a', job, 'c')
    state.evidence('c', {'data': {'web': [{'url': 'https://example.org/source'}]}})
    state.save_handle(job, {})
    lifecycle = SimpleNamespace(wait=lambda *a, **kw: None,
        result=lambda h: SimpleNamespace(ready=True, terminal_state=SimpleNamespace(value='SUCCEEDED'), summary='fixture'))
    def reviewing(**kwargs):
        state.cancel(job)
        return SimpleNamespace(parsed={'accepted': [{'text': 'x', 'sources': [1]}], 'complete': True, 'feedback': ''})
    ctx = SimpleNamespace(subagent_lifecycle=lifecycle, llm=SimpleNamespace(complete_structured=reviewing))
    assert json.loads(ResearchTools(ctx, lambda: state).tool({'action': 'poll', 'job_id': job}, session_id='a')) == {'state': 'CANCELLED'}
