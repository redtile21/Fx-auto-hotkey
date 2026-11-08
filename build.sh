#!/usr/bin/env bash
# Builds "dist/FX Hotkeys.app" and "dist/FXHotkeys-macOS.dmg".
# Usage:  ./build.sh            (needs Python 3.10+ from python.org or Homebrew)
set -euo pipefail
cd "$(dirname "$0")"

APP="FX Hotkeys"
PY="${PYTHON:-python3}"

if [ ! -d .venv ]; then
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip >/dev/null
python -m pip install -r requirements-build.txt

python tests/test_logic.py

rm -rf build "dist/$APP.app" "dist/FXHotkeys-macOS.dmg"
pyinstaller --noconfirm --clean --windowed \
  --name "$APP" \
  --icon assets/icon-1024.png \
  --osx-bundle-identifier com.fxhotkeys.mac \
  --add-data "assets:assets" \
  --hidden-import Quartz --hidden-import AppKit \
  --hidden-import ApplicationServices --hidden-import CoreFoundation \
  main.py

# A stable ad-hoc signature, so macOS remembers the Accessibility permission.
# (Use your Developer ID instead with:  CODESIGN_ID="Developer ID Application: ..." ./build.sh)
codesign --force --deep --sign "${CODESIGN_ID:--}" "dist/$APP.app"

# Disk image with a shortcut to /Applications
STAGE="$(mktemp -d)"
cp -R "dist/$APP.app" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
hdiutil create -volname "$APP" -srcfolder "$STAGE" -ov -format UDZO "dist/FXHotkeys-macOS.dmg"
rm -rf "$STAGE"

echo
echo "Done:"
echo "  dist/$APP.app"
echo "  dist/FXHotkeys-macOS.dmg"
