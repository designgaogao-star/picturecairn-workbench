# Isolated source and desktop validation. Never runs native recycle-bin probes.
param(
    [string]$Desktop,
    [switch]$SkipUi,
    [int]$SoakMinutes = 0
)

$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectDir '.venv\Scripts\python.exe'
if ($SoakMinutes -ne 0 -and ($SoakMinutes -lt 60 -or -not $Desktop)) {
    throw 'A soak test requires -Desktop and at least 60 minutes.'
}
if ($Desktop) { $Desktop = (Resolve-Path -LiteralPath $Desktop).Path }

function Invoke-Check([string]$Command, [string[]]$Arguments) {
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Validation failed: $Command $($Arguments -join ' ')" }
}

Push-Location $projectDir
try {
    Invoke-Check -Command $pythonPath -Arguments @('scripts/public_release_check.py', '--json')
    Invoke-Check -Command 'npm' -Arguments @('run', 'contract')
    Invoke-Check -Command 'npm' -Arguments @('run', 'check')
    Invoke-Check -Command 'npm' -Arguments @('run', 'ui:check')
    Invoke-Check -Command 'npm' -Arguments @('run', 'brand:build')
    Invoke-Check -Command 'npm' -Arguments @('run', 'ui:build')
    # The process HTTP tests exercise the same static frontend mounted by the backend.
    # Build it before pytest so a clean checkout does not depend on an ignored ui/dist.
    Invoke-Check -Command $pythonPath -Arguments @('-m', 'pytest')
    Invoke-Check -Command $pythonPath -Arguments @('-m', 'ruff', 'check', '.')
    $scripts = & git ls-files --cached --others --exclude-standard -- '*.js' '*.mjs' '*.cjs'
    if ($LASTEXITCODE -ne 0) { throw 'Cannot enumerate maintained JavaScript files.' }
    foreach ($script in ($scripts | Sort-Object -Unique)) {
        Invoke-Check -Command 'node' -Arguments @('--check', $script)
    }
    Invoke-Check -Command 'node' -Arguments @('scripts/ui-qa/image-memory-policy.mjs')
    if (-not $SkipUi) {
        Invoke-Check -Command 'node' -Arguments @('scripts/ui-qa/review-regressions.mjs')
        Invoke-Check -Command 'node' -Arguments @('scripts/ui-qa/desktop-shutdown.mjs')
        Invoke-Check -Command 'node' -Arguments @('scripts/ui-qa/workbench.mjs')
        Invoke-Check -Command 'node' -Arguments @('scripts/ui-qa/run.mjs')
    }
    if ($Desktop) {
        Invoke-Check -Command $pythonPath -Arguments @('scripts/write_release_manifest.py', '--verify',
            '--app', (Split-Path -Parent $Desktop))
        Invoke-Check -Command 'node' -Arguments @('scripts/ui-qa/run.mjs', '--desktop', $Desktop)
        Invoke-Check -Command 'node' -Arguments @('scripts/ui-qa/desktop-shutdown.mjs', '--desktop', $Desktop)
    }
    if ($SoakMinutes) {
        Invoke-Check -Command 'node' -Arguments @('scripts/ui-qa/soak.mjs', '--desktop', $Desktop,
            '--minutes', [string]$SoakMinutes)
    }
    Write-Host 'PASS: all requested validations completed using isolated test data.'
} finally { Pop-Location }
