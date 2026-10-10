param(
  [string]$EdgeDriverPath,
  [string]$ScreenshotDirectory,
  [string]$TaskApiUrl,
  [string]$WebAdminPassword,
  [int]$FlutterPort = 7357,
  [int]$DriverPort = 4444
)

$ErrorActionPreference = 'Stop'
$workspace = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$temporaryRoot = Join-Path $env:TEMP ("smart_planner_edge_test_{0}" -f [guid]::NewGuid().ToString('N'))
$driverProcess = $null
$flutterProcess = $null
$sessionId = $null

function Wait-ForPort([int]$Port, [int]$TimeoutSeconds = 40) {
  $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
  do {
    if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
      return
    }
    Start-Sleep -Milliseconds 250
  } while ([DateTime]::UtcNow -lt $deadline)
  throw "Port $Port did not start listening within $TimeoutSeconds seconds."
}

function Wait-ForFlutterWeb([string]$StdoutPath, [int]$TimeoutSeconds = 80) {
  $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
  do {
    $output = ''
    if (Test-Path -LiteralPath $StdoutPath) {
      $output = Get-Content -Raw -Encoding UTF8 $StdoutPath -ErrorAction SilentlyContinue
      if ($output.Contains('is being served at')) {
        return
      }
    }
    if ($null -ne $flutterProcess -and $flutterProcess.HasExited) {
      throw "Flutter Web exited before becoming ready. Output: $output"
    }
    Start-Sleep -Milliseconds 300
  } while ([DateTime]::UtcNow -lt $deadline)
  throw "Flutter Web did not report its served URL within $TimeoutSeconds seconds."
}
function Invoke-WebDriver(
  [ValidateSet('Get', 'Post', 'Delete')][string]$Method,
  [string]$Path,
  [object]$Body
) {
  $parameters = @{
    Method = $Method
    Uri = "http://127.0.0.1:$DriverPort$Path"
  }
  if ($null -ne $Body) {
    $parameters.ContentType = 'application/json'
    $parameters.Body = $Body | ConvertTo-Json -Depth 10
  }
  return Invoke-RestMethod @parameters
}

function Save-EdgeScreenshot([string]$FileName) {
  if ([string]::IsNullOrWhiteSpace($ScreenshotDirectory)) {
    return
  }
  New-Item -ItemType Directory -Force -Path $ScreenshotDirectory | Out-Null
  $response = Invoke-WebDriver Get "/session/$sessionId/screenshot" $null
  $bytes = [Convert]::FromBase64String($response.value)
  [IO.File]::WriteAllBytes((Join-Path $ScreenshotDirectory $FileName), $bytes)
}
function Get-PageSource {
  return (Invoke-WebDriver Get "/session/$sessionId/source" $null).value
}

function Find-Element([string]$Selector) {
  $result = Invoke-WebDriver Post "/session/$sessionId/element" @{
    using = 'css selector'
    value = $Selector
  }
  return $result.value.'element-6066-11e4-a52e-4f735466cecf'
}
function Find-Elements([string]$Selector) {
  $result = Invoke-WebDriver Post "/session/$sessionId/elements" @{
    using = 'css selector'
    value = $Selector
  }
  return @($result.value | ForEach-Object {
    $_.'element-6066-11e4-a52e-4f735466cecf'
  })
}

function Click-Element([string]$ElementId) {
  Invoke-WebDriver Post "/session/$sessionId/element/$ElementId/click" @{} | Out-Null
}

function Get-SemanticIdByText([string]$Text) {
  $source = Get-PageSource
  $pattern = '<flt-semantics id="([^"]+)"[^>]*>' + [regex]::Escape($Text) + '</flt-semantics>'
  $match = [regex]::Match($source, $pattern)
  if (-not $match.Success) {
    $labelPattern = '<flt-semantics id="([^"]+)"[^>]*aria-label="' + [regex]::Escape($Text) + '"[^>]*>'
    $match = [regex]::Match($source, $labelPattern)
  }
  if (-not $match.Success) {
    $containsLabelPattern = '<flt-semantics id="([^"]+)"[^>]*aria-label="[^"]*' + [regex]::Escape($Text) + '[^"]*"[^>]*>'
    $match = [regex]::Match($source, $containsLabelPattern)
  }
  if (-not $match.Success) {
    $containsTextPattern = '<flt-semantics id="([^"]+)"[^>]*>[^<]*' + [regex]::Escape($Text) + '[^<]*</flt-semantics>'
    $match = [regex]::Match($source, $containsTextPattern)
  }
  if (-not $match.Success) {
    throw "Semantic element with text or aria-label '$Text' was not found."
  }
  return $match.Groups[1].Value
}
function Click-SemanticText([string]$Text) {
  Write-Host "EDGE CLICK: $Text"
  Click-Element (Find-Element ("#{0}" -f (Get-SemanticIdByText $Text)))
}

