"""Build the offline translation pack (M2M100 418M, MIT licence) on GitHub's own servers and check it against the values that were tested.

    python scripts/build_translation_pack.py OUT_DIR

1. downloads the seven files of facebook/m2m100_418M at a fixed revision from Hugging Face and checks every size and SHA-256 against scripts/translation_pack.json;
2. converts the model to CTranslate2 int8 and copies the SentencePiece file;
3. writes pack.json and translation-m2m100.sha256.json and the licence notice;
4. compares the result with the pinned, tested values. Anything that differs stops the run (set PACK_ALLOW_DIFFERENT=1 only to see the new values; nothing is then published).

OUT_DIR then holds exactly the files to upload. Nothing unverified is ever uploaded.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = "https://huggingface.co/{model}/resolve/{revision}/{name}"
OFFERED = ["en", "tr", "de", "hu", "ko", "zh", "hi", "nl", "fr", "es"]
NOTICE = """MIT License

Copyright (c) Facebook, Inc. and its affiliates.

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software
without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit
persons to whom the Software is furnished to do so, subject to the following conditions: The above copyright notice and this permission notice shall be included in all copies
or substantial portions of the Software. THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED.

This pack is facebook/m2m100_418M (https://huggingface.co/facebook/m2m100_418M, revision {revision}) converted to the CTranslate2 int8 format. It is used by MELETRA for
optional offline translation of saved transcripts.
"""


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
            request = urllib.request.Request(url, headers={"Range": f"bytes={have}-", "User-Agent": "meletra-pack-build"})
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
    work = out.parent / (out.name + "_source")
    work.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    pins = json.loads((HERE / "translation_pack.json").read_text(encoding="utf-8"))
    for name, pin in pins["source"].items():
        target = work / name
        print(f"download {name} ({pin['size'] / 1e6:.1f} MB)", flush=True)
        download(BASE.format(model=pins["model"], revision=pins["revision"], name=name), target, pin["size"])
        if target.stat().st_size != pin["size"] or sha256(target) != pin["sha256"]:
            raise SystemExit(f"{name} does not match its pinned size / SHA-256 - not building")
        print(f"  verified {name}", flush=True)

    import ctranslate2
    from ctranslate2.converters import TransformersConverter

    if ctranslate2.__version__ != pins["converter"]["ctranslate2"]:
        print(f"WARNING: ctranslate2 {ctranslate2.__version__} differs from the tested {pins['converter']['ctranslate2']}", flush=True)
    target_dir = out / "translation-m2m100"
    if target_dir.exists():
        shutil.rmtree(target_dir)
    TransformersConverter(str(work)).convert(str(target_dir), quantization=pins["converter"]["quantization"])
    shutil.copyfile(work / "sentencepiece.bpe.model", target_dir / "sentencepiece.bpe.model")
    pack = {"name": "translation-m2m100", "pack_version": 1, "model": pins["model"], "source_revision": pins["revision"], "licence": "MIT (Facebook AI Research / Meta)",
            "format": "CTranslate2 int8", "converted_with": f"ctranslate2 {ctranslate2.__version__}", "languages": OFFERED,
            "note": "Neural machine translation, one direct step between any two of the listed languages (no pivot through English). Quality is that of a 418M-parameter model: "
                    "usually understandable, sometimes wrong on rare medical terms - the original transcript is always kept."}
    (target_dir / "pack.json").write_text(json.dumps(pack, indent=1, ensure_ascii=False), encoding="utf-8")
    files = {p.name: {"size": p.stat().st_size, "sha256": sha256(p)} for p in sorted(target_dir.iterdir()) if p.is_file()}
    differences = [f"{n}: built {files.get(n)} but tested {pins['output'].get(n)}" for n in sorted(set(files) | set(pins["output"])) if files.get(n) != pins["output"].get(n)]
    if differences:
        print("THE BUILD DIFFERS FROM THE TESTED PACK:\n  " + "\n  ".join(differences), flush=True)
        if os.environ.get("PACK_ALLOW_DIFFERENT") != "1":
            raise SystemExit("not publishing a pack that is not byte-identical to the tested one")
    release = out / "release"
    release.mkdir(exist_ok=True)
    for name in files:
        shutil.copyfile(target_dir / name, release / name)
    manifest = {"model": pins["model"], "revision": pins["revision"], "licence": pins["licence"], "format": "CTranslate2 int8", "pack_version": 1, "tag": pins["tag"],
                "languages": OFFERED, "files": {n: {"bytes": f["size"], "sha256": f["sha256"]} for n, f in files.items()}}
    (release / "translation-m2m100.sha256.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    (release / "LICENSE-M2M100.txt").write_text(NOTICE.format(revision=pins["revision"]), encoding="utf-8")
    print("PACK_READY", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
