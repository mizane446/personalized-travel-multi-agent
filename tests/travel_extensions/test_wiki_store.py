"""Evidence, conflict, restart and concurrency contracts using synthetic people."""
from concurrent.futures import ThreadPoolExecutor

import pytest

from travel_extensions.travel.wiki import WikiStore


def test_evidence_conflict_confirmation_and_restart(tmp_path):
    wiki = WikiStore(tmp_path)
    first = wiki.record('session-a', 'turn-1', '我不吃辣')
    fact = wiki.propose(first, 'food.diet', '不吃辣')
    assert wiki.propose(first, 'food.diet', '不吃辣') == fact
    with pytest.raises(ValueError, match='原话'):
        wiki.propose(first, 'food.diet', '花生过敏')
    second = wiki.record('session-b', 'turn-2', '现在可以吃微辣')
    other = wiki.propose(second, 'food.diet', '微辣')
    assert 'conflict' in {f['status'] for f in wiki.facts()}
    wiki.confirm(other)
    restored = WikiStore(tmp_path)
    assert [f['quote'] for f in restored.facts() if f['status'] == 'active'] == ['微辣']
    assert restored.lint() == []
    assert 'sources:' in (tmp_path / 'Wiki/preferences.md').read_text('utf-8')
    assert (tmp_path / f'Raw/{first}.md').read_text('utf-8').endswith('我不吃辣\n')


@pytest.mark.parametrize('case', ['missing_source', 'invented_quote', 'unknown_key', 'changed_raw'])
def test_invalid_writes_rejected(tmp_path, case):
    wiki = WikiStore(tmp_path)
    source = wiki.record('session-a', 'turn-1', '不吃辣')
    with pytest.raises(ValueError):
        if case == 'missing_source':
            wiki.propose('missing', 'food.diet', '不吃辣')
        elif case == 'invented_quote':
            wiki.propose(source, 'food.diet', '海鲜过敏')
        elif case == 'unknown_key':
            wiki.propose(source, '../../x', '不吃辣')
        else:
            wiki.record('session-a', 'turn-1', '改写原话')
    assert wiki.facts() == []


def test_profiles_concurrency_and_projection_repair(tmp_path):
    a, b = WikiStore(tmp_path / 'a'), WikiStore(tmp_path / 'b')
    source = a.record('session-a', 'turn-a', '住宿预算500元，喜欢安静')
    with ThreadPoolExecutor(max_workers=6) as pool:
        ids = list(pool.map(lambda _: a.propose(source, 'hotel.budget', '500元'), range(12)))
    assert len(set(ids)) == 1
    assert b.facts() == []
    with pytest.raises(ValueError):
        b.propose(source, 'hotel.budget', '500元')
    (tmp_path / 'a/Wiki/preferences.md').write_text('手工篡改', encoding='utf-8')
    assert a.lint()
    a.project()
    assert not a.lint()
    a.forget(ids[0])
    assert a.facts()[0]['status'] == 'forgotten'
    # Windows refuses this if a completed transaction still holds a connection.
    a.path.unlink()
