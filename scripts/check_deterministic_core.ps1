param(
    [string]$ProjectPython = $env:PROJECT_PYTHON,
    [string]$RuntimeRoot = '',
    [string]$ReportDirectory = '',
    [string]$V1Root = '',
    [string]$ColdWorkspace = ''
)
$ErrorActionPreference = 'Stop'
$RepoV3 = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $RepoV3
if (-not $ProjectPython) {
    $LocalPython = Join-Path $RepoV3 '.venv\Scripts\python.exe'
    $ExternalPython = 'C:\_Support\.venv_dslm3\Scripts\python.exe'
    if (Test-Path -LiteralPath $LocalPython) { $ProjectPython = $LocalPython }
    elseif (Test-Path -LiteralPath $ExternalPython) { $ProjectPython = $ExternalPython }
    else { throw 'Set -ProjectPython to the project Python 3.12 x64 executable.' }
}
if (-not (Test-Path -LiteralPath $ProjectPython)) { throw 'Python executable not found.' }
& $ProjectPython -c "import sys,struct; assert sys.version_info[:2]==(3,12); assert struct.calcsize('P')==8; import pytest,sqlglot,docling,playwright; print(sys.executable)"
if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 x64 or project dependencies unavailable. Install editable .[dev].' }
if (-not $ReportDirectory) { $ReportDirectory = Join-Path $RepoV3 ('reports\deterministic_core\run_' + (Get-Date -Format 'yyyyMMdd_HHmmss')) }
$Runner = Join-Path $PSScriptRoot 'core_acceptance.py'
$RunnerArgs = @($Runner, '--report-dir', $ReportDirectory, '--shell-version', $PSVersionTable.PSVersion.ToString())
if ($RuntimeRoot) { $RunnerArgs += @('--runtime-root', $RuntimeRoot) }
if ($V1Root) { $RunnerArgs += @('--v1-root', $V1Root) }
if ($ColdWorkspace) { $RunnerArgs += @('--cold-workspace', $ColdWorkspace) }
& $ProjectPython @RunnerArgs
if ($LASTEXITCODE -ne 0) { throw 'Deterministic acceptance failed: inspect acceptance.json and logs.' }
exit 0
