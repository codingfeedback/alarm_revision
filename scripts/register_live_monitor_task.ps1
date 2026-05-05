$ErrorActionPreference = "Stop"

$legacyTaskNames = @(
    "AlarmRevisionFastPremarket",
    "AlarmRevisionMarketMonitor"
)
$hourlyTaskName = "AlarmRevisionLiveMonitor"
$premarketTaskName = "AlarmRevisionFastPremarket"
$powershellExe = "C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe"
$scriptPath = Join-Path $PSScriptRoot "run_live_monitor.ps1"
$action = "`"$powershellExe`" -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$scriptPath`""

foreach ($legacyTaskName in $legacyTaskNames) {
    cmd /c "schtasks /Delete /TN $legacyTaskName /F >nul 2>&1"
}

schtasks /Create /SC DAILY /TN $hourlyTaskName /TR $action /ST 08:00 /RI 60 /DU 16:00 /F
schtasks /Create /SC DAILY /TN $premarketTaskName /TR $action /ST 07:00 /RI 15 /DU 02:00 /F
