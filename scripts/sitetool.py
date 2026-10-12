"""Maintain the public download site: release-manifest.json and the stable "latest" redirect pages.

    python scripts/sitetool.py show
    python scripts/sitetool.py set-platform windows entry.json         replace one platform's entry (status stays "uploaded" until it is verified)
    python scripts/sitetool.py set-verified windows RUN_URL            record that the anonymous download + real install + start + transcription test passed
    python scripts/sitetool.py set-status windows ready                refused unless the platform was verified (and, if required, the owner confirmed the licence notices in the workflow)
    python scripts/sitetool.py redirects                               rewrite latest/windows/index.html and latest/mac-intel/index.html from the manifest

A platform button on the landing page is enabled only when its entry says "status": "ready". Nothing here uploads files; it only edits small text files.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "release-manifest.json"
KEYS = {"windows": "windows", "mac-intel": "mac_intel", "mac_intel": "mac_intel"}
REDIRECT = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>WhisperMedical download</title>
<meta http-equiv="refresh" content="0; url={url}">
<link rel="canonical" href="{url}">
</head><body><p>Starting the download of WhisperMedical for {label} &hellip; if nothing happens, <a href="{url}">click here</a>.</p></body></html>
"""
PENDING = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>WhisperMedical</title>
<meta http-equiv="refresh" content="3; url=../../">
</head><body><p>The {label} download is not available yet. Going back to the download page &hellip;</p></body></html>
"""


def load(path: Path | None = None) -> dict:
    return json.loads((path or MANIFEST).read_text(encoding="utf-8"))


def save(data: dict, path: Path | None = None) -> None:
    data["generated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    (path or MANIFEST).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def ready(entry: dict) -> bool:
    return bool(entry) and entry.get("status") == "ready" and bool((entry.get("bootstrapper") or {}).get("url"))


def write_redirects(data: dict, root: Path | None = None) -> list[Path]:
    root = root or ROOT
    written = []
    for key, folder, label in (("windows", "windows", "Windows"), ("mac_intel", "mac-intel", "Intel Mac")):
        entry = data.get(key) or {}
        target = root / "latest" / folder / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((REDIRECT.format(url=entry["bootstrapper"]["url"], label=label) if ready(entry) else PENDING.format(label=label)), encoding="utf-8")
        written.append(target)
    return written


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("show")
    sub.add_parser("redirects")
    p = sub.add_parser("set-platform")
    p.add_argument("platform")
    p.add_argument("entry", type=Path)
    v = sub.add_parser("set-verified")
    v.add_argument("platform")
    v.add_argument("run_url")
    s = sub.add_parser("set-status")
    s.add_argument("platform")
    s.add_argument("status", choices=["pending", "uploaded", "ready"])
    args = parser.parse_args(argv)
    data = load()
    if args.cmd == "show":
        print(json.dumps({k: (v.get("status") if isinstance(v, dict) else v) for k, v in data.items()}, indent=2))
        return 0
    if args.cmd == "set-platform":
        key = KEYS[args.platform]
        entry = json.loads(args.entry.read_text(encoding="utf-8"))
        entry["status"] = "uploaded" if entry.get("status") == "ready" else entry.get("status", "uploaded")
        entry.pop("verification", None)                        # a new entry has not been verified yet
        data[key] = entry
    elif args.cmd == "set-verified":
        key = KEYS[args.platform]
        if not (data.get(key, {}).get("bootstrapper") or {}).get("url"):
            print("refused: the platform has no bootstrapper entry")
            return 1
        data[key]["verification"] = {"passed": True, "run": args.run_url, "date": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    elif args.cmd == "set-status":
        key = KEYS[args.platform]
        if args.status == "ready" and not (data.get(key, {}).get("bootstrapper") or {}).get("url"):
            print("refused: the platform has no bootstrapper entry")
            return 1
        if args.status == "ready" and not (data[key].get("verification") or {}).get("passed"):
            print("refused: the platform has not passed the end-to-end verification")
            return 1
        data[key]["status"] = args.status
    save(data)
    write_redirects(data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
