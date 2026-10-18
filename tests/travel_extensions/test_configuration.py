def test_dedicated_profile_keeps_secrets_and_effective_limits(tmp_path, monkeypatch):
    import hermes_yaml as yaml
    from travel_extensions.configure import configure
    profile = tmp_path / 'profile'
    profile.mkdir()
    (profile / '.env').write_text('DEEPSEEK_API_KEY=fixture-private\n', encoding='utf-8')
    (profile / 'config.yaml').write_text('display:\n  language: zh-CN\n', encoding='utf-8')
    configure(profile)
    assert 'fixture-private' in (profile / '.env').read_text('utf-8')
    monkeypatch.setenv('HERMES_HOME', str(profile))
    from hermes_cli.config import load_config
    config = load_config()
    assert config['delegation']['max_concurrent_children'] == 3
    assert config['delegation']['max_spawn_depth'] == 1
    assert config['delegation']['inherit_mcp_toolsets'] is False
    assert config['tools']['tool_search']['enabled'] == 'off'
    assert config['model']['provider'] == 'deepseek'
    assert config['model']['default'] == 'deepseek-v4-pro'
    assert config['delegation']['model'] == 'deepseek-flash'
    assert config['auxiliary']['travel_review']['model'] == 'deepseek-flash'
    assert list(profile.glob('config-before-travel-*.yaml'))
    stored = yaml.safe_load((profile / 'config.yaml').read_text('utf-8'))
    assert 'fixture-private' not in str(stored)
    from pm.workspace import enabled_member_dirs
    assert profile / 'plugins/travel-enhancements' in enabled_member_dirs()