function Send-Text([string]$ElementId, [string]$Text) {
  $characters = @($Text.ToCharArray() | ForEach-Object { [string]$_ })
  Invoke-WebDriver Post "/session/$sessionId/element/$ElementId/value" @{
    text = $Text
    value = $characters
  } | Out-Null
}

function Enable-FlutterSemantics([int]$TimeoutSeconds = 60) {
  $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
  do {
    $result = Invoke-WebDriver Post "/session/$sessionId/execute/sync" @{
      script = "const p=document.querySelector('flt-semantics-placeholder'); if(p){p.click(); return true;} return false;"
      args = @()
    }
    if ($result.value -eq $true) {
      Start-Sleep -Milliseconds 600
      return
    }
    Start-Sleep -Milliseconds 250
  } while ([DateTime]::UtcNow -lt $deadline)
  $title = (Invoke-WebDriver Get "/session/$sessionId/title" $null).value
  $url = (Invoke-WebDriver Get "/session/$sessionId/url" $null).value
  $source = Get-PageSource
  $sourcePreview = $source.Substring(0, [Math]::Min(300, $source.Length)).Replace("`r", ' ').Replace("`n", ' ')
  $browserLogs = ''
  try {
    $logResponse = Invoke-WebDriver Post "/session/$sessionId/log" @{ type = 'browser' }
    $browserLogs = ($logResponse.value | ForEach-Object { $_.message }) -join ' | '
  } catch {
    $browserLogs = "browser logs unavailable: $($_.Exception.Message)"
  }
  throw "Flutter accessibility placeholder was not available within $TimeoutSeconds seconds. Title='$title', URL='$url', length=$($source.Length), hasFlutterView=$($source.Contains('<flutter-view')), logs='$browserLogs', source='$sourcePreview'"
}

function Login-WebAdmin {
  Wait-ForSource 'Веб-доступ администратора'
  $passwordInput = Find-Element 'input[data-semantics-role="text-field"]'
  Send-Text $passwordInput $WebAdminPassword
  Click-SemanticText 'Войти'
  Wait-ForSource 'Smart Planner' 12
}

function Assert-SourceContains([string]$Value, [string]$Message) {
  if (-not (Get-PageSource).Contains($Value)) {
    throw $Message
  }
}

function Wait-ForSource([string]$Value, [int]$TimeoutSeconds = 12) {
  $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
  do {
    if ((Get-PageSource).Contains($Value)) {
      return
    }
    Start-Sleep -Milliseconds 250
  } while ([DateTime]::UtcNow -lt $deadline)
  throw "The Edge page did not expose '$Value' within $TimeoutSeconds seconds."
}
function Wait-ForSourceAbsent([string]$Value, [int]$TimeoutSeconds = 12) {
  $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
  do {
    if (-not (Get-PageSource).Contains($Value)) {
      return
    }
    Start-Sleep -Milliseconds 250
  } while ([DateTime]::UtcNow -lt $deadline)
  throw "The Edge page still exposed '$Value' after $TimeoutSeconds seconds."
}

try {
  if (Get-NetTCPConnection -LocalPort $DriverPort,$FlutterPort -State Listen -ErrorAction SilentlyContinue) {
    throw "Ports $DriverPort or $FlutterPort are already in use."
  }
  New-Item -ItemType Directory -Force -Path $temporaryRoot | Out-Null

  if ([string]::IsNullOrWhiteSpace($EdgeDriverPath)) {
    $edgeCandidates = @(
      'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
      'C:\Program Files\Microsoft\Edge\Application\msedge.exe'
    )
    $edgeExecutable = $edgeCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if ($null -eq $edgeExecutable) {
      throw 'Microsoft Edge executable was not found.'
    }
    $edgeVersion = (Get-Item -LiteralPath $edgeExecutable).VersionInfo.ProductVersion
    $driverArchive = Join-Path $temporaryRoot 'edgedriver_win64.zip'
    $driverDirectory = Join-Path $temporaryRoot 'driver'
    $driverUri = "https://msedgedriver.microsoft.com/$edgeVersion/edgedriver_win64.zip"
    Write-Host "Downloading Microsoft Edge WebDriver $edgeVersion..."
    Invoke-WebRequest -Uri $driverUri -OutFile $driverArchive -UseBasicParsing
    Expand-Archive -LiteralPath $driverArchive -DestinationPath $driverDirectory -Force
    $EdgeDriverPath = Join-Path $driverDirectory 'msedgedriver.exe'
  }

  $driverProcess = Start-Process -FilePath $EdgeDriverPath `
    -ArgumentList "--port=$DriverPort" `
    -RedirectStandardOutput (Join-Path $temporaryRoot 'webdriver.stdout.log') `
    -RedirectStandardError (Join-Path $temporaryRoot 'webdriver.stderr.log') `
    -WindowStyle Hidden -PassThru
  Wait-ForPort $DriverPort

  $flutterStdout = Join-Path $temporaryRoot 'flutter.stdout.log'
  $flutterArguments = @('run', '-d', 'web-server', '--web-hostname', '127.0.0.1', '--web-port', "$FlutterPort")
  if (-not [string]::IsNullOrWhiteSpace($TaskApiUrl)) {
    $flutterArguments += "--dart-define=TASK_API_URL=$TaskApiUrl"
  }
  $flutterProcess = Start-Process -FilePath 'C:\src\flutter\bin\flutter.bat' `
    -ArgumentList $flutterArguments `
    -WorkingDirectory $workspace `
    -RedirectStandardOutput $flutterStdout `
    -RedirectStandardError (Join-Path $temporaryRoot 'flutter.stderr.log') `
    -WindowStyle Hidden -PassThru
  Wait-ForPort $FlutterPort 80
  Wait-ForFlutterWeb $flutterStdout 80
  $session = Invoke-WebDriver Post '/session' @{
    capabilities = @{
      alwaysMatch = @{
        browserName = 'MicrosoftEdge'
        'ms:edgeOptions' = @{
          args = @('headless=new', 'window-size=1280,900')
        }
      }
    }
  }
  $sessionId = $session.value.sessionId
  Invoke-WebDriver Post "/session/$sessionId/url" @{ url = "http://127.0.0.1:$FlutterPort/" } | Out-Null
  Start-Sleep -Seconds 3
  Enable-FlutterSemantics

  $apiHeaders = @{}
  if (-not [string]::IsNullOrWhiteSpace($TaskApiUrl)) {
    Login-WebAdmin


    $sessionResponse = Invoke-RestMethod -Method Post `
      -Headers $apiHeaders `
      -Uri "$TaskApiUrl/api/v1/web/session" `
      -ContentType 'application/json; charset=utf-8' `
      -Body (@{ password = $WebAdminPassword } | ConvertTo-Json)
    $apiHeaders = @{
      Authorization = "Session $($sessionResponse.session_token)"
      'X-User-Id' = $sessionResponse.admin_user_id
    }
  }

  Save-EdgeScreenshot 'planner-desktop.png'

  if (-not [string]::IsNullOrWhiteSpace($TaskApiUrl)) {
    Click-SemanticText 'Edge Admin (@edgeadmin)'
    Wait-ForSource 'Edge User (@edgeuser)' 4
    Click-SemanticText 'Edge User (@edgeuser)'
    Wait-ForSource 'Second user private task' 10
    Assert-SourceContains '13:00–14:00' 'The selected user task duration was not displayed.'
    Save-EdgeScreenshot 'planner-second-user.png'
    Click-SemanticText 'Edge User (@edgeuser)'
    Wait-ForSource 'Edge Admin (@edgeadmin)' 4
    Click-SemanticText 'Edge Admin (@edgeadmin)'
    Wait-ForSourceAbsent 'Second user private task' 10
  }

  Wait-ForSource 'Обучение'
  Click-SemanticText 'Обучение'
  Start-Sleep -Milliseconds 350
  Assert-SourceContains 'Добро пожаловать' 'The tutorial did not open.'
  Assert-SourceContains '1 из 6' 'The tutorial did not start at step 1.'
  Save-EdgeScreenshot 'planner-tutorial.png'
  foreach ($expectedTitle in @('Поиск задач', 'Календарь', 'План выбранного дня', 'Новая задача', 'Резервная копия')) {
    Click-SemanticText 'Далее'
    Start-Sleep -Milliseconds 250
    Assert-SourceContains $expectedTitle "Tutorial step '$expectedTitle' was not shown."
  }
  Assert-SourceContains '6 из 6' 'The tutorial did not reach its final step.'
  Click-SemanticText 'Готово'
  Start-Sleep -Milliseconds 250
  if ((Get-PageSource).Contains('6 из 6')) {
    throw 'The tutorial did not close after the final step.'
  }
  if (-not [string]::IsNullOrWhiteSpace($TaskApiUrl)) {
    Click-SemanticText 'Данные'
    Start-Sleep -Milliseconds 250
    Click-SemanticText 'Группы и цвета'
    Wait-ForSource 'Группы задач' 5
    Click-SemanticText 'Новая группа'
    Wait-ForSource 'Название группы' 3
    $groupInput = Find-Element 'input[data-semantics-role="text-field"]'
    Send-Text $groupInput 'Edge Work'
    Click-SemanticText 'Цвет группы #14B8A6'
    Click-SemanticText 'Создать'
    Wait-ForSource 'Edge Work' 5

    $groupResponse = Invoke-RestMethod -Headers $apiHeaders -Uri "$TaskApiUrl/api/v1/groups"
    $edgeGroups = @($groupResponse.GetEnumerator() | Where-Object { $_.name -eq 'Edge Work' })
    if ($edgeGroups.Count -ne 1 -or $edgeGroups[0].colorHex -ne '#14B8A6') {
      throw 'The colored group was not persisted through the shared API.'
    }
    $edgeGroupId = $edgeGroups[0].id
    Click-SemanticText 'Закрыть'
    Wait-ForSource 'Новая задача' 5
    Start-Sleep -Milliseconds 300
    $groupedTaskTimestamp = [DateTime]::UtcNow.ToString('o')
    $groupedTaskPayload = @{
      id = 'edge-grouped-task'
      title = 'Edge grouped task'
      note = 'Created for the colored group Edge scenario'
      date = (Get-Date).ToString('yyyy-MM-dd')
      startMinute = $null
      priority = 'normal'
      isCompleted = $false
      groupId = $edgeGroupId
      createdAt = $groupedTaskTimestamp
      updatedAt = $groupedTaskTimestamp
    }
    Invoke-RestMethod -Method Post `
      -Headers $apiHeaders `
      -Uri "$TaskApiUrl/api/v1/tasks" `
      -ContentType 'application/json; charset=utf-8' `
      -Body ($groupedTaskPayload | ConvertTo-Json) | Out-Null
    Wait-ForSource 'Edge grouped task' 10

    $taskResponse = Invoke-RestMethod -Headers $apiHeaders -Uri "$TaskApiUrl/api/v1/tasks"
    $edgeGroupedTasks = @($taskResponse.GetEnumerator() | Where-Object { $_.title -eq 'Edge grouped task' })
    if ($edgeGroupedTasks.Count -ne 1 -or $edgeGroupedTasks[0].groupId -ne $edgeGroupId) {
      throw 'The task was not assigned to its selected group.'
    }
    Invoke-RestMethod -Method Delete -Headers $apiHeaders -Uri "$TaskApiUrl/api/v1/groups/$edgeGroupId" | Out-Null
    Start-Sleep -Seconds 3
    $allAfterGroupDelete = Invoke-RestMethod -Headers $apiHeaders -Uri "$TaskApiUrl/api/v1/tasks"
    $ungroupedTask = @($allAfterGroupDelete.GetEnumerator() | Where-Object { $_.id -eq $edgeGroupedTasks[0].id })[0]
    if ($null -ne $ungroupedTask.groupId) {
      throw 'Deleting a group did not leave its task ungrouped.'
    }
    Invoke-RestMethod -Method Delete -Headers $apiHeaders -Uri "$TaskApiUrl/api/v1/tasks/$($edgeGroupedTasks[0].id)" | Out-Null
    Wait-ForSourceAbsent 'Edge grouped task' 10
  }

  if (-not [string]::IsNullOrWhiteSpace($TaskApiUrl)) {
    Click-SemanticText 'Новая цель'
    Start-Sleep -Milliseconds 400
    Wait-ForSource 'Создать цель'
    $goalInputs = Find-Elements 'input[data-semantics-role="text-field"]'
    if ($goalInputs.Count -lt 1) {
      throw 'Goal dialog did not expose its title field.'
    }
    Send-Text $goalInputs[0] 'Edge fitness goal'
    Click-SemanticText 'Создать цель'
    Wait-ForSource 'Edge fitness goal' 8
    Assert-SourceContains '0% · 0 из' 'Goal progress was not displayed.'
    Click-SemanticText 'Скрыть прогресс целей'
    Wait-ForSource 'Показать прогресс целей' 3
    Click-SemanticText 'Показать прогресс целей'
    Wait-ForSource 'Скрыть прогресс целей' 3

    $createdGoals = @(Invoke-RestMethod -Headers $apiHeaders -Uri "$TaskApiUrl/api/v1/goals")
    if ($createdGoals.Count -ne 1) {
      throw 'Goal was not persisted through the shared API.'
    }
    $createdGoalId = $createdGoals[0].id
    $goalScenarioTaskResponse = Invoke-RestMethod -Headers $apiHeaders -Uri "$TaskApiUrl/api/v1/tasks"
    $generatedGoalTasks = @(
      $goalScenarioTaskResponse.GetEnumerator() |
        Where-Object { $_.goalId -eq $createdGoalId }
    )
    if ($generatedGoalTasks.Count -ne 16) {
      throw "Expected 16 generated goal tasks, got $($generatedGoalTasks.Count)."
    }
    if ($generatedGoalTasks | Where-Object { $_.title -ne 'Edge fitness goal' }) {
      throw 'Generated task title did not follow the full goal title.'
    }
    $firstGoalTask = $generatedGoalTasks[0]
    $firstGoalTask.isCompleted = $true
    $firstGoalTask.completedAt = [DateTime]::UtcNow.ToString('o')
    $firstGoalTask.updatedAt = $firstGoalTask.completedAt
    Invoke-RestMethod -Method Put `
      -Headers $apiHeaders `
      -Uri "$TaskApiUrl/api/v1/tasks/$($firstGoalTask.id)" `
      -ContentType 'application/json; charset=utf-8' `
      -Body ($firstGoalTask | ConvertTo-Json -Depth 5) | Out-Null
    Wait-ForSource 'Вовремя: 1' 10

    Invoke-RestMethod -Method Delete `
      -Headers $apiHeaders `
      -Uri "$TaskApiUrl/api/v1/goals/$createdGoalId" | Out-Null
    Wait-ForSourceAbsent 'Edge fitness goal' 10
  }
  if (-not [string]::IsNullOrWhiteSpace($TaskApiUrl)) {
    $timestamp = [DateTime]::UtcNow.ToString('o')
    $liveTask = @{
      id = 'edge-live-sync-task'
      title = 'Telegram live sync'
      note = 'Created outside Flutter while the page is open'
      date = (Get-Date).ToString('yyyy-MM-dd')
      startMinute = 600
      durationMinutes = 90
      priority = 'normal'
      isCompleted = $false
      createdAt = $timestamp
      updatedAt = $timestamp
    }
    Invoke-RestMethod -Method Post `
      -Headers $apiHeaders `
      -Uri "$TaskApiUrl/api/v1/tasks" `
      -ContentType 'application/json; charset=utf-8' `
      -Body ($liveTask | ConvertTo-Json) | Out-Null
    Wait-ForSource 'Telegram live sync' 10
    Wait-ForSource '10:00–11:30' 10

    Invoke-RestMethod -Method Delete `
      -Headers $apiHeaders `
      -Uri "$TaskApiUrl/api/v1/tasks/edge-live-sync-task" | Out-Null
    Wait-ForSourceAbsent 'Telegram live sync' 10
  }
  Wait-ForSource 'Новая задача'
  Click-SemanticText 'Новая задача'
  Start-Sleep -Milliseconds 400
  Click-SemanticText 'Создать'
  Start-Sleep -Milliseconds 300
  Assert-SourceContains 'Введите название задачи' 'An empty title was accepted.'

  $titleInput = Find-Element 'input[data-semantics-role="text-field"]'
  Send-Text $titleInput 'Edge browser test'
  Click-SemanticText 'Добавить время'
  Start-Sleep -Milliseconds 400
  Click-SemanticText 'ОК'
  Start-Sleep -Milliseconds 400
  Wait-ForSource 'Длительность'

  Click-SemanticText 'Длительность'
  Start-Sleep -Milliseconds 300
  Click-SemanticText '2 ч'
  Start-Sleep -Milliseconds 300
  Click-SemanticText 'Создать'
  Start-Sleep -Milliseconds 600
  Assert-SourceContains 'Edge browser test' 'The task was not created.'
  Assert-SourceContains '09:00–11:00' 'The selected two-hour duration was not displayed.'

  Invoke-WebDriver Post "/session/$sessionId/refresh" @{} | Out-Null
  Start-Sleep -Seconds 3
  Enable-FlutterSemantics
  Login-WebAdmin
  Wait-ForSource 'Edge browser test'
  Assert-SourceContains 'Edge browser test' 'The task did not survive an Edge refresh.'

  $source = Get-PageSource
  $taskTag = [regex]::Matches($source, '<flt-semantics[^>]+>') |
    Where-Object { $_.Value.Contains('Edge browser test') -and $_.Value.Contains('role="checkbox"') } |
    Select-Object -First 1
  if ($null -eq $taskTag) {
    throw 'The task checkbox semantic node was not found.'
  }
  $taskId = [regex]::Match($taskTag.Value, 'id="([^"]+)"').Groups[1].Value
  Click-Element (Find-Element "#$taskId")
  Start-Sleep -Milliseconds 500
  Assert-SourceContains '1 выполнено' 'Task completion did not update.'

  $searchInput = Find-Element 'input[data-semantics-role="text-field"]'
  Send-Text $searchInput 'missing'
  Start-Sleep -Milliseconds 500
  if ((Get-PageSource).Contains('Edge browser test')) {
    throw 'Search did not hide a non-matching task.'
  }

  Invoke-WebDriver Post "/session/$sessionId/refresh" @{} | Out-Null
  Start-Sleep -Seconds 3
  Enable-FlutterSemantics
  Login-WebAdmin
  Wait-ForSource 'Действия с задачей'
  Click-SemanticText 'Действия с задачей'
  Start-Sleep -Milliseconds 250
  Wait-ForSource 'Удалить'
  Click-SemanticText 'Удалить'
  Start-Sleep -Milliseconds 300
  Assert-SourceContains 'Удалить задачу' 'Delete confirmation did not open.'
  Click-SemanticText 'Удалить'
  Start-Sleep -Milliseconds 500
  Assert-SourceContains '0 задач' 'The task was not deleted.'

  Invoke-WebDriver Post "/session/$sessionId/window/rect" @{
    width = 480
    height = 900
    x = 0
    y = 0
  } | Out-Null
  Start-Sleep -Milliseconds 500
  Assert-SourceContains 'Smart Planner' 'The planner failed in a narrow Edge window.'
  Save-EdgeScreenshot 'planner-mobile.png'

  Write-Host 'EDGE WEB TESTS PASSED'
  Write-Host 'Covered: load, 6-step tutorial, colored group create/assign/delete, goal creation/16-task schedule/mood/collapse, live API sync without refresh, empty-title validation, timed create with 2-hour duration, refresh persistence, complete, search, delete confirmation, narrow window.'
}
finally {
  if ($null -ne $sessionId) {
    try { Invoke-WebDriver Delete "/session/$sessionId" $null | Out-Null } catch { }
  }
  if ($null -ne $flutterProcess) {
    Stop-Process -Id $flutterProcess.Id -Force -ErrorAction SilentlyContinue
  }
  if ($null -ne $driverProcess) {
    Stop-Process -Id $driverProcess.Id -Force -ErrorAction SilentlyContinue
  }
  foreach ($port in @($FlutterPort, $DriverPort)) {
    $listeners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    foreach ($listener in $listeners) {
      Stop-Process -Id $listener.OwningProcess -Force -ErrorAction SilentlyContinue
    }
  }
  Start-Sleep -Milliseconds 500
  if (Test-Path -LiteralPath $temporaryRoot) {
    Remove-Item -LiteralPath $temporaryRoot -Recurse -Force -ErrorAction SilentlyContinue
  }
}
