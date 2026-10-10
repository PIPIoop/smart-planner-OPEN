param(
  [string]$DatabasePath,
  [int]$Port = 8080
)

$ErrorActionPreference = 'Stop'
$workspace = (Resolve-Path $PSScriptRoot).Path
$python = Join-Path $workspace 'services\tg_voice_bot\venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
  throw "Python environment was not found: $python"
}
if (-not [string]::IsNullOrWhiteSpace($DatabasePath)) {
  $env:TASK_DB_PATH = $DatabasePath
}
$env:TASK_API_HOST = '127.0.0.1'
$env:TASK_API_PORT = "$Port"
& $python -m services.task_api
exit $LASTEXITCODE