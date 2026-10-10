param(
  [string]$TaskApiUrl = 'http://127.0.0.1:8080'
)

$ErrorActionPreference = 'Stop'
$workspace = (Resolve-Path $PSScriptRoot).Path
& 'C:\src\flutter\bin\flutter.bat' run -d edge "--dart-define=TASK_API_URL=$TaskApiUrl"
exit $LASTEXITCODE