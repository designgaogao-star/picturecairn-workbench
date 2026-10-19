param([switch]$NoOpen, [switch]$Stop)
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$galleryDataPath = if ($env:GALLERY_DATA) { $env:GALLERY_DATA } else { Join-Path $env:LOCALAPPDATA 'GalleryTool' }
New-Item -ItemType Directory -Path $galleryDataPath -Force | Out-Null
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
    } else { Write-Host 'No matching Gallery service is running.' }
    return
}
if (-not $descriptor) {
    $pythonPath = Join-Path $project '.venv\Scripts\pythonw.exe'
    if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Run uv sync --extra dev --extra desktop first.' }
    $sessionToken = [Guid]::NewGuid().ToString('N') + [Guid]::NewGuid().ToString('N')
    $sessionToken | Set-Content -LiteralPath $tokenPath -Encoding ascii -NoNewline
    $env:GALLERY_DATA = $galleryDataPath
    $env:GALLERY_DESKTOP_TOKEN = $sessionToken
    Start-Process -FilePath $pythonPath -WorkingDirectory $project -WindowStyle Hidden -ArgumentList @(
        '-m','gallery','--port','8765','--data',('"' + $galleryDataPath + '"'),
        '--ready-file',('"' + $readyPath + '"'),'--no-open')
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
