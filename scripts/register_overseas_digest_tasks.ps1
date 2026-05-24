$ErrorActionPreference = "Stop"

$wscriptExe = "C:\WINDOWS\System32\wscript.exe"
$hiddenRunner = Join-Path $PSScriptRoot "run_hidden.vbs"
$dstScriptPath = Join-Path $PSScriptRoot "run_overseas_digest_1015.ps1"
$standardScriptPath = Join-Path $PSScriptRoot "run_overseas_digest_1115.ps1"
$dstAction = "`"$wscriptExe`" `"$hiddenRunner`" `"$dstScriptPath`""
$standardAction = "`"$wscriptExe`" `"$hiddenRunner`" `"$standardScriptPath`""

schtasks /Create /SC DAILY /ST 10:15 /TN AlarmRevisionOverseasDigestDST /TR $dstAction /F
schtasks /Create /SC DAILY /ST 11:15 /TN AlarmRevisionOverseasDigestStandard /TR $standardAction /F
