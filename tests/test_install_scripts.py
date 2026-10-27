"""The one-command installers and the files around them: the documented commands are the tested commands, nothing is a placeholder, the Windows script
downloads / verifies / runs / propagates the exit code / refuses, the manifest rules hold. The Windows script runs against a local server and a FAKE installer
program; the Mac engine has its own macOS-only tests (test_mac_installer.py)."""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import sitetool  # noqa: E402

PS1 = ROOT / "install" / "install-windows.ps1"
SH = ROOT / "install" / "install-macos.sh"
COMMAND = ROOT / "install" / "Install MELETRA.command"
BASE = "https://twonezerotwo-hue.github.io/whispermedical-downloads"
WINDOWS_COMMAND = ("$f = \"$env:TEMP\\meletra-install.ps1\"; iwr -UseBasicParsing '" + BASE + "/install/install-windows.ps1' -OutFile $f; "
                   "powershell -NoProfile -ExecutionPolicy Bypass -File $f")
MAC_COMMAND = "curl -fsSL --proto '=https' '" + BASE + "/install/install-macos.sh' -o /tmp/meletra-install.sh && bash /tmp/meletra-install.sh"
windows_only = pytest.mark.skipif(sys.platform != "win32", reason="runs Windows PowerShell")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# --------------------------------------------------------------------------------------------------------- documented commands == tested commands
def test_the_readme_and_the_download_page_show_exactly_the_commands_the_workflow_tests():
    readme, page = read(ROOT / "README.md"), read(ROOT / "index.html")
    assert WINDOWS_COMMAND in readme and MAC_COMMAND in readme
    assert WINDOWS_COMMAND in page
    assert "mac-apple-silicon-40313169466" in page and "mac-intel-40470251885" in page
    workflow = read(ROOT / ".github" / "workflows" / "test-install-scripts.yml")
    assert WINDOWS_COMMAND in workflow and "install-windows.ps1" in workflow
    for url in re.findall(r"https://twonezerotwo-hue\.github\.io/whispermedical-downloads/(install/[^'\"\s]+)", WINDOWS_COMMAND + " " + MAC_COMMAND):
        assert (ROOT / url).is_file(), url


def test_no_placeholder_is_left_in_the_install_instructions_or_scripts():
    pattern = re.compile(r"<[A-Z][A-Z _-]{3,}>|(?i:\bTODO\b|\bPLACEHOLDER\b|example\.com|<EXACT)")
    for path in (ROOT / "README.md", ROOT / "index.html", PS1, SH, COMMAND, ROOT / "downloads" / "install-windows.html",
                 ROOT / "downloads" / "install-mac-intel.html", ROOT / "downloads" / "install-mac-apple-silicon.html"):
        assert not pattern.search(read(path)), path.name


def test_the_scripts_trust_only_official_https_addresses_and_ask_nobody_for_a_login():
    ps, sh, cmd = read(PS1), read(SH), read(COMMAND)
    for text in (ps, sh, cmd):
        assert "https://twonezerotwo-hue.github.io/whispermedical-downloads" in text
        assert not re.search(r"(?i)\b(GH_TOKEN|GITHUB_TOKEN|Authorization|Bearer|password|ghp_)\b", text)
    assert "AllowedHostSuffixes" in ps and "github.com" in ps and ".githubusercontent.com" in ps
    assert "Get-FileHash" in ps and "SHA256" in ps and "not run" in ps.lower()                          # the checksum is checked before anything is run
    assert "--proto =https" in sh and "shasum -a 256" in sh and "x86_64" in sh and "Intel Macs" in sh and "hdiutil detach" in sh


def test_the_double_click_file_holds_no_installation_logic_of_its_own():
    cmd = read(COMMAND)
    assert "install-macos.sh" in cmd and "curl" in cmd and "bash" in cmd
    for forbidden in ("hdiutil", "shasum", "ditto", "/Applications"):
        assert forbidden not in cmd
    assert os.name == "nt" or os.access(COMMAND, os.X_OK)
    index = subprocess.run(["git", "ls-files", "-s", "install"], cwd=ROOT, capture_output=True, text=True).stdout
    if index:
        assert re.search(r"^100755 \S+ 0\tinstall/Install MELETRA\.command$", index, re.M) and re.search(r"^100755 \S+ 0\tinstall/install-macos\.sh$", index, re.M)


