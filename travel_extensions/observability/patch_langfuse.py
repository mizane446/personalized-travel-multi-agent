"""Version-locked compatibility patch; reuse the official client and sanitizers.

Upstream MIT source: NousResearch/hermes-official-plugins,
c2a95963c442f3f23e4bc6fe0da898e1dd1fb63d, langfuse 2.0.0.
Original files remain beside patched files for inspection and rollback.
"""
import argparse
import hashlib
from pathlib import Path

SOURCE_SHA256 = 'd49fcf5911b3d75170fffe32a599a43d5ab163513db29fbd78a8f214b1015aba'
MANIFEST_SHA256 = '00998e10421fda73a47b05eccf931704c22dff6c08f0a0b7a95ce130deebbb41'

HANDLERS = '''
def on_pre_travel_review(*, aux_task: str = "", api_request_id: str = "", **kwargs: Any) -> None:
    if aux_task != "travel_review" or not api_request_id:
        return
    kwargs["api_call_count"] = f"aux:{aux_task}:{api_request_id}"
    on_pre_llm_request(api_request_id=api_request_id, **kwargs)


def on_post_travel_review(*, aux_task: str = "", api_request_id: str = "",
                          error: Any = None, error_type: str = "", **kwargs: Any) -> None:
    if aux_task != "travel_review" or not api_request_id:
        return
    kwargs["api_call_count"] = f"aux:{aux_task}:{api_request_id}"
    if error is not None:
        # An auxiliary failure must close its generation, not the parent's turn.
        # Keep only the error type; raw provider exceptions may contain secrets.
        kwargs["retryable"] = True
        on_api_request_error(api_request_id=api_request_id, error={"type": error_type}, **kwargs)
    else:
        on_post_llm_call(api_request_id=api_request_id, finish_turn=False, **kwargs)


'''


def patched_source(original):
    if hashlib.sha256(original).hexdigest() != SOURCE_SHA256:
        raise ValueError('Official Langfuse source differs from the pinned version; refusing to patch')
    text = original.decode('utf-8')
    edits = [
        ('response_model: Any = None, moa_references: Any = None, **_: Any) -> None:',
         'response_model: Any = None, moa_references: Any = None, finish_turn: bool = True, **_: Any) -> None:'),
        ('if not has_tools and output.get("content"):', 'if finish_turn and not has_tools and output.get("content"):'),
        ('def _core_ships_langfuse() -> bool:', HANDLERS + 'def _core_ships_langfuse() -> bool:'),
        ('("subagent_stop", on_subagent_stop),',
         '("subagent_stop", on_subagent_stop),\n        ("pre_auxiliary_call", on_pre_travel_review),\n        ("post_auxiliary_call", on_post_travel_review),'),
    ]
    for old, new in edits:
        if text.count(old) != 1:
            raise ValueError('Unexpected upstream patch anchor')
        text = text.replace(old, new)
    return text.encode('utf-8')


def apply(directory, restore=False):
    directory = Path(directory)
    source = directory / '__init__.py'
    backup = directory / '__init__.py.travel-original'
    original = backup.read_bytes() if backup.exists() else source.read_bytes()
    patched = patched_source(original)
    current = source.read_bytes()
    if current not in (original, patched):
        raise ValueError('Installed plugin has unrelated changes; refusing to overwrite')
    manifest = directory / 'plugin.yaml'
    manifest_backup = directory / 'plugin.yaml.travel-original'
    manifest_original = manifest_backup.read_bytes() if manifest_backup.exists() else manifest.read_bytes()
    if hashlib.sha256(manifest_original).hexdigest() != MANIFEST_SHA256:
        raise ValueError('Official Langfuse manifest differs from the pinned version')
    manifest_patch = manifest_original + b'\n# Travel compatibility patch: additional observed auxiliary events.\n'
    # Add within provides_hooks, preserving all upstream environment declarations.
    manifest_patch = manifest_patch.replace(b'  - subagent_stop\n', b'  - subagent_stop\n  - pre_auxiliary_call\n  - post_auxiliary_call\n')
    if manifest.read_bytes() not in (manifest_original, manifest_patch):
        raise ValueError('Plugin manifest has unrelated changes; refusing to overwrite')
    if not backup.exists():
        backup.write_bytes(original)
    if not manifest_backup.exists():
        manifest_backup.write_bytes(manifest_original)
    source.write_bytes(original if restore else patched)
    manifest.write_bytes(manifest_original if restore else manifest_patch)
    return 'restored' if restore else 'patched'


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--plugin', type=Path, required=True)
    parser.add_argument('--restore', action='store_true')
    args = parser.parse_args()
    print(apply(args.plugin, args.restore))
