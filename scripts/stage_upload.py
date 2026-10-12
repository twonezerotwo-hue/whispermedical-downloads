"""Put a big file into a DRAFT release of this repository over a slow or unreliable line (run on the machine that has the file).

    python scripts/stage_upload.py TAG FILE --name PUBLIC_NAME --sha256 EXPECTED [--part-mb 64] [--repo owner/name]

The file is checked against the expected SHA-256 first, then cut into pieces ``PUBLIC_NAME.stage0001`` ... that are uploaded one at a time. A piece that is
already in the draft with the right size is skipped, so the script can be stopped and started again at any time and continues where it was. When all pieces are
there it adds ``PUBLIC_NAME.stage.done`` (piece count, size, SHA-256). The "assemble-release" workflow then joins the pieces ON GITHUB'S network, checks the
SHA-256 again, publishes the final files and deletes the pieces. Nothing here is visible to the public: the release stays a draft.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = "twonezerotwo-hue/whispermedical-downloads"


def gh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], capture_output=True, text=True, check=False)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(16 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def assets(tag: str, repo: str) -> dict[str, int]:
    done = gh("release", "view", tag, "--repo", repo, "--json", "assets")
    return {a["name"]: a["size"] for a in json.loads(done.stdout)["assets"]} if done.returncode == 0 else {}


def ensure_draft(tag: str, repo: str, title: str) -> None:
    if gh("release", "view", tag, "--repo", repo).returncode == 0:
        return
    done = gh("release", "create", tag, "--repo", repo, "--draft", "--latest=false", "--title", title,
              "--notes", "Pieces and files of this release are being uploaded; the release is published when everything is there and has been tested.")
    if done.returncode != 0:
        raise SystemExit(f"could not create the draft release {tag}: {done.stderr.strip()[:200]}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("tag")
    parser.add_argument("file", type=Path)
    parser.add_argument("--name", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--title", default="")
    parser.add_argument("--repo", default=REPO)
    parser.add_argument("--part-mb", type=int, default=64)
    args = parser.parse_args(argv)

    size = args.file.stat().st_size
    print(f"checking {args.file.name} ({size} bytes) ...", flush=True)
    actual = sha256_of(args.file)
    if actual != args.sha256:
        print(f"REFUSED: the file's SHA-256 is {actual}, expected {args.sha256}", flush=True)
        return 2
    ensure_draft(args.tag, args.repo, args.title or args.tag)
    part_bytes = args.part_mb * 1024 * 1024
    count = (size + part_bytes - 1) // part_bytes
    print(f"{args.name}: {count} pieces of up to {args.part_mb} MiB", flush=True)
    with tempfile.TemporaryDirectory(prefix="stage_") as tmp, args.file.open("rb") as source:
        for index in range(1, count + 1):
            name = f"{args.name}.stage{index:04d}"
            source.seek((index - 1) * part_bytes)
            block = source.read(part_bytes)
            for attempt in range(1, 41):
                if assets(args.tag, args.repo).get(name) == len(block):
                    break
                piece = Path(tmp) / name
                piece.write_bytes(block)
                started = time.monotonic()
                done = gh("release", "upload", args.tag, "--repo", args.repo, "--clobber", str(piece))
                piece.unlink(missing_ok=True)
                if done.returncode == 0:
                    print(f"  {name} uploaded in {time.monotonic() - started:.0f} s ({index}/{count})", flush=True)
                    break
                print(f"  {name} attempt {attempt} failed: {(done.stderr or '').strip()[:150]}", flush=True)
                time.sleep(min(60, 5 * attempt))
            else:
                print(f"giving up on {name}", flush=True)
                return 1
        marker = Path(tmp) / f"{args.name}.stage.done"
        marker.write_text(json.dumps({"name": args.name, "pieces": count, "size": size, "sha256": args.sha256, "piece_bytes": part_bytes}), encoding="utf-8")
        for attempt in range(1, 11):
            if gh("release", "upload", args.tag, "--repo", args.repo, "--clobber", str(marker)).returncode == 0:
                break
            time.sleep(5 * attempt)
        else:
            print("could not upload the completion marker", flush=True)
            return 1
    print("STAGE_OK", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