def test_the_mac_scripts_are_valid_bash():
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("no bash")
    for path in (SH, COMMAND, ROOT / "bootstrap" / "mac-intel" / "build.sh"):
        assert subprocess.run([bash, "-n", str(path)], capture_output=True, text=True).returncode == 0, path.name


# --------------------------------------------------------------------------------------------------------- the manifest rules
def good_manifest():
    sha = "a" * 64
    boot = {"name": "b.exe", "url": BASE.replace("twonezerotwo-hue.github.io/whispermedical-downloads", "github.com/o/r/releases/download/t") + "/b.exe", "size": 5, "sha256": sha}
    win = {"status": "ready", "version": "4.0.0", "architecture": "x64", "download_bytes": 9, "bootstrapper": boot, "verification": {"passed": True},
           "payload": {"setup": {"name": "s.exe", "size": 3, "sha256": sha, "url": boot["url"]}, "model": {"files": [{"name": "m", "size": 1, "sha256": sha, "url": boot["url"]}]}}}
    mac = {"status": "uploaded", "version": "3.1.0", "architecture": "x86_64", "download_bytes": 9, "bootstrapper": boot,
           "payload": {"dmg": {"name": "d", "size": 3, "sha256": sha, "parts": [{"name": "p1", "size": 3, "sha256": sha, "url": boot["url"]}]}}}
    return {"product_version": "4.0.0", "windows": win, "mac_intel": mac}


def test_the_live_manifest_follows_the_rules():
    data = sitetool.load()
    assert sitetool.problems(data) == []
    version = tuple(int(part) for part in data["product_version"].split("."))
    assert data["windows"]["version"] == data["product_version"]                       # Windows is the current product version (the Mac build may be older and is then never offered)
    assert (data.get("product") == "MELETRA") == (version >= (4, 1, 0))                 # the name MELETRA starts with 4.1.0
    for key in ("windows", "mac_intel"):
        assert re.match(r"\d{4}-\d{2}-\d{2}$", data[key]["release_date"])


def test_the_manifest_rules_catch_what_would_mislead_an_installer():
    assert sitetool.problems(good_manifest()) == []
    cases = []
    m = good_manifest(); m["windows"]["bootstrapper"]["url"] = "http://github.com/x"; cases.append((m, "https github address"))
    m = good_manifest(); m["windows"]["payload"]["setup"]["sha256"] = "zz"; cases.append((m, "SHA-256 or size missing"))
    m = good_manifest(); m["windows"]["verification"] = {}; cases.append((m, "without a passed end-to-end"))
    m = good_manifest(); m["mac_intel"]["status"] = "ready"; m["mac_intel"]["verification"] = {"passed": True}; cases.append((m, "not the product version"))
    m = good_manifest(); m["windows"]["payload"]["setup"]["url"] = "https://evil.example.org/s.exe"; cases.append((m, "is not an https github address"))
    m = good_manifest(); m["windows"]["note"] = "<URL HERE>"; cases.append((m, "placeholder"))
    m = good_manifest(); del m["product_version"]; cases.append((m, "product_version"))
    m = good_manifest(); m["windows"]["status"] = "done"; cases.append((m, "status"))
    for manifest, expected in cases:
        assert any(expected in p for p in sitetool.problems(manifest)), (expected, sitetool.problems(manifest))


# --------------------------------------------------------------------------------------------------------- the Windows script against a local server
FAKE_EXE = """using System; using System.IO;
class P { static int Main(string[] a) { File.WriteAllText(Path.Combine(Environment.GetEnvironmentVariable("FAKE_LOG"), "args.txt"), string.Join("|", a));
  string e = Environment.GetEnvironmentVariable("FAKE_EXIT"); return e == null ? 0 : int.Parse(e); } }
"""


@pytest.fixture(scope="module")
def fake_installer(tmp_path_factory):
    csc = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
    if sys.platform != "win32" or not csc.is_file():
        pytest.skip("no C# compiler")
    folder = tmp_path_factory.mktemp("fake")
    (folder / "p.cs").write_text(FAKE_EXE, encoding="utf-8")
    done = subprocess.run([str(csc), "/nologo", "/out:" + str(folder / "MELETRA-Installer-Windows.exe"), str(folder / "p.cs")], capture_output=True, text=True)
    assert done.returncode == 0, done.stdout
    return (folder / "MELETRA-Installer-Windows.exe").read_bytes()


class Server:
    def __init__(self, files):
        self.files, self.hits = files, []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                body = outer.files.get(self.path.split("?")[0])
                outer.hits.append(self.path)
                if body is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_port
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"

    def close(self):
        self.httpd.shutdown()


