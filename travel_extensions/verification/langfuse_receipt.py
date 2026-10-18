"""Read only explicit acceptance traces from a local Langfuse v4 service.

Model/search fixtures and real telemetry ingestion are separate evidence classes.
No transcript, credential, or arbitrary observation metadata is exported.
"""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from .live_flow import read_env


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--env-file', type=Path, required=True)
    parser.add_argument('--trace-id', action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Use a new receipt filename')
    env = read_env(args.env_file)
    base = env['HERMES_LANGFUSE_BASE_URL'].rstrip('/')
    if urlsplit(base).hostname not in ('localhost', '127.0.0.1', '::1'):
        raise ValueError('Only local Langfuse is authorized')
    rows = []
    with httpx.Client(base_url=base, auth=(env['HERMES_LANGFUSE_PUBLIC_KEY'],
                                         env['HERMES_LANGFUSE_SECRET_KEY']), timeout=20) as client:
        for trace_id in args.trace_id:
            cursor = None
            while True:
                params = {'traceId': trace_id, 'limit': 100, 'fields': 'core,basic,usage'}
                if cursor:
                    params['cursor'] = cursor
                response = client.get('/api/public/v2/observations', params=params)
                response.raise_for_status()
                payload = response.json()
                for item in payload['data']:
                    if item['traceId'] != trace_id:
                        raise ValueError('Server returned an unrelated trace')
                    rows.append({key: item.get(key) for key in ('id', 'traceId', 'parentObservationId',
                                 'name', 'type', 'startTime', 'endTime', 'level', 'statusMessage', 'usageDetails')})
                cursor = payload.get('meta', {}).get('cursor')
                if not cursor:
                    break
    if not rows:
        raise ValueError('No observations found; ingestion is not verified')
    report = {'scope': 'real local Langfuse ingestion; synthetic model and search',
              'trace_count': len({row['traceId'] for row in rows}), 'observation_count': len(rows),
              'generation_count': sum(row['type'] == 'GENERATION' for row in rows),
              'error_observations': [row['name'] for row in rows if row['level'] == 'ERROR'],
              'observations': rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    print(json.dumps({key: value for key, value in report.items() if key != 'observations'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
