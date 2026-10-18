"""Copy development plugins into an isolated profile; Hermes remains the loader."""
import argparse
from datetime import datetime, UTC
from pathlib import Path
import shutil

import hermes_yaml as yaml


def configure(home):
    source = Path(__file__).resolve().parent
    home = Path(home).resolve()
    home.mkdir(parents=True, exist_ok=True)
    # PM resolves enabled plugins by directory key; match each manifest name.
    for name, relative in [('doubao_search', 'plugins/web-doubao'), ('travel', 'plugins/travel-enhancements')]:
        destination = home / relative
        destination.mkdir(parents=True, exist_ok=True)
        if destination.resolve() != destination:
            raise ValueError('插件目录不能为链接')
        for path in (source / name).iterdir():
            if path.is_file() and path.suffix in ('.py', '.yaml', '.toml'):
                if (destination / path.name).is_symlink():
                    raise ValueError('插件文件不能为链接')
                shutil.copyfile(path, destination / path.name)
    config_path = home / 'config.yaml'
    previous = yaml.safe_load(config_path.read_text('utf-8')) if config_path.exists() else {}
    config = yaml.safe_load((source / 'config.travel.example.yaml').read_text('utf-8'))
    if previous:
        stamp = datetime.now(UTC).strftime('%Y%m%d-%H%M%S-%f')
        shutil.copyfile(config_path, home / f'config-before-travel-{stamp}.yaml')
        # This is a dedicated travel profile. Preserve unrelated local settings,
        # but explicitly apply the reviewed model, permissions and quota choices.
        merged = {**previous, **config}
        merged['plugins'] = {**previous.get('plugins', {}), **config['plugins']}
        enabled = set(config['plugins']['enabled'])
        if 'langfuse' in previous.get('plugins', {}).get('enabled', []):
            enabled.add('langfuse')
        merged['plugins']['enabled'] = sorted(enabled)
        config = merged
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding='utf-8')
    env_path = home / '.env'
    if not env_path.exists():
        shutil.copyfile(source / '.env.example', env_path)
    else:
        existing = env_path.read_text('utf-8')
        names = {line.partition('=')[0].strip() for line in existing.splitlines() if '=' in line}
        missing = [line for line in (source / '.env.example').read_text('utf-8').splitlines()
                   if '=' in line and not line.startswith('#') and line.partition('=')[0] not in names]
        if missing:
            with env_path.open('a', encoding='utf-8') as stream:
                stream.write('\n' + '\n'.join(missing) + '\n')
    return home


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--home', required=True, help='Dedicated travel profile; do not point at an unrelated production profile')
    print(configure(parser.parse_args().home))
