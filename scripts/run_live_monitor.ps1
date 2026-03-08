$ErrorActionPreference = "Stop"

$projectRoot = Split-Path $PSScriptRoot -Parent
$pythonExe = "D:\anaconda\python.exe"
$summaryDir = Join-Path $projectRoot "data\runs"
New-Item -ItemType Directory -Force $summaryDir | Out-Null
$summaryPath = Join-Path $summaryDir ("live_monitor_{0}.json" -f (Get-Date -Format "yyyyMMdd_HHmmss"))

& $pythonExe (Join-Path $projectRoot "manage.py") run_live_monitor --naver-pages 1 | Tee-Object -FilePath $summaryPath
