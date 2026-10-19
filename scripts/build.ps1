# GalleryTool portable build. Requires PowerShell 7, Node.js and Python 3.9+.
param([switch]$NoZip)

$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $PSScriptRoot
$pythonPath = $env:GALLERY_PYTHON
if (-not $pythonPath) {
    $pythonPath = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
    if (-not (Test-Path -LiteralPath $pythonPath)) { $pythonPath = 'python' }
}
$electronDir = Join-Path $projectDir 'node_modules\electron\dist'
if (-not (Test-Path -LiteralPath (Join-Path $electronDir 'electron.exe'))) {
    throw 'Electron is missing. Run npm ci first.'
}
& $pythonPath -c 'import PIL, numpy, scipy, PyInstaller'
if ($LASTEXITCODE -ne 0) { throw 'Install Python dependencies: pip install -e ".[desktop]"' }

$package = Get-Content -LiteralPath (Join-Path $projectDir 'package.json') -Raw | ConvertFrom-Json
$outputDir = Join-Path $projectDir ('build-out\' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
$appDir = Join-Path $outputDir 'GalleryTool'
$backendDir = Join-Path $outputDir 'backend-dist'
New-Item -ItemType Directory -Path $outputDir | Out-Null

Write-Host '[1/4] Building Python backend...'
& $pythonPath -m PyInstaller (Join-Path $PSScriptRoot 'gallery.spec') --noconfirm `
    --distpath $backendDir --workpath (Join-Path $outputDir 'pyi') *> (Join-Path $outputDir 'build.log')
if ($LASTEXITCODE -ne 0) { throw "Backend build failed. See $outputDir\build.log" }
$backendSource = Join-Path $backendDir 'gallery_server'
if (-not (Test-Path -LiteralPath (Join-Path $backendSource 'gallery_server.exe'))) {
    throw 'Backend executable was not produced.'
}

Write-Host '[2/4] Assembling Electron app...'
New-Item -ItemType Directory -Path $appDir | Out-Null
Copy-Item -Path (Join-Path $electronDir '*') -Destination $appDir -Recurse
Rename-Item -LiteralPath (Join-Path $appDir 'electron.exe') -NewName 'GalleryTool.exe'
$appResources = Join-Path $appDir 'resources\app'
New-Item -ItemType Directory -Path $appResources | Out-Null
Copy-Item -LiteralPath (Join-Path $projectDir 'electron') -Destination $appResources -Recurse
@{
    name = $package.name
    version = $package.version
    description = $package.description
    main = $package.main
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $appResources 'package.json') -Encoding utf8NoBOM

Write-Host '[3/4] Adding backend...'
Copy-Item -LiteralPath $backendSource -Destination (Join-Path $appDir 'resources\backend') -Recurse

if (-not $NoZip) {
    Write-Host '[4/4] Creating portable archive...'
    $archivePath = Join-Path $outputDir ("GalleryTool-$($package.version)-win-x64.zip")
    Compress-Archive -Path (Join-Path $appDir '*') -DestinationPath $archivePath
}
Write-Host "Ready: $appDir\GalleryTool.exe"
