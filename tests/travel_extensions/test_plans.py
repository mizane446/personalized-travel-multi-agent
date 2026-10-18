import pytest

from travel_extensions.travel.plans import Plans
from travel_extensions.travel.research import Research
from travel_extensions.travel.wiki import WikiStore


def seed(tmp_path):
    state = Research(WikiStore(tmp_path / 'wiki'))
    state.begin('a', 'revision')
    job = state.create('a', 'attraction', '杭州', '两个独立景点')
    state.finish(job, {'reviewed': True, 'accepted': [{'text': '西湖，时间待确认', 'sources': ['https://example.org/westlake']}],
                       'complete': False, 'feedback': '缺少第二个景点'})
    return state, job, Plans(state)


def test_save_idempotency_versions_sources_and_markdown(tmp_path):
    _state, job, plans = seed(tmp_path)
    first = plans.save('a', '杭州方案', [job])
    assert plans.save('a', '杭州方案', [job]) == first
    assert 'https://example.org/westlake' in plans.load('a')['markdown']
    assert '缺少第二个景点' in plans.load('a')['markdown']
    second = plans.save('a', '调整后的标题', [job])
    assert second['version'] == 2
    assert plans.load('a', 1)['title'] == '杭州方案'
    exported = plans.export('a', 1, 'markdown')
    original = exported['markdown']
    assert original.is_file()
    assert plans.export('a', 1, 'markdown')['markdown'] != original
    assert original.is_file()


def test_scope_stale_and_cancelled_rejected(tmp_path):
    state, job, plans = seed(tmp_path)
    with pytest.raises(ValueError):
        plans.save('b', 'x', [job])
    state.cancel(job)
    with pytest.raises(ValueError):
        plans.save('a', 'x', [job])
    state.begin('a', 'next')
    with pytest.raises(ValueError):
        plans.save('a', 'x', [job])


def test_invalid_or_unreviewed_plan_rejected(tmp_path):
    state, job, plans = seed(tmp_path)
    with pytest.raises(ValueError):
        plans.save('a', '', [job])
    state.finish(job, {'accepted': [{'text': 'raw', 'sources': []}], 'complete': True})
    with pytest.raises(ValueError):
        plans.save('a', 'x', [job])
    with pytest.raises(ValueError):
        plans.load('a', 0)


def test_pdf_failure_does_not_publish_partial_markdown(tmp_path, monkeypatch):
    _state, job, plans = seed(tmp_path)
    plans.save('a', '杭州', [job])
    def fail(*args):
        raise ValueError('字体不可用')
    monkeypatch.setattr('travel_extensions.travel.plans.render_pdf', fail)
    with pytest.raises(ValueError, match='字体'):
        plans.export('a', format='both')
    assert not list((tmp_path / 'exports').rglob('*.md'))
