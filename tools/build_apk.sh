#!/usr/bin/env bash
# Rebuild the Android APK. Handles the two things that trip this up:
#  - flutter.bat and the venv's flet.exe aren't on PATH by default here.
#  - flet build's Rich console output crashes on Windows' cp1252 terminal
#    (UnicodeEncodeError on the checkmark emoji) unless forced to UTF-8.
#
#   bash tools/build_apk.sh
#
# Output: build/apk/fitapp.apk
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_SCRIPTS="/d/Project/git_pull/Scripts"
FLUTTER_BIN="/d/flutter/bin"
ANDROID_PLATFORM_TOOLS="/c/Users/GeorgeArn/AppData/Local/Android/Sdk/platform-tools"

export PATH="$VENV_SCRIPTS:$FLUTTER_BIN:$ANDROID_PLATFORM_TOOLS:$PATH"
export PYTHONIOENCODING=utf-8
export PYTHONUTF8=1

for tool in flet flutter; do
    command -v "$tool" >/dev/null 2>&1 || {
        echo "$tool not found on PATH after adding $VENV_SCRIPTS / $FLUTTER_BIN — check those paths still exist." >&2
        exit 1
    }
done

cd "$REPO_ROOT"
flet build apk
