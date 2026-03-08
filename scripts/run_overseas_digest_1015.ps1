$ErrorActionPreference = "Stop"

$projectRoot = Split-Path $PSScriptRoot -Parent
$pythonExe = "D:\anaconda\python.exe"
$summaryDir = Join-Path $projectRoot "data\runs"
New-Item -ItemType Directory -Force $summaryDir | Out-Null
$summaryPath = Join-Path $summaryDir ("overseas_digest_dst_{0}.json" -f (Get-Date -Format "yyyyMMdd_HHmmss"))

& $pythonExe (Join-Path $projectRoot "manage.py") send_scheduled_digest --region overseas --respect-us-dst dst | Tee-Object -FilePath $summaryPath
