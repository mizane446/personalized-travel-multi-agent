param([switch]$Desktop)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$env:HERMES_HOME = Join-Path $projectRoot '.hermes-runtime/profile'
$env:HERMES_RUNTIME_DIR = Join-Path $projectRoot '.hermes-runtime/tools'
$env:HERMES_TUI_TOOLSETS = 'search,travel'
$env:PYTHONUTF8 = '1'
Set-Location $projectRoot
. (Join-Path $projectRoot 'activate.ps1') -TestExtras web
if ($Desktop) {
    $env:HERMES_DESKTOP_HERMES_ROOT = $projectRoot
    $env:HERMES_DESKTOP_PYTHON = (Get-Command python).Source
    $env:HERMES_DESKTOP_USER_DATA_DIR = Join-Path $projectRoot '.hermes-runtime/desktop'
    $env:HERMES_DESKTOP_IGNORE_EXISTING = '1'
    $env:HERMES_DESKTOP_ISOLATED_BACKEND = '1'
    # Launch explicitly requested by the person running this command.
    npm run start --workspace apps/desktop
} else {
    python -m hermes_cli.main chat
}
