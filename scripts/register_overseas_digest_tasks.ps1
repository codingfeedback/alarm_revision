$ErrorActionPreference = "Stop"

$powershellExe = "C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe"
$dstScriptPath = Join-Path $PSScriptRoot "run_overseas_digest_1015.ps1"
$standardScriptPath = Join-Path $PSScriptRoot "run_overseas_digest_1115.ps1"
$dstAction = "`"$powershellExe`" -NoProfile -ExecutionPolicy Bypass -File `"$dstScriptPath`""
$standardAction = "`"$powershellExe`" -NoProfile -ExecutionPolicy Bypass -File `"$standardScriptPath`""

schtasks /Create /SC DAILY /ST 10:15 /TN AlarmRevisionOverseasDigestDST /TR $dstAction /F
schtasks /Create /SC DAILY /ST 11:15 /TN AlarmRevisionOverseasDigestStandard /TR $standardAction /F
