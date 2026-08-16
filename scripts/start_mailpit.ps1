param(
    [string]$Executable = "mailpit"
)

$ErrorActionPreference = "Stop"
$command = Get-Command $Executable -ErrorAction SilentlyContinue
if (-not $command) {
    throw "Mailpit is not installed. Download a reviewed v1.30.0 or newer release from https://github.com/axllent/mailpit/releases"
}

Write-Host "Starting local Mailpit UI at http://127.0.0.1:8025 and SMTP at 127.0.0.1:1025"
& $command.Source `
    --listen 127.0.0.1:8025 `
    --smtp 127.0.0.1:1025 `
    --disable-version-check `
    --block-remote-css-and-fonts `
    --smtp-disable-rdns `
    --max 100 `
    --max-age 1d `
    --max-message-size 10
