"""Mirror the Whisper large-v3 speech model (MIT licence) into a public GitHub release, byte for byte, on GitHub's own servers.

    python scripts/mirror_model.py OUT_DIR

Downloads the five files of Systran/faster-whisper-large-v3 (a fixed revision) from Hugging Face, checks every size and SHA-256 against scripts/model_files.json,
cuts model.bin into the pieces listed in scripts/model_parts.json (a release asset may be at most 2 GiB) and checks each piece. OUT_DIR then holds exactly the
files to upload. Anything that does not match stops the run: nothing unverified is ever uploaded.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = "https://huggingface.co/Systran/faster-whisper-large-v3/resolve/{revision}/{name}"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(16 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def download(url: str, dest: Path, size: int) -> None:
    have = dest.stat().st_size if dest.is_file() else 0
    attempts = 0
    while have < size:
        try:
            request = urllib.request.Request(url, headers={"Range": f"bytes={have}-", "User-Agent": "meletra-mirror"})
            with urllib.request.urlopen(request, timeout=120) as response, dest.open("ab" if have else "wb") as out:
                while block := response.read(8 * 1024 * 1024):
                    out.write(block)
                    have += len(block)
        except OSError as exc:
            attempts += 1
            have = dest.stat().st_size if dest.is_file() else 0
            print(f"  connection problem ({exc}); continuing from {have}", flush=True)
            if attempts > 30:
                raise SystemExit(f"giving up on {dest.name}")
            time.sleep(min(60, 3 * attempts))


def main() -> int:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    layout = json.loads((HERE / "model_parts.json").read_text(encoding="utf-8"))
    expected = json.loads((HERE / "model_files.json").read_text(encoding="utf-8"))
    for entry in layout["files"]:
        name = entry["name"]
        assert entry["sha256"] == expected[name]["sha256"] and entry["size"] == expected[name]["size"], f"the layout disagrees with the pinned values for {name}"
        target = out / ("model.bin.whole" if name == "model.bin" else name)
        print(f"download {name} ({entry['size'] / 1e6:.1f} MB)", flush=True)
        download(BASE.format(revision=layout["revision"], name=name), target, entry["size"])
        if target.stat().st_size != entry["size"] or sha256(target) != entry["sha256"]:
            raise SystemExit(f"{name} does not match its pinned size / SHA-256 - not mirroring")
        print(f"  verified {name}", flush=True)
        if name == "model.bin":
            with target.open("rb") as source:
                for part in entry["parts"]:
                    block = source.read(part["size"])
                    piece = out / part["name"]
                    piece.write_bytes(block)
                    if len(block) != part["size"] or hashlib.sha256(block).hexdigest() != part["sha256"]:
                        raise SystemExit(f"piece {part['name']} does not match the layout")
                    print(f"  piece {part['name']} ok ({len(block)} bytes)", flush=True)
            target.unlink()
    print("MIRROR_READY", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
