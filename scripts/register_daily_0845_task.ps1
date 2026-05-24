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
$wscriptExe = "C:\WINDOWS\System32\wscript.exe"
$hiddenRunner = Join-Path $PSScriptRoot "run_hidden.vbs"
$scriptPath = Join-Path $PSScriptRoot "run_desktop_cycle.ps1"
$action = '"' + $wscriptExe + '" "' + $hiddenRunner + '" "' + $scriptPath + '"'

foreach ($legacyTaskName in $legacyTaskNames) {
    cmd /c "schtasks /Delete /TN $legacyTaskName /F >nul 2>&1"
}

schtasks /Create /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 07:30 /TN $weekdayTaskName /TR $action /F
schtasks /Create /SC WEEKLY /D SAT,SUN /ST 09:00 /TN $weekendTaskName /TR $action /F
