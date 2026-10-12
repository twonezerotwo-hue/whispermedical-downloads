"""The Windows bootstrapper against a local server that serves a small FAKE payload: success, resume after cut connections, and every refusal.

Windows only (it compiles and runs the real program with the C# compiler that ships with Windows). The fake "Setup" is a tiny program that only writes a marker
file, so a test can prove whether the bootstrapper started it - and, in the refusal tests, that it did NOT.
"""

import hashlib
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="runs the Windows bootstrapper")
ROOT = Path(__file__).resolve().parent.parent
CSC = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
MODEL_NAMES = ["config.json", "model.bin", "preprocessor_config.json", "tokenizer.json", "vocabulary.json"]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Server:
    def __init__(self, files: dict):
        self.files, self.requests, self.cut = files, [], {}
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                path = self.path.split("?")[0]
                body = outer.files.get(path)
                if body is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                start = 0
                rng = self.headers.get("Range")
                if rng:
                    start = int(rng.split("=")[1].split("-")[0])
                outer.requests.append((path, start))
                data = body[start:]
                self.send_response(206 if rng else 200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                if outer.cut.get(path, 0) > 0:
                    outer.cut[path] -= 1
                    self.wfile.write(data[: max(1, len(data) // 3)])
                    self.wfile.flush()
                    self.connection.close()
                    return
                self.wfile.write(data)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_port
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.port}{path}"

    def close(self):
        self.httpd.shutdown()


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    base = tmp_path_factory.mktemp("boot")
    fake_cs = base / "fake_setup.cs"
    fake_cs.write_text('using System; using System.IO; class P { static int Main(string[] a) { File.WriteAllText(Environment.GetEnvironmentVariable("WM_FAKE_MARKER"), string.Join(" ", a)); '
                       'return 0; } }', encoding="utf-8")
    fake_exe = base / "fake_setup.exe"
    done = subprocess.run([str(CSC), "/nologo", "/target:exe", f"/out:{fake_exe}", str(fake_cs)], capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr
    setup_bytes = fake_exe.read_bytes()
    model = {n: os.urandom(30_000 if n != "model.bin" else 700_000) for n in MODEL_NAMES}
    pins = {"version": "9.9.9", "setup_name": "WhisperMedical-Setup-Windows-x64.exe", "setup_sha256": sha(setup_bytes), "setup_size": len(setup_bytes),
            "model": {n: {"sha256": sha(b)} for n, b in model.items()}}
    (base / "pins.json").write_text(json.dumps(pins), encoding="utf-8")
    exe = base / "boot_test.exe"
    done = subprocess.run([sys.executable, str(ROOT / "bootstrap" / "windows" / "build.py"), "--test", "--pins", str(base / "pins.json"), "--out", str(exe)],
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr
    return {"base": base, "exe": exe, "setup": setup_bytes, "model": model, "pins": pins}


def make_manifest(srv, w, status="ready", version="9.9.9", setup_override=None):
    setup = setup_override or w["setup"]
    files = []
    for name, data in w["model"].items():
        entry = {"name": name, "size": len(data), "sha256": sha(data), "url": srv.url("/m/" + name)}
        if name == "model.bin":
            half = len(data) // 2
            entry["parts"] = [{"name": "model.bin.part001", "size": half, "sha256": sha(data[:half]), "url": srv.url("/m/model.bin.part001")},
                              {"name": "model.bin.part002", "size": len(data) - half, "sha256": sha(data[half:]), "url": srv.url("/m/model.bin.part002")}]
        files.append(entry)
    return {"version": version, "windows": {"status": status, "version": version, "payload": {
        "setup": {"name": "WhisperMedical-Setup-Windows-x64.exe", "size": len(setup), "sha256": sha(setup), "url": srv.url("/setup.exe")}, "model": {"files": files}}}}


def serve(w, **kw):
    manifest = make_manifest(None, w, **{k: v for k, v in kw.items() if k in ("status", "version")}) if False else None
    srv = Server({})
    manifest = make_manifest(srv, w, **{k: v for k, v in kw.items() if k in ("status", "version")})
    setup_served = kw.get("setup_served", w["setup"])
    model_bin = w["model"]["model.bin"]
    half = len(model_bin) // 2
    srv.files.update({"/manifest.json": json.dumps(manifest).encode(), "/setup.exe": setup_served, "/m/model.bin.part001": model_bin[:half],
                      "/m/model.bin.part002": model_bin[half:]})
    for name, data in w["model"].items():
        if name != "model.bin":
            srv.files["/m/" + name] = data
    return srv


def run(w, srv, tmp_path):
    marker = tmp_path / "setup_ran.txt"
    env = dict(os.environ, WM_FAKE_MARKER=str(marker))
    done = subprocess.run([str(w["exe"]), "--console", "--no-launch", "--manifest-url", srv.url("/manifest.json"), "--cache-dir", str(tmp_path / "cache"),
                           "--model-dir", str(tmp_path / "model"), "--setup-args", "/SILENT /SUPPRESSMSGBOXES"], capture_output=True, text=True, env=env, timeout=180)
    return done, marker


def test_the_whole_path_downloads_verifies_places_the_model_runs_the_installer_and_cleans_up(world, tmp_path):
    srv = serve(world)
    try:
        done, marker = run(world, srv, tmp_path)
    finally:
        srv.close()
    assert done.returncode == 0, done.stdout + done.stderr
    assert marker.read_text(encoding="utf-8") == "/SILENT /SUPPRESSMSGBOXES"            # the real installer was started, with the silent switches
    for name, data in world["model"].items():
        assert (tmp_path / "model" / name).read_bytes() == data                            # model.bin was joined from its two pieces
    assert not (tmp_path / "cache").exists()                                              # temporary files are gone
    assert not list((tmp_path / "model").glob("*.partial"))


def test_cut_connections_resume_where_they_stopped(world, tmp_path):
    srv = serve(world)
    srv.cut = {"/setup.exe": 2, "/m/model.bin.part001": 2, "/m/model.bin.part002": 1}
    try:
        done, marker = run(world, srv, tmp_path)
    finally:
        srv.close()
    assert done.returncode == 0, done.stdout + done.stderr
    assert (tmp_path / "model" / "model.bin").read_bytes() == world["model"]["model.bin"] and marker.exists()
    resumed = [r for r in srv.requests if r[1] > 0]
    assert resumed, srv.requests                                                          # later requests started inside the file (HTTP Range)


def test_an_existing_complete_model_is_not_downloaded_again(world, tmp_path):
    (tmp_path / "model").mkdir()
    for name, data in world["model"].items():
        (tmp_path / "model" / name).write_bytes(data)
    srv = serve(world)
    try:
        done, marker = run(world, srv, tmp_path)
    finally:
        srv.close()
    assert done.returncode == 0 and marker.exists(), done.stdout + done.stderr
    assert not [r for r in srv.requests if r[0].startswith("/m/")], srv.requests


def test_a_tampered_installer_is_refused_and_never_started(world, tmp_path):
    bad = bytearray(world["setup"])
    bad[-1] ^= 0xFF
    srv = serve(world, setup_served=bytes(bad))
    try:
        done, marker = run(world, srv, tmp_path)
    finally:
        srv.close()
    assert done.returncode != 0 and "checksum" in done.stdout.lower(), done.stdout + done.stderr
    assert not marker.exists()                                                            # nothing was executed before the checksum succeeded


def test_a_corrupted_model_piece_is_refused(world, tmp_path):
    srv = serve(world)
    srv.files["/m/model.bin.part002"] = srv.files["/m/model.bin.part002"][:-1] + b"\x00"
    try:
        done, marker = run(world, srv, tmp_path)
    finally:
        srv.close()
    assert done.returncode != 0 and "checksum" in done.stdout.lower(), done.stdout + done.stderr
    assert not marker.exists() and not (tmp_path / "model" / "model.bin").exists()


@pytest.mark.parametrize("kw, expected", [({"status": "pending"}, "not available yet"), ({"version": "1.0.0"}, "out of date")])
def test_a_manifest_that_is_not_ready_or_not_for_this_installer_stops_everything(world, tmp_path, kw, expected):
    srv = serve(world, **kw)
    try:
        done, marker = run(world, srv, tmp_path)
    finally:
        srv.close()
    assert done.returncode != 0 and expected in done.stdout.lower(), done.stdout + done.stderr
    assert not marker.exists() and not srv.requests[1:]                                    # only the manifest was fetched


def test_a_manifest_whose_installer_hash_differs_from_the_pinned_one_is_refused(world, tmp_path):
    other = world["setup"] + b"x"
    srv = serve(world, setup_served=other)
    srv.files["/manifest.json"] = json.dumps(make_manifest(srv, world, setup_override=other)).encode()
    try:
        done, marker = run(world, srv, tmp_path)
    finally:
        srv.close()
    assert done.returncode != 0 and "out of date" in done.stdout.lower() and not marker.exists(), done.stdout + done.stderr


def test_the_release_build_does_not_accept_plain_http_or_overrides(tmp_path):
    """The shipped program has no test switches: build it and ask for a loopback http manifest."""
    pins = {"version": "9.9.9", "setup_name": "x.exe", "setup_sha256": "0" * 64, "setup_size": 1, "model": {n: {"sha256": "0" * 64} for n in MODEL_NAMES}}
    (tmp_path / "p.json").write_text(json.dumps(pins), encoding="utf-8")
    exe = tmp_path / "release.exe"
    done = subprocess.run([sys.executable, str(ROOT / "bootstrap" / "windows" / "build.py"), "--pins", str(tmp_path / "p.json"), "--out", str(exe)], capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr
    srv = Server({"/manifest.json": b"{}"})
    try:
        run_ = subprocess.run([str(exe), "--console", "--manifest-url", srv.url("/manifest.json")], capture_output=True, text=True, timeout=120)
    finally:
        srv.close()
    assert not srv.requests, "the shipped installer must not talk to a local http server"
    assert "reach the download server" in run_.stdout.lower() or "not available" in run_.stdout.lower() or run_.returncode != 0
