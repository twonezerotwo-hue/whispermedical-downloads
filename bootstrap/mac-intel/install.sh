#!/bin/bash
# WhisperMedical installer for INTEL Macs. Started by the "WhisperMedical Installer" app (it shows the progress); can also be run from Terminal.
#
# It downloads the disk image of WhisperMedical (with the Whisper Large-v3 speech model inside it) from the official public release location, checks every
# piece and the whole file against SHA-256 values that were compiled into this installer (pins.env) AND are listed in the public manifest, mounts the image,
# copies "Medical Lecture Transcriber.app" into Applications and removes its temporary files.
#
# Rules: HTTPS only; nothing is mounted or copied before the final SHA-256 matches; a broken connection resumes where it stopped (HTTP Range, retries);
# the Gatekeeper / quarantine system of macOS is neither switched off nor changed by this installer.
# Written for the bash 3.2 that ships with macOS (no external tools needed).
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
[ -f "$HERE/pins.env" ] && . "$HERE/pins.env"
MANIFEST_URL="https://twonezerotwo-hue.github.io/whispermedical-downloads/release-manifest.json"
DEST="/Applications"
PROGRESS=""
OPEN_APP=1
CURL_PROTO="--proto =https --proto-redir =https"
CACHE="$HOME/Library/Caches/WhisperMedicalInstaller"
APP_NAME="Medical Lecture Transcriber.app"

while [ $# -gt 0 ]; do
    case "$1" in
        --progress-file) PROGRESS="$2"; shift 2 ;;
        --dest) DEST="$2"; shift 2 ;;
        --no-open) OPEN_APP=0; shift ;;
        *) shift ;;
    esac
done
if [ "${MLT_TEST:-0}" = "1" ]; then            # the automated tests talk to a local server and use their own fake payload; a shipped installer never sets this
    MANIFEST_URL="${MLT_MANIFEST_URL:-$MANIFEST_URL}"
    PIN_VERSION="${MLT_PIN_VERSION:-${PIN_VERSION:-}}"
    PIN_DMG_SHA256="${MLT_PIN_DMG_SHA256:-${PIN_DMG_SHA256:-}}"
    PIN_DMG_SIZE="${MLT_PIN_DMG_SIZE:-${PIN_DMG_SIZE:-0}}"
    CACHE="${MLT_CACHE:-$CACHE}"
    CURL_PROTO=""
fi
PIN_VERSION="${PIN_VERSION:-}"
PIN_DMG_SHA256="${PIN_DMG_SHA256:-}"
PIN_DMG_SIZE="${PIN_DMG_SIZE:-0}"

TOTAL=0
DONE_BYTES=0
emit() { [ -n "$PROGRESS" ] && printf '%s\n' "$1" >> "$PROGRESS"; printf '%s\n' "$1"; }
fail() { emit "E|$1"; exit 1; }
fsize() { if [ -f "$1" ]; then /usr/bin/stat -f %z "$1"; else echo 0; fi; }
sha() { /usr/bin/shasum -a 256 "$1" | /usr/bin/awk '{print $1}'; }
progress() { emit "P|$((DONE_BYTES + ${1:-0}))|$TOTAL|$2"; }

# ---------------------------------------------------------------------------------------------------------------- checks
[ "$(uname -s)" = "Darwin" ] || fail "This installer is for macOS."
[ "$(uname -m)" = "x86_64" ] || fail "This version of WhisperMedical is for Intel Macs. This Mac has an Apple Silicon processor ($(uname -m)), which is not supported."
MAJOR="$(/usr/bin/sw_vers -productVersion | /usr/bin/cut -d. -f1)"
[ "${MAJOR:-0}" -ge 12 ] || fail "macOS 12 or newer is required (this Mac has $(/usr/bin/sw_vers -productVersion))."
[ -n "$PIN_DMG_SHA256" ] || fail "This installer has no checksum built in; please download it again from the download page."
case "$MANIFEST_URL" in https://*) ;; *) [ "${MLT_TEST:-0}" = "1" ] || fail "The download address is not secure." ;; esac

mkdir -p "$CACHE" || fail "Could not create the temporary folder."
free_kb() { /bin/df -k "$1" | /usr/bin/awk 'NR==2{print $4}'; }
mkdir -p "$DEST" 2>/dev/null
[ -w "$DEST" ] || { DEST="$HOME/Applications"; mkdir -p "$DEST" || fail "Cannot write to Applications."; }
NEED_KB=$(( (PIN_DMG_SIZE / 1024) * 2 + 3000000 ))        # the image + the installed app (about 1.4x) + a margin
[ "${MLT_TEST:-0}" = "1" ] && NEED_KB=100
[ "$(free_kb "$CACHE")" -ge "$NEED_KB" ] || fail "Not enough free disk space: about $((NEED_KB / 1000000)) GB are needed during installation; $(( $(free_kb "$CACHE") / 1000000 )) GB are free."

# ---------------------------------------------------------------------------------------------------------------- manifest
emit "S|Checking for the latest version ..."
MANIFEST="$CACHE/manifest.json"
tries=0
until /usr/bin/curl $CURL_PROTO -fsSL --connect-timeout 20 --max-time 60 -A "WhisperMedicalInstaller/$PIN_VERSION" -o "$MANIFEST" "$MANIFEST_URL"; do
    tries=$((tries + 1)); [ $tries -ge 6 ] && fail "Could not reach the download server. Check your internet connection and try again."
    sleep $((tries * 2))
