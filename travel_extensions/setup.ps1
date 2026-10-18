param([switch]$SkipBootstrap, [switch]$WithLangfuse)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$env:HERMES_HOME = Join-Path $projectRoot '.hermes-runtime/profile'
$env:HERMES_RUNTIME_DIR = Join-Path $projectRoot '.hermes-runtime/tools'
$env:PYTHONUTF8 = '1'
Set-Location $projectRoot
if (-not $SkipBootstrap) {
    & (Join-Path $projectRoot 'setup-hermes.ps1') -RuntimeOnly -TestExtras web
    if ($LASTEXITCODE -ne 0) { throw '官方环境安装失败' }
}
. (Join-Path $projectRoot 'activate.ps1') -TestExtras web
python -m travel_extensions.configure --home $env:HERMES_HOME
if ($LASTEXITCODE -ne 0) { throw '旅行 profile 配置失败' }
if ($WithLangfuse -and -not (Test-Path (Join-Path $env:HERMES_HOME 'plugins/langfuse/__init__.py'))) {
    python -m hermes_cli.main plugins install langfuse --ref c2a95963c442f3f23e4bc6fe0da898e1dd1fb63d --yes-deps --enable
    if ($LASTEXITCODE -ne 0) { throw '官方 Langfuse 固定版本安装失败' }
}
if (Test-Path (Join-Path $env:HERMES_HOME 'plugins/langfuse/__init__.py')) {
    python -m travel_extensions.observability.patch_langfuse --plugin (Join-Path $env:HERMES_HOME 'plugins/langfuse')
    if ($LASTEXITCODE -ne 0) { throw 'Langfuse 兼容补丁失败；保留原文件，不跳过版本校验' }
}
python -m hermes_cli.main plugins validate (Join-Path $env:HERMES_HOME 'plugins/travel-enhancements') --install-deps
if ($LASTEXITCODE -ne 0) { throw '旅行插件依赖或验证失败' }
# PM publishes a new environment; activate it before the next command.
. (Join-Path $projectRoot 'activate.ps1') -TestExtras web
python -c 'import reportlab; print("PDF dependency ready:", reportlab.Version)'
if ($LASTEXITCODE -ne 0) { throw '重新激活后 PDF 依赖缺失，不能标记安装成功' }
python -m hermes_cli.main plugins doctor (Join-Path $env:HERMES_HOME 'plugins/travel-enhancements')
if ($LASTEXITCODE -ne 0) { throw '插件运行检查失败' }
Write-Host '将中转站密钥填入 CUSTOM_API_KEY，搜索密钥填入 ASK_ECHO_SEARCH_INFINITY_API_KEY，然后运行 travel_extensions/start.ps1。'
