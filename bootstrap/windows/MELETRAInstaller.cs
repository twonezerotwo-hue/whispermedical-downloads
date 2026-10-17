// MELETRA-Installer-Windows.exe - the small program a Windows user downloads and double-clicks.
//
// It downloads the real installer and the speech model (Whisper Large-v3) from the official public release location, checks every SHA-256,
// puts the model where the program finds it, starts the real installer (Windows asks for administrator approval - nothing is bypassed) and starts the program.
//
// Rules this file keeps:
//   * HTTPS only, and only to github.com / *.githubusercontent.com / *.github.io (redirects are followed by hand and checked);
//   * what is installed must match the SHA-256 values compiled into this file (Pins.cs) AND the public release manifest; any mismatch stops everything;
//   * nothing is run before the final installer's SHA-256 has been verified;
//   * downloads resume after a broken connection (HTTP Range) and failed pieces are retried; partial files are kept for the next try.
// Compiled with the C# compiler that ships with Windows (no SDK needed): see build.py. Source is public so that anyone can read what the installer does.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Win32;

namespace MELETRA
{
    // ------------------------------------------------------------------------------------------------------------------ plumbing
    interface IReporter
    {
        void Step(string text);
        void Progress(long done, long total);
        void Log(string text);
    }

    class InstallerException : Exception
    {
        public bool Retryable;
        public InstallerException(string message, bool retryable) : base(message) { Retryable = retryable; }
    }

    class Asset
    {
        public string Name;
        public long Size;
        public string Sha256;
        public string Url;
        public List<Asset> Parts = new List<Asset>();
    }

    static class Net
    {
        public static bool AllowLoopbackHttp = false;     // only the test build turns this on

        public static bool HostAllowed(Uri u)
        {
            if (AllowLoopbackHttp && u.Scheme == Uri.UriSchemeHttp && (u.Host == "127.0.0.1" || u.Host == "localhost")) return true;
            if (u.Scheme != Uri.UriSchemeHttps) return false;
            string h = u.Host.ToLowerInvariant();
            return h == "github.com" || h.EndsWith(".github.com") || h.EndsWith(".githubusercontent.com") || h == "githubusercontent.com" || h.EndsWith(".github.io");
        }

        // Opens url with an optional start offset; follows redirects by hand (each hop must be an allowed host). Returns the response; caller disposes.
        public static HttpWebResponse Open(string url, long from, int timeoutMs)
        {
            Uri uri = new Uri(url);
            for (int hop = 0; hop < 6; hop++)
            {
                if (!HostAllowed(uri)) throw new InstallerException("The download address is not an official one: " + uri.Host, false);
                HttpWebRequest req = (HttpWebRequest)WebRequest.Create(uri);
                req.AllowAutoRedirect = false;
                req.UserAgent = "MELETRA-Installer/" + Pins.Version;
                req.Timeout = timeoutMs;
                req.ReadWriteTimeout = timeoutMs;
                req.KeepAlive = false;
                if (from > 0) req.AddRange(from);
                HttpWebResponse resp;
                try { resp = (HttpWebResponse)req.GetResponse(); }
                catch (WebException ex)
                {
                    resp = ex.Response as HttpWebResponse;
                    if (resp == null) throw;
                }
                int code = (int)resp.StatusCode;
                if (code >= 300 && code < 400)
                {
                    string loc = resp.Headers["Location"];
                    resp.Close();
                    if (string.IsNullOrEmpty(loc)) throw new InstallerException("A redirect had no target.", true);
                    uri = new Uri(uri, loc);
                    continue;
                }
                if (code == 416) { resp.Close(); throw new InstallerException("range", true); }
                if (code < 200 || code >= 300) { resp.Close(); throw new InstallerException("The server answered " + code + " for " + uri.Host + ".", code >= 500 || code == 429 || code == 403); }
                return resp;
            }
            throw new InstallerException("Too many redirects.", true);
        }

        public static string Sha256File(string path, Action<long> progress)
        {
            using (SHA256 sha = SHA256.Create())
            using (FileStream f = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read, 1 << 20))
            {
                byte[] buf = new byte[1 << 20];
                int n;
                while ((n = f.Read(buf, 0, buf.Length)) > 0)
                {
                    sha.TransformBlock(buf, 0, n, null, 0);
                    if (progress != null) progress(n);
                }
                sha.TransformFinalBlock(buf, 0, 0);
                return Hex(sha.Hash);
            }
        }

