<#
  Bokin Upscaler - Windows installer.
  Downloads uv (a small Python manager), creates the app's Python environment
  and runs installer\setup.py, which installs ComfyUI, PyTorch, the Bokin
  node pack and models. Safe to run again: finished steps are skipped.

  Usage (normally started by Install-Bokin.bat or BokinUpscaler-Setup.exe):
    powershell -ExecutionPolicy Bypass -File setup.ps1 [-InstallDir DIR] [-Models sdxl|sd15|fast|flux|none]
                                                       [-Torch auto|cuda|cpu|skip] [-NoShortcut] [-Yes]
#>
param(
  [string]$InstallDir = (Join-Path $env:LOCALAPPDATA "BokinUpscaler"),
  [string]$Models = "",
  [string]$Torch = "auto",
  [switch]$NoShortcut,
  [switch]$Yes,
  [switch]$PauseOnError
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"  # Invoke-WebRequest is very slow with its progress bar

try {
  [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
  $Src = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
  $Tools = Join-Path $InstallDir "tools"
  New-Item -ItemType Directory -Force -Path $Tools | Out-Null

  $env:UV_PYTHON_INSTALL_DIR = Join-Path $Tools "python"
  $env:UV_CACHE_DIR = Join-Path $Tools "uv-cache"
  $env:UV_PYTHON_PREFERENCE = "only-managed"  # never depend on a system Python
  $env:PYTHONUTF8 = "1"

  $Uv = Join-Path $Tools "uv.exe"
  if (-not (Test-Path $Uv)) {
    Write-Host "Downloading uv..."
    $Zip = Join-Path $Tools "uv.zip"
    Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip" -OutFile $Zip
    $Unpacked = Join-Path $Tools "uv-unpacked"
    Expand-Archive -Path $Zip -DestinationPath $Unpacked -Force
    Get-ChildItem -Path $Unpacked -Recurse -Filter "uv*.exe" | Move-Item -Destination $Tools -Force
    Remove-Item $Zip, $Unpacked -Recurse -Force
  }

  $Venv = Join-Path $InstallDir ".venv"
  $Py = Join-Path $Venv "Scripts\python.exe"
  if (-not (Test-Path $Py)) {
    Write-Host "Creating the Python 3.12 environment..."
    & $Uv venv --python 3.12 $Venv
    if ($LASTEXITCODE -ne 0) { throw "uv venv failed (exit code $LASTEXITCODE)" }
  }

  $SetupArgs = @((Join-Path $Src "installer\setup.py"), "--dir", $InstallDir, "--uv", $Uv, "--torch", $Torch)
  if ($Models) { $SetupArgs += @("--models", $Models) }
  if ($NoShortcut) { $SetupArgs += "--no-shortcut" }
  if ($Yes) { $SetupArgs += "--yes" }
  & $Py @SetupArgs
  if ($LASTEXITCODE -ne 0) { throw "Setup failed (exit code $LASTEXITCODE). See $InstallDir\install-log.txt" }
}
catch {
  Write-Host ""
  Write-Host "ERROR: $_" -ForegroundColor Red
  if ($PauseOnError) { Read-Host "Press Enter to close" | Out-Null }
  exit 1
}
