param(
    [switch]$Apply
)

$ErrorActionPreference = "Stop"

function Fail([string]$Message) {
    Write-Error $Message
    exit 1
}

$repo = (& git rev-parse --show-toplevel 2>$null)
if ($LASTEXITCODE -ne 0 -or -not $repo) {
    Fail "Esegui questo script dentro il repository dsl_manager-v3."
}
Set-Location $repo

$expected = @{
    "src/dslm3/web.py" = "bf43c3363261afd3d599cb90e662994dccf03e6d"
    "tests/test_web.py" = "d2b7c0228a2d767e86309bf08e01b22f118d569f"
}

foreach ($path in $expected.Keys) {
    if (-not (Test-Path $path)) {
        Fail "File atteso non trovato: $path"
    }
    $actual = (& git hash-object -- $path).Trim()
    if ($LASTEXITCODE -ne 0) {
        Fail "Impossibile calcolare l'hash Git di $path."
    }
    if ($actual -ne $expected[$path]) {
        Fail "Patch NON applicata: $path non corrisponde alla versione analizzata. Atteso $($expected[$path]), trovato $actual."
    }
}

$patch = Join-Path $PSScriptRoot "dslm3_fix_windows_download_paths.patch"
if (-not (Test-Path $patch)) {
    Fail "Patch non trovata accanto allo script: $patch"
}

& git apply --check -- $patch
if ($LASTEXITCODE -ne 0) {
    Fail "git apply --check non superato. Nessun file e' stato modificato."
}

if (-not $Apply) {
    Write-Host "OK: versione sorgente verificata e patch applicabile."
    Write-Host "Nessun file e' stato modificato."
    Write-Host "Per applicarla: .\apply_dslm3_fix_windows_download_paths.ps1 -Apply"
    exit 0
}

& git apply -- $patch
if ($LASTEXITCODE -ne 0) {
    Fail "Applicazione patch fallita."
}

& git diff --check
if ($LASTEXITCODE -ne 0) {
    Write-Error "git diff --check ha trovato problemi. Ripristino la patch."
    & git apply -R -- $patch
    exit 1
}

Write-Host "Patch applicata."
Write-Host ""
Write-Host "Modifiche:"
& git diff -- src/dslm3/web.py tests/test_web.py
Write-Host ""
Write-Host "Test consigliato:"
Write-Host "  python -m pytest -q tests/test_web.py"
Write-Host ""
Write-Host "Per annullare, finche' non fai altre modifiche agli stessi hunk:"
Write-Host "  git apply -R `"$patch`""
