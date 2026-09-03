# CAM350 Review Assistant - Build update installer
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\build_update.ps1
#
# Requires: PyInstaller (python -m PyInstaller) and Inno Setup 7 (ISCC.exe).
# Output: dist\installer\CAM350_Review_Setup_{version}.exe

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$startedAt = Get-Date

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

# ---- Stamp build info so the running app can prove which build it is -------
$gitHash = ""
try {
    $gitHash = (git rev-parse --short HEAD 2>$null).Trim()
} catch { $gitHash = "" }
$buildTime = $startedAt.ToLocalTime().ToString("yyyy-MM-dd HH:mm")
$buildInfoPy = @"
BUILD_TIME = "$buildTime"
GIT_HASH = "$gitHash"
VERSION = "$version"
"@
Set-Content -LiteralPath "utils\_build_info.py" -Value $buildInfoPy -Encoding utf8
Write-Host "Stamped utils\_build_info.py (build $buildTime, git $gitHash)"

# ---- Clean stale artifacts so PyInstaller cannot reuse cached analysis -----
Write-Host "[0/2] Cleaning stale build artifacts..."
if (Test-Path -LiteralPath "build\build") {
    Remove-Item -LiteralPath "build\build" -Recurse -Force
}
if (Test-Path -LiteralPath "dist\CAM350_Review.exe") {
    Remove-Item -LiteralPath "dist\CAM350_Review.exe" -Force
}

Write-Host "[1/2] PyInstaller: CAM350_Review.exe"
python -m PyInstaller scripts\build.spec --noconfirm --clean `
    --workpath "build\build" --distpath "dist"
if ($LASTEXITCODE -ne 0) { Write-Error "PyInstaller failed (exit $LASTEXITCODE)." }

$exe = "dist\CAM350_Review.exe"
if (-not (Test-Path -LiteralPath $exe)) {
    Write-Error "PyInstaller did not produce $exe."
}
$exeTime = (Get-Item -LiteralPath $exe).LastWriteTime
if ($exeTime -lt $startedAt) {
    Write-Error "Stale artifact detected: $exe was not rebuilt (timestamp $exeTime)."
}

Write-Host "[2/2] Inno Setup: CAM350_Review_Setup_${version}.exe"
& $ISCC "/DMyAppVersion=$version" "scripts\installer.iss"
if ($LASTEXITCODE -ne 0) { Write-Error "ISCC failed (exit $LASTEXITCODE)." }

$setup = "dist\installer\CAM350_Review_Setup_${version}.exe"
if (-not (Test-Path -LiteralPath $setup)) {
    Write-Error "Installer not found at $setup."
}

$exeSha = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash
$setupSha = (Get-FileHash -LiteralPath $setup -Algorithm SHA256).Hash
Write-Host ""
Write-Host "Done. Update file: $setup"
Write-Host ("  exe    built : {0}" -f $exeTime)
Write-Host ("  exe    sha256: {0}" -f $exeSha)
Write-Host ("  setup  sha256: {0}" -f $setupSha)
