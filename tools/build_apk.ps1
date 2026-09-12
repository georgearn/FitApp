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
        Write-Error "$tool not found on PATH after adding $Venv / $Flutter -- check those paths still exist."
    }
}

Push-Location $RepoRoot
try {
    flet build apk

    # Flutter's bundled gradle plugin still defaults compileSdk/targetSdk to 36 -- no
    # upstream flag exists yet to bump this to API 37 (Android 17, platform hash
    # "android-37.0" -- Android 17 introduced fractional platform versions, so AGP
    # needs compileSdk=37 *and* compileSdkMinor=0, not just an int bump). Patch the
    # generated gradle file post-flet-build (line-pattern match, not exact-value match,
    # so this stays idempotent across reruns whether the file is still template-default
    # or already patched) and redo the release assembly + APK copy so this stays a
    # single-command, no-manual-edit build.
    $GradleFile = Join-Path $RepoRoot "build\flutter\android\app\build.gradle.kts"
    $Content = Get-Content $GradleFile -Raw
    $Patched = $Content `
        -replace '(?m)^\s*compileSdkMinor\s*=.*\r?\n', '' `
        -replace '(?m)^(\s*)compileSdk\s*=.*$', "`$1compileSdk = 37`r`n`$1compileSdkMinor = 0" `
        -replace '(?m)^(\s*)val resolvedTargetSdk\s*=.*$', '$1val resolvedTargetSdk = 37'
    if ($Patched -notmatch 'compileSdk = 37' -or $Patched -notmatch 'compileSdkMinor = 0' -or $Patched -notmatch 'resolvedTargetSdk = 37') {
        Write-Error "compileSdk/targetSdk patch did not apply cleanly to $GradleFile -- flet template must have changed, update the -replace patterns in this script."
    }
    Set-Content -Path $GradleFile -Value $Patched -NoNewline

    Push-Location (Join-Path $RepoRoot "build\flutter\android")
    try {
        $env:SERIOUS_PYTHON_SITE_PACKAGES = Join-Path $RepoRoot "build\site-packages"
        $env:SERIOUS_PYTHON_APP = Join-Path $RepoRoot "build\python-app"
        & .\gradlew.bat :app:assembleRelease
    } finally {
        Remove-Item Env:\SERIOUS_PYTHON_SITE_PACKAGES -ErrorAction SilentlyContinue
        Remove-Item Env:\SERIOUS_PYTHON_APP -ErrorAction SilentlyContinue
        Pop-Location
    }

    $ReleaseApk = Join-Path $RepoRoot "build\flutter\build\app\outputs\apk\release\app-release.apk"
    $FinalApk = Join-Path $RepoRoot "build\apk\fitapp.apk"
    Copy-Item -Path $ReleaseApk -Destination $FinalApk -Force
} finally {
    Pop-Location
}
