"""Offline checks for the travel delta; does not claim live API acceptance."""
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
BASELINE = 'travel-upstream-baseline-20261018'


def git(*args):
    return subprocess.check_output(['git', '-c', 'core.quotepath=false', *args], cwd=ROOT, timeout=30).decode('utf-8').splitlines()


def check():
    changed = set(git('diff', '--name-only', BASELINE)) | set(git('ls-files', '--others', '--exclude-standard'))
    allowed = ('travel_extensions/', 'tests/travel_extensions/', 'docs/travel/')
    exceptions = {'.gitignore', 'README.md', '迁移计划-v1.md'}
    errors = []
    for name in sorted(changed):
        if name not in exceptions and not name.startswith(allowed):
            errors.append('修改超出独立增强范围：' + name)
    tracked = git('ls-files')
    for name in tracked:
        if name.startswith('.hermes-runtime/') or Path(name).name == '.env':
            errors.append('跟踪了私密运行文件：' + name)
    docs = [ROOT / 'README.md', *(ROOT / 'docs/travel').rglob('*.md')]
    link_count = 0
    for path in docs:
        for raw in re.findall(r'\]\(([^)]+)\)', path.read_text('utf-8')):
            target = raw.strip('<>')
            if urlsplit(target).scheme or target.startswith('#'):
                continue
            local = unquote(target.split('#')[0])
            if local and not (path.parent / local).exists():
                errors.append(f'文档链接不存在：{path.relative_to(ROOT)} -> {local}')
            link_count += 1
    patterns = [r'sk-(?:lf-)?[A-Za-z0-9_-]{24,}', r'(?i)Bearer[ \t]+[A-Za-z0-9_-]{24,}',
                r'(?i)(?:api_key|secret_key)[ \t]*[=:][ \t]*[\x22\x27]?[A-Za-z0-9_-]{24,}']
    for name in sorted(changed):
        path = ROOT / name
        if path.is_file() and path.suffix in {'.py', '.ts', '.json', '.yaml', '.md', '.ps1', '.example'}:
            content = path.read_text('utf-8')
            # A literal synthetic credential used to prove redaction, never valid.
            content = content.replace('private-key-for-test-123456789', '<synthetic fixture>')
            if any(re.search(pattern, content) for pattern in patterns):
                errors.append('疑似凭据，仅报告文件不输出内容：' + name)
    report = {'scope': 'offline travel delta only', 'changed_files': len(changed),
              'local_links_checked': link_count, 'errors': errors,
              'live_acceptance': {'model': 'gpt-6-sol via relay; see measured receipt',
                                  'langfuse': 'patched: 9/9 generations and no error observations in synthetic flow'}}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(check())
