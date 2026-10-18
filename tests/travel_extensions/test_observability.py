"""Optional installed official-plugin regression; no live SDK or credentials."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.fixture
def plugin(monkeypatch):
    path = Path(__file__).resolve().parents[2] / '.hermes-runtime/profile/plugins/langfuse/__init__.py'
    if not path.exists():
        pytest.skip('Install the pinned optional Langfuse plugin before this integration test')
    spec = importlib.util.spec_from_file_location('travel_test_langfuse', path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


def test_auxiliary_registration_and_request_identity(plugin, monkeypatch):
    hooks = {}
    monkeypatch.setattr(plugin, '_core_ships_langfuse', lambda: False)
    plugin.register(SimpleNamespace(register_hook=lambda name, fn: hooks.update({name: fn})))
    assert {'pre_auxiliary_call', 'post_auxiliary_call'} <= hooks.keys()
    pre = Mock()
    post = Mock()
    error = Mock()
    monkeypatch.setattr(plugin, 'on_pre_llm_request', pre)
    monkeypatch.setattr(plugin, 'on_post_llm_call', post)
    monkeypatch.setattr(plugin, 'on_api_request_error', error)
    event = dict(aux_task='travel_review', session_id='s', turn_id='t', api_request_id='r1', api_call_count=1)
    hooks['pre_auxiliary_call'](**event)
    hooks['post_auxiliary_call'](**event, usage={'input_tokens': 20, 'output_tokens': 20})
    assert pre.call_args.kwargs['api_call_count'] == 'aux:travel_review:r1'
    assert post.call_args.kwargs['api_call_count'] == 'aux:travel_review:r1'
    assert post.call_args.kwargs['finish_turn'] is False
    assert post.call_args.kwargs['usage']['input_tokens'] == 20
    hooks['pre_auxiliary_call'](**{**event, 'api_request_id': 'r2'})
    assert pre.call_args.kwargs['api_call_count'] == 'aux:travel_review:r2'
    hooks['post_auxiliary_call'](**event, error='sensitive raw exception', error_type='TimeoutError')
    assert error.call_args.kwargs['retryable'] is True
    assert error.call_args.kwargs['error'] == {'type': 'TimeoutError'}
    hooks['pre_auxiliary_call'](**{**event, 'aux_task': 'title_generation'})
    assert pre.call_count == 2, 'Patch is scoped to travel_review, not every auxiliary service'


def test_review_end_preserves_parent_trace(plugin, monkeypatch):
    generation = Mock()
    state = SimpleNamespace(turn_tool_calls=[])
    monkeypatch.setattr(plugin, '_client_and_key', lambda *args: (object(), 'parent'))
    monkeypatch.setattr(plugin, '_pop_generation', lambda *args: (state, generation))
    finish = Mock()
    monkeypatch.setattr(plugin, '_finish_trace', finish)
    plugin.on_post_llm_call(assistant_content_chars=12, finish_turn=False)
    finish.assert_not_called()
    plugin.on_post_llm_call(assistant_content_chars=12)
    finish.assert_called_once()


def test_patch_is_repeatable_reversible_and_refuses_drift(plugin, tmp_path):
    from travel_extensions.observability.patch_langfuse import apply
    installed = Path(plugin.__file__).parent
    for name in ('__init__.py', 'plugin.yaml'):
        original = installed / (name + '.travel-original')
        (tmp_path / name).write_bytes((original if original.exists() else installed / name).read_bytes())
    before = (tmp_path / '__init__.py').read_bytes()
    apply(tmp_path)
    after = (tmp_path / '__init__.py').read_bytes()
    assert after != before
    apply(tmp_path)
    assert (tmp_path / '__init__.py').read_bytes() == after
    apply(tmp_path, restore=True)
    assert (tmp_path / '__init__.py').read_bytes() == before
    (tmp_path / '__init__.py').write_bytes(before + b'\n# unrelated user edit\n')
    with pytest.raises(ValueError, match='unrelated'):
        apply(tmp_path)
