"""Thin protocol adapter; Hermes owns the tool, dispatch and profile isolation."""
from urllib.parse import urlsplit

import httpx

from agent.web_search_provider import WebSearchProvider, get_provider_env

ENDPOINT = 'https://open.feedcoopapi.com/search_api/web_search'
KEY_ENV = 'ASK_ECHO_SEARCH_INFINITY_API_KEY'


def failure(message):
    return {'success': False, 'error': message}


def normalize(payload, limit):
    if not isinstance(payload, dict):
        return failure('Doubao returned a non-object response.')
    metadata = payload.get('ResponseMetadata') or {}
    if not isinstance(metadata, dict) or metadata.get('Error'):
        # Remote diagnostics may echo request data or credentials.
        return failure('Doubao reported an API error; check credentials, quota and request limits.')
    result = payload.get('Result')
    rows = result.get('WebResults') if isinstance(result, dict) else None
    if not isinstance(rows, list):
        return failure('Doubao response is missing Result.WebResults.')
    items = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        url = row.get('Url')
        if not isinstance(url, str):
            continue
        try:
            parsed = urlsplit(url)
            valid = parsed.scheme in {'https', 'http'} and parsed.hostname and not parsed.username
        except ValueError:
            valid = False
        if not valid:
            continue
        summary = row.get('Summary') or row.get('Snippet') or ''
        title = row.get('Title') or ''
        items.append({'title': title if isinstance(title, str) else '', 'url': url,
                      'description': summary if isinstance(summary, str) else '',
                      'position': len(items) + 1})
        if len(items) == limit:
            break
    if rows and not items:
        return failure('Doubao returned results without usable source URLs.')
    return {'success': True, 'data': {'web': items}}


class DoubaoSearchProvider(WebSearchProvider):
    @property
    def name(self):
        return 'doubao'

    @property
    def display_name(self):
        return 'Doubao Search · direct API'

    def is_available(self):
        return bool(get_provider_env(KEY_ENV))

    def search(self, query, limit=5):
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 100:
            return failure('Query must contain 1–100 characters; split longer requests into focused searches.')
        if type(limit) is not int or not 1 <= limit <= 50:
            return failure('Search result limit must be an integer from 1 to 50.')
        key = get_provider_env(KEY_ENV)
        if not key:
            return failure(f'{KEY_ENV} is not configured for this profile.')
        try:
            response = httpx.post(
                ENDPOINT,
                headers={'Authorization': f'Bearer {key}'},
                json={'Query': query.strip(), 'SearchType': 'web', 'Count': limit,
                      'Filter': {'NeedContent': False, 'NeedUrl': True},
                      'QueryControl': {'QueryRewrite': False}},
                timeout=30, follow_redirects=False,
            )
            if response.status_code != 200:
                return failure(f'Doubao search HTTP {response.status_code}; no automatic retry.')
            return normalize(response.json(), limit)
        except httpx.TimeoutException:
            return failure('Doubao search timed out (30s); no automatic retry.')
        except httpx.HTTPError:
            return failure('Doubao search network error; no automatic retry.')
        except ValueError:
            return failure('Doubao returned invalid JSON.')
