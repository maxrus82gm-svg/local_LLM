# Offline-only regression for the unchanged manager_dev baseline.
# The original tests expect ../c/coli and ../c/version.py as read-only Colibri 2.1.0 sources.
# Copies of those files are temporary and must never be committed to GitHub.
param(
    [string]$ColibriSource = 'S:\Ultra_LLM\Engine\Colibri\c'
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$fixture = Join-Path $projectRoot 'c'
if (Test-Path -LiteralPath $fixture) {
    throw "Cannot safely create temporary fixture: path already exists: $fixture"
}
foreach ($file in @('coli','version.py')) {
    if (-not (Test-Path -LiteralPath (Join-Path $ColibriSource $file))) {
        throw "Required Colibri 2.1.0 source missing: $file in $ColibriSource"
    }
}
$created = $false
try {
    New-Item -ItemType Directory -Path $fixture -ErrorAction Stop | Out-Null
    $created = $true
    foreach ($file in @('coli','version.py')) {
        Copy-Item -LiteralPath (Join-Path $ColibriSource $file) -Destination (Join-Path $fixture $file) -ErrorAction Stop
    }
    & py -3.12 -B -m unittest discover -s $PSScriptRoot -p 'test_*.py' -q
    if ($LASTEXITCODE -ne 0) {
        throw "Offline regression failed with exit code $LASTEXITCODE"
    }
}
finally {
    if ($created) {
        foreach ($file in @('coli','version.py')) {
            $path = Join-Path $fixture $file
            if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force }
        }
        if (@(Get-ChildItem -LiteralPath $fixture -Force).Count -eq 0) {
            Remove-Item -LiteralPath $fixture -Force
        }
    }
}