def serve(exe: bytes, tmp_path, status="ready", product="9.9.9", version="9.9.9", verified=True, served=None):
    srv = Server({})
    name = "MELETRA-Installer-Windows.exe"
    srv.files["/" + name] = served if served is not None else exe
    entry = {"status": status, "version": version, "download_bytes": 4_000_000_000,
             "bootstrapper": {"name": name, "url": srv.url("/" + name), "size": len(exe), "sha256": hashlib.sha256(exe).hexdigest()}}
    if verified:
        entry["verification"] = {"passed": True}
    manifest = {"product_version": product, "windows": entry}
    srv.files["/m.json"] = json.dumps(manifest).encode()
    return srv


def run_script(srv, tmp_path, *extra, env_extra=None, manifest="/m.json"):
    temp, log = tmp_path / "temp", tmp_path / "log"
    temp.mkdir(exist_ok=True)
    log.mkdir(exist_ok=True)
    env = dict(os.environ, TEMP=str(temp), TMP=str(temp), FAKE_LOG=str(log), MELETRA_TEST="1")
    env.update(env_extra or {})
    done = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(PS1), "-ManifestUrl", srv.url(manifest), *extra],
                          capture_output=True, text=True, env=env, timeout=180)
    args = (log / "args.txt").read_text(encoding="utf-8") if (log / "args.txt").exists() else None
    return done, args, temp


