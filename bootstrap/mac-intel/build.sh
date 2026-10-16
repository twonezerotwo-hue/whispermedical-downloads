#!/bin/bash
# Build "WhisperMedical Installer.app" (and the zip a user downloads) on a Mac.
#   bash bootstrap/mac-intel/build.sh PINS_JSON OUT_DIR
# PINS_JSON (pins/mac-intel.json) holds the version and the final disk image's size and SHA-256; they are written into the app as pins.env so that the installer
# only ever accepts exactly that image.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PINS="$1"
OUT="$2"
mkdir -p "$OUT"
APP="$OUT/WhisperMedical Installer.app"
rm -rf "$APP" "$OUT/WhisperMedical-Installer-IntelMac.zip"
/usr/bin/osacompile -o "$APP" "$HERE/Installer.applescript"
cp "$HERE/../../install/install-macos.sh" "$APP/Contents/Resources/install.sh"        # ONE installer engine for the app, the .command and the one-command install
chmod +x "$APP/Contents/Resources/install.sh"
/usr/bin/python3 - "$PINS" "$APP/Contents/Resources/pins.env" <<'EOF'
import json, sys
pins = json.load(open(sys.argv[1]))
open(sys.argv[2], "w").write("PIN_VERSION=%s\nPIN_DMG_SIZE=%d\nPIN_DMG_SHA256=%s\n" % (pins["version"], pins["dmg"]["size"], pins["dmg"]["sha256"]))
EOF
PLIST="$APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier com.whispermedical.installer" "$PLIST" || true
/usr/libexec/PlistBuddy -c "Set :CFBundleName WhisperMedical Installer" "$PLIST" || true
/usr/libexec/PlistBuddy -c "Add :LSMinimumSystemVersion string 12.0" "$PLIST" 2>/dev/null || /usr/libexec/PlistBuddy -c "Set :LSMinimumSystemVersion 12.0" "$PLIST"
/usr/bin/codesign --force --deep --sign - "$APP"
/usr/bin/codesign --verify --deep --strict "$APP"
# the zip holds the installer app and the double-click alternative (same engine; the zip keeps the executable bit)
PACK="$OUT/zip-content"
rm -rf "$PACK"; mkdir -p "$PACK"
/usr/bin/ditto "$APP" "$PACK/WhisperMedical Installer.app"
cp "$HERE/../../install/Install WhisperMedical.command" "$PACK/Install WhisperMedical.command"
chmod +x "$PACK/Install WhisperMedical.command"
(cd "$PACK" && /usr/bin/zip -qry -X "../WhisperMedical-Installer-IntelMac.zip" .)
rm -rf "$PACK"
ls -l "$OUT/WhisperMedical-Installer-IntelMac.zip"
