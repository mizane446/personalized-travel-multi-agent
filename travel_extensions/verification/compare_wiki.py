"""Synthetic integrity challenge; NOT a model hallucination benchmark."""
import json
from pathlib import Path
import tempfile

from travel_extensions.travel.wiki import WikiStore


def run():
    with tempfile.TemporaryDirectory() as tmp:
        wiki = WikiStore(Path(tmp) / 'wiki')
        source = wiki.record('synthetic', '1', '我不吃辣')
        attacks = {
            'missing_source': lambda: wiki.propose('missing', 'food.diet', '不吃辣'),
            'invented_quote': lambda: wiki.propose(source, 'food.diet', '花生过敏'),
            'unknown_key': lambda: wiki.propose(source, '../../x', '不吃辣'),
            'changed_raw': lambda: wiki.record('synthetic', '1', '改写原话'),
        }
        cases = []
        for name, attack in attacks.items():
            # Explicitly unguarded editable-file baseline: same invalid payload is accepted.
            (Path(tmp) / 'MEMORY.md').write_text(name, encoding='utf-8')
            try:
                attack()
                rejected = False
            except ValueError:
                rejected = True
            cases.append({'case': name, 'plain_file_rejected': False, 'wiki_rejected': rejected})
        wiki.propose(source, 'food.diet', '不吃辣')
        changed = wiki.record('synthetic', '2', '现在吃微辣')
        wiki.propose(changed, 'food.diet', '微辣')
        return {'method': 'synthetic write-validation challenge, no LLM', 'cases': cases,
                'conflicting_facts_retained': len([f for f in wiki.facts() if f['status'] == 'conflict']),
                'limitation': 'Does not measure semantic correctness, model hallucinations or upstream Hermes memory quality.'}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('output')
    args = parser.parse_args()
    target = Path(args.output)
    with target.open('x', encoding='utf-8') as stream:
        json.dump(run(), stream, ensure_ascii=False, indent=2)
