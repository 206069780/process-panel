$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$buildPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $buildPython)) {
    if (Get-Command py -ErrorAction SilentlyContinue) { & py -3 -m venv .venv }
    elseif (Get-Command python -ErrorAction SilentlyContinue) { & python -m venv .venv }
    else { throw 'Python 3.10 or newer is required to build the EXE.' }
    if ($LASTEXITCODE -ne 0) { throw 'Failed to create Python virtual environment.' }
}
& $buildPython -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw 'Failed to install build dependencies.' }
New-Item -ItemType Directory -Path (Join-Path $PSScriptRoot 'assets') -Force | Out-Null
& $buildPython -c "from panel.tray import icon_image; icon_image().save('assets/portside.ico', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])"
if ($LASTEXITCODE -ne 0) { throw 'Failed to generate the application icon.' }
& $buildPython -m PyInstaller --noconfirm --clean Portside.spec
if ($LASTEXITCODE -ne 0) { throw 'EXE build failed.' }
Write-Host ('Ready: ' + (Join-Path $PSScriptRoot 'dist\Portside.exe'))