done
LIST="$(/usr/bin/osascript -l JavaScript -e 'function run(argv){ ObjC.import("Foundation"); var s=$.NSString.stringWithContentsOfFileEncodingError(argv[0],$.NSUTF8StringEncoding,null).js; var m=JSON.parse(s); var e=m.mac_intel||{}; if(e.status!=="ready") return "STATUS|"+(e.status||"missing"); var d=e.payload.dmg; var out=["VERSION|"+e.version,"DMG|"+d.name+"|"+d.size+"|"+d.sha256]; (d.parts||[]).forEach(function(p){out.push("PART|"+p.name+"|"+p.size+"|"+p.sha256+"|"+p.url);}); return out.join("\n"); }' "$MANIFEST" 2>/dev/null)"
case "$LIST" in STATUS*) fail "This download is not available yet. Please try again later." ;; "") fail "The download list could not be read." ;; esac
M_VERSION="$(printf '%s\n' "$LIST" | /usr/bin/awk -F'|' '$1=="VERSION"{print $2}')"
M_DMG="$(printf '%s\n' "$LIST" | /usr/bin/awk -F'|' '$1=="DMG"{print $2"|"$3"|"$4}')"
M_SIZE="$(printf '%s' "$M_DMG" | /usr/bin/cut -d'|' -f2)"
M_SHA="$(printf '%s' "$M_DMG" | /usr/bin/cut -d'|' -f3)"
if [ "$M_VERSION" != "$PIN_VERSION" ] || [ "$M_SHA" != "$PIN_DMG_SHA256" ] || [ "$M_SIZE" != "$PIN_DMG_SIZE" ]; then
    fail "This installer is out of date. Please download the newest WhisperMedical installer from the download page."
fi
PARTS="$(printf '%s\n' "$LIST" | /usr/bin/awk -F'|' '$1=="PART"{print $2"|"$3"|"$4"|"$5}')"
[ -n "$PARTS" ] || fail "The download list has no files."
TOTAL=$M_SIZE

# ---------------------------------------------------------------------------------------------------------------- download
download() {   # url dest size
    local url="$1" dest="$2" size="$3" attempts=0 pid
    while [ "$(fsize "$dest")" -lt "$size" ]; do
        attempts=$((attempts + 1))
        [ $attempts -gt 80 ] && return 1
        /usr/bin/curl $CURL_PROTO -fL -sS -C - --connect-timeout 30 --max-time 5400 -A "WhisperMedicalInstaller/$PIN_VERSION" -o "$dest" "$url" 2>>"$CACHE/curl.log" &
        pid=$!
        while kill -0 "$pid" 2>/dev/null; do
            progress "$(fsize "$dest")" "Downloading WhisperMedical ..."
            sleep 1
        done
        wait "$pid" || sleep $(( attempts < 10 ? attempts * 2 : 20 ))
    done
    [ "$(fsize "$dest")" -eq "$size" ]
}

PART_FILES=""
while IFS='|' read -r name size psha url; do
    [ -n "$name" ] || continue
    part="$CACHE/$name"
    # a piece that was fully downloaded and verified in an earlier try is not downloaded again
    if [ "$(fsize "$part")" -eq "$size" ] && [ "$(sha "$part")" = "$psha" ]; then
        :
    else
        rm -f "$part"
        download "$url" "$part" "$size" || fail "The download of $name kept failing. Your progress is kept; open the installer again when the connection is back."
        [ "$(sha "$part")" = "$psha" ] || { rm -f "$part"; fail "A downloaded piece ($name) failed its checksum and was deleted. Please try again."; }
    fi
    DONE_BYTES=$((DONE_BYTES + size))
    progress 0 "Downloading WhisperMedical ..."
    PART_FILES="$PART_FILES
$part"
done <<EOF
$PARTS
EOF

emit "S|Assembling and verifying the download ..."
DMG="$CACHE/WhisperMedical.dmg"
rm -f "$DMG"
echo "$PART_FILES" | while IFS= read -r part; do [ -n "$part" ] && cat "$part" >> "$DMG"; done
[ "$(sha "$DMG")" = "$PIN_DMG_SHA256" ] || { rm -f "$DMG"; fail "The assembled download failed its checksum and was deleted. Please try again."; }
echo "$PART_FILES" | while IFS= read -r part; do [ -n "$part" ] && rm -f "$part"; done

# ---------------------------------------------------------------------------------------------------------------- install
emit "S|Installing into Applications ..."
MNT="$CACHE/mount"
mkdir -p "$MNT"
/usr/bin/hdiutil attach "$DMG" -nobrowse -readonly -noverify -mountpoint "$MNT" -quiet >/dev/null 2>&1 || fail "The disk image could not be opened."
cleanup() { /usr/bin/hdiutil detach "$MNT" -quiet >/dev/null 2>&1; }
[ -d "$MNT/$APP_NAME" ] || { cleanup; fail "The disk image does not contain $APP_NAME."; }
if /usr/bin/pgrep -f "$DEST/$APP_NAME/Contents/MacOS" >/dev/null 2>&1; then
    /usr/bin/osascript -e 'tell application "Medical Lecture Transcriber" to quit' >/dev/null 2>&1; sleep 3
fi
rm -rf "$DEST/$APP_NAME.new"
/usr/bin/ditto "$MNT/$APP_NAME" "$DEST/$APP_NAME.new" || { cleanup; rm -rf "$DEST/$APP_NAME.new"; fail "Copying the app failed (is there enough disk space?)."; }
rm -rf "$DEST/$APP_NAME"
mv "$DEST/$APP_NAME.new" "$DEST/$APP_NAME" || { cleanup; fail "Could not place the app in Applications."; }
cleanup

# ---------------------------------------------------------------------------------------------------------------- clean up
emit "S|Cleaning up ..."
rm -rf "$CACHE"
emit "D|$DEST/$APP_NAME"
[ "$OPEN_APP" = "1" ] && /usr/bin/open "$DEST/$APP_NAME" >/dev/null 2>&1
exit 0
