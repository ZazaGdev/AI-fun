"""A made-up Windows PC in a temp folder, for the disk-cleanup tests.

Two made-up drives, C and D: a Windows folder, programs, ProgramData, a profile with AppData,
caches, downloads, pictures, OneDrive, Dropbox, code projects, another user's profile, game
libraries and sync folders. Everything is 400 days old (modified and created) unless built with
another age; a few files are created today with an old modified time, as an extracted or copied
file is. Junctions point out of the scan root to a folder holding precious.txt, and a deny rule
stands for access denied. cleanup() takes the deny rule and the junctions away, then removes the
whole temp folder.
"""
import ctypes
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "skill", "scripts")))

import rules  # noqa: E402

DAY = rules.DAY
KB = 1024
OLD = 400
OFFLINE = 0x1000

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ulong,
                             ctypes.c_ulong, ctypes.c_void_p]
_k32.CreateFileW.restype = ctypes.c_void_p
_k32.SetFileTime.argtypes = [ctypes.c_void_p] + [ctypes.POINTER(ctypes.c_ulonglong)] * 3
_k32.CloseHandle.argtypes = [ctypes.c_void_p]
_k32.SetFileAttributesW.argtypes = [ctypes.c_wchar_p, ctypes.c_ulong]
_k32.GetFileAttributesW.argtypes = [ctypes.c_wchar_p]
_k32.GetFileAttributesW.restype = ctypes.c_ulong


class FakeWin:
    """Stands in for winsys.WinSys: a made-up process list and Recycle Bin. recycle() takes the same
    gate as the real call (winsys.from_list), then moves each path into `bin_dir`, a folder of the
    made-up PC, unless it is one of `stuck` (in use) or of `cancel`: Windows asked whether to delete
    it for good and the user said No, so the call comes back cancelled, as the real one does."""

    def __init__(self, running=(), bin_size=0, bin_items=0, max_mb=1000, nuke=False, policy=False, drive=3,
                 bin_dir=None, stuck=(), cancel=()):
        self.running = {p.lower() for p in running}
        self.bin = (bin_size, bin_items)
        self.settings = {"max_mb": max_mb, "nuke": nuke, "policy": policy}
        self.drive = drive
        self.bin_dir, self.stuck = bin_dir, {os.path.normcase(p) for p in stuck}
        self.cancel = {os.path.normcase(p) for p in cancel}
        self.calls, self.moved = [], []

    def recycle(self, paths):
        import winsys
        winsys.from_list(paths)
        self.calls.append(list(paths))
        if self.bin_dir is None:
            raise AssertionError("this test does not expect anything to be moved")
        os.makedirs(self.bin_dir, exist_ok=True)
        for p in paths:
            if os.path.normcase(p) not in self.stuck | self.cancel and os.path.lexists(ext(p)):
                os.rename(ext(p), ext(os.path.join(self.bin_dir, "%d-%s" % (len(self.moved), os.path.basename(p)))))
                self.moved.append(p)
        if any(os.path.normcase(p) in self.cancel for p in paths):
            return 0x4C7, True  # ERROR_CANCELLED, fAnyOperationsAborted
        return 0, False

    def processes(self):
        return set(self.running)

    def drive_type(self, root):
        return self.drive

    def recycle_settings(self, root):
        return dict(self.settings)

    def recycle_usage(self, root):
        return self.bin


def ext(p):
    """The \\\\?\\ form of a full path, as is: no abspath, which would drop a trailing space or dot."""
    return p if p.startswith("\\\\?\\") else "\\\\?\\" + p


def set_times(path, t):
    """Created, accessed and modified time of a file or folder (not following a link)."""
    h = _k32.CreateFileW(ext(path), 0x100, 7, None, 3, 0x02000000 | 0x00200000, None)  # FILE_WRITE_ATTRIBUTES
    if h in (None, ctypes.c_void_p(-1).value):
        raise OSError(ctypes.get_last_error(), "CreateFileW", path)
    ft = ctypes.c_ulonglong(int((t + 11644473600) * 10 ** 7))
    try:
        if not _k32.SetFileTime(h, ctypes.byref(ft), ctypes.byref(ft), ctypes.byref(ft)):
            raise OSError(ctypes.get_last_error(), "SetFileTime", path)
    finally:
        _k32.CloseHandle(h)


