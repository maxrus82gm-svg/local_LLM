# Self-contained synthetic contract regression; no source copy/import/LLM launch.
# Optional -ColibriSource adds a read-only installed-source AST drift audit.
param([string]$ColibriSource = '')
$ErrorActionPreference = 'Stop'
$previous = $env:UL_COLIBRI_SOURCE
try {
    $env:UL_COLIBRI_SOURCE = $ColibriSource
    if ($ColibriSource) {
        foreach ($file in @('coli','version.py')) {
            if (-not (Test-Path -LiteralPath (Join-Path $ColibriSource $file) -PathType Leaf)) {
                throw "Optional installed source absent: $file"
            }
        }
    }
    & py -3.12 -B -m unittest discover -s $PSScriptRoot -p 'test_*.py' -q
    if ($LASTEXITCODE -ne 0) { throw "Offline regression failed: $LASTEXITCODE" }
} finally {
    $env:UL_COLIBRI_SOURCE = $previous
}
