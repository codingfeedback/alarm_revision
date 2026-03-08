$ErrorActionPreference = "Stop"

$tasks = @(
    "AlarmRevisionDaily0845",
    "AlarmRevisionLiveMonitor",
    "AlarmRevisionOverseasDigestDST",
    "AlarmRevisionOverseasDigestStandard"
)

powercfg /SETACVALUEINDEX SCHEME_CURRENT SUB_SLEEP RTCWAKE 1 | Out-Null
powercfg /SETACTIVE SCHEME_CURRENT | Out-Null

foreach ($taskName in $tasks) {
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction Stop
    $task.Settings.WakeToRun = $true
    Set-ScheduledTask -TaskName $taskName -Settings $task.Settings | Out-Null
}
