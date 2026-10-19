$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
Set-Location (Split-Path $PSScriptRoot -Parent)
function Check-Exit { if ($LASTEXITCODE -ne 0) { throw '构建失败，请检查上方输出' } }
python -m venv .venv
Check-Exit
& .venv/Scripts/python.exe -m pip install -r requirements.txt
Check-Exit
npm ci
Check-Exit
& .venv/Scripts/python.exe -m unittest discover -s tests -v
Check-Exit
& .venv/Scripts/python.exe scripts/package_core.py
Check-Exit
npm run tauri -- build
Check-Exit
