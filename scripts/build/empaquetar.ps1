param([switch]$SinInstalar)
$ErrorActionPreference = 'Stop'
$Project = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Scripts = Join-Path $Project 'scripts'
$BuildEnv = Join-Path $PSScriptRoot '.venv'
$Version = (Get-Content (Join-Path $Project 'VERSION') -Raw).Trim()
if (-not $SinInstalar) {
    if (-not (Test-Path $BuildEnv)) { py -3.11 -m venv $BuildEnv }
    & (Join-Path $BuildEnv 'Scripts\python.exe') -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo preparar pip en el entorno de construcción.' }
    & (Join-Path $BuildEnv 'Scripts\python.exe') -m pip install -r (Join-Path $Project 'scripts\requirements.txt') pyinstaller
    if ($LASTEXITCODE -ne 0) { throw 'Falló la instalación de dependencias en el entorno de construcción.' }
}
$Python = Join-Path $BuildEnv 'Scripts\python.exe'
if (-not (Test-Path $Python)) { throw "No existe el entorno de construcción: $Python" }
Push-Location $Scripts
try { & $Python -m PyInstaller --noconfirm --clean --distpath (Join-Path $Project 'dist') --workpath (Join-Path $Project 'build\pyinstaller') (Join-Path $PSScriptRoot 'MKClips.spec') }
finally { Pop-Location }
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller no pudo construir MKClips.' }
$Dist = Join-Path $Project 'dist'
if (-not (Test-Path (Join-Path $Dist 'MKClips\MKClips.exe'))) { throw 'PyInstaller terminó sin crear dist/MKClips/MKClips.exe.' }
$ZipPath = Join-Path $Dist "MKClips-v$Version-win64.zip"
if (Test-Path $ZipPath) { Remove-Item -LiteralPath $ZipPath -Force }
Compress-Archive -Path (Join-Path $Dist 'MKClips\*') -DestinationPath $ZipPath -CompressionLevel Optimal
Write-Host "Creado: $ZipPath"
Write-Host "Tamaño: $([math]::Round((Get-Item $ZipPath).Length / 1MB, 2)) MiB"
