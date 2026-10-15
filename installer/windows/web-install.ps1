# Bokin Upscaler - one-line installer for Windows (no browser download, so no "dangerous file" block).
# Open PowerShell and paste:
#
#   irm https://raw.githubusercontent.com/vhung-spec/Bokin-comfyui/claude/fervent-heisenberg-17b0js/installer/windows/web-install.ps1 | iex
#
# It downloads the Bokin source from GitHub into %LOCALAPPDATA%\BokinUpscaler\src and runs setup.ps1.
# Optional environment variables: BOKIN_DIR (install folder), BOKIN_REF (branch, tag or commit),
# BOKIN_MODELS (sdxl|sd15|fast|flux|none), BOKIN_TORCH (auto|cuda|cpu), BOKIN_YES=1 (ask nothing).
& {
  $ErrorActionPreference = "Stop"
  $Repo = "vhung-spec/Bokin-comfyui"
  $Ref = if ($env:BOKIN_REF) { $env:BOKIN_REF } else { "claude/fervent-heisenberg-17b0js" }
  $Dir = if ($env:BOKIN_DIR) { $env:BOKIN_DIR } else { Join-Path $env:LOCALAPPDATA "BokinUpscaler" }
  $Zip = Join-Path $Dir "bokin-src.zip"
  $Unpack = Join-Path $Dir "src-unpack"
  $Src = Join-Path $Dir "src"

  [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
  New-Item -ItemType Directory -Force -Path $Dir | Out-Null
  Write-Host "Downloading Bokin ($Ref)..."
  $Client = New-Object System.Net.WebClient
  if ($Client.Proxy) { $Client.Proxy.Credentials = [System.Net.CredentialCache]::DefaultNetworkCredentials }
  try { $Client.DownloadFile("https://codeload.github.com/$Repo/zip/$Ref", $Zip) } finally { $Client.Dispose() }

  if (Test-Path $Unpack) { cmd /c rmdir /s /q "$Unpack" }
  New-Item -ItemType Directory -Force -Path $Unpack | Out-Null
  & (Join-Path $env:SystemRoot "System32\tar.exe") -xf $Zip -C $Unpack
  if ($LASTEXITCODE -ne 0) { throw "Could not unpack the Bokin source (tar exit code $LASTEXITCODE)" }
  if (Test-Path $Src) { cmd /c rmdir /s /q "$Src" }
  Move-Item -Path @(Get-ChildItem -Path $Unpack -Directory)[0].FullName -Destination $Src
  Remove-Item -Path $Zip -Force
  cmd /c rmdir /s /q "$Unpack"

  $SetupArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $Src "installer\windows\setup.ps1"), "-InstallDir", $Dir)
  if ($env:BOKIN_MODELS) { $SetupArgs += @("-Models", $env:BOKIN_MODELS) }
  if ($env:BOKIN_TORCH) { $SetupArgs += @("-Torch", $env:BOKIN_TORCH) }
  if ($env:BOKIN_YES) { $SetupArgs += "-Yes" }
  & (Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe") @SetupArgs
  if ($LASTEXITCODE -ne 0) {
    Write-Host "Setup did not finish (exit code $LASTEXITCODE). See $Dir\setup-log.txt and $Dir\install-log.txt" -ForegroundColor Red
  }
}
