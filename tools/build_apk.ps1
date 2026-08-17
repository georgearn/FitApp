# Rebuild the Android APK. Handles the two things that trip this up:
#  - flutter.bat and the venv's flet.exe aren't on PATH by default here.
#  - flet build's Rich console output crashes on Windows' cp1252 terminal
#    (UnicodeEncodeError on the checkmark emoji) unless forced to UTF-8.
#
#   powershell -File tools\build_apk.ps1
#
# Output: build\apk\fitapp.apk

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Venv = "D:\Project\git_pull\Scripts"
$Flutter = "D:\flutter\bin"
$AndroidPlatformTools = "$env:LOCALAPPDATA\Android\Sdk\platform-tools"

$env:Path = "$Venv;$Flutter;$AndroidPlatformTools;$env:Path"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

foreach ($tool in @("flet.exe", "flutter.bat")) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        Write-Error "$tool not found on PATH after adding $Venv / $Flutter — check those paths still exist."
    }
}

Push-Location $RepoRoot
try {
    flet build apk
} finally {
    Pop-Location
}
