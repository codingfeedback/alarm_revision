$ErrorActionPreference = "Stop"

$legacyTaskNames = @(
    "AlarmRevisionDaily0845",
    "AlarmRevisionDaily0830",
    "AlarmRevisionDaily0800"
)
$taskName = "AlarmRevisionDaily0730"
$powershellExe = "C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe"
$scriptPath = Join-Path $PSScriptRoot "run_desktop_cycle.ps1"
$action = '"' + $powershellExe + '" -NoProfile -ExecutionPolicy Bypass -File "' + $scriptPath + '"'

foreach ($legacyTaskName in $legacyTaskNames) {
    cmd /c "schtasks /Delete /TN $legacyTaskName /F >nul 2>&1"
}

schtasks /Create /SC DAILY /ST 07:30 /TN $taskName /TR $action /F
