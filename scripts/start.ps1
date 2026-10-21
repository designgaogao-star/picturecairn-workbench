param([switch]$NoOpen, [switch]$Stop, [switch]$Desktop, [string]$DataDirectory,
    [string]$BackendPath, [string]$DesktopPath, [int]$Port = 0)
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$localConfigPath = Join-Path $project 'runtime.local.json'
$localConfig = if (Test-Path -LiteralPath $localConfigPath) { Get-Content -LiteralPath $localConfigPath -Raw | ConvertFrom-Json } else { $null }
$galleryDataPath = if ($DataDirectory) { $DataDirectory } elseif ($env:GALLERY_DATA) { $env:GALLERY_DATA } `
    elseif ($localConfig.dataDirectory) { $localConfig.dataDirectory } else { Join-Path $env:LOCALAPPDATA 'GalleryTool' }
if (-not $BackendPath -and $localConfig.backendPath) { $BackendPath = $localConfig.backendPath }
if (-not $DesktopPath -and $localConfig.desktopPath) { $DesktopPath = $localConfig.desktopPath }
New-Item -ItemType Directory -Path $galleryDataPath -Force | Out-Null
if ($Desktop) {
    if (-not $DesktopPath -or -not (Test-Path -LiteralPath $DesktopPath)) { throw 'Build GalleryTool and set desktopPath in runtime.local.json.' }
    $env:GALLERY_DATA = $galleryDataPath
    Start-Process -FilePath $DesktopPath -WorkingDirectory (Split-Path -Parent $DesktopPath)
    return
}
$readyPath = Join-Path $galleryDataPath 'service.json'
$tokenPath = Join-Path $galleryDataPath 'service-token.txt'
$descriptor = $null
if (Test-Path -LiteralPath $readyPath) {
    try {
        $candidate = Get-Content -LiteralPath $readyPath -Raw | ConvertFrom-Json
        $health = Invoke-RestMethod -Uri ($candidate.url + '/api/v1/health') -TimeoutSec 2
        if ($health.api_version -eq '1' -and $health.instance_id -eq $candidate.instance_id) { $descriptor = $candidate }
    } catch { Write-Verbose $_ }
}
if ($Stop) {
    if ($descriptor -and (Test-Path -LiteralPath $tokenPath)) {
        $sessionToken = Get-Content -LiteralPath $tokenPath -Raw
        Invoke-RestMethod -Method Post -Uri ($descriptor.url + '/api/v1/system/shutdown') `
            -Headers @{'X-Gallery-Desktop'=$sessionToken.Trim()} -TimeoutSec 5 | Out-Null
        Write-Host 'Gallery service is stopping.'
        $deadline = (Get-Date).AddSeconds(30)
        do {
            Start-Sleep -Milliseconds 100
            if (-not (Test-Path -LiteralPath $readyPath)) { return }
            $currentDescriptor = Get-Content -LiteralPath $readyPath -Raw | ConvertFrom-Json
            if ($currentDescriptor.instance_id -ne $descriptor.instance_id) { return }
        } while ((Get-Date) -lt $deadline)
        throw 'Gallery service has not finished stopping; see server.log.'
    } else { Write-Host 'No matching Gallery service is running.' }
    return
}
if (-not $descriptor) {
    $pythonPath = if ($BackendPath) { $BackendPath } else { Join-Path $project '.venv\Scripts\pythonw.exe' }
    if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Run uv sync --extra dev --extra desktop first.' }
    $sessionToken = [Guid]::NewGuid().ToString('N') + [Guid]::NewGuid().ToString('N')
    $sessionToken | Set-Content -LiteralPath $tokenPath -Encoding ascii -NoNewline
    $env:GALLERY_DATA = $galleryDataPath
    $env:GALLERY_DESKTOP_TOKEN = $sessionToken
    $env:GALLERY_APPLICATION = $project
    $backendArguments = @('--port', [string]$Port, '--data', ('"' + $galleryDataPath + '"'),
        '--ready-file', ('"' + $readyPath + '"'), '--no-open')
    if (-not $BackendPath) { $backendArguments = @('-m', 'gallery') + $backendArguments }
    Start-Process -FilePath $pythonPath -WorkingDirectory $project -WindowStyle Hidden -ArgumentList $backendArguments
    $deadline = (Get-Date).AddSeconds(30)
    do {
        Start-Sleep -Milliseconds 100
        if (Test-Path -LiteralPath $readyPath) {
            try {
                $candidate = Get-Content -LiteralPath $readyPath -Raw | ConvertFrom-Json
                $health = Invoke-RestMethod -Uri ($candidate.url + '/api/v1/health') -TimeoutSec 2
                if ($health.instance_id -eq $candidate.instance_id) { $descriptor = $candidate }
            } catch { Write-Verbose $_ }
        }
    } while (-not $descriptor -and (Get-Date) -lt $deadline)
    if (-not $descriptor) { throw "Gallery startup failed. See $galleryDataPath\server.log" }
}
Write-Host $descriptor.url
if (-not $NoOpen) { Start-Process $descriptor.url }
