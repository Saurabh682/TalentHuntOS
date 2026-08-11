param(
    [switch]$SkipBrowser
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw 'uv is required. Install it from https://docs.astral.sh/uv/getting-started/installation/'
}

uv sync --frozen
if (-not $SkipBrowser) {
    uv run playwright install chromium
}

Write-Host 'TalentHunt OS environment is ready.'
Write-Host 'Run: uv run python -m app.main'
Write-Host 'Open: http://127.0.0.1:8080/'
