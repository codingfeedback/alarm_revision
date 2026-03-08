$ErrorActionPreference = "Stop"

$taskName = "AlarmRevisionLiveMonitor"
$powershellExe = "C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe"
$scriptPath = Join-Path $PSScriptRoot "run_live_monitor.ps1"
$action = "`"$powershellExe`" -NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`""

schtasks /Create /SC DAILY /TN $taskName /TR $action /ST 08:00 /RI 15 /DU 15:45 /F
