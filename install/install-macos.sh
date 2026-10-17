#!/bin/bash
# WhisperMedical installer for INTEL Macs - the ONE installer engine. Three entry points use it:
#   * "WhisperMedical Installer.app" (one click: the app copies this file next to pins.env and shows the progress),
#   * "Install WhisperMedical.command" (double click: fetches this file and runs it),
#   * the one-command install of the README:  curl -fL --proto '=https' '<address of this file>' -o /tmp/whispermedical-install.sh && bash /tmp/whispermedical-install.sh
#
# It reads the public release manifest (release-manifest.json: the single source of truth), downloads the disk image of WhisperMedical (with the Whisper Large-v3 speech
# model inside it) from the official public release location, checks every piece and the whole file against the SHA-256 values of the manifest (and, inside the app, against the
# values compiled into it - pins.env), mounts the image, copies "WhisperMedical.app" (releases before 4.1: "Medical Lecture Transcriber.app") into Applications, ejects the image and removes its temporary files.
#
# Rules: HTTPS only; nothing is mounted or copied before the final SHA-256 matches; a broken connection resumes where it stopped (HTTP Range, retries);
# the Gatekeeper / quarantine system of macOS is neither switched off nor changed by this installer; Intel Macs only (an Apple Silicon Mac is told so and nothing is installed).
# Without pins.env (the one-command and .command paths) only a release that is announced (status "ready") and is the current product version is installed; a release that
# passed verification but was not announced yet is installed only with MLT_ALLOW_UNANNOUNCED=1 (testing). Exit codes: 0 installed | 1 failed | 2 not supported | 3 not available yet.
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
APP_NAME="WhisperMedical.app"
LEGACY_APP_NAME="Medical Lecture Transcriber.app"        # the name of 4.0 and older: an old image still holds it, an old install may still be in Applications
BUNDLE_ID="com.medicallecturetranscriber.app"           # unchanged by the rename: it is how an old copy is recognised as this program

while [ $# -gt 0 ]; do
    case "$1" in
        --progress-file) PROGRESS="$2"; shift 2 ;;
        --dest) DEST="$2"; shift 2 ;;
        --no-open) OPEN_APP=0; shift ;;
        -h|--help) /usr/bin/sed -n '2,15p' "$0" | /usr/bin/sed 's/^# \{0,1\}//'; exit 0 ;;
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
PINNED=0
[ -n "$PIN_DMG_SHA256" ] && PINNED=1           # inside the installer app the values were compiled in; the one-command path trusts the manifest alone

TOTAL=0
DONE_BYTES=0
human() {   # the one-command path in a Terminal: readable text instead of the S|/P|/E|/D| lines the installer app parses
    case "$1" in
        S\|*) printf '\n%s\n' "${1#S|}" ;;
        P\|*) printf '%s\n' "$1" | /usr/bin/awk -F'|' '{ printf "\r  %.2f of %.2f GB (%d%%)   ", $2/1e9, $3/1e9, ($3 > 0 ? 100*$2/$3 : 0) }' ;;
        E\|*) printf '\nERROR: %s\n' "${1#E|}" >&2 ;;
        D\|*) printf '\nInstalled: %s\n' "${1#D|}" ;;
    esac
}
emit() {
    [ -n "$PROGRESS" ] && printf '%s\n' "$1" >> "$PROGRESS"
    if [ -n "$PROGRESS" ] || { [ "${MLT_TEST:-0}" = "1" ] && [ "${MLT_PLAIN:-0}" != "1" ]; }; then printf '%s\n' "$1"; else human "$1"; fi
}
fail() { emit "E|$1"; exit "${2:-1}"; }
fsize() { if [ -f "$1" ]; then /usr/bin/stat -f %z "$1"; else echo 0; fi; }
sha() { /usr/bin/shasum -a 256 "$1" | /usr/bin/awk '{print $1}'; }
progress() { emit "P|$((DONE_BYTES + ${1:-0}))|$TOTAL|$2"; }

