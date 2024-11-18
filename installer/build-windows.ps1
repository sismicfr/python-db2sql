<#
.SYNOPSIS
    Build a standalone db2sql.exe on Windows (x86_64).

.DESCRIPTION
    Creates an isolated virtual environment under installer/.venv-build,
    installs db2sql and PyInstaller, then runs installer/build.py.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File installer/build-windows.ps1
    powershell -ExecutionPolicy Bypass -File installer/build-windows.ps1 -OneDir

.PARAMETER OneDir
    Produce a directory bundle instead of a single-file executable.

.PARAMETER Python
    Path or command name for the Python interpreter to use (default: py -3).
#>
[CmdletBinding()]
param(
    [switch]$OneDir,
    [string]$Python = "py -3"
)

$ErrorActionPreference = "Stop"

$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $Here
$VenvDir = Join-Path $Here ".venv-build"

Set-Location $Root

if (-not (Test-Path (Join-Path $VenvDir "Scripts/python.exe"))) {
    Write-Host "→ creating build venv: $VenvDir"
    # Split because "py -3" may include arguments
    $pyParts = $Python -split " "
    & $pyParts[0] @($pyParts[1..($pyParts.Length - 1)]) -m venv $VenvDir
}

$VenvPython = Join-Path $VenvDir "Scripts/python.exe"

& $VenvPython -m pip install --upgrade pip wheel
& $VenvPython -m pip install -e ".[all]"
& $VenvPython -m pip install "pyinstaller>=6"

$ExtraArgs = @("--archive")
if ($OneDir) {
    $ExtraArgs += "--onedir"
}

& $VenvPython installer/build.py @ExtraArgs
if ($LASTEXITCODE -ne 0) {
    throw "installer/build.py failed with exit code $LASTEXITCODE"
}
