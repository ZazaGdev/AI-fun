"""A made-up Windows PC in a temp folder, for the disk-cleanup tests.

Two made-up drives, C and D: a Windows folder, programs, ProgramData, a profile with AppData,
caches, downloads, pictures, OneDrive, code projects, another user's profile and a game
library. Everything is 400 days old unless built with another age. A junction points out of
the scan root to a folder holding precious.txt, and a deny rule stands for access denied.
cleanup() takes the deny rule and the junctions away, then removes the whole temp folder.
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


class FakeWin:
    """Stands in for winsys.WinSys: a made-up process list and Recycle Bin."""

    def __init__(self, running=(), bin_size=0, bin_items=0, max_mb=1000, nuke=False, policy=False, drive=3):
        self.running = {p.lower() for p in running}
        self.bin = (bin_size, bin_items)
        self.settings = {"max_mb": max_mb, "nuke": nuke, "policy": policy}
        self.drive = drive

    def processes(self):
        return set(self.running)

    def drive_type(self, root):
        return self.drive

    def recycle_settings(self, root):
        return dict(self.settings)

    def recycle_usage(self, root):
        return self.bin


def ext(p):
    return "\\\\?\\" + os.path.abspath(p)


class PC:
    def __init__(self):
        self.base = tempfile.mkdtemp(prefix="disk-cleanup-test-")
        j = os.path.join
        self.C, self.D = j(self.base, "C"), j(self.base, "D")
        self.outside, self.out = j(self.base, "outside"), j(self.base, "out")
        self.profile = j(self.C, "Users", "you")
        self.local = j(self.profile, "AppData", "Local")
        self.roaming = j(self.profile, "AppData", "Roaming")
        self.ages, self.junctions, self.denied = {}, [], []
        self.now = time.time()
        self.build()

    # ---- building ----

    def p(self, *parts):
        return os.path.join(self.base, *parts)

    def file(self, rel, size=100, age=OLD, data=None):
        path = self.p(rel)
        os.makedirs(os.path.dirname(ext(path)), exist_ok=True)
        with open(ext(path), "wb") as f:
            f.write(data if data is not None else os.urandom(size))
        self.ages[os.path.normcase(path)] = age
        return path

    def dir(self, rel, age=OLD):
        path = self.p(rel)
        os.makedirs(ext(path), exist_ok=True)
        self.ages[os.path.normcase(path)] = age
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
        f(lo + "Temp\\old-folder\\a.txt", 2 * KB)
        f(lo + "Temp\\new.tmp", KB, age=1)
        f(lo + "Temp\\mixed-folder\\new.txt", KB, age=1)
        f(lo + "Temp\\linked-folder\\a.txt")
        f(lo + "Temp\\online-folder\\cloud.txt")
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
        f(u + "Downloads\\old-setup.exe", 6 * KB)
        f(u + "Downloads\\new-setup.msi", 6 * KB, age=2)
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
        f(u + "Videos\\old-trip.mp4", 300 * KB)
        f(u + "Documents\\report.docx", 2 * KB)
        d(u + "Documents\\old-empty\\inner")
        d(u + "Documents\\new-empty", age=1)
        f(u + "Documents\\locked\\secret.txt")
        d(u + "Music")
        f(u + "Desktop\\notes.txt")
        f(u + "envs\\old-env\\pyvenv.cfg", data=b"home = C:\\Python313\n")
        f(u + "envs\\old-env\\Lib\\site-packages\\x.py", 2 * KB)
        f(u + "envs\\new-env\\pyvenv.cfg", data=b"home = C:\\Python313\n")
        f(u + "envs\\new-env\\Lib\\site-packages\\y.py", 2 * KB, age=3)

        # code projects
        c = u + "code\\"
        f(c + "old-app\\package.json", data=b"{}")
        f(c + "old-app\\index.js")
        f(c + "old-app\\node_modules\\dep\\index.js", 4 * KB)
        f(c + "old-app\\assets\\intro.mp4", 300 * KB)
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
        f(c + "rust-app\\Cargo.toml", data=b"[package]")
        f(c + "rust-app\\src\\main.rs")
        f(c + "rust-app\\target\\debug\\app.exe", 3 * KB)
        f(c + "py-app\\requirements.txt", data=b"requests\n")
        f(c + "py-app\\main.py")
        f(c + "py-app\\__pycache__\\main.cpython-313.pyc", KB)
        f(c + "py-app\\.venv\\pyvenv.cfg", data=b"home = C:\\Python313\n")
        f(c + "py-app\\.venv\\Lib\\site-packages\\x.py", 2 * KB)
        f(c + "py-app\\.pytest_cache\\v\\cache\\lastfailed", data=b"{}")
        img = os.urandom(20 * KB)
        f(c + "repo\\.git\\HEAD", data=b"ref: refs/heads/main\n")
        f(c + "repo\\assets\\a.png", data=img)
        f(c + "repo\\assets\\b.png", data=img)

        # other people's profiles
        f("C\\Users\\other\\AppData\\Local\\Temp\\old.tmp", KB)
        f("C\\Users\\other\\Pictures\\x.jpg", 20 * KB)
        f("C\\Users\\Public\\Documents\\shared.txt")

        # drive D: stray installer files in its root, a game, a Steam library
        f("D\\install.exe")
        f("D\\install.res.1033.dll")
        f("D\\Games\\SomeGame\\game.exe")
        f("D\\Games\\SomeGame\\game.dll")
        f("D\\Games\\SomeGame\\data\\big.pak", 300 * KB)
        f("D\\SteamLibrary\\steamapps\\common\\G\\g.exe")
        f("D\\SteamLibrary\\steamapps\\common\\G\\g.dat", 300 * KB)

        self.set_ages()
        # links, an online-only file and a deny rule come after the dates, then the dates of their folders
        self.junction("C\\Users\\you\\code\\linked-app\\node_modules\\outside-link", self.outside)
        self.junction(lo + "Temp\\linked-folder\\outside-link", self.outside)
        # .gradle moved to another drive and linked back: its caches live outside the scan root
        self.junction(u + ".gradle", self.p("outside\\gradle-home"))
        online = self.p(lo + "Temp\\online-folder\\cloud.txt")
        ctypes.windll.kernel32.SetFileAttributesW(online, 0x1000)  # FILE_ATTRIBUTE_OFFLINE
        self.deny(self.p(u + "Documents\\locked"))
        for rel in ("C\\Users\\you\\code\\linked-app\\node_modules", lo + "Temp\\linked-folder", u.rstrip("\\")):
            self.age(self.p(rel), OLD)
        os.utime(self.ancient, (-315619200, -315619200))  # 1960-01-01, before what Windows' localtime takes

    def age(self, path, days):
        t = self.now - days * DAY
        os.utime(ext(path), (t, t))

    def set_ages(self):
        for top, dirs, files in os.walk(ext(self.base)):
            for name in dirs + files:
                full = os.path.join(top, name)[4:]
                self.age(full, self.ages.get(os.path.normcase(full), OLD))

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
                ctypes.windll.kernel32.SetFileAttributesW(os.path.join(top, name), 0x80)
        shutil.rmtree(ext(self.base))