class PC:
    def __init__(self):
        # realpath: %TEMP% may hold an 8.3 short name (C:\Users\JOHNSM~1), which the scan resolves
        self.base = os.path.realpath(tempfile.mkdtemp(prefix="disk-cleanup-test-"))
        j = os.path.join
        self.C, self.D = j(self.base, "C"), j(self.base, "D")
        self.outside, self.out = j(self.base, "outside"), j(self.base, "out")
        self.profile = j(self.C, "Users", "you")
        self.local = j(self.profile, "AppData", "Local")
        self.roaming = j(self.profile, "AppData", "Roaming")
        self.ages, self.fresh, self.junctions, self.denied, self.offline = {}, set(), [], [], []
        self.now = time.time()
        self.build()

    # ---- building ----

    def p(self, *parts):
        return os.path.join(self.base, *parts)

    def file(self, rel, size=100, age=OLD, data=None, born_today=False):
        path = self.p(rel)
        os.makedirs(os.path.dirname(ext(path)), exist_ok=True)
        with open(ext(path), "wb") as f:
            f.write(data if data is not None else os.urandom(size))
        self.ages[os.path.normcase(path)] = age
        if born_today:
            self.fresh.add(os.path.normcase(path))
        return path

    def dir(self, rel, age=OLD, born_today=False):
        path = self.p(rel)
        os.makedirs(ext(path), exist_ok=True)
        self.ages[os.path.normcase(path)] = age
        if born_today:
            self.fresh.add(os.path.normcase(path))
        return path

    def junction(self, rel, target):
        link = self.p(rel)
        os.makedirs(os.path.dirname(link), exist_ok=True)
        r = subprocess.run(["cmd", "/c", "mklink", "/J", link, target], capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError("mklink /J failed: " + r.stdout + r.stderr)
        self.junctions.append(link)
        return link

    def build(self):
        u = "C\\Users\\you\\"
        lo, ro = u + "AppData\\Local\\", u + "AppData\\Roaming\\"
        f, d = self.file, self.dir
        self.precious = f("outside\\precious.txt", data=b"keep me")
        self.big_jar = f("outside\\gradle-home\\caches\\modules-2\\big.jar", 50 * KB)
        d("out")

        # Windows, programs, ProgramData, the drive root's own folders
        f("C\\Windows\\SoftwareDistribution\\Download\\update.cab", 2 * KB)
        f("C\\Windows\\Temp\\wintemp.tmp", KB)
        f("C\\Windows\\Minidump\\112024-01.dmp", 3 * KB)
        f("C\\Windows\\System32\\kernel.exe")
        f("C\\Windows\\System32\\kernel.dll")
        f("C\\$Windows.~BT\\Sources\\setup.bin", 2 * KB)
        f("C\\inetpub\\wwwroot\\iisstart.htm")
        d("C\\inetpub\\history\\old")
        f("C\\Program Files\\App\\app.exe")
        f("C\\Program Files\\App\\app.dll")
        f("C\\Program Files\\App\\package.json", data=b"{}")
        f("C\\Program Files\\App\\node_modules\\dep\\index.js")
        f("C\\Program Files (x86)\\Old\\old.exe")
        f("C\\ProgramData\\Microsoft\\Windows\\WER\\ReportQueue\\r1\\Report.wer", KB)
        f("C\\ProgramData\\Vendor\\cache\\blob.bin", 4 * KB)
        f("C\\$Recycle.Bin\\S-1-5-21-1\\$Rabc.txt")
        f("C\\System Volume Information\\tracking.log")

        # the profile's AppData: temp files, crash dumps, caches, programs, packages
        f(lo + "Temp\\old.tmp", KB)
        self.ancient = f(lo + "Temp\\ancient.tmp")  # dated 1960 below
        f(lo + "Temp\\extracted-today.txt", born_today=True)
        f(lo + "Temp\\old-folder\\a.txt", 2 * KB)
        f(lo + "Temp\\new.tmp", KB, age=1)
        f(lo + "Temp\\mixed-folder\\new.txt", KB, age=1)
        f(lo + "Temp\\linked-folder\\a.txt")
        f(lo + "Temp\\online-folder\\cloud.txt")
        d(lo + "Temp\\offline-child")
        f(lo + "Temp\\holds-offline\\x.txt")
        d(lo + "Temp\\holds-offline\\sub")
        f(lo + "Temp\\spaced-folder \\a.txt")
        f(lo + "Temp\\dotted-file.")
        deep = lo + "Temp\\deep-old\\" + "\\".join(["a-folder-name-of-forty-characters-long-x"] * 8)
        self.deep_file = f(deep + "\\deep.txt", 5 * KB)
        f(lo + "Google\\Chrome\\User Data\\Default\\Cache\\Cache_Data\\data_0", 4 * KB)
        f(lo + "Google\\Chrome\\User Data\\Default\\Code Cache\\js\\index", 2 * KB)
        f(lo + "Google\\Chrome\\User Data\\Default\\GPUCache\\data_1", KB)
        f(lo + "Google\\Chrome\\User Data\\Default\\History", 8 * KB)
        f(lo + "Google\\Chrome\\User Data\\Default\\Local Storage\\leveldb\\000003.ldb")
        f(lo + "Google\\Chrome\\User Data\\Profile 1\\Cache\\Cache_Data\\f_000001", 3 * KB)
        f(lo + "Google\\Chrome\\User Data\\System Profile\\Cache\\x")
        f(lo + "Google\\Chrome\\User Data\\ShaderCache\\data_0", KB)
        f(lo + "Google\\Chrome\\User Data\\Local State")
        f(lo + "Mozilla\\Firefox\\Profiles\\abc.default-release\\cache2\\entries\\E1", 2 * KB)
        f(lo + "Mozilla\\Firefox\\Profiles\\abc.default-release\\startupCache\\startupCache.8.little", KB)
        f(ro + "Mozilla\\Firefox\\Profiles\\abc.default-release\\places.sqlite", 4 * KB)
        f(ro + "discord\\Cache\\Cache_Data\\d1", 2 * KB)
        f(ro + "discord\\Code Cache\\js\\x", KB)
        f(ro + "discord\\GPUCache\\g", KB)
        f(ro + "discord\\Local Storage\\leveldb\\l.ldb")
        f(ro + "UnknownApp\\Cache\\c", KB)
        f(ro + "UnknownApp\\Code Cache\\js\\x", KB)
        f(ro + "UnknownApp\\GPUCache\\g", KB)
        f(ro + "UnknownApp\\Preferences")
        f(lo + "SomeVendor\\ElectronApp\\Code Cache\\x", KB)
        f(lo + "SomeVendor\\ElectronApp\\GPUCache\\g", KB)
        f(lo + "SomeVendor\\ElectronApp\\settings.json")
        f(lo + "NVIDIA\\DXCache\\dx1.bin", 2 * KB)
        f(lo + "npm-cache\\_cacache\\content-v2\\sha512\\x", 5 * KB)
        f(lo + "CrashDumps\\app.exe.1234.dmp", 2 * KB)
        f(lo + "Microsoft\\Windows\\WER\\ReportArchive\\AppCrash_x\\Report.wer", KB)
        f(lo + "Microsoft\\Windows\\Explorer\\thumbcache_32.db", KB)
        f(lo + "Microsoft\\Windows\\INetCache\\IE\\x.dat", KB)
        f(lo + "Packages\\SomeApp_1\\LocalCache\\Cache\\x")
        f(lo + "Packages\\SomeApp_1\\LocalCache\\Code Cache\\x")
        f(lo + "Packages\\SomeApp_1\\LocalCache\\GPUCache\\x")
        f(lo + "Programs\\SomeApp\\SomeApp.exe")
        f(lo + "Programs\\SomeApp\\SomeApp.dll")
        f(lo + "Programs\\SomeApp\\resources\\app\\package.json", data=b"{}")
        f(lo + "Programs\\SomeApp\\resources\\app\\node_modules\\dep\\index.js")
        f(u + ".nuget\\packages\\newtonsoft.json\\13.0.1\\n.nupkg", 3 * KB)
        f(u + ".vscode\\extensions\\x\\package.json", data=b"{}")
        f(u + ".vscode\\extensions\\x\\node_modules\\dep\\index.js")
        f(u + ".claude\\projects\\p\\session.jsonl")

        # the user's own folders
        f(u + "package.json", data=b"{}")  # a stray npm init in the home folder: not a project
        f(u + "Downloads\\old-setup.exe", 6 * KB)
        f(u + "Downloads\\new-setup.msi", 6 * KB, age=2)
        f(u + "Downloads\\copied-setup.exe", 6 * KB, born_today=True)
        f(u + "Downloads\\movie.mp4.crdownload", 7 * KB, age=10)
        f(u + "Downloads\\fresh.crdownload", KB, age=1)
        f(u + "Downloads\\manual.pdf", 2 * KB)
        f(u + "Downloads\\tools\\old-setup2.exe", KB)
        photo = os.urandom(20 * KB)
        f(u + "Pictures\\beach.jpg", data=photo)
        f(u + "Pictures\\Backup\\beach.jpg", data=photo)
        f(u + "Downloads\\beach (1).jpg", data=photo)
        hard = f(u + "Pictures\\hard1.jpg", 20 * KB)
        os.link(hard, self.p(u + "Pictures\\hard2.jpg"))
        cloud = os.urandom(20 * KB)
        f(u + "OneDrive\\photo.jpg", data=cloud)
        f(u + "OneDrive\\Old\\photo.jpg", data=cloud)
        trip = os.urandom(25 * KB)
        f(u + "Dropbox (Personal)\\Photos\\trip.jpg", data=trip)
        f(u + "Dropbox (Personal)\\Photos\\Backup\\trip.jpg", data=trip)
        d(u + "Dropbox (Personal)\\Team")
        twin = os.urandom(26 * KB)
        f(u + "cloudy\\online-dir\\a.jpg", data=twin)  # online-only folder, set below
        f(u + "cloudy\\online-dir\\b.jpg", data=twin)
        f(u + "Videos\\old-trip.mp4", 300 * KB)
        f(u + "Videos\\copied-movie.mp4", 300 * KB, born_today=True)
        f(u + "Documents\\report.docx", 2 * KB)
        d(u + "Documents\\old-empty\\inner")
        d(u + "Documents\\new-empty", age=1)
        d(u + "Documents\\made-today", born_today=True)
        f(u + "Documents\\locked\\secret.txt")
        f(u + "Documents\\locked\\sub\\clip.mp4", 300 * KB)  # behind the deny rule: never read by the scan
        d(u + "Music")
        f(u + "Desktop\\notes.txt")
        for env_dir, age in (("old-env", OLD), ("new-env", 3)):
            f(u + "envs\\%s\\pyvenv.cfg" % env_dir, data=b"home = C:\\Python313\n")
            f(u + "envs\\%s\\Scripts\\python.exe" % env_dir)
            f(u + "envs\\%s\\Lib\\site-packages\\x.py" % env_dir, 2 * KB, age=age)
        # folders with a pyvenv.cfg that hold someone's own files too
        f(u + "Documents\\thesis-env\\pyvenv.cfg", data=b"home = C:\\Python313\n")
        f(u + "Documents\\thesis-env\\Scripts\\python.exe")
        f(u + "Documents\\thesis-env\\Lib\\site-packages\\numpy\\core.py", 2 * KB)
        f(u + "Documents\\thesis-env\\thesis-final.docx", 9 * KB)
        f(u + "Documents\\thesis-env\\data\\results.xlsx", 5 * KB)
        f(u + "pipx\\venvs\\black\\pyvenv.cfg", data=b"home = C:\\Python313\n")
        f(u + "pipx\\venvs\\black\\pipx_metadata.json", data=b"{}")
        f(u + "pipx\\venvs\\black\\Scripts\\black.exe")
        f(u + "pipx\\venvs\\black\\Lib\\site-packages\\black\\__init__.py", 2 * KB)
        f(u + "Saved Games\\pyvenv.cfg", data=b"home = C:\\Python313\n")  # a shell folder is never offered
        f(u + "Saved Games\\Scripts\\python.exe")
        f(u + "Saved Games\\Lib\\site-packages\\s.py")
        # node_modules folders without a package.json beside them: npm itself, global packages
        node = u + "scoop\\apps\\nodejs\\20.11.0\\"
        f(node + "node.exe")
        f(node + "node_modules\\npm\\package.json", data=b'{"name": "npm"}')
        f(node + "node_modules\\npm\\lib\\cli.js", 2 * KB)
        f(node + "node_modules\\npm\\node_modules\\abbrev\\package.json", data=b'{"name": "abbrev"}')
        f(node + "node_modules\\npm\\node_modules\\abbrev\\index.js", 4 * KB)
        f(u + "npm-global\\node_modules\\firebase-tools\\package.json", data=b"{}")
        f(u + "npm-global\\node_modules\\firebase-tools\\node_modules\\express\\index.js", 4 * KB)

        # code projects
        c = u + "code\\"
        f(c + "old-app\\package.json", data=b"{}")
        f(c + "old-app\\index.js")
        f(c + "old-app\\node_modules\\dep\\index.js", 4 * KB)
        f(c + "old-app\\assets\\intro.mp4", 300 * KB)
        f(c + "copied-app\\package.json", data=b"{}", born_today=True)  # copied in today, old modified times
        f(c + "copied-app\\index.js", born_today=True)
        f(c + "copied-app\\node_modules\\dep\\index.js", 4 * KB)
        f(c + "mono\\package.json", data=b"{}")
        f(c + "mono\\node_modules\\dep\\index.js", 4 * KB)
        f(c + "mono\\packages\\a\\package.json", data=b"{}")
        f(c + "mono\\packages\\a\\src\\x.js", age=2)
        f(c + "new-app\\package.json", data=b"{}")
        f(c + "new-app\\src\\index.js", age=2)
        f(c + "new-app\\node_modules\\dep\\index.js", 4 * KB)
        f(c + "linked-app\\package.json", data=b"{}")
        f(c + "linked-app\\node_modules\\dep\\index.js", 4 * KB)
        f(c + "dotnet-app\\App.csproj", data=b"<Project/>")
        f(c + "dotnet-app\\Program.cs")
        f(c + "dotnet-app\\bin\\Debug\\App.dll", 3 * KB)
        f(c + "dotnet-app\\obj\\project.assets.json", KB)
        f(c + "sln\\Shop.sln", data=b"Microsoft Visual Studio Solution File")  # committed 8 days ago
        f(c + "sln\\README.md", age=8)
        f(c + "sln\\src\\Shop\\Shop.csproj", data=b"<Project/>")
        f(c + "sln\\src\\Shop\\Program.cs")
        f(c + "sln\\src\\Shop\\bin\\Debug\\Shop.dll", 3 * KB)
        f(c + "sln\\src\\Shop\\obj\\project.assets.json", KB)
        f(c + "rust-app\\Cargo.toml", data=b"[package]")
        f(c + "rust-app\\src\\main.rs")
        f(c + "rust-app\\target\\debug\\app.exe", 3 * KB)
        f(c + "py-app\\requirements.txt", data=b"requests\n")
        f(c + "py-app\\main.py")
        f(c + "py-app\\__pycache__\\main.cpython-313.pyc", KB)
        f(c + "py-app\\.venv\\pyvenv.cfg", data=b"home = C:\\Python313\n")
        f(c + "py-app\\.venv\\Scripts\\python.exe")
        f(c + "py-app\\.venv\\Lib\\site-packages\\x.py", 2 * KB)
        f(c + "py-app\\.pytest_cache\\v\\cache\\lastfailed", data=b"{}")
        f(c + "old-tool\\.git\\HEAD", data=b"ref: refs/heads/main\n")  # python -m venv . run in a repo
        f(c + "old-tool\\pyvenv.cfg", data=b"home = C:\\Python313\n")
        f(c + "old-tool\\Scripts\\python.exe")
        f(c + "old-tool\\Lib\\site-packages\\x.py")
        f(c + "old-tool\\main.py", 3 * KB)
        img = os.urandom(20 * KB)
        f(c + "repo\\.git\\HEAD", data=b"ref: refs/heads/main\n")
        f(c + "repo\\assets\\a.png", data=img)
        f(c + "repo\\assets\\b.png", data=img)
        svn, hg = os.urandom(30 * KB), os.urandom(30 * KB)
        f(c + "svn-site\\.svn\\wc.db")
        f(c + "svn-site\\img\\a.png", data=svn)
        f(c + "svn-site\\img\\b.png", data=svn)
        d(c + "svn-site\\old\\empty\\inner")
        f(c + "hg-site\\.hg\\store\\00changelog.i")
        f(c + "hg-site\\a.jpg", data=hg)
        f(c + "hg-site\\copy\\a.jpg", data=hg)
        f(c + "tool-proj\\requirements.txt", data=b"requests\n")
        f(c + "tool-proj\\tools\\venv\\pyvenv.cfg", data=b"home = C:\\Python313\n")
        f(c + "tool-proj\\tools\\venv\\Scripts\\python.exe")
        f(c + "tool-proj\\tools\\venv\\Lib\\site-packages\\z.py", KB)

        # other people's profiles
        f("C\\Users\\other\\AppData\\Local\\Temp\\old.tmp", KB)
        f("C\\Users\\other\\Pictures\\x.jpg", 20 * KB)
        f("C\\Users\\Public\\Documents\\shared.txt")

        # drive D: stray files in its root, games, programs, sync folders, a backup
        f("D\\install.exe")
        f("D\\install.res.1033.dll")
        f("D\\.git\\HEAD", data=b"ref: refs/heads/main\n")  # a dotfiles repo in the drive root: not a project
        f("D\\Games\\SomeGame\\game.exe")
        f("D\\Games\\SomeGame\\game.dll")
        f("D\\Games\\SomeGame\\data\\big.pak", 300 * KB)
        movie = os.urandom(27 * KB)
        sg = "D\\Games\\Shooter\\"
        f(sg + "Shooter.exe")
        f(sg + ".egstore\\Shooter.mancpn")
        f(sg + "Engine\\Binaries\\Win64\\tbb.dll")
        f(sg + "ShooterGame\\Content\\Movies\\Intro.mp4", data=movie)
        f(sg + "ShooterGame\\Content\\Movies\\de\\Intro.mp4", data=movie)
        d(sg + "ShooterGame\\Content\\Mods")
        f("D\\PostgreSQL\\16\\uninstall-postgresql.exe")
        d("D\\PostgreSQL\\16\\data\\base\\pgsql_tmp")
        f("D\\GOGLib\\Witcher\\goggame-1207664643.info", data=b"{}")
        d("D\\GOGLib\\Witcher\\saves")
        f("D\\Amazon Games\\Library\\x.dat")
        f("D\\SteamLibrary\\steamapps\\common\\G\\g.exe")
        f("D\\SteamLibrary\\steamapps\\common\\G\\g.dat", 300 * KB)
        scan_pdf, img1, docx = os.urandom(28 * KB), os.urandom(29 * KB), os.urandom(31 * KB)
        f("D\\Dropbox\\.dropbox", data=b"{}")
        f("D\\Dropbox\\scan.pdf", data=scan_pdf)
        f("D\\Dropbox\\old\\scan.pdf", data=scan_pdf)
        d("D\\Dropbox\\Clients")
        f("D\\PhoneSync\\.stfolder\\syncthing-folder-abc.txt")
        f("D\\PhoneSync\\DCIM\\img1.jpg", data=img1)
        f("D\\PhoneSync\\DCIM\\sent\\img1.jpg", data=img1)
        f("D\\WorkCloud\\._sync_4f2a.db")
        f("D\\WorkCloud\\a.docx", data=docx)
        f("D\\WorkCloud\\copy\\a.docx", data=docx)
        backup = os.urandom(32 * KB)
        f("D\\Backup\\photo.jpg", data=backup)
        f("D\\Backup\\old\\photo.jpg", data=backup)

        self.set_ages()
        # links, online-only files and folders, and a deny rule come after the dates, then the dates of their folders
        self.junction("C\\Users\\you\\code\\linked-app\\node_modules\\outside-link", self.outside)
        self.junction(lo + "Temp\\linked-folder\\outside-link", self.outside)
        # .gradle moved to another drive and linked back: its caches live outside the scan root
        self.junction(u + ".gradle", self.p("outside\\gradle-home"))
        for rel in (lo + "Temp\\online-folder\\cloud.txt", lo + "Temp\\offline-child", lo + "Temp\\holds-offline\\sub",
                    u + "cloudy\\online-dir"):
            self.set_offline(self.p(rel))
        self.deny(self.p(u + "Documents\\locked"))
        for rel in ("C\\Users\\you\\code\\linked-app\\node_modules", lo + "Temp\\linked-folder", u.rstrip("\\")):
            self.age(self.p(rel), OLD)
        os.utime(self.ancient, (-315619200, -315619200))  # 1960-01-01, before what Windows' localtime takes

    def age(self, path, days):
        set_times(path, self.now - days * DAY)

    def set_ages(self):
        for top, dirs, files in os.walk(ext(self.base)):
            for name in dirs + files:
                full = os.path.join(top, name)[4:]
                n = os.path.normcase(full)
                t = self.now - self.ages.get(n, OLD) * DAY
                if n in self.fresh:
                    os.utime(ext(full), (t, t))  # modified long ago, created today
                else:
                    set_times(full, t)

    def set_offline(self, path):
        a = _k32.GetFileAttributesW(ext(path))
        _k32.SetFileAttributesW(ext(path), (a & 0x10) | OFFLINE)  # keep FILE_ATTRIBUTE_DIRECTORY
        self.offline.append(path)

    def deny(self, path):
        sid = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"], capture_output=True,
                             text=True).stdout.strip().split(",")[-1].strip('"')
        r = subprocess.run(["icacls", path, "/deny", "*%s:(RD)" % sid], capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError("icacls failed: " + r.stdout + r.stderr)
        self.denied.append((path, sid))

    # ---- what the tests use ----

    def env(self, **change):
        j = os.path.join
        kw = dict(profile=self.profile, local=self.local, roaming=self.roaming,
                  locallow=j(self.profile, "AppData", "LocalLow"), temps=[j(self.local, "Temp")],
                  downloads=j(self.profile, "Downloads"), system_root=j(self.C, "Windows"), system_drive=self.C,
                  program_files=[j(self.C, "Program Files"), j(self.C, "Program Files (x86)")],
                  program_data=j(self.C, "ProgramData"), synced=[j(self.profile, "OneDrive")], out_dir=self.out,
                  drive_roots=[self.C, self.D])
        kw.update(change)
        return rules.Env(**kw)

    def cleanup(self):
        for path, sid in self.denied:
            subprocess.run(["icacls", path, "/remove:d", "*" + sid], capture_output=True)
        for link in self.junctions:
            if os.path.lexists(link):
                os.rmdir(link)  # removes the link only, never what it points to
        for top, dirs, files in os.walk(ext(self.base)):
            for name in files:
                _k32.SetFileAttributesW(os.path.join(top, name), 0x80)
            for name in dirs:
                _k32.SetFileAttributesW(os.path.join(top, name), 0x10)
        shutil.rmtree(ext(self.base))
