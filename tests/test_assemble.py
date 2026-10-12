"""scripts/assemble.py: joining staged pieces and cutting the final parts - exact, and every difference is refused."""

import hashlib
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import assemble  # noqa: E402


def specs_for(data: bytes, sizes):
    out, at = [], 0
    for i, size in enumerate(sizes, 1):
        chunk = data[at:at + size]
        out.append({"name": f"x.part{i:03d}", "size": len(chunk), "sha256": hashlib.sha256(chunk).hexdigest()})
        at += size
    return out


def test_pieces_are_joined_in_order_and_cut_into_the_pinned_parts(tmp_path):
    data = os.urandom(100_000)
    pieces = []
    for i in range(0, len(data), 7_000):
        p = tmp_path / f"p{i // 7_000:04d}"
        p.write_bytes(data[i:i + 7_000])
        pieces.append(p)
    joined = tmp_path / "whole"
    assemble.join_parts(pieces, joined)
    assert joined.read_bytes() == data
    out = tmp_path / "out"
    out.mkdir()
    made = assemble.split_file(joined, specs_for(data, [60_000, 40_000]), out)
    assert [m.name for m in made] == ["x.part001", "x.part002"]
    assert b"".join(m.read_bytes() for m in made) == data


@pytest.mark.parametrize("sizes", [[60_000, 39_999], [60_000, 40_001]])
def test_a_file_that_is_shorter_or_longer_than_the_pinned_parts_is_refused(tmp_path, sizes):
    data = os.urandom(100_000)
    whole = tmp_path / "whole"
    whole.write_bytes(data)
    out = tmp_path / "out"
    out.mkdir()
    pinned = specs_for(data + b"\0" * 5, sizes) if sizes[1] == 40_001 else specs_for(data, sizes)
    with pytest.raises(SystemExit, match="REFUSED"):
        assemble.split_file(whole, pinned, out)


def test_a_changed_byte_is_refused(tmp_path):
    data = os.urandom(50_000)
    pinned = specs_for(data, [30_000, 20_000])
    whole = tmp_path / "whole"
    whole.write_bytes(data[:40_000] + bytes([data[40_000] ^ 1]) + data[40_001:])
    out = tmp_path / "out"
    out.mkdir()
    with pytest.raises(SystemExit, match="REFUSED"):
        assemble.split_file(whole, pinned, out)
