$ErrorActionPreference = "Stop"
$env:PYTHONPATH = "$PSScriptRoot\..\vendor_lib"

python "$PSScriptRoot\..\manage.py" runserver