@windows_only
def test_the_script_is_valid_powershell():
    parse = ("$e=$null;$t=$null;[void][System.Management.Automation.Language.Parser]::ParseFile('" + str(PS1) + "',[ref]$t,[ref]$e);if($e.Count){$e|%{$_.Message};exit 1}")
    done = subprocess.run(["powershell.exe", "-NoProfile", "-Command", parse], capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr


@windows_only
def test_it_downloads_checks_runs_the_installer_in_text_mode_and_cleans_up(fake_installer, tmp_path):
    srv = serve(fake_installer, tmp_path)
    try:
        done, args, temp = run_script(srv, tmp_path)
        done2, args2, _ = run_script(srv, tmp_path, env_extra={"MELETRA_NO_LAUNCH": "1"})
        done3, args3, _ = run_script(srv, tmp_path, "-Gui", "-NoLaunch")
    finally:
        srv.close()
    assert done.returncode == 0 and args == "--console", done.stdout + done.stderr
    assert "matches its published SHA-256" in done.stdout and "MELETRA 9.9.9 for Windows" in done.stdout and "is installed" in done.stdout
    assert args2 == "--console|--no-launch" and args3 == "--unattended|--no-launch"
    assert not (temp / "MELETRAInstall").exists()                                      # the downloaded installer program is removed


@windows_only
def test_the_exit_code_of_the_installer_is_the_exit_code_of_the_command(fake_installer, tmp_path):
    srv = serve(fake_installer, tmp_path)
    try:
        done, args, _ = run_script(srv, tmp_path, env_extra={"FAKE_EXIT": "7"})
    finally:
        srv.close()
    assert done.returncode == 7 and "ended with code 7" in done.stdout


@windows_only
def test_a_download_that_does_not_match_the_manifest_is_deleted_and_never_run(fake_installer, tmp_path):
    srv = serve(fake_installer, tmp_path, served=fake_installer[:-1] + bytes([fake_installer[-1] ^ 0xFF]))
    try:
        done, args, temp = run_script(srv, tmp_path)
    finally:
        srv.close()
    assert done.returncode == 4 and args is None and "NOT run" in done.stdout + done.stderr
    assert not (temp / "MELETRAInstall" / "MELETRA-Installer-Windows.exe").exists()


@windows_only
@pytest.mark.parametrize("kw, allow, code, text", [
    ({"status": "uploaded"}, False, 3, "not announced"),                       # verified but the owner has not announced it
    ({"status": "ready", "product": "10.0.0"}, False, 3, "10.0.0 for windows is not available yet"),
    ({"status": "uploaded", "verified": False}, True, 3, "not passed its end-to-end verification"),
    ({"status": "pending"}, False, 3, "not announced"),
])
def test_only_an_announced_current_release_is_installed(fake_installer, tmp_path, kw, allow, code, text):
    srv = serve(fake_installer, tmp_path, **kw)
    try:
        done, args, _ = run_script(srv, tmp_path, env_extra={"MELETRA_ALLOW_UNANNOUNCED": "1"} if allow else None)
    finally:
        srv.close()
    assert done.returncode == code and text in (done.stdout + done.stderr).lower() and args is None
    assert not [h for h in srv.hits if h.endswith(".exe")]                                    # nothing was even downloaded


@windows_only
def test_the_test_switch_installs_a_verified_but_unannounced_release(fake_installer, tmp_path):
    srv = serve(fake_installer, tmp_path, status="uploaded")
    try:
        done, args, _ = run_script(srv, tmp_path, "-AllowUnannounced")
    finally:
        srv.close()
    assert done.returncode == 0 and args == "--console", done.stdout + done.stderr


@windows_only
def test_an_address_that_is_not_official_is_refused_without_a_request(fake_installer, tmp_path):
    srv = serve(fake_installer, tmp_path)
    try:
        done, args, _ = run_script(srv, tmp_path, env_extra={"MELETRA_TEST": "0"})                # outside the test mode http://127.0.0.1 is not an official address
    finally:
        srv.close()
    assert done.returncode == 4 and "secure official address" in done.stdout + done.stderr and not srv.hits


# --------------------------------------------------------------------------------------------------------- 4.1.0: the sharing notice before anything is installed
NOTICE = "Nothing is shared unless you switch it on. Sharing completed transcript text with MELETRA to improve transcription quality is OFF by default; you can turn it on in Settings -> Privacy & Data."


@windows_only
@pytest.mark.parametrize("version, shown", [("4.0.0", False), ("3.1.0", False), ("4.1.0", True), ("9.9.9", True)])
def test_the_one_command_installer_states_that_sharing_is_off_by_default_from_4_1_0_on(fake_installer, tmp_path, version, shown):
    srv = serve(fake_installer, tmp_path, product=version, version=version)
    try:
        done, args, _ = run_script(srv, tmp_path)
    finally:
        srv.close()
    assert done.returncode == 0 and (NOTICE in done.stdout) == shown, done.stdout + done.stderr
    assert ("never sent" in done.stdout) == shown


def test_the_mac_engine_and_the_bootstrapper_carry_the_same_notice():
    assert NOTICE in read(SH) and NOTICE in read(ROOT / "install" / "install-windows.ps1")
    cs = read(ROOT / "bootstrap" / "windows" / "MELETRAInstaller.cs")
    assert NOTICE in cs and "new Version(4, 1, 0)" in cs and "[notice] " in cs


def test_the_download_page_is_branded_and_the_privacy_text_is_true_for_every_version():
    for name in ("favicon.ico", "favicon-32.png", "favicon-192.png", "apple-touch-icon.png", "meletra-logo.png", "meletra-symbol.png", "meletra.ico", "meletra-icon-64.png"):
        assert (ROOT / "assets" / name).stat().st_size > 400, name
    page, readme = read(ROOT / "index.html"), read(ROOT / "README.md")
    assert 'rel="icon" href="assets/favicon.ico"' in page and 'src="assets/meletra-symbol.png"' in page and re.search(r"<h1>(?:<[^>]+>)*MELETRA(?:<[^>]+>)*</h1>", page) is not None
    assert "Medical Learning &amp; Transcription" in page and "Download MELETRA for" in page and "Installation instructions" in page
    assert "Nothing is shared unless you switch it on" in readme and "off by default" in readme and "Settings → Privacy & Data" in readme
    assert "shared with the developer by default" not in readme and "shared with the developer by default" not in page
    assert "stay on your computer. The installer" not in readme                                   # the old unqualified claim is gone
    for text in (page, readme):
        assert "MedLecture" not in text and "MEDLECTURE" not in text


def test_the_public_audit_accepts_only_genuine_small_brand_images_under_assets(tmp_path):
    import audit_public

    png = bytes.fromhex("89504e470d0a1a0a") + b"\x00" * 64
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "logo.png").write_bytes(png)
    (tmp_path / "assets" / "fake.png").write_bytes(b"MZ" + b"\x00" * 64)                 # an executable named like an image
    (tmp_path / "logo.png").write_bytes(png)                                              # an image outside assets/
    (tmp_path / "assets" / "big.png").write_bytes(png + b"\x00" * 700_000)
    found = " ".join(audit_public.scan(tmp_path))
    assert "assets/logo.png" not in found and "assets/fake.png: only" in found and "assets/big.png: only" in found and " logo.png: binary file" in " " + found.replace("assets/", "").replace("only small genuine PNG / ICO images may live in", "")
