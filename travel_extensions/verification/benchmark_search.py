"""Explicit live benchmark; never imported by offline tests. 18 requests, ~CNY 0.36."""
import argparse
from datetime import date
import json
from pathlib import Path
import statistics
import time

from travel_extensions.doubao_search.provider import DoubaoSearchProvider


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true', required=True)
    parser.add_argument('--output', type=Path, required=True)
    options = parser.parse_args()
    if options.output.exists():
        raise SystemExit('Output already exists; choose a new report filename.')
    cases = json.loads(Path(__file__).with_name('search-cases.json').read_text(encoding='utf-8'))
    provider = DoubaoSearchProvider()
    if not provider.is_available():
        raise SystemExit('Configure the search key in this isolated Hermes profile first.')
    rows = []
    for trial in range(3):
        for case in cases:
            started = time.perf_counter()
            result = provider.search(case['query'], 5)
            elapsed = round(time.perf_counter() - started, 4)
            items = result.get('data', {}).get('web', [])
            rows.append({'case': case['id'], 'trial': trial + 1, 'seconds': elapsed,
                         'success': result['success'], 'count': len(items),
                         'sources': [{'url': item['url'], 'title': item['title'],
                                      'summary_chars': len(item['description'])} for item in items]})
            print(json.dumps({k: rows[-1][k] for k in ('case', 'trial', 'seconds', 'success', 'count')}), flush=True)
    durations = sorted(row['seconds'] for row in rows)
    report = {'date': date.today().isoformat(), 'kind': 'real_search_not_agent_e2e',
              'provider': 'Doubao direct HTTP', 'count_per_query': 5, 'query_rewrite': False,
              'trials': 3, 'case_count': len(cases), 'request_count': len(rows),
              'estimated_cny': round(len(rows) * 0.02, 2), 'actual_charge': None,
              'median_seconds': statistics.median(durations),
              'p95_seconds_nearest_rank': durations[-1],
              'successes': sum(row['success'] for row in rows), 'rows': rows}
    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
