# Scarica una build statica di ffmpeg e copia ffmpeg.exe / ffprobe.exe in bin\ (chiamato da build.bat).
param(
    [string]$Url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
    [string]$Dest = "bin"
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

if ([string]::IsNullOrWhiteSpace($Url)) { $Url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip" }
$zip = Join-Path $env:TEMP "confmerge-ffmpeg.zip"
$tmp = Join-Path $env:TEMP "confmerge-ffmpeg"
Write-Host "Download da $Url ..."
Invoke-WebRequest -Uri $Url -OutFile $zip -UseBasicParsing
if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
Expand-Archive -Path $zip -DestinationPath $tmp
$ff = Get-ChildItem -Path $tmp -Recurse -Filter ffmpeg.exe | Select-Object -First 1
if (-not $ff) { throw "ffmpeg.exe non trovato nell'archivio scaricato" }
$fp = Join-Path $ff.DirectoryName "ffprobe.exe"
if (-not (Test-Path $fp)) { throw "ffprobe.exe non trovato nell'archivio scaricato" }
New-Item -ItemType Directory -Force -Path $Dest | Out-Null
Copy-Item $ff.FullName (Join-Path $Dest "ffmpeg.exe") -Force
Copy-Item $fp (Join-Path $Dest "ffprobe.exe") -Force
$lic = Get-ChildItem -Path $tmp -Recurse -Filter "LICENSE*" | Select-Object -First 1
if ($lic) { Copy-Item $lic.FullName (Join-Path $Dest "FFMPEG-LICENSE.txt") -Force }
Remove-Item $zip -Force -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
Write-Host "ffmpeg e ffprobe copiati in $Dest"