        public static string Hex(byte[] b)
        {
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < b.Length; i++) sb.Append(b[i].ToString("x2"));
            return sb.ToString();
        }
    }

    // ------------------------------------------------------------------------------------------------------------------ the work
    class Engine
    {
        readonly IReporter ui;
        readonly string cacheDir, modelDir, setupArgs;
        readonly bool launch;
        long total, done;
        volatile bool cancelled;
        public string ManifestUrl = Pins.ManifestUrl;

        public Engine(IReporter ui, string cacheDir, string modelDir, string setupArgs, bool launch)
        {
            this.ui = ui; this.cacheDir = cacheDir; this.modelDir = modelDir; this.setupArgs = setupArgs; this.launch = launch;
        }

        public void Cancel() { cancelled = true; }
        void Check() { if (cancelled) throw new InstallerException("Cancelled. Your progress is kept; run the installer again to continue.", false); }
        void Add(long n) { done += n; ui.Progress(done, total); }

        static string Str(Dictionary<string, object> d, string k)
        {
            object o; return d.TryGetValue(k, out o) && o != null ? o.ToString() : "";
        }
        static long Num(Dictionary<string, object> d, string k)
        {
            object o; return d.TryGetValue(k, out o) && o != null ? Convert.ToInt64(o) : 0;
        }
        static Dictionary<string, object> Obj(Dictionary<string, object> d, string k)
        {
            object o; return d.TryGetValue(k, out o) ? o as Dictionary<string, object> : null;
        }

        static Asset ReadAsset(Dictionary<string, object> d)
        {
            Asset a = new Asset { Name = Str(d, "name"), Size = Num(d, "size"), Sha256 = Str(d, "sha256").ToLowerInvariant(), Url = Str(d, "url") };
            object parts;
            if (d.TryGetValue("parts", out parts) && parts is System.Collections.IEnumerable)
                foreach (object p in (System.Collections.IEnumerable)parts) a.Parts.Add(ReadAsset((Dictionary<string, object>)p));
            return a;
        }

        public void Run()
        {
            Directory.CreateDirectory(cacheDir);
            // 1. the public manifest
            ui.Step("Checking for the latest version ...");
            string json = FetchText(ManifestUrl);
            Dictionary<string, object> m = new JavaScriptSerializer { MaxJsonLength = 1 << 24 }.Deserialize<Dictionary<string, object>>(json);
            Dictionary<string, object> w = Obj(m, "windows");
            if (w == null || (Str(w, "status") != "ready" && Str(w, "status") != "uploaded"))
                throw new InstallerException("This download is not available yet. Please try again later.", false);
            Dictionary<string, object> payload = Obj(w, "payload");
            Asset setup = ReadAsset(Obj(payload, "setup"));
            List<Asset> model = new List<Asset>();
            foreach (object o in (System.Collections.IEnumerable)Obj(payload, "model")["files"]) model.Add(ReadAsset((Dictionary<string, object>)o));
            // what the manifest says must be what this installer was built for
            if (Str(w, "version") != Pins.Version || setup.Sha256 != Pins.SetupSha256 || setup.Size != Pins.SetupSize)
                throw new InstallerException("This installer is out of date. Please download the newest MELETRA installer from the download page.", false);
            foreach (Asset f in model)
            {
                string pinned = Pins.ModelSha(f.Name);
                if (pinned == null || pinned != f.Sha256) throw new InstallerException("The speech model list does not match this installer (" + f.Name + ").", false);
            }

            // 2. what is already there
            ui.Step("Checking your computer ...");
            Directory.CreateDirectory(modelDir);
            List<Asset> missingModel = new List<Asset>();
            foreach (Asset f in model)
            {
                string target = Path.Combine(modelDir, f.Name);
                bool good = File.Exists(target) && new FileInfo(target).Length == f.Size;
                if (good && f.Size > 50000000) { ui.Step("Checking the speech model that is already installed ..."); good = Net.Sha256File(target, null) == f.Sha256; }
                else if (good) good = Net.Sha256File(target, null) == f.Sha256;
                if (!good) missingModel.Add(f);
                Check();
            }
            long need = 0;
            foreach (Asset f in missingModel) need += f.Size;
            need += setup.Size;
            total = need;
            long free = FreeBytes(cacheDir), freeModel = FreeBytes(modelDir);
            long installGuess = 3500000000L, margin = 1500000000L;
            if (free < need + margin || (SameDrive(cacheDir, modelDir) ? false : freeModel < need) || FreeBytes(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles)) < installGuess)
                throw new InstallerException(string.Format("Not enough free disk space. About {0:0.0} GB are needed during the installation; {1:0.0} GB are free.", (need + installGuess + margin) / 1e9, free / 1e9), false);

            // 3. download and check everything
            string setupPath = Path.Combine(cacheDir, Pins.SetupName);
            ui.Step("Downloading MELETRA ...");
            if (!(File.Exists(setupPath) && new FileInfo(setupPath).Length == setup.Size && Net.Sha256File(setupPath, null) == Pins.SetupSha256))
                Fetch(setup, setupPath, Pins.SetupSha256);
            else Add(setup.Size);
            foreach (Asset f in missingModel)
            {
                ui.Step("Downloading the speech model (Whisper Large-v3) ...");
                string partial = Path.Combine(modelDir, f.Name + ".partial");
                Fetch(f, partial, f.Sha256);
                string target = Path.Combine(modelDir, f.Name);
                if (File.Exists(target)) File.Delete(target);
                File.Move(partial, target);
            }
            Check();

            // 4. the real installer, only after its checksum is verified (Fetch verified it)
            ui.Step("Installing MELETRA (Windows may ask for your permission) ...");
            string exeDir = RunSetup(setupPath);

            // 5. clean up and start
            ui.Step("Finishing ...");
            try { Directory.Delete(cacheDir, true); } catch (Exception) { }
            try { string old = Path.Combine(Path.GetDirectoryName(cacheDir), "..", "WhisperMedicalInstaller", "cache"); if (Directory.Exists(old)) Directory.Delete(old, true); } catch (Exception) { }          // leftovers of the earlier installer
            if (launch && exeDir != null)
            {
                string exe = Path.Combine(exeDir, "MELETRA.exe");
                if (File.Exists(exe)) Process.Start(new ProcessStartInfo(exe) { UseShellExecute = true, WorkingDirectory = exeDir });
            }
            ui.Step("MELETRA is installed.");
        }

        string RunSetup(string setupPath)
        {
            ProcessStartInfo psi = new ProcessStartInfo(setupPath, setupArgs) { UseShellExecute = true };
            Process p;
            try { p = Process.Start(psi); }
            catch (System.ComponentModel.Win32Exception ex)
            {
                throw new InstallerException(ex.NativeErrorCode == 1223 ? "The installation was cancelled (administrator permission was not given)." : "The installer could not be started: " + ex.Message, true);
            }
            p.WaitForExit();
            if (p.ExitCode != 0) throw new InstallerException("The installer ended with code " + p.ExitCode + ". Nothing else was changed; you can try again.", true);
            return InstalledFolder();
        }

        static string InstalledFolder()
        {
            string[] keys = { @"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{6F0B7C52-3A1E-4E7D-9C54-8D2A7B1E4F60}_is1" };
            foreach (RegistryHive hive in new RegistryHive[] { RegistryHive.LocalMachine, RegistryHive.CurrentUser })
                foreach (string k in keys)
                    using (RegistryKey b = RegistryKey.OpenBaseKey(hive, RegistryView.Registry64))
                    using (RegistryKey key = b.OpenSubKey(k))
                        if (key != null && key.GetValue("InstallLocation") != null) return key.GetValue("InstallLocation").ToString().TrimEnd('\\');
            string fallback = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "MELETRA");
            return Directory.Exists(fallback) ? fallback : null;
        }

        static long FreeBytes(string path)
        {
            try { return new DriveInfo(Path.GetPathRoot(Path.GetFullPath(path))).AvailableFreeSpace; } catch (Exception) { return long.MaxValue; }
        }
        static bool SameDrive(string a, string b)
        {
            return string.Equals(Path.GetPathRoot(Path.GetFullPath(a)), Path.GetPathRoot(Path.GetFullPath(b)), StringComparison.OrdinalIgnoreCase);
        }

        string FetchText(string url)
        {
            for (int attempt = 1; ; attempt++)
            {
                try
                {
                    using (HttpWebResponse r = Net.Open(url, 0, 30000))
                    using (StreamReader sr = new StreamReader(r.GetResponseStream(), Encoding.UTF8)) return sr.ReadToEnd();
                }
                catch (Exception ex)
                {
                    if (attempt >= 6) throw new InstallerException("Could not reach the download server (" + ex.Message + "). Check your internet connection and try again.", true);
                    Check(); Thread.Sleep(1500 * attempt);
                }
            }
        }

        // Downloads an asset (whole file or its parts) into dest, resuming, retrying, verifying each part and the whole. Refuses anything that does not match.
        void Fetch(Asset a, string dest, string expectedSha)
        {
            if (a.Parts.Count == 0)
            {
                FetchOne(a, dest);
                string actual = Net.Sha256File(dest, null);
                if (actual != expectedSha) { File.Delete(dest); throw new InstallerException("The downloaded file " + a.Name + " failed its checksum. It was deleted; please try again.", true); }
                return;
            }
            string joined = dest + ".joining";
            if (File.Exists(joined)) File.Delete(joined);
            using (FileStream outFile = new FileStream(joined, FileMode.Create, FileAccess.Write, FileShare.None, 1 << 20))
                foreach (Asset part in a.Parts)
                {
                    string pp = Path.Combine(cacheDir, part.Name);
                    FetchOne(part, pp);
                    if (Net.Sha256File(pp, null) != part.Sha256) { File.Delete(pp); throw new InstallerException("A downloaded piece (" + part.Name + ") failed its checksum. It was deleted; please try again.", true); }
                    using (FileStream pin = new FileStream(pp, FileMode.Open, FileAccess.Read, FileShare.Read, 1 << 20)) pin.CopyTo(outFile, 1 << 20);
                    File.Delete(pp);
                    Check();
                }
            ui.Step("Verifying " + a.Name + " ...");
            if (Net.Sha256File(joined, null) != expectedSha) { File.Delete(joined); throw new InstallerException("The assembled file " + a.Name + " failed its checksum. It was deleted; please try again.", true); }
            if (File.Exists(dest)) File.Delete(dest);
            File.Move(joined, dest);
        }

        void FetchOne(Asset a, string dest)
        {
            long have = File.Exists(dest) ? new FileInfo(dest).Length : 0;
            if (have > a.Size) { File.Delete(dest); have = 0; }
            Add(have);                                              // the part that is already on disk counts as done
            int failures = 0;
            while (have < a.Size)
            {
                Check();
                try
                {
                    using (HttpWebResponse r = Net.Open(a.Url, have, 60000))
                    {
                        if (have > 0 && r.StatusCode == HttpStatusCode.OK) { Add(-have); have = 0; }          // the server ignored the range: start over
                        using (Stream s = r.GetResponseStream())
                        using (FileStream f = new FileStream(dest, have == 0 ? FileMode.Create : FileMode.Append, FileAccess.Write, FileShare.None, 1 << 20))
                        {
                            byte[] buf = new byte[1 << 17];
                            int n;
                            while ((n = s.Read(buf, 0, buf.Length)) > 0)
                            {
                                f.Write(buf, 0, n);
                                have += n; Add(n);
                                if (cancelled) break;
                            }
                        }
                    }
                    failures = 0;
                }
                catch (InstallerException ex)
                {
                    if (!ex.Retryable) throw;
                    if (ex.Message == "range") { try { File.Delete(dest); } catch (Exception) { } Add(-have); have = 0; }
                    if (++failures > 60) throw;
                    ui.Log("retry: " + ex.Message);
                    Thread.Sleep(Math.Min(30000, 1000 + 1000 * failures));
                }
                catch (Exception ex)
                {
                    have = File.Exists(dest) ? new FileInfo(dest).Length : 0;
                    if (++failures > 60) throw new InstallerException("The connection keeps failing (" + ex.Message + "). Your progress is kept; run the installer again when the connection is back.", true);
                    ui.Log("connection problem, continuing: " + ex.Message);
                    Thread.Sleep(Math.Min(30000, 1000 + 1000 * failures));
                }
            }
            Check();
            if (new FileInfo(dest).Length != a.Size) throw new InstallerException(a.Name + " has the wrong size after the download.", true);
        }
    }

    // ------------------------------------------------------------------------------------------------------------------ user interface
    class ConsoleReporter : IReporter
    {
        string last = "";
        DateTime lastLine = DateTime.MinValue;
        public void Step(string t) { Console.WriteLine("[step] " + t); }
        public void Log(string t) { Console.WriteLine("[log] " + t); }
        public void Progress(long d, long t)
        {
            if ((DateTime.UtcNow - lastLine).TotalSeconds < 5) return;
            lastLine = DateTime.UtcNow;
            string s = string.Format("[progress] {0:0.00} of {1:0.00} GB", d / 1e9, t / 1e9);
            if (s != last) { Console.WriteLine(s); last = s; }
        }
    }

    // From 4.1.0 on the program can share completed transcript text with MELETRA, but ONLY if the student switches it on (Settings -> Privacy & Data): the installer says so BEFORE anything is downloaded.
    static class Notice
    {
        public const string Text = "Nothing is shared unless you switch it on. Sharing completed transcript text with MELETRA to improve transcription quality is OFF by default; you can turn it on in Settings -> Privacy & Data.";
        public const string Detail = "Your audio, video, PDF files and pictures are never sent.";
        public static bool Applies()
        {
            try { return new Version(Pins.Version) >= new Version(4, 1, 0); } catch (Exception) { return false; }
        }
    }

    class InstallerForm : Form, IReporter
    {
        Label title, tagline, step, detail, notice;
        ProgressBar bar;
        Button main, cancel;
        Engine engine;
        Thread worker;
        readonly Func<Engine> factory;
        readonly bool unattended;
        long startTicks, lastDone, lastTicks;
        double speed;

        public InstallerForm(Func<Engine> factory, bool unattended)
        {
            this.factory = factory; this.unattended = unattended;
            Text = "MELETRA Installer";
            bool notices = Notice.Applies();
            ClientSize = new Size(540, notices ? 348 : 262);
            FormBorderStyle = FormBorderStyle.FixedDialog; MaximizeBox = false; StartPosition = FormStartPosition.CenterScreen;
            Font = new Font("Segoe UI", 9.5f);
            try { Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch (Exception) { }
            PictureBox symbol = null;
            try
            {
                using (Stream rs = System.Reflection.Assembly.GetExecutingAssembly().GetManifestResourceStream("meletra-symbol.png"))
                    if (rs != null) symbol = new PictureBox { Image = Image.FromStream(rs), SizeMode = PictureBoxSizeMode.Zoom, Left = 22, Top = 14, Width = 52, Height = 52, AccessibleName = "MELETRA logo" };
            }
            catch (Exception) { }
            int textLeft = symbol != null ? 84 : 22;
            title = new Label { UseMnemonic = false, Text = "MELETRA", Font = new Font("Segoe UI", 16f, FontStyle.Bold), Left = textLeft, Top = 12, Width = 440, Height = 32 };
            tagline = new Label { UseMnemonic = false, Text = "Medical Learning & Transcription", ForeColor = Color.DimGray, Left = textLeft, Top = 44, Width = 440, Height = 22 };
            step = new Label { UseMnemonic = false, Text = "MELETRA will download about 3.6 GB (the program and the Whisper Large-v3 speech model), check them and install. Nothing more is downloaded later.", Left = 22, Top = 82, Width = 496, Height = 56 };
            bar = new ProgressBar { Left = 22, Top = 146, Width = 496, Height = 22, Maximum = 1000, Visible = false };
            detail = new Label { UseMnemonic = false, Text = "", Left = 22, Top = 174, Width = 496, Height = 22, ForeColor = Color.DimGray };
            int buttons = notices ? 302 : 216;
            notice = new Label { UseMnemonic = false, Text = Notice.Text + "\r\n" + Notice.Detail, Left = 22, Top = 204, Width = 496, Height = 88, Visible = notices };
            main = new Button { Text = "Install", Left = 330, Top = buttons, Width = 90, Height = 30 };
            cancel = new Button { Text = "Cancel", Left = 428, Top = buttons, Width = 90, Height = 30 };
            Controls.AddRange(new Control[] { title, tagline, step, bar, detail, notice, main, cancel });
            if (symbol != null) Controls.Add(symbol);
            main.Click += delegate { Start(); };
            cancel.Click += delegate { if (engine != null && worker != null && worker.IsAlive) { engine.Cancel(); cancel.Enabled = false; } else Close(); };
            Shown += delegate { if (unattended) Start(); };
            FormClosing += delegate(object s, FormClosingEventArgs e)
            {
                if (worker != null && worker.IsAlive) { engine.Cancel(); worker.Join(5000); }
            };
        }

        void Start()
        {
            main.Enabled = false; cancel.Enabled = true; bar.Visible = true; bar.Value = 0;
            startTicks = lastTicks = DateTime.UtcNow.Ticks; lastDone = 0;
            engine = factory();
            worker = new Thread(delegate()
            {
                try { engine.Run(); Ui(delegate { Done(); }); }
                catch (InstallerException ex) { Ui(delegate { Failed(ex.Message, ex.Retryable); }); }
                catch (Exception ex) { Ui(delegate { Failed("Something went wrong: " + ex.Message, true); }); }
            });
            worker.IsBackground = true;
            worker.Start();
        }

        void Ui(MethodInvoker a) { if (IsHandleCreated && !IsDisposed) try { BeginInvoke(a); } catch (Exception) { } }
        void Done() { bar.Value = 1000; step.Text = "MELETRA is installed and starting. You can close this window."; detail.Text = ""; main.Visible = false; cancel.Text = "Close"; cancel.Enabled = true; if (unattended) Close(); }
        void Failed(string msg, bool retry)
        {
            step.Text = msg; detail.Text = ""; cancel.Text = "Close"; cancel.Enabled = true; main.Text = "Try again"; main.Enabled = retry;
        }
        public void Step(string t) { Ui(delegate { step.Text = t; }); }
        public void Log(string t) { Ui(delegate { detail.Text = t; }); }
        public void Progress(long d, long t)
        {
            Ui(delegate
            {
                bar.Value = t > 0 ? (int)Math.Max(0, Math.Min(1000, d * 1000 / t)) : 0;
                long now = DateTime.UtcNow.Ticks;
                if (now - lastTicks > 2 * TimeSpan.TicksPerSecond)
                {
                    speed = (d - lastDone) / ((now - lastTicks) / (double)TimeSpan.TicksPerSecond);
                    lastTicks = now; lastDone = d;
                }
                detail.Text = string.Format("{0:0.00} GB of {1:0.00} GB   ({2:0}%)   {3:0.0} MB/s", d / 1e9, t / 1e9, t > 0 ? 100.0 * d / t : 0, Math.Max(0, speed) / 1e6);
            });
        }
    }

    static class Program
    {
        [System.Runtime.InteropServices.DllImport("kernel32.dll")]
        static extern bool AttachConsole(int processId);

        [STAThread]
        static int Main(string[] args)
        {
            ServicePointManager.SecurityProtocol = (SecurityProtocolType)3072;     // TLS 1.2
            bool console = Array.IndexOf(args, "--console") >= 0, unattended = console || Array.IndexOf(args, "--unattended") >= 0;
            bool launch = Array.IndexOf(args, "--no-launch") < 0;
            string local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            string cache = Path.Combine(local, "MELETRAInstaller", "cache");
            string model = Path.Combine(local, "MedicalLectureTranscriber", "models", "whisper-large-v3");
            string setupArgs = "/SILENT /SUPPRESSMSGBOXES /NORESTART";
            string manifest = Pins.ManifestUrl;
#if TESTBUILD
            Net.AllowLoopbackHttp = true;
            for (int i = 0; i + 1 < args.Length; i++)
            {
                if (args[i] == "--manifest-url") manifest = args[i + 1];
                if (args[i] == "--cache-dir") cache = args[i + 1];
                if (args[i] == "--model-dir") model = args[i + 1];
                if (args[i] == "--setup-args") setupArgs = args[i + 1];
            }
#endif
            Func<IReporter, Engine> make = delegate(IReporter r) { Engine e = new Engine(r, cache, model, setupArgs, launch); e.ManifestUrl = manifest; return e; };
            if (console)
            {
                AttachConsole(-1);                                           // the window-less program writes to the console it was started from
                if (Notice.Applies()) Console.WriteLine("[notice] " + Notice.Text);
                ConsoleReporter r = new ConsoleReporter();
                try { make(r).Run(); Console.WriteLine("[done]"); return 0; }
                catch (Exception ex) { Console.WriteLine("[error] " + ex.Message); return 1; }
            }
            Application.EnableVisualStyles();
            InstallerForm form = null;
            form = new InstallerForm(delegate { return make(form); }, unattended);
            Application.Run(form);
            return 0;
        }
    }
}
