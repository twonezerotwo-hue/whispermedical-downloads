"""Build the manifest entry of a platform from the pinned facts (pins/*.json), the model layout and the bootstrapper that was just built.

    python scripts/build_entries.py windows  PATH_TO_MELETRA-Installer-Windows.exe    -> prints the entry as JSON
    python scripts/build_entries.py mac-intel PATH_TO_MELETRA-Installer-IntelMac.zip

The entry describes exactly the files of the public release of that platform; the installers read it, compare it with the values compiled into them, and
download from the URLs in it (only from github.com / githubusercontent.com hosts). The status is always "uploaded": only the verification step may make it "ready".
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO_URL = "https://github.com/twonezerotwo-hue/whispermedical-downloads/releases/download"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(16 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def bootstrapper(path: Path, tag: str) -> dict:
    return {"name": path.name, "url": f"{REPO_URL}/{tag}/{path.name}", "size": path.stat().st_size, "sha256": sha256(path)}


def windows_entry(pins: dict, layout: dict, boot: Path) -> dict:
    tag = f"windows-v{pins['version']}"
    setup = pins["setup"]
    model_bytes = sum(f["size"] for f in layout["files"])
    return {"status": "uploaded", "version": pins["version"], "architecture": "x64", "minimum_os": "Windows 10", "download_bytes": setup["size"] + model_bytes,
            "bootstrapper": bootstrapper(boot, tag),
            "payload": {"setup": {"name": setup["name"], "size": setup["size"], "sha256": setup["sha256"], "url": f"{REPO_URL}/{tag}/{setup['name']}"},
                        "model": {"revision": layout["revision"], "files": layout["files"]}}}


def mac_entry(pins: dict, boot: Path) -> dict:
    tag = f"mac-intel-v{pins['version']}"
    dmg = pins["dmg"]
    return {"status": "uploaded", "version": pins["version"], "architecture": "x86_64", "minimum_macos": "12.0", "download_bytes": dmg["size"],
            "bootstrapper": bootstrapper(boot, tag),
            "payload": {"dmg": {"name": dmg["name"], "size": dmg["size"], "sha256": dmg["sha256"],
                                "parts": [{**p, "url": f"{REPO_URL}/{tag}/{p['name']}"} for p in dmg["parts"]]}}}


def main(argv=None) -> int:
    argv = argv or sys.argv[1:]
    if len(argv) != 2 or argv[0] not in ("windows", "mac-intel"):
        print(__doc__)
        return 2
    boot = Path(argv[1])
    if argv[0] == "windows":
        entry = windows_entry(json.loads((ROOT / "pins" / "windows.json").read_text(encoding="utf-8")),
                              json.loads((ROOT / "scripts" / "model_parts.json").read_text(encoding="utf-8")), boot)
    else:
        entry = mac_entry(json.loads((ROOT / "pins" / "mac-intel.json").read_text(encoding="utf-8")), boot)
    print(json.dumps(entry, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
