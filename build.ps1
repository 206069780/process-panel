param([switch]$SingleFile)

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
$buildDist = Join-Path $PSScriptRoot $(if ($SingleFile) { 'dist\singlefile' } else { 'dist' })
$previousMode = [Environment]::GetEnvironmentVariable('PORTSIDE_SINGLE_FILE', 'Process')
try {
    $env:PORTSIDE_SINGLE_FILE = $(if ($SingleFile) { '1' } else { '0' })
    & $buildPython -m PyInstaller --noconfirm --clean --distpath $buildDist Portside.spec
    if ($LASTEXITCODE -ne 0) { throw 'EXE build failed.' }
}
finally {
    if ($null -eq $previousMode) { Remove-Item Env:PORTSIDE_SINGLE_FILE -ErrorAction SilentlyContinue }
    else { $env:PORTSIDE_SINGLE_FILE = $previousMode }
}
if ($SingleFile) {
    Write-Host ('Ready: ' + (Join-Path $buildDist 'Portside.exe'))
}
else {
    $portableArchive = Join-Path $buildDist 'Portside-windows-x64.zip'
    Compress-Archive -LiteralPath (Join-Path $buildDist 'Portside') -DestinationPath $portableArchive -Force
    Write-Host ('Ready: ' + (Join-Path $buildDist 'Portside\Portside.exe'))
    Write-Host ('Portable ZIP: ' + $portableArchive)
}
