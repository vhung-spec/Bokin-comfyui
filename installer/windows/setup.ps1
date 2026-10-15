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

# Only plain .NET calls and built-in tools below, no module cmdlets such as
# Invoke-WebRequest, Expand-Archive or Get-FileHash: those fail to auto-load
# when PSModulePath points at PowerShell 7 modules (e.g. Setup started from pwsh).
function Get-File([string]$Url, [string]$Path) {
  $Client = New-Object System.Net.WebClient
  if ($Client.Proxy) { $Client.Proxy.Credentials = [System.Net.CredentialCache]::DefaultNetworkCredentials }
  try { $Client.DownloadFile($Url, $Path) } finally { $Client.Dispose() }
}
$Tar = Join-Path $env:SystemRoot "System32\tar.exe"

try {
  New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
  Start-Transcript -Path (Join-Path $InstallDir "setup-log.txt") -Append | Out-Null
  [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
  $Src = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
  $Tools = Join-Path $InstallDir "tools"
  New-Item -ItemType Directory -Force -Path $Tools | Out-Null

  $env:UV_CACHE_DIR = Join-Path $Tools "uv-cache"
  # uv-managed Python links its minor version with a junction, which some Windows
  # setups (e.g. OneDrive Files On-Demand) refuse with "untrusted mount point"
  # (os error 448). Use a plain standalone Python folder instead, never uv's.
  $env:UV_PYTHON_DOWNLOADS = "never"
  $env:PYTHONUTF8 = "1"

  $Uv = Join-Path $Tools "uv.exe"
  if (-not (Test-Path $Uv)) {
    Write-Host "Downloading uv..."
    $Zip = Join-Path $Tools "uv.zip"
    Get-File "https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip" $Zip
    $Unpacked = Join-Path $Tools "uv-unpacked"
    if (Test-Path $Unpacked) { cmd /c rmdir /s /q "$Unpacked" }
    New-Item -ItemType Directory -Force -Path $Unpacked | Out-Null
    & $Tar -xf $Zip -C $Unpacked
    if ($LASTEXITCODE -ne 0) { throw "Could not unpack uv (tar exit code $LASTEXITCODE)" }
    Get-ChildItem -Path $Unpacked -Recurse -Filter "uv*.exe" | Move-Item -Destination $Tools -Force
    Remove-Item -Path $Zip -Force
    cmd /c rmdir /s /q "$Unpacked"
  }

  $Venv = Join-Path $InstallDir ".venv"
  $Py = Join-Path $Venv "Scripts\python.exe"
  if (-not (Test-Path $Py)) {
    # python-build-standalone, the same build uv would download, unpacked to a normal folder.
    $PyVersion = "3.12.14"
    $PyUrl = "https://github.com/astral-sh/python-build-standalone/releases/download/20260929/cpython-3.12.14%2B20260929-x86_64-pc-windows-msvc-install_only_stripped.tar.gz"
    $PySha256 = "f38e68f4d612ade6dd50c894fc80b14c0be0c3b5201145d6fff5f20b9323204d"
    $PyHome = Join-Path $Tools "python-$PyVersion"
    $BasePy = Join-Path $PyHome "python.exe"
    if (-not (Test-Path $BasePy)) {
      Write-Host "Downloading Python $PyVersion (22 MB)..."
      $Archive = Join-Path $Tools "python.tar.gz"
      Get-File $PyUrl $Archive
      $Sha = [System.Security.Cryptography.SHA256]::Create()
      $Stream = [System.IO.File]::OpenRead($Archive)
      try { $Hash = -join ($Sha.ComputeHash($Stream) | ForEach-Object { $_.ToString("x2") }) }
      finally { $Stream.Dispose(); $Sha.Dispose() }
      if ($Hash -ne $PySha256) { throw "Python download is corrupted (SHA256 $Hash). Please run Setup again." }
      $Unpack = Join-Path $Tools "python-unpack"
      if (Test-Path $Unpack) { cmd /c rmdir /s /q "$Unpack" }
      New-Item -ItemType Directory -Force -Path $Unpack | Out-Null
      & $Tar -xzf $Archive -C $Unpack
      if ($LASTEXITCODE -ne 0) { throw "Could not unpack Python (tar exit code $LASTEXITCODE)" }
      Move-Item -Path (Join-Path $Unpack "python") -Destination $PyHome
      Remove-Item -Path $Archive -Force
      cmd /c rmdir /s /q "$Unpack"
    }
    # Left over by older installers that let uv manage Python; rmdir does not follow junctions.
    $OldManaged = Join-Path $Tools "python"
    if (Test-Path $OldManaged) { cmd /c rmdir /s /q "$OldManaged" }

    Write-Host "Creating the Python environment..."
    & $Uv venv --python $BasePy $Venv
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
  Write-Host $_.ScriptStackTrace
  if ($PauseOnError) { Read-Host "Press Enter to close" | Out-Null }
  exit 1
}