# ---------------------------------------------------------------------------------------------------------------- checks
[ "$(uname -s)" = "Darwin" ] || fail "This installer is for macOS." 2
[ "$(uname -m)" = "x86_64" ] || fail "This release is for Intel Macs. This Mac has an Apple Silicon processor ($(uname -m)); nothing was installed." 2
MAJOR="$(/usr/bin/sw_vers -productVersion | /usr/bin/cut -d. -f1)"
[ "${MAJOR:-0}" -ge 12 ] || fail "macOS 12 or newer is required (this Mac has $(/usr/bin/sw_vers -productVersion))." 2
case "$MANIFEST_URL" in https://*) ;; *) [ "${MLT_TEST:-0}" = "1" ] || fail "The download address is not secure." ;; esac

mkdir -p "$CACHE" || fail "Could not create the temporary folder."
free_kb() { /bin/df -k "$1" | /usr/bin/awk 'NR==2{print $4}'; }
mkdir -p "$DEST" 2>/dev/null
[ -w "$DEST" ] || { DEST="$HOME/Applications"; mkdir -p "$DEST" || fail "Cannot write to Applications."; }

# ---------------------------------------------------------------------------------------------------------------- manifest
emit "S|Checking for the latest version ..."
MANIFEST="$CACHE/manifest.json"
tries=0
until /usr/bin/curl $CURL_PROTO -fsSL --connect-timeout 20 --max-time 60 -A "WhisperMedicalInstaller/$PIN_VERSION" -o "$MANIFEST" "$MANIFEST_URL"; do
    tries=$((tries + 1)); [ $tries -ge 6 ] && fail "Could not reach the download server. Check your internet connection and try again."
    sleep $((tries * 2))
done
LIST="$(/usr/bin/osascript -l JavaScript -e 'function run(argv){ ObjC.import("Foundation"); var s=$.NSString.stringWithContentsOfFileEncodingError(argv[0],$.NSUTF8StringEncoding,null).js; var m=JSON.parse(s); var e=m.mac_intel||{}; var out=["STATUS|"+(e.status||"missing"),"PRODUCT|"+(m.product_version||""),"VERIFIED|"+((e.verification&&e.verification.passed)?"yes":"no")]; if(e.payload&&e.payload.dmg){ var d=e.payload.dmg; out.push("VERSION|"+e.version,"DMG|"+d.name+"|"+d.size+"|"+d.sha256); (d.parts||[]).forEach(function(p){out.push("PART|"+p.name+"|"+p.size+"|"+p.sha256+"|"+p.url);}); } return out.join("\n"); }' "$MANIFEST" 2>/dev/null)"
[ -n "$LIST" ] || fail "The download list could not be read."
field() { printf '%s\n' "$LIST" | /usr/bin/awk -F'|' -v k="$1" '$1==k{print $2; exit}'; }
M_STATUS="$(field STATUS)"; M_PRODUCT="$(field PRODUCT)"; M_VERIFIED="$(field VERIFIED)"; M_VERSION="$(field VERSION)"
M_DMG="$(printf '%s\n' "$LIST" | /usr/bin/awk -F'|' '$1=="DMG"{print $2"|"$3"|"$4}')"
M_SIZE="$(printf '%s' "$M_DMG" | /usr/bin/cut -d'|' -f2)"
M_SHA="$(printf '%s' "$M_DMG" | /usr/bin/cut -d'|' -f3)"
if [ "$PINNED" = "1" ]; then                   # inside the installer app: the app only ever installs exactly the image it was built for
    case "$M_STATUS" in ready|uploaded) ;; *) fail "This download is not available yet. Please try again later." 3 ;; esac
    if [ "$M_VERSION" != "$PIN_VERSION" ] || [ "$M_SHA" != "$PIN_DMG_SHA256" ] || [ "$M_SIZE" != "$PIN_DMG_SIZE" ]; then
        fail "This installer is out of date. Please download the newest WhisperMedical installer from the download page."
    fi
