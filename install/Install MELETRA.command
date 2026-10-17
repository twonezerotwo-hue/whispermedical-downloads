#!/bin/bash
# Install MELETRA on an Intel Mac - double-click this file (a Terminal window opens and shows the progress).
#
# It contains NO installation logic of its own: it fetches the one installer engine (install-macos.sh) from the official download site, over HTTPS, and runs it.
# The engine reads the public release manifest, downloads MELETRA, checks every SHA-256, copies the app into Applications and removes its temporary files.
# If macOS refuses to open this file because it came from the internet: right-click it > Open > Open (once). Do not disable Gatekeeper.
ENGINE_URL="https://twonezerotwo-hue.github.io/whispermedical-downloads/install/install-macos.sh"
TMP_ENGINE="$(mktemp "${TMPDIR:-/tmp}/meletra-install.XXXXXX")"
trap 'rm -f "$TMP_ENGINE"' EXIT
echo "MELETRA installer"
if /usr/bin/curl -fL --proto '=https' --proto-redir '=https' --connect-timeout 20 --retry 5 --retry-delay 3 -sS -o "$TMP_ENGINE" "$ENGINE_URL"; then
    /bin/bash "$TMP_ENGINE" "$@"
    status=$?
else
    echo "Could not reach the download site. Check your internet connection and double-click this file again." >&2
    status=4
fi
echo
if [ "$status" -eq 0 ]; then echo "Done. You can close this window."; else echo "The installation did not finish (code $status). You can run this file again to continue."; fi
exit "$status"
