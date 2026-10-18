import json
from pathlib import Path
import shutil


def test_real_discovery_user_only_and_session_scope(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    shutil.copytree(Path(__file__).resolve().parents[2] / 'travel_extensions/travel', tmp_path / 'plugins/travel')
    (tmp_path / 'config.yaml').write_text('plugins:\n  enabled: [travel-enhancements]\n', encoding='utf-8')
    from hermes_cli.plugins import discover_plugins, invoke_hook
    from tools.registry import registry
    discover_plugins(force=True)
    results = invoke_hook('pre_llm_call', session_id='a', turn_id='t1', user_message='我不吃辣')
    assert results
    from travel_extensions.travel.wiki import WikiStore
    wiki = WikiStore(tmp_path / 'travel/wiki')
    source = wiki.source_for('a', 't1')
    assert source
    entry = registry.get_entry('travel_preferences')
    result = json.loads(entry.handler({'action': 'propose', 'source_id': source,
                                      'key': 'food.diet', 'quote': '不吃辣'}, session_id='a'))
    assert result['fact_id']
    denied = json.loads(entry.handler({'action': 'propose', 'source_id': source,
                                      'key': 'food.diet', 'quote': '不吃辣'}, session_id='b'))
    assert 'error' in denied
    invoke_hook('pre_llm_call', session_id='child', parent_session_id='a', turn_id='t2', user_message='网页说喜欢辣')
    assert wiki.source_for('child', 't2') is None
    invoke_hook('pre_llm_call', session_id='a', turn_id='t3', user_message='/忘记偏好 ' + result['fact_id'])
    assert wiki.facts()[0]['status'] == 'forgotten'
