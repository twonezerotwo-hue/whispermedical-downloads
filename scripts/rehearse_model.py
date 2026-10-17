"""Rehearsal helper (see .github/workflows/rehearse-model.yml): the test build of the Windows installer program downloads the real, public model files; the Setup
program is replaced by a stand-in that only writes a marker file."""

import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
work = Path(os.environ.get("RUNNER_TEMP", ROOT / "_rehearsal")) / "rehearse"
work.mkdir(parents=True, exist_ok=True)
CSC = Path(os.environ["WINDIR"]) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
layout = json.loads((ROOT / "scripts" / "model_parts.json").read_text(encoding="utf-8"))

(work / "fake.cs").write_text('using System; using System.IO; class P { static int Main(string[] a) { File.WriteAllText(Environment.GetEnvironmentVariable("WM_FAKE_MARKER"), string.Join(" ", a)); return 0; } }')
subprocess.run([str(CSC), "/nologo", "/target:exe", f"/out:{work / 'setup.exe'}", str(work / "fake.cs")], check=True)
setup = (work / "setup.exe").read_bytes()
sha = hashlib.sha256(setup).hexdigest()
pins = {"version": "9.9.9", "setup_name": "MELETRA-Setup-Windows-x64.exe", "setup_sha256": sha, "setup_size": len(setup),
        "model": {f["name"]: {"sha256": f["sha256"]} for f in layout["files"]}}
(work / "pins.json").write_text(json.dumps(pins), encoding="utf-8")
subprocess.run([sys.executable, str(ROOT / "bootstrap" / "windows" / "build.py"), "--test", "--pins", str(work / "pins.json"), "--out", str(work / "boot_test.exe")], check=True)

handler = type("H", (SimpleHTTPRequestHandler,), {"log_message": lambda *a: None})
os.chdir(work)
srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{srv.server_port}"
manifest = {"version": "9.9.9", "windows": {"status": "uploaded", "version": "9.9.9", "payload": {
    "setup": {"name": "MELETRA-Setup-Windows-x64.exe", "size": len(setup), "sha256": sha, "url": base + "/setup.exe"},
    "model": {"files": layout["files"]}}}}
(work / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

marker = work / "marker.txt"
env = dict(os.environ, WM_FAKE_MARKER=str(marker))
started = time.time()
done = subprocess.run([str(work / "boot_test.exe"), "--console", "--no-launch", "--manifest-url", base + "/manifest.json", "--cache-dir", str(work / "cache"),
                       "--model-dir", str(work / "model"), "--setup-args", "/SILENT"], env=env, capture_output=True, text=True, timeout=3000)
print(done.stdout[-3000:])
print(done.stderr[-1000:])
print(f"exit {done.returncode} after {time.time() - started:.0f} s")
assert done.returncode == 0, "the installer program failed"
for f in layout["files"]:
    path = work / "model" / f["name"]
    h = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(16 << 20):
            h.update(block)
    assert path.stat().st_size == f["size"] and h.hexdigest() == f["sha256"], f"{f['name']} is wrong"
    print("OK", f["name"], f["size"])
assert marker.read_text() == "/SILENT"
assert not (work / "cache").exists(), "temporary files were left behind"
print("REHEARSAL_OK")
