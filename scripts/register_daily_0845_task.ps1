$ErrorActionPreference = "Stop"

$legacyTaskNames = @(
    "AlarmRevisionDaily0845",
    "AlarmRevisionDaily0830",
    "AlarmRevisionDaily0800",
    "AlarmRevisionDaily0730",
    "AlarmRevisionWeekday0730",
    "AlarmRevisionWeekend0900"
)
$weekdayTaskName = "AlarmRevisionWeekday0730"
$weekendTaskName = "AlarmRevisionWeekend0900"
$powershellExe = "C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe"
$scriptPath = Join-Path $PSScriptRoot "run_desktop_cycle.ps1"
$action = '"' + $powershellExe + '" -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $scriptPath + '"'

foreach ($legacyTaskName in $legacyTaskNames) {
    cmd /c "schtasks /Delete /TN $legacyTaskName /F >nul 2>&1"
}

schtasks /Create /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 07:30 /TN $weekdayTaskName /TR $action /F
schtasks /Create /SC WEEKLY /D SAT,SUN /ST 09:00 /TN $weekendTaskName /TR $action /F