else                                           # the one-command path: the manifest decides, and only an announced current release is offered
    [ -n "$M_VERSION" ] && [ -n "$M_SHA" ] || fail "WhisperMedical for Intel Macs is not available yet. Please try again later." 3
    if [ -n "$M_PRODUCT" ] && [ "$M_VERSION" != "$M_PRODUCT" ]; then
        fail "WhisperMedical $M_PRODUCT for Intel Macs is not available yet (the newest Mac build in the release list is $M_VERSION). Please try again later." 3
    fi
    if [ "$M_STATUS" != "ready" ]; then
        if [ "${MLT_ALLOW_UNANNOUNCED:-0}" = "1" ] && [ "$M_VERIFIED" = "yes" ]; then
            emit "S|TEST MODE: installing WhisperMedical $M_VERSION although it is not announced yet"
        else
            fail "WhisperMedical $M_VERSION for Intel Macs is not announced yet, so it is not offered for installation. Please try again later." 3
        fi
    fi
    PIN_VERSION="$M_VERSION"; PIN_DMG_SHA256="$M_SHA"; PIN_DMG_SIZE="$M_SIZE"
fi
PARTS="$(printf '%s\n' "$LIST" | /usr/bin/awk -F'|' '$1=="PART"{print $2"|"$3"|"$4"|"$5}')"
[ -n "$PARTS" ] || fail "The download list has no files."
TOTAL=$M_SIZE
NEED_KB=$(( (PIN_DMG_SIZE / 1024) * 2 + 3000000 ))        # the image + the installed app (about 1.4x) + a margin
[ "${MLT_TEST:-0}" = "1" ] && NEED_KB=100
[ "$(free_kb "$CACHE")" -ge "$NEED_KB" ] || fail "Not enough free disk space: about $((NEED_KB / 1000000)) GB are needed during installation; $(( $(free_kb "$CACHE") / 1000000 )) GB are free." 2
emit "S|WhisperMedical $PIN_VERSION for Intel Macs ($((PIN_DMG_SIZE / 1000000000)) GB download)"
case "$PIN_VERSION" in 0.*|1.*|2.*|3.*|4.0.*) ;; *)       # from 4.1.0 on: said before anything is downloaded
    emit "S|Completed transcripts are shared with the developer by default to improve transcription quality. You can turn this off in Settings -> Privacy & Data. Your audio, video, PDF files and pictures are never sent." ;;
esac

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
if [ ! -d "$MNT/$APP_NAME" ] && [ -d "$MNT/$LEGACY_APP_NAME" ]; then APP_NAME="$LEGACY_APP_NAME"; fi      # prefer WhisperMedical.app, fall back to the old name
[ -d "$MNT/$APP_NAME" ] || { cleanup; fail "The disk image does not contain WhisperMedical.app."; }
OLD_COPY="$DEST/$LEGACY_APP_NAME"                        # a copy under the old name: replaced by the new one (only when it really is this program)
REPLACE_OLD=0
if [ "$APP_NAME" != "$LEGACY_APP_NAME" ] && [ -d "$OLD_COPY" ] && [ "$(/usr/bin/defaults read "$OLD_COPY/Contents/Info" CFBundleIdentifier 2>/dev/null)" = "$BUNDLE_ID" ]; then REPLACE_OLD=1; fi
for running in "$DEST/$APP_NAME" "$OLD_COPY"; do
    if /usr/bin/pgrep -f "$running/Contents/MacOS" >/dev/null 2>&1; then
        /usr/bin/osascript -e "tell application \"$(basename "$running" .app)\" to quit" >/dev/null 2>&1; sleep 3
    fi
done
rm -rf "$DEST/$APP_NAME.new"
/usr/bin/ditto "$MNT/$APP_NAME" "$DEST/$APP_NAME.new" || { cleanup; rm -rf "$DEST/$APP_NAME.new"; fail "Copying the app failed (is there enough disk space?)."; }
rm -rf "$DEST/$APP_NAME"
mv "$DEST/$APP_NAME.new" "$DEST/$APP_NAME" || { cleanup; fail "Could not place the app in Applications."; }
[ "$REPLACE_OLD" = "1" ] && rm -rf "$OLD_COPY"
cleanup

# ---------------------------------------------------------------------------------------------------------------- clean up
emit "S|Cleaning up ..."
rm -rf "$CACHE"
emit "D|$DEST/$APP_NAME"
[ "$OPEN_APP" = "1" ] && /usr/bin/open "$DEST/$APP_NAME" >/dev/null 2>&1
exit 0
