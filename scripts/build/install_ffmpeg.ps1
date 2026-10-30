param(
    [Parameter(Mandatory = $true)]
    [string]$InstallDir
)

$ErrorActionPreference = 'Stop'
$version = '9.0.2'
$archiveUrl = "https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-$version-essentials_build.zip"
$expectedSha256 = '60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba'
$workDir = Join-Path $env:TEMP ("MKClips-FFmpeg-" + [guid]::NewGuid().ToString('N'))
$exitCode = 0

try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    New-Item -ItemType Directory -Path $workDir -Force | Out-Null
    $archive = Join-Path $workDir 'ffmpeg.zip'
    $extractDir = Join-Path $workDir 'unpacked'

    Invoke-WebRequest -UseBasicParsing -Uri $archiveUrl -OutFile $archive
    $actualSha256 = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualSha256 -ne $expectedSha256) {
        throw 'La verificacion SHA-256 de FFmpeg fallo. No se instalara el archivo descargado.'
    }

    Expand-Archive -LiteralPath $archive -DestinationPath $extractDir -Force
    $ffmpeg = Get-ChildItem -LiteralPath $extractDir -Filter 'ffmpeg.exe' -File -Recurse | Select-Object -First 1
    if (-not $ffmpeg) { throw 'El paquete descargado no contiene ffmpeg.exe.' }
    $ffprobe = Join-Path $ffmpeg.DirectoryName 'ffprobe.exe'
    if (-not (Test-Path -LiteralPath $ffprobe)) { throw 'El paquete descargado no contiene ffprobe.exe.' }

    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
    Copy-Item -LiteralPath $ffmpeg.FullName -Destination (Join-Path $InstallDir 'ffmpeg.exe') -Force
    Copy-Item -LiteralPath $ffprobe -Destination (Join-Path $InstallDir 'ffprobe.exe') -Force
    $readme = Get-ChildItem -LiteralPath $extractDir -Filter 'README.txt' -File -Recurse | Select-Object -First 1
    if ($readme) {
        Copy-Item -LiteralPath $readme.FullName -Destination (Join-Path $InstallDir 'FFmpeg-BUILD-README.txt') -Force
    }
    @"
FFmpeg $version Essentials for Windows x64, provided by Gyan Doshi.
This build is licensed under GPLv3 and includes libx264.
Build and package information: https://www.gyan.dev/ffmpeg/builds/
FFmpeg source: https://github.com/FFmpeg/FFmpeg/commit/946fcce07b
FFmpeg license: https://ffmpeg.org/legal.html
Package SHA-256: $expectedSha256
"@ | Set-Content -LiteralPath (Join-Path $InstallDir 'FFmpeg-THIRD-PARTY.txt') -Encoding UTF8

    & (Join-Path $InstallDir 'ffmpeg.exe') -version | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'FFmpeg se instalo pero no pudo iniciarse.' }
}
catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    $exitCode = 1
}
finally {
    if (Test-Path -LiteralPath $workDir) {
        Remove-Item -LiteralPath $workDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

exit $exitCode
