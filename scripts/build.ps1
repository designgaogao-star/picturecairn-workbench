# GalleryTool portable build. Requires PowerShell 7, uv and Node.js.
param([switch]$NoZip)

$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectDir '.venv\Scripts\python.exe'
Push-Location $projectDir
try {
    & uv sync --frozen --extra dev --extra desktop --link-mode copy
    if ($LASTEXITCODE -ne 0) { throw 'Locked Python environment setup failed.' }
    & npm ci
    if ($LASTEXITCODE -ne 0) { throw 'Locked Node dependency setup failed.' }
    & node node_modules/electron/install.js
    if ($LASTEXITCODE -ne 0) { throw 'Electron runtime download failed.' }
    & npm run contract
    if ($LASTEXITCODE -ne 0) { throw 'API contract export failed.' }
    & npm run check
    if ($LASTEXITCODE -ne 0) { throw 'TypeScript contract check failed.' }
    & npm run brand:build
    if ($LASTEXITCODE -ne 0) { throw 'Brand asset validation and conversion failed.' }
    & npm run ui:build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
} finally { Pop-Location }
$electronDir = Join-Path $projectDir 'node_modules\electron\dist'
if (-not (Test-Path -LiteralPath (Join-Path $electronDir 'electron.exe'))) {
    throw 'Electron is missing. Run npm ci first.'
}
& $pythonPath -c 'import PIL, numpy, scipy, fastapi, uvicorn, watchfiles, pythoncom, PyInstaller'
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
Copy-Item -Path (Join-Path $electronDir '*') -Exclude 'electron.exe' -Destination $appDir -Recurse
& node (Join-Path $PSScriptRoot 'stamp-desktop.mjs') (Join-Path $electronDir 'electron.exe') (Join-Path $appDir 'GalleryTool.exe')
if ($LASTEXITCODE -ne 0) { throw 'Desktop icon and version metadata update failed.' }
$appResources = Join-Path $appDir 'resources\app'
New-Item -ItemType Directory -Path $appResources | Out-Null
Copy-Item -LiteralPath (Join-Path $projectDir 'electron') -Destination $appResources -Recurse
Copy-Item -LiteralPath (Join-Path $projectDir 'output\brand\runtime') -Destination (Join-Path $appResources 'electron\brand') -Recurse
@{
    name = $package.name
    version = $package.version
    releaseChannel = $package.releaseChannel
    releaseLabel = $package.releaseLabel
    productName = $package.productName
    description = $package.description
    main = $package.main
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $appResources 'package.json') -Encoding utf8NoBOM

Write-Host '[3/4] Adding backend...'
Copy-Item -LiteralPath $backendSource -Destination (Join-Path $appDir 'resources\backend') -Recurse
& $pythonPath (Join-Path $PSScriptRoot 'collect_licenses.py') --app $appDir
if ($LASTEXITCODE -ne 0) { throw 'Third-party license collection failed.' }
Copy-Item -LiteralPath (Join-Path $projectDir 'docs\portable-readme.md') -Destination (Join-Path $appDir 'README.md')

$manifestPath = Join-Path $outputDir 'release-manifest.json'
& $pythonPath (Join-Path $PSScriptRoot 'write_release_manifest.py') --app $appDir --output $manifestPath
if ($LASTEXITCODE -ne 0) { throw 'Build manifest generation failed.' }
Copy-Item -LiteralPath $manifestPath -Destination (Join-Path $appDir 'release-manifest.json')

if (-not $NoZip) {
    Write-Host '[4/4] Creating portable archive...'
    $archivePath = Join-Path $outputDir 'GalleryTool-dev-win-x64.zip'
    Compress-Archive -Path (Join-Path $appDir '*') -DestinationPath $archivePath
    $archiveHash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
    "$archiveHash  $(Split-Path -Leaf $archivePath)" | Set-Content -LiteralPath ($archivePath + '.sha256') -Encoding ascii
    & $pythonPath (Join-Path $PSScriptRoot 'write_release_manifest.py') --archive $archivePath `
        --output (Join-Path $outputDir 'archive-verification.json')
    if ($LASTEXITCODE -ne 0) { throw 'Portable archive verification failed.' }
    Write-Host "Archive: $archivePath"
}
Write-Host "Ready: $appDir\GalleryTool.exe"
