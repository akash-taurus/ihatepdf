# Build ihatepdf.exe with PyInstaller. Run from repo root:
#   powershell -ExecutionPolicy Bypass -File build_exe.ps1
# Output: dist\ihatepdf.exe (single-file, windowed, fully offline, ~75MB)
#
# IMPORTANT: builds inside an isolated venv (.venv-build) containing ONLY the
# app's deps. Building with your global Python drags every installed package
# (torch, tensorflow, ...) into the exe — that produced an 828MB binary once.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path .venv-build\Scripts\python.exe)) {
  python -m venv .venv-build
}
.\.venv-build\Scripts\pip install -q pymupdf pypdf Pillow PySide6 pyinstaller

# --paths . : so PyInstaller resolves the top-level `core` package
# --collect-all pymupdf : ship MuPDF + its data files
.\.venv-build\Scripts\pyinstaller --noconfirm --clean `
  --onefile --windowed --name ihatepdf `
  --paths . `
  --collect-all pymupdf `
  app/main.py

Write-Host "`nDone."
Get-Item dist\ihatepdf.exe | Format-Table Name, @{n='MB';e={[math]::Round($_.Length/1MB,1)}}, LastWriteTime
Write-Host "Smoke test: QT_QPA_PLATFORM=offscreen dist\ihatepdf.exe (should stay running; close it manually)"
