# Runs the test suite with the Python bundled in a local QGIS install.
# One-time setup (dev-only dependency, not shipped with the plugin):
#   & "$env:QGIS_ROOT\bin\python-qgis-ltr.bat" -m pip install --target .devdeps pytest
# Usage: scripts\run_tests.ps1 [pytest args]
param([Parameter(ValueFromRemainingArguments = $true)] [string[]] $PytestArgs)

$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not $env:QGIS_ROOT) {
    $candidate = Get-ChildItem "C:\Program Files" -Directory -Filter "QGIS *" |
        Sort-Object { [version]($_.Name -replace '^QGIS ', '') } -Descending |
        Select-Object -First 1
    if (-not $candidate) { throw "QGIS not found. Set QGIS_ROOT to the QGIS install directory." }
    $env:QGIS_ROOT = $candidate.FullName
}
$launcher = Get-ChildItem (Join-Path $env:QGIS_ROOT "bin") -Filter "python-qgis*.bat" | Select-Object -First 1
if (-not $launcher) { throw "python-qgis*.bat not found under $env:QGIS_ROOT\bin" }

$env:QT_QPA_PLATFORM = "offscreen"
Push-Location $repoRoot
try {
    & $launcher.FullName (Join-Path $PSScriptRoot "pytest_runner.py") @PytestArgs
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
