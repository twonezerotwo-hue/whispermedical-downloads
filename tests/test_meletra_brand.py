"""The public distribution repository says MELETRA wherever a person sees a name. The old names (WhisperMedical, Medical Lecture Transcriber) may appear only where an
earlier installation has to be recognised, in the technical address of this repository, and in the record of what the program used to be called."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OLD = re.compile(r"whisper\s?medical|medical lecture transcriber|medlecture", re.I)
REPO_SLUG = re.compile("whispermedical-downloads|" + "com\\.whispermedical\\.installer", re.I)                # the technical address of THIS repository and the installer app's bundle id


def read(path):
    return Path(path).read_text(encoding="utf-8")


def old_names(text):
    return [m.group(0) for m in OLD.finditer(REPO_SLUG.sub("", text))]


def test_the_download_page_is_meletra():
    page = read(ROOT / "index.html")
    assert "<title>MELETRA - Medical Learning &amp; Transcription</title>" in page and "<h1>MELETRA</h1>" in page and "Medical Learning &amp; Transcription" in page
    assert 'src="assets/meletra-symbol.png"' in page and 'alt="MELETRA logo"' in page
    assert "Download MELETRA for " in page and "Installation instructions" in page
    assert "Apple Silicon Mac" in page and "Intel Mac" in page and "mac-intel-40470251885" in page and "mac-apple-silicon-40313169466" in page
    assert "meletra-install.ps1" in page
    # the old names: only the sentence that tells people an upgrade keeps their data
    assert old_names(page) == ["WhisperMedical", "Medical Lecture Transcriber"]
    assert "Nothing is shared unless you switch it on" in page


def test_the_help_pages_the_readme_and_the_release_notes_say_meletra():
    for rel in ("downloads/install-windows.html", "downloads/install-mac-intel.html", "downloads/install-mac-apple-silicon.html", "README.md",
                "release-notes/MELETRA-4.1.0.md", "latest/windows/index.html", "latest/mac-intel/index.html", "latest/mac-apple-silicon/index.html"):
        text = read(ROOT / rel)
        assert "MELETRA" in text, rel
        allowed = {"WhisperMedical", "Medical Lecture Transcriber"}
        assert set(old_names(text)) <= allowed, (rel, old_names(text))
    notes = read(ROOT / "release-notes" / "MELETRA-4.1.0.md")
    assert notes.startswith("# MELETRA 4.1.0 - Medical Learning & Transcription") and "off by default" in notes and "not code-signed" in notes
    assert "branch" not in notes.lower() and "pytest" not in notes.lower()                      # no developer-internal history in the notes people read


def test_the_installers_and_scripts_carry_the_new_names_and_keep_the_old_ones_only_for_upgrades():
    cs = read(ROOT / "bootstrap" / "windows" / "MELETRAInstaller.cs")
    assert "namespace MELETRA" in cs and '"MELETRA.exe"' in cs and 'Text = "MELETRA Installer"' in cs and '"MELETRAInstaller", "cache"' in cs
    assert old_names(cs.replace("WhisperMedicalInstaller", "")) == [] and cs.count("WhisperMedicalInstaller") == 1            # only the clean-up of the earlier installer's cache
    assert cs.count("UseMnemonic = false") >= 5                                         # "Learning & Transcription" must show its ampersand
    build = read(ROOT / "bootstrap" / "windows" / "build.py")
    assert "MELETRA-Installer-Windows.exe" in build and "MELETRA-Setup-Windows-x64.exe" in build and "/win32icon" in build
    ps1 = read(ROOT / "install" / "install-windows.ps1")
    assert "Install-MELETRA" in ps1 and "MELETRA_ALLOW_UNANNOUNCED" in ps1 and "WHISPERMEDICAL_ALLOW_UNANNOUNCED" in ps1          # the old switches keep working
    sh = read(ROOT / "install" / "install-macos.sh")
    assert 'APP_NAME="MELETRA.app"' in sh and "LEGACY_APP_NAMES=" in sh and "WhisperMedical.app" in sh and "Medical Lecture Transcriber.app" in sh
    assert (ROOT / "install" / "Install MELETRA.command").is_file() and not (ROOT / "install" / "Install WhisperMedical.command").exists()
    assert not (ROOT / "bootstrap" / "windows" / "WhisperMedicalInstaller.cs").exists()


def test_the_brand_files_are_the_new_ones():
    for name in ("meletra-logo.png", "meletra-logo-horizontal.png", "meletra-symbol.png", "meletra-icon-64.png", "meletra-icon-256.png", "meletra.ico", "favicon.ico", "favicon-32.png",
                 "favicon-192.png", "apple-touch-icon.png"):
        assert (ROOT / "assets" / name).stat().st_size > 400, name
    assert not (ROOT / "assets" / "logo.png").exists() and not (ROOT / "assets" / "logo-symbol.png").exists()
    ico = (ROOT / "assets" / "meletra.ico").read_bytes()
    assert ico[:4] == b"\x00\x00\x01\x00" and int.from_bytes(ico[4:6], "little") >= 6               # an icon with several sizes (16 ... 256)


def test_the_release_workflow_stages_verifies_and_only_then_promotes_the_manifest():
    flow = read(ROOT / ".github" / "workflows" / "finalize-release.yml")
    start = flow.index("\n  windows-build:")
    windows = flow[start:flow.index("# ====", start)]
    order = [windows.index(f"\n  {job}:") for job in ("windows-build", "windows-stage", "windows-verify-clean", "windows-verify-upgrade", "windows-verify-upgrade-410", "windows-promote", "windows-verify", "windows-rollback", "windows-ready")]
    assert order == sorted(order)
    assert "--draft=false --prerelease --latest=false" in windows and 'needs: [windows-build, windows-verify-clean, windows-verify-upgrade, windows-verify-upgrade-410]' in windows
    stage = windows[:windows.index("\n  windows-promote:")]
    assert "set-platform" not in stage and "release-manifest.json" not in stage      # nothing before the promotion touches the public manifest
    assert 'sitetool.py set-product "$VER" --name MELETRA' in windows and "windows-rollback" in windows and 'git checkout "$BEFORE" -- release-manifest.json latest' in windows
    assert "MELETRA.exe" in windows and "MedicalLectureTranscriber.exe" in windows                         # the upgrade job proves that the old program file is gone
    assert "Install the PUBLIC WhisperMedical 4.0.0" in windows and "user data was lost" in windows
    assert "Install the PUBLIC MELETRA 4.1.0" in windows and "translation pack file differs from its pin" in windows and "--translate-lecture" in windows        # 4.1.1: upgrade over the last release, the optional pack, re-translation offline


def test_sitetool_records_the_product_name_with_the_version(tmp_path, monkeypatch):
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    import sitetool

    manifest = tmp_path / "release-manifest.json"
    manifest.write_text(json.dumps({"schema": 1, "product": "WhisperMedical", "product_version": "4.0.0", "windows": {"status": "pending"}, "mac_intel": {"status": "pending"}}), encoding="utf-8")
    monkeypatch.setattr(sitetool, "MANIFEST", manifest)
    monkeypatch.setattr(sitetool, "ROOT", tmp_path)
    assert sitetool.main(["set-product", "4.1.0", "--name", "MELETRA"]) == 0
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["product"] == "MELETRA" and data["product_name"] == "MELETRA" and data["product_version"] == "4.1.0"
