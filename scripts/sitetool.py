"""Maintain the public download site: release-manifest.json and the stable "latest" redirect pages.

    python scripts/sitetool.py show
    python scripts/sitetool.py set-platform windows entry.json         replace one platform's entry (status stays "uploaded" until it is verified)
    python scripts/sitetool.py set-verified windows RUN_URL            record that the anonymous download + real install + start + transcription test passed
    python scripts/sitetool.py set-status windows ready                refused unless the platform was verified (and, if required, the owner confirmed the licence notices in the workflow)
    python scripts/sitetool.py redirects                               rewrite latest/windows/index.html and latest/mac-intel/index.html from the manifest
    python scripts/sitetool.py set-product 4.1.0 [--name MELETRA]      the version every platform has to reach before its installer is offered (the one-command installers check it); --name sets the product name
    python scripts/sitetool.py validate                                check the manifest for the rules below; exit 1 with the problems listed

A platform button on the landing page is enabled only when its entry says "status": "ready". Nothing here uploads files; it only edits small text files.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "release-manifest.json"
KEYS = {"windows": "windows", "mac-intel": "mac_intel", "mac_intel": "mac_intel"}
REDIRECT = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>MELETRA download</title>
<meta http-equiv="refresh" content="0; url={url}">
<link rel="canonical" href="{url}">
</head><body><p>Starting the download of MELETRA for {label} &hellip; if nothing happens, <a href="{url}">click here</a>.</p></body></html>
"""
PENDING = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>MELETRA</title>
<meta http-equiv="refresh" content="3; url=../../">
</head><body><p>The {label} download is not available yet. Going back to the download page &hellip;</p></body></html>
"""


def load(path: Path | None = None) -> dict:
    return json.loads((path or MANIFEST).read_text(encoding="utf-8"))


def save(data: dict, path: Path | None = None) -> None:
    data["generated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    (path or MANIFEST).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


HOSTS = ("github.com", ".githubusercontent.com", ".github.io")
SHA = re.compile(r"^[0-9a-f]{64}$")


def allowed_url(url: str) -> bool:
    m = re.match(r"^https://([^/:]+)/", url or "")
    return bool(m) and any(m.group(1) == h or (h.startswith(".") and m.group(1).endswith(h)) for h in HOSTS)


def problems(data: dict) -> list[str]:
    """The rules of release-manifest.json: the installers (button, one-click program, one-command scripts) trust nothing else."""
    out: list[str] = []
    product = data.get("product_version")
    if not product or not re.match(r"^\d+\.\d+\.\d+$", product):
        out.append("product_version is missing or not x.y.z")
    for key in ("windows", "mac_intel"):
        entry = data.get(key)
        if not entry:
            out.append(f"{key}: no entry")
            continue
        if entry.get("status") not in ("pending", "uploaded", "ready"):
            out.append(f"{key}: status {entry.get('status')!r} is not pending / uploaded / ready")
        if entry.get("status") in ("uploaded", "ready"):
            boot = entry.get("bootstrapper") or {}
            if not allowed_url(boot.get("url", "")) or not SHA.match(boot.get("sha256", "")) or not boot.get("size"):
                out.append(f"{key}: the bootstrapper needs an https github address, a SHA-256 and a size")
            payload = entry.get("payload") or {}
            files = ([payload["setup"]] if payload.get("setup") else []) + [f for f in (payload.get("model") or {}).get("files", [])] + \
                    [part for part in ((payload.get("dmg") or {}).get("parts") or [])]
            if not files:
                out.append(f"{key}: no payload files")
            for f in files:
                if not SHA.match(f.get("sha256", "")) or not f.get("size"):
                    out.append(f"{key}: {f.get('name')}: SHA-256 or size missing")
                for u in ([f["url"]] if f.get("url") else []) + [p["url"] for p in f.get("parts", [])]:
                    if not allowed_url(u):
                        out.append(f"{key}: {f.get('name')}: address {u!r} is not an https github address")
            if "download_bytes" not in entry or not entry.get("version") or not entry.get("architecture"):
                out.append(f"{key}: version, architecture and download_bytes are required")
        if entry.get("status") == "ready":
            if not (entry.get("verification") or {}).get("passed"):
                out.append(f"{key}: ready without a passed end-to-end verification")
            if product and entry.get("version") != product:
                out.append(f"{key}: ready, but version {entry.get('version')} is not the product version {product}")
    text = json.dumps(data)
    if re.search(r"(?i)(<[A-Z_ ]+>|\bTODO\b|\bexample\.com\b|\bPLACEHOLDER\b)", text):
        out.append("the manifest contains a placeholder")
    return out


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
    sub.add_parser("validate")
    pv = sub.add_parser("set-product")
    pv.add_argument("version")
    pv.add_argument("--name", default=None, help="the product name shown by the installers (default: unchanged)")
    s = sub.add_parser("set-status")
    s.add_argument("platform")
    s.add_argument("status", choices=["pending", "uploaded", "ready"])
    args = parser.parse_args(argv)
    data = load()
    if args.cmd == "validate":
        found = problems(data)
        print("\n".join(found) if found else "release-manifest.json: OK")
        return 1 if found else 0
    if args.cmd == "set-product":
        data["product_version"] = args.version
        if args.name:
            data["product"] = args.name                        # "product" is what the installers have always read; "product_name" is the same value under its clear name
            data["product_name"] = args.name
        save(data)
        write_redirects(data)
        return 0
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
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        data[key]["verification"] = {"passed": True, "run": args.run_url, "date": now}
        data[key]["release_date"] = now[:10]
        data[key]["published_at"] = now
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
