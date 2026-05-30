# Windows x64 桌面 venv -> sumvideo\dist\venv-win32
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Out = Join-Path $Root "dist\venv-win32"

if (Test-Path $Out) { Remove-Item -Recurse -Force $Out }
python -m venv $Out
& "$Out\Scripts\pip.exe" install -U pip wheel
& "$Out\Scripts\pip.exe" install -r (Join-Path $Root "backend\requirements-desktop-win.txt")
Write-Host "venv ready: $Out"
