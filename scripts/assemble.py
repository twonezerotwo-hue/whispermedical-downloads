"""Join the pieces that scripts/stage_upload.py put into a draft release into the final files of a platform (runs on GitHub's network).

    python scripts/assemble.py windows   --work WORKDIR      -> WORKDIR/out/WhisperMedical-Setup-Windows-x64.exe
    python scripts/assemble.py mac-intel --work WORKDIR      -> WORKDIR/out/WhisperMedical-Intel-Mac-Offline.dmg.part001, .part002

The final files must be exactly what pins/<platform>.json says: size and SHA-256 of the whole file (and, for the disk image, of each part). Anything else is
refused and nothing is published. Prints ASSEMBLE_OK and the names to upload as the last lines.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = os.environ.get("GITHUB_REPOSITORY", "twonezerotwo-hue/whispermedical-downloads")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(16 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def join_parts(parts: list[Path], target: Path) -> None:
    with target.open("wb") as out:
        for part in parts:
            with part.open("rb") as handle:
                while block := handle.read(16 * 1024 * 1024):
                    out.write(block)


def split_file(source: Path, specs: list[dict], folder: Path) -> list[Path]:
    """Cut ``source`` into the pieces described by ``specs`` (name, size, sha256), in order; refuse on any difference."""
    made = []
    with source.open("rb") as handle:
        for spec in specs:
            target = folder / spec["name"]
            remaining = spec["size"]
            digest = hashlib.sha256()
            with target.open("wb") as out:
                while remaining:
                    block = handle.read(min(16 * 1024 * 1024, remaining))
                    if not block:
                        raise SystemExit(f"REFUSED: the file ends before {spec['name']} is complete")
                    out.write(block)
                    digest.update(block)
                    remaining -= len(block)
            if digest.hexdigest() != spec["sha256"]:
                raise SystemExit(f"REFUSED: piece {spec['name']} has SHA-256 {digest.hexdigest()}, expected {spec['sha256']}")
            made.append(target)
        if handle.read(1):
            raise SystemExit("REFUSED: the file is longer than the sum of its pieces")
    return made


def gh_json(*args: str):
    done = subprocess.run(["gh", "api", *args], capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise SystemExit(f"gh api {' '.join(args)} failed: {done.stderr.strip()[:200]}")
    return json.loads(done.stdout)


def draft_assets(tag: str) -> dict[str, dict]:
    releases = gh_json(f"repos/{REPO}/releases?per_page=100")
    release = next((r for r in releases if r["tag_name"] == tag), None)
    if release is None:
        raise SystemExit(f"there is no release {tag}")
    return {a["name"]: a for a in release["assets"]}


def download_asset(asset: dict, target: Path) -> None:
    with target.open("wb") as out:
        done = subprocess.run(["gh", "api", f"repos/{REPO}/releases/assets/{asset['id']}", "-H", "Accept: application/octet-stream"], stdout=out, check=False)
    if done.returncode != 0 or target.stat().st_size != asset["size"]:
        raise SystemExit(f"could not download {asset['name']}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("platform", choices=["windows", "mac-intel"])
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args(argv)
    pins = json.loads((ROOT / "pins" / f"{args.platform}.json").read_text(encoding="utf-8"))
    if args.platform == "windows":
        tag, whole = f"windows-v{pins['version']}", pins["setup"]
        finals = [whole]
    else:
        tag, whole = f"mac-intel-v{pins['version']}", pins["dmg"]
        finals = whole["parts"]
    have = draft_assets(tag)
    marker = have.get(f"{whole['name']}.stage.done")
    if marker is None:
        raise SystemExit(f"the upload of {whole['name']} is not complete yet (no {whole['name']}.stage.done)")
    args.work.mkdir(parents=True, exist_ok=True)
    stage = args.work / "stage"
    stage.mkdir(exist_ok=True)
    download_asset(marker, stage / "done.json")
    done = json.loads((stage / "done.json").read_text(encoding="utf-8"))
    if done["sha256"] != whole["sha256"] or done["size"] != whole["size"]:
        raise SystemExit("REFUSED: the staged file is not the one pinned for this release")
    names = sorted(n for n in have if re.fullmatch(re.escape(whole["name"]) + r"\.stage\d{4}", n))
    if len(names) != done["pieces"]:
        raise SystemExit(f"REFUSED: {len(names)} pieces are in the release, {done['pieces']} were announced")
    paths = []
    for name in names:
        download_asset(have[name], stage / name)
        paths.append(stage / name)
    joined = args.work / whole["name"]
    join_parts(paths, joined)
    if joined.stat().st_size != whole["size"] or sha256_of(joined) != whole["sha256"]:
        raise SystemExit("REFUSED: the joined file does not match the pinned size / SHA-256")
    out = args.work / "out"
    out.mkdir(exist_ok=True)
    if args.platform == "windows":
        joined.replace(out / whole["name"])
        produced = [out / whole["name"]]
    else:
        produced = split_file(joined, finals, out)
    print("ASSEMBLE_OK")
    for path in produced:
        print(path)
    print("STAGED " + " ".join(names + [marker["name"]]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
