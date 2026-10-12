"""The Intel Mac installer script against a local server with a FAKE disk image (a tiny app folder): success, resume, and every refusal. macOS only."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="needs macOS (hdiutil, osascript)")
ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "bootstrap" / "mac-intel" / "install.sh"
APP = "Medical Lecture Transcriber.app"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Server:
    def __init__(self, files):
        self.files, self.requests, self.cut = files, [], {}
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                body = outer.files.get(self.path.split("?")[0])
                if body is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                rng = self.headers.get("Range")
                start = int(rng.split("=")[1].split("-")[0]) if rng else 0
                outer.requests.append((self.path, start))
                data = body[start:]
                self.send_response(206 if rng else 200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                if outer.cut.get(self.path, 0) > 0:
                    outer.cut[self.path] -= 1
                    self.wfile.write(data[: max(1, len(data) // 3)])
                    self.wfile.flush()
                    self.connection.close()
                    return
                self.wfile.write(data)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_port
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"

    def close(self):
        self.httpd.shutdown()


@pytest.fixture(scope="module")
def image(tmp_path_factory):
    base = tmp_path_factory.mktemp("img")
    src = base / "src"
    (src / APP / "Contents" / "MacOS").mkdir(parents=True)
    (src / APP / "Contents" / "MacOS" / "tool").write_bytes(os.urandom(300_000))
    (src / APP / "Contents" / "Info.plist").write_text("<plist/>")
    dmg = base / "fake.dmg"
    subprocess.run(["hdiutil", "create", "-volname", "Fake", "-srcfolder", str(src), "-format", "UDZO", "-quiet", str(dmg)], check=True)
    data = dmg.read_bytes()
    size = max(40_000, len(data) // 3)
    parts = [data[i:i + size] for i in range(0, len(data), size)]
    return {"data": data, "parts": parts, "sha": sha(data)}


def make(srv, image, status="ready", version="9.9.9", tamper=False):
    parts = []
    for i, p in enumerate(image["parts"], 1):
        name = f"WhisperMedical-Intel-Mac-Offline.dmg.part{i:03d}"
        served = p[:-1] + bytes([p[-1] ^ 0xFF]) if (tamper and i == 2) else p
        srv.files["/" + name] = served
        parts.append({"name": name, "size": len(p), "sha256": sha(p), "url": srv.url("/" + name)})
    manifest = {"mac_intel": {"status": status, "version": version, "payload": {"dmg": {"name": "WhisperMedical-Intel-Mac-Offline.dmg", "size": len(image["data"]),
                                                                                        "sha256": image["sha"], "parts": parts}}}}
    srv.files["/manifest.json"] = json.dumps(manifest).encode()


def run(srv, image, tmp_path, pin_sha=None):
    dest = tmp_path / "Applications"
    dest.mkdir()
    progress = tmp_path / "progress.txt"
    env = dict(os.environ, MLT_TEST="1", MLT_MANIFEST_URL=srv.url("/manifest.json"), MLT_PIN_VERSION="9.9.9", MLT_PIN_DMG_SHA256=pin_sha or image["sha"],
               MLT_PIN_DMG_SIZE=str(len(image["data"])), MLT_CACHE=str(tmp_path / "cache"))
    done = subprocess.run(["/bin/bash", str(SCRIPT), "--dest", str(dest), "--progress-file", str(progress), "--no-open"], capture_output=True, text=True, env=env, timeout=300)
    return done, dest, progress


def test_download_verify_mount_copy_and_clean_up(image, tmp_path):
    srv = Server({})
    make(srv, image)
    try:
        done, dest, progress = run(srv, image, tmp_path)
    finally:
        srv.close()
    assert done.returncode == 0, done.stdout + done.stderr
    assert (dest / APP / "Contents" / "Info.plist").read_text() == "<plist/>" and (dest / APP / "Contents" / "MacOS" / "tool").stat().st_size == 300_000
    assert progress.read_text().strip().splitlines()[-1].startswith("D|")
    assert not (tmp_path / "cache").exists()                                              # pieces, joined image and mount point are gone
    assert subprocess.run(["mount"], capture_output=True, text=True).stdout.count("mlt") == 0 and "Fake" not in subprocess.run(["mount"], capture_output=True, text=True).stdout


def test_cut_connections_resume_inside_the_file(image, tmp_path):
    srv = Server({})
    make(srv, image)
    srv.cut = {"/WhisperMedical-Intel-Mac-Offline.dmg.part001": 2, "/WhisperMedical-Intel-Mac-Offline.dmg.part002": 1}
    try:
        done, dest, _ = run(srv, image, tmp_path)
    finally:
        srv.close()
    assert done.returncode == 0 and (dest / APP).is_dir(), done.stdout + done.stderr
    assert [r for r in srv.requests if r[1] > 0], srv.requests


def test_a_damaged_piece_is_refused_and_nothing_is_installed(image, tmp_path):
    srv = Server({})
    make(srv, image, tamper=True)
    try:
        done, dest, progress = run(srv, image, tmp_path)
    finally:
        srv.close()
    assert done.returncode != 0 and "checksum" in progress.read_text().lower()
    assert not (dest / APP).exists()


@pytest.mark.parametrize("kw, pin, expected", [({"status": "pending"}, None, "not available yet"), ({"version": "1.0.0"}, None, "out of date"), ({}, "0" * 64, "out of date")])
def test_a_manifest_that_is_not_ready_or_not_for_this_installer_stops_before_any_download(image, tmp_path, kw, pin, expected):
    srv = Server({})
    make(srv, image, **kw)
    try:
        done, dest, progress = run(srv, image, tmp_path, pin_sha=pin)
    finally:
        srv.close()
    assert done.returncode != 0 and expected in progress.read_text().lower()
    assert not (dest / APP).exists() and not [r for r in srv.requests if "part" in r[0]]
