# CAM350 Review Assistant - Build update installer
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\build_update.ps1
#
# Requires: PyInstaller (python -m PyInstaller) and Inno Setup 7 (ISCC.exe).
# Output: dist\installer\CAM350_Review_Setup_{version}.exe

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$ISCC = "C:\Program Files\Inno Setup 7\ISCC.exe"
if (-not (Test-Path -LiteralPath $ISCC)) {
    Write-Error "ISCC.exe not found at $ISCC. Install Inno Setup 7 or edit the path in this script."
}

$versionLine = Get-Content -LiteralPath "utils\version.py" | Where-Object { $_ -match '^APP_VERSION\s*=' }
if (-not $versionLine) {
    Write-Error "Could not read APP_VERSION from utils\version.py"
}
$version = ($versionLine -split '=', 2)[1].Trim().Trim('"').Trim("'")
Write-Host "Building version: $version"

Write-Host "[1/2] PyInstaller: CAM350_Review.exe"
python -m PyInstaller scripts\build.spec --noconfirm
if ($LASTEXITCODE -ne 0) { Write-Error "PyInstaller failed (exit $LASTEXITCODE)." }

Write-Host "[2/2] Inno Setup: CAM350_Review_Setup_${version}.exe"
& $ISCC "/DMyAppVersion=$version" "scripts\installer.iss"
if ($LASTEXITCODE -ne 0) { Write-Error "ISCC failed (exit $LASTEXITCODE)." }

Write-Host "Done. Update file: dist\installer\CAM350_Review_Setup_${version}.exe"