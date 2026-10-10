param(
  [string]$EdgeDriverPath,
  [string]$ScreenshotDirectory,
  [int]$ApiPort = 8080,
  [int]$FlutterPort = 7357,
  [int]$DriverPort = 4444
)

$ErrorActionPreference = 'Stop'
$workspace = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $workspace 'services\tg_voice_bot\venv\Scripts\python.exe'
$temporaryRoot = Join-Path $env:TEMP ("smart_planner_shared_test_{0}" -f [guid]::NewGuid().ToString('N'))
$apiProcess = $null
$previousDatabasePath = $env:TASK_DB_PATH
$previousHost = $env:TASK_API_HOST
$previousPort = $env:TASK_API_PORT
$previousServiceToken = $env:TASK_API_SERVICE_TOKEN
$previousWebPassword = $env:TASK_API_WEB_ADMIN_PASSWORD
$serviceToken = 'edge-test-service-token-000000000000000000000000'
$webAdminPassword = 'edge-test-web-admin-password'
$adminId = '100'
$userId = '200'

function Wait-ForApi([string]$Url, [int]$TimeoutSeconds = 40) {
  $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
  do {
    try {
      $health = Invoke-RestMethod -Uri "$Url/health" -TimeoutSec 2
      if ($health.status -eq 'ok') { return }
    } catch { }
    if ($null -ne $apiProcess -and $apiProcess.HasExited) {
      throw 'Task API exited before becoming ready.'
    }
    Start-Sleep -Milliseconds 250
  } while ([DateTime]::UtcNow -lt $deadline)
  throw "Task API did not become ready within $TimeoutSeconds seconds."
}

try {
  if (-not (Test-Path -LiteralPath $python)) { throw "Python environment was not found: $python" }
  if (Get-NetTCPConnection -LocalPort $ApiPort -State Listen -ErrorAction SilentlyContinue) { throw "Port $ApiPort is already in use." }
  New-Item -ItemType Directory -Force -Path $temporaryRoot | Out-Null
  $env:TASK_DB_PATH = Join-Path $temporaryRoot 'tasks.sqlite3'
  $env:TASK_API_HOST = '127.0.0.1'
  $env:TASK_API_PORT = "$ApiPort"
  $env:TASK_API_SERVICE_TOKEN = $serviceToken
  $env:TASK_API_WEB_ADMIN_PASSWORD = $webAdminPassword
  $apiUrl = "http://127.0.0.1:$ApiPort"
  $apiProcess = Start-Process -FilePath $python `
    -ArgumentList @('-m', 'services.task_api') `
    -WorkingDirectory $workspace `
    -RedirectStandardOutput (Join-Path $temporaryRoot 'api.stdout.log') `
    -RedirectStandardError (Join-Path $temporaryRoot 'api.stderr.log') `
    -WindowStyle Hidden -PassThru
  Wait-ForApi $apiUrl

  $serviceHeaders = @{ Authorization = "Bearer $serviceToken" }
  Invoke-RestMethod -Method Post -Uri "$apiUrl/api/v1/users/bootstrap-admin" -Headers $serviceHeaders -ContentType 'application/json; charset=utf-8' -Body (@{ telegramUserId = $adminId; username = 'edgeadmin'; displayName = 'Edge Admin' } | ConvertTo-Json) | Out-Null
  Invoke-RestMethod -Method Post -Uri "$apiUrl/api/v1/users/requests" -Headers $serviceHeaders -ContentType 'application/json; charset=utf-8' -Body (@{ telegramUserId = $userId; username = 'edgeuser'; displayName = 'Edge User' } | ConvertTo-Json) | Out-Null
  $webSession = Invoke-RestMethod -Method Post -Uri "$apiUrl/api/v1/web/session" -ContentType 'application/json; charset=utf-8' -Body (@{ password = $webAdminPassword } | ConvertTo-Json)
  $adminHeaders = @{ Authorization = "Session $($webSession.session_token)"; 'X-User-Id' = $webSession.admin_user_id }
  Invoke-RestMethod -Method Post -Uri "$apiUrl/api/v1/users/$userId/status/active" -Headers $adminHeaders | Out-Null

  $timestamp = [DateTime]::UtcNow.ToString('o')
  $userTask = @{ id = 'edge-second-user-task'; title = 'Second user private task'; note = 'Must never appear in the admin calendar'; date = (Get-Date).ToString('yyyy-MM-dd'); startMinute = 780; durationMinutes = 60; priority = 'normal'; isCompleted = $false; createdAt = $timestamp; updatedAt = $timestamp }
  Invoke-RestMethod -Method Post -Uri "$apiUrl/api/v1/tasks?userId=$userId" -Headers $adminHeaders -ContentType 'application/json; charset=utf-8' -Body ($userTask | ConvertTo-Json) | Out-Null

  & (Join-Path $PSScriptRoot 'run_edge_web_tests.ps1') -EdgeDriverPath $EdgeDriverPath -ScreenshotDirectory $ScreenshotDirectory -TaskApiUrl $apiUrl -WebAdminPassword $webAdminPassword -FlutterPort $FlutterPort -DriverPort $DriverPort
  if ($null -ne $LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw "Edge test runner exited with code $LASTEXITCODE." }

  $remainingAdminRaw = Invoke-RestMethod -Headers $adminHeaders -Uri "$apiUrl/api/v1/tasks"
  $remainingAdmin = @($remainingAdminRaw | Where-Object { $null -ne $_ })
  if ($remainingAdmin.Count -ne 0) {
    $remainingJson = $remainingAdmin | Select-Object id,title,goalId | ConvertTo-Json -Compress
    throw "The Edge flow left admin records: $remainingJson"
  }
  $remainingUserRaw = Invoke-RestMethod -Headers $adminHeaders -Uri "$apiUrl/api/v1/tasks?userId=$userId"
  $remainingUser = @($remainingUserRaw | Where-Object { $null -ne $_ })
  if ($remainingUser.Count -ne 1 -or $remainingUser[0].id -ne 'edge-second-user-task') { throw 'The second user calendar was changed by the admin calendar flow.' }
  Write-Host 'SHARED MULTI-USER STACK EDGE TESTS PASSED'
}
finally {
  if ($null -ne $apiProcess) { Stop-Process -Id $apiProcess.Id -Force -ErrorAction SilentlyContinue }
  $env:TASK_DB_PATH = $previousDatabasePath
  $env:TASK_API_HOST = $previousHost
  $env:TASK_API_PORT = $previousPort
  $env:TASK_API_SERVICE_TOKEN = $previousServiceToken
  $env:TASK_API_WEB_ADMIN_PASSWORD = $previousWebPassword
  if (Test-Path -LiteralPath $temporaryRoot) { Remove-Item -LiteralPath $temporaryRoot -Recurse -Force -ErrorAction SilentlyContinue }
}