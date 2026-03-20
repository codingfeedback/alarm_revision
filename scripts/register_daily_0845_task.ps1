$ErrorActionPreference = "Stop"

$legacyTaskName = "AlarmRevisionDaily0845"
$taskName = "AlarmRevisionDaily0830"
$powershellExe = "C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe"
$scriptPath = Join-Path $PSScriptRoot "run_desktop_cycle.ps1"
$action = '"' + $powershellExe + '" -NoProfile -ExecutionPolicy Bypass -File "' + $scriptPath + '"'

schtasks /Delete /TN $legacyTaskName /F 2>$null | Out-Null
schtasks /Create /SC DAILY /ST 08:30 /TN $taskName /TR $action /F
