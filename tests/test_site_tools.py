"""The public site tools: a button is enabled only for a platform that is verified, and nothing private can be published."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import audit_public  # noqa: E402
import sitetool as site_tools  # noqa: E402
import pytest  # noqa: E402


def entry(status="ready"):
    return {"status": status, "bootstrapper": {"name": "x.exe", "url": "https://github.com/o/r/releases/download/v1/x.exe"}}


def test_a_pending_platform_gets_a_page_that_goes_back_and_a_ready_one_a_redirect(tmp_path):
    data = {"windows": entry("uploaded"), "mac_intel": entry("ready")}
    site_tools.write_redirects(data, tmp_path)
    assert "not available yet" in (tmp_path / "latest" / "windows" / "index.html").read_text(encoding="utf-8")
    mac = (tmp_path / "latest" / "mac-intel" / "index.html").read_text(encoding="utf-8")
    assert "https://github.com/o/r/releases/download/v1/x.exe" in mac and "refresh" in mac


def test_ready_needs_a_bootstrapper_and_an_exact_status():
    assert site_tools.ready(entry()) and not site_tools.ready(entry("uploaded")) and not site_tools.ready({"status": "ready"}) and not site_tools.ready({})


def test_set_status_refuses_ready_without_a_bootstrapper(tmp_path, monkeypatch):
    path = tmp_path / "release-manifest.json"
    path.write_text(json.dumps({"windows": {"status": "uploaded"}, "mac_intel": {"status": "pending"}}), encoding="utf-8")
    monkeypatch.setattr(site_tools, "MANIFEST", path)
    monkeypatch.setattr(site_tools, "ROOT", tmp_path)
    assert site_tools.main(["set-status", "windows", "ready"]) == 1
    assert json.loads(path.read_text(encoding="utf-8"))["windows"]["status"] == "uploaded"


def test_ready_is_refused_until_the_end_to_end_verification_is_recorded(tmp_path, monkeypatch):
    path = tmp_path / "release-manifest.json"
    path.write_text(json.dumps({"windows": entry("uploaded"), "mac_intel": {"status": "pending"}}), encoding="utf-8")
    monkeypatch.setattr(site_tools, "MANIFEST", path)
    monkeypatch.setattr(site_tools, "ROOT", tmp_path)
    assert site_tools.main(["set-status", "windows", "ready"]) == 1
    assert json.loads(path.read_text(encoding="utf-8"))["windows"]["status"] == "uploaded"
    assert site_tools.main(["set-verified", "windows", "https://github.com/o/r/actions/runs/1"]) == 0
    assert json.loads(path.read_text(encoding="utf-8"))["windows"]["verification"]["passed"] is True
    assert site_tools.main(["set-status", "windows", "ready"]) == 0
    assert site_tools.ready(json.loads(path.read_text(encoding="utf-8"))["windows"])
    new = tmp_path / "entry.json"
    new.write_text(json.dumps(entry("uploaded")), encoding="utf-8")
    assert site_tools.main(["set-platform", "windows", str(new)]) == 0                  # a replaced entry loses the verification
    assert "verification" not in json.loads(path.read_text(encoding="utf-8"))["windows"]


def test_set_platform_never_publishes_directly(tmp_path, monkeypatch):
    path = tmp_path / "release-manifest.json"
    path.write_text(json.dumps({"windows": {"status": "pending"}, "mac_intel": {"status": "pending"}}), encoding="utf-8")
    new = tmp_path / "entry.json"
    new.write_text(json.dumps(entry("ready")), encoding="utf-8")
    monkeypatch.setattr(site_tools, "MANIFEST", path)
    monkeypatch.setattr(site_tools, "ROOT", tmp_path)
    assert site_tools.main(["set-platform", "windows", str(new)]) == 0
    assert json.loads(path.read_text(encoding="utf-8"))["windows"]["status"] == "uploaded"       # becomes "ready" only after the verification step


@pytest.mark.parametrize("name, text, expected", [
    ("a.txt", "token ghp_" + "A" * 36, "token"),
    ("a.txt", "see C:" + chr(92) + "Users" + chr(92) + "someone" + chr(92) + "file", "personal path"),
    ("a.txt", "mail me@example.org", "e-mail"),
    ("a.txt", "source: https://github.com/twonezerotwo-hue/" + "whispermedical" + "/tree/main", "private source repo"),
    ("a.mp4", "x", "must not be published"),
    ("a.txt", "-----BEGIN " + "PRIVATE KEY-----", "token"),
])
def test_the_audit_finds_private_material(tmp_path, name, text, expected):
    (tmp_path / name).write_text(text, encoding="utf-8")
    assert any(expected in p for p in audit_public.scan(tmp_path))


def test_the_audit_accepts_the_public_repo_and_noreply_addresses(tmp_path):
    (tmp_path / "a.txt").write_text("https://github.com/twonezerotwo-hue/whispermedical-downloads/issues and 1234+x@users.noreply.github.com", encoding="utf-8")
    assert audit_public.scan(tmp_path) == []


def test_entries_follow_the_pins_and_never_say_ready(tmp_path):
    import build_entries as be

    boot = tmp_path / "WhisperMedical-Installer-Windows.exe"
    boot.write_bytes(b"MZ" + b"0" * 100)
    pins = json.loads((Path(be.ROOT) / "pins" / "windows.json").read_text(encoding="utf-8"))
    layout = json.loads((Path(be.ROOT) / "scripts" / "model_parts.json").read_text(encoding="utf-8"))
    w = be.windows_entry(pins, layout, boot)
    assert w["status"] == "uploaded" and w["payload"]["setup"]["sha256"] == pins["setup"]["sha256"]
    assert w["bootstrapper"]["url"].startswith("https://github.com/twonezerotwo-hue/whispermedical-downloads/releases/download/windows-v3.1.0/")
    model = {f["name"]: f for f in w["payload"]["model"]["files"]}
    assert [p["size"] for p in model["model.bin"]["parts"]] == [1992294400, 1094989837] and sum(p["size"] for p in model["model.bin"]["parts"]) == model["model.bin"]["size"]
    assert w["download_bytes"] == pins["setup"]["size"] + sum(f["size"] for f in layout["files"])
    mac_pins = json.loads((Path(be.ROOT) / "pins" / "mac-intel.json").read_text(encoding="utf-8"))
    z = tmp_path / "WhisperMedical-Installer-IntelMac.zip"
    z.write_bytes(b"PK")
    m = be.mac_entry(mac_pins, z)
    assert m["status"] == "uploaded" and sum(p["size"] for p in m["payload"]["dmg"]["parts"]) == m["payload"]["dmg"]["size"]
    assert all(p["url"].startswith("https://github.com/") for p in m["payload"]["dmg"]["parts"])


def test_every_pinned_part_is_below_the_two_gib_asset_limit():
    root = Path(__file__).resolve().parent.parent
    mac = json.loads((root / "pins" / "mac-intel.json").read_text(encoding="utf-8"))
    layout = json.loads((root / "scripts" / "model_parts.json").read_text(encoding="utf-8"))
    sizes = [p["size"] for p in mac["dmg"]["parts"]] + [p["size"] for f in layout["files"] for p in f.get("parts", [])]
    assert max(sizes) < 2 * 1024 ** 3
