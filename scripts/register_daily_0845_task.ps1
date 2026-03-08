$ErrorActionPreference = "Stop"

$taskName = "AlarmRevisionDaily0845"
$powershellExe = "C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe"
$scriptPath = Join-Path $PSScriptRoot "run_desktop_cycle.ps1"
$action = "`"$powershellExe`" -NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`""

schtasks /Create /SC DAILY /ST 08:45 /TN $taskName /TR $action /F
