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
cp "$HERE/install.sh" "$APP/Contents/Resources/install.sh"
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
/usr/bin/ditto -c -k --sequesterRsrc --keepParent "$APP" "$OUT/WhisperMedical-Installer-IntelMac.zip"
ls -l "$OUT/WhisperMedical-Installer-IntelMac.zip"
