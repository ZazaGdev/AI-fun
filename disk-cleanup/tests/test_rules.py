"""Locations, path comparison, areas and the known-location rule tables."""
import json
import os
import shutil
import tempfile
import time
import unittest

from fixture import PC
from helpers import LO, RO, U, rel
import rules


class Paths(unittest.TestCase):
    def test_is_under(self):
        self.assertTrue(rules.is_under("C:\\Users\\You\\Temp", "c:\\users\\you"))
        self.assertTrue(rules.is_under("C:\\Users\\you", "C:\\Users\\you"))
        self.assertTrue(rules.is_under("C:\\Users\\you\\", "C:\\Users\\you"))
        self.assertFalse(rules.is_under("C:\\Users\\young", "C:\\Users\\you"))
        self.assertFalse(rules.is_under("C:\\Users", "C:\\Users\\you"))
        self.assertTrue(rules.is_under("c:\\x\\y", "C:\\"))
        self.assertTrue(rules.is_under("C:\\", "c:\\"))
        self.assertFalse(rules.is_under("D:\\x", "C:\\"))
        self.assertTrue(rules.is_under("C:/Users/you/a", "C:\\Users\\you"))

    def test_downloads_item(self):
        now = time.time()
        self.assertTrue(rules.downloads_item("Setup.EXE", now - 31 * rules.DAY, now))
        self.assertFalse(rules.downloads_item("setup.exe", now - 29 * rules.DAY, now))
        self.assertTrue(rules.downloads_item("film.mkv.part", now - 8 * rules.DAY, now))
        self.assertFalse(rules.downloads_item("film.mkv.part", now - 6 * rules.DAY, now))
        self.assertFalse(rules.downloads_item("manual.pdf", now - 900 * rules.DAY, now))


class Areas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pc = PC()
        cls.env = cls.pc.env()

    @classmethod
    def tearDownClass(cls):
        cls.pc.cleanup()

    def kind(self, rel_path):
        return rules.context(self.env, self.pc.p(rel_path))[0]

    def test_context_finds_programs_projects_and_rule_targets_above(self):
        c = U + "code\\"
        self.assertEqual(self.kind("D\\Games\\SomeGame\\data"), rules.PROGRAM)
        self.assertEqual(self.kind("D\\SteamLibrary\\steamapps\\common"), rules.PROGRAM)
        self.assertIsNone(self.kind("D\\Games"))  # the stray .exe and .dll in the drive root do not count
        self.assertEqual(self.kind(c + "old-app\\node_modules"), rules.INSIDE)
        self.assertEqual(self.kind(c + "old-app\\node_modules\\dep"), rules.INSIDE)
        self.assertEqual(self.kind(c + "py-app\\.venv\\Lib"), rules.INSIDE)
        self.assertEqual(self.kind(c + "py-app\\__pycache__"), rules.INSIDE)
        self.assertIsNone(self.kind(c + "py-app\\.venv"))  # the walk itself finds pyvenv.cfg in it
        kind, projects, stop = rules.context(self.env, self.pc.p(c + "mono\\packages\\a\\src"))
        self.assertEqual((kind, stop), (None, None))
        self.assertEqual([rel(self.pc, p) for p in projects], [c + "mono", c + "mono\\packages\\a"])

    def test_context_says_where_it_stopped(self):
        c = U + "code\\"
        stop = lambda p: rel(self.pc, rules.context(self.env, self.pc.p(p))[2])  # noqa: E731
        self.assertEqual(stop(c + "old-app\\node_modules"), c + "old-app\\node_modules")  # the item itself
        self.assertEqual(stop(c + "old-app\\node_modules\\dep"), c + "old-app\\node_modules")
        self.assertEqual(stop(c + "py-app\\.venv\\Lib\\site-packages"), c + "py-app\\.venv")
        self.assertEqual(stop("D\\Games\\SomeGame\\data"), "D\\Games\\SomeGame")
        self.assertEqual(stop(U + "OneDrive\\Old"), U + "OneDrive")
        # a node_modules with no package.json beside it is never walked, so nothing below it is offered
        npm = U + "scoop\\apps\\nodejs\\20.11.0\\node_modules"
        self.assertEqual(rules.context(self.env, self.pc.p(npm + "\\npm\\node_modules"))[0], rules.INSIDE)
        self.assertEqual(stop(npm + "\\npm\\node_modules"), npm)

    def test_context_of_synced_venv_like_and_online_only_folders(self):
        self.assertEqual(rules.context(self.env, self.pc.p("D\\PhoneSync\\DCIM"))[::2],
                         (rules.SYNCED, self.pc.p("D\\PhoneSync")))
        self.assertEqual(self.kind("D\\WorkCloud\\copy"), rules.SYNCED)
        self.assertEqual(self.kind(U + "Dropbox (Personal)\\Photos"), rules.SYNCED)
        self.assertEqual(self.kind(U + "Documents\\thesis-env\\data"), rules.SKIP)
        self.assertEqual(self.kind(U + "cloudy\\online-dir"), rules.SKIP)
        self.assertEqual(self.kind("D\\Games\\Shooter\\ShooterGame\\Content"), rules.PROGRAM)
        self.assertEqual(self.kind("D\\PostgreSQL\\16\\data"), rules.PROGRAM)
        self.assertEqual(self.kind("C\\inetpub\\history"), rules.WINDOWS)
        self.assertEqual(rules.context(self.env, self.pc.p(U + "Pictures"))[1], ())  # the stray package.json
        self.assertEqual(rules.context(self.env, self.pc.p("D\\Backup"))[1], ())  # the dotfiles .git

    def test_context(self):
        self.assertIsNone(self.kind("C"))
        self.assertIsNone(self.kind(U + "Downloads"))
        self.assertIsNone(self.kind(U + "code\\old-app"))
        self.assertEqual(self.kind("C\\Windows\\System32"), rules.WINDOWS)
        self.assertEqual(self.kind("C\\$Windows.~BT"), rules.WINDOWS)
        self.assertEqual(self.kind("C\\Program Files\\App"), rules.PROGRAM)
        self.assertEqual(self.kind("C\\ProgramData\\Vendor"), rules.APPDATA)
        self.assertEqual(self.kind(LO + "Google"), rules.APPDATA)
        self.assertEqual(self.kind(U + "OneDrive\\Old"), rules.SYNCED)
        self.assertEqual(self.kind(U + ".vscode\\extensions"), rules.DOT)
        self.assertEqual(self.kind("C\\Users\\other\\Pictures"), rules.SKIP)
        self.assertEqual(self.kind("C\\Users\\Public"), rules.SKIP)
        self.assertEqual(self.kind("C\\$Recycle.Bin"), rules.SKIP)
        self.assertEqual(self.kind(U + "code\\repo\\.git"), rules.SKIP)
        # (the out folder lies outside both made-up drives, so only how the walk meets it is tested)
        self.assertEqual(rules.dir_kind(self.env, self.pc.out, "out", False, False, False), rules.SKIP)

    def test_names_that_are_never_walked(self):
        k = lambda p, name, root=False: rules.dir_kind(self.env, p, name, root, False, False)  # noqa: E731
        for name in ("Program Files", "program files (x86)", "steamapps", "SteamLibrary", "Epic Games", "GOG Games",
                     "XboxGames", "Riot Games", "EA Games", "Ubisoft Game Launcher", "Amazon Games"):
            self.assertEqual(k("X:\\stuff\\" + name, name), rules.PROGRAM, name)
        self.assertEqual(k("X:\\Backup\\Users\\old\\AppData", "AppData"), rules.APPDATA)
        self.assertEqual(k("X:\\Windows", "Windows", True), rules.WINDOWS)
        self.assertEqual(k("X:\\inetpub", "inetpub", True), rules.WINDOWS)
        self.assertEqual(k("X:\\ProgramData", "ProgramData", True), rules.APPDATA)
        self.assertIsNone(k("X:\\Projects\\Windows", "Windows"))
        self.assertIsNone(k("X:\\Projects\\inetpub", "inetpub"))

    def test_onedrive_and_dropbox_named_folders_in_the_profile_are_synced(self):
        for name in ("OneDrive - Contoso", "Dropbox (Personal)", "Dropbox (Team)"):
            self.assertEqual(rules.dir_kind(self.env, self.pc.p(U + name), name, False, True, False), rules.SYNCED)
        self.assertIsNone(rules.dir_kind(self.env, self.pc.p(U + "code\\OneDrive"), "OneDrive", False, False, False))

    def test_protected(self):
        for p in ("C\\Windows\\Temp", "C\\Program Files\\App", "C\\ProgramData\\x", LO + "Packages\\a",
                  LO + "Programs\\SomeApp", U + "OneDrive\\x", "C\\Users\\other\\AppData\\Local\\Temp"):
            self.assertTrue(rules.protected(self.env, self.pc.p(p)), p)
        for p in (LO + "Temp\\old.tmp", LO + "Microsoft\\Windows\\WER\\ReportArchive", U + ".nuget\\packages"):
            self.assertFalse(rules.protected(self.env, self.pc.p(p)), p)

    def test_known_targets(self):
        got = {(t["group"], rel(self.pc, t["path"])) for t in rules.known_targets(self.env)}
        for want in [("temp", LO + "Temp"), ("crash-dumps", LO + "CrashDumps"),
                     ("browser-cache", LO + "Google\\Chrome\\User Data\\Default\\Code Cache"),
                     ("browser-cache", LO + "Microsoft\\Edge\\User Data\\ShaderCache"),
                     ("browser-cache", LO + "Opera Software\\Opera GX Stable\\Cache"),
                     ("app-cache", RO + "Code\\CachedExtensionVSIXs"), ("app-cache", RO + "Cursor\\CachedData"),
                     ("app-cache", LO + "Steam\\htmlcache\\GPUCache"), ("app-cache", RO + "UnknownApp\\Cache"),
                     ("gpu-cache", U + "AppData\\LocalLow\\NVIDIA\\PerDriverVersion\\DXCache"),
                     ("dev-cache", U + ".bun\\install\\cache"), ("dev-cache", LO + "uv\\cache")]:
            self.assertIn(want, got)
        paths = {p for _, p in got}
        self.assertFalse(any("Packages" in p or "Spotify" in p or "pnpm" in p or ".m2" in p for p in paths))
        self.assertEqual(len(paths), len(got), "one rule per path")

    def test_link_between(self):
        C = self.pc.C
        self.assertTrue(rules.link_between(C, self.pc.p(U + ".gradle\\caches")))
        self.assertTrue(rules.link_between(C, self.pc.p(U + ".gradle")))
        self.assertFalse(rules.link_between(C, self.pc.p(LO + "npm-cache")))
        self.assertFalse(rules.link_between(C, C))
        # a link above the root is the user's own choice of path: only what is below the root counts
        self.assertFalse(rules.link_between(self.pc.p(U + ".gradle"), self.pc.p(U + ".gradle\\caches")))
        with self.assertRaises(OSError):
            rules.link_between(C, self.pc.p(LO + "no-such-folder\\x"))

    def test_may_offer_empty(self):
        root = self.pc.C
        ok = lambda p: rules.may_offer_empty(self.env, self.pc.p(p), root)  # noqa: E731
        self.assertTrue(ok(U + "Documents\\old-empty"))
        for p in ("C", "C\\Users", U.rstrip("\\"), U + "Music", U + "Documents", U + "Downloads", U + "Saved Games",
                  "D\\Games"):
            self.assertFalse(ok(p), p)
        self.assertFalse(rules.may_offer_empty(self.env, self.pc.p(U + "Documents\\old-empty"),
                                               self.pc.p(U + "Documents\\old-empty")))

    def test_chromium_apps(self):
        found = {rel(self.pc, p) for p in rules.chromium_apps(self.env)}
        self.assertEqual(found, {RO + "discord", RO + "UnknownApp", LO + "SomeVendor\\ElectronApp"})


class PatternRules(unittest.TestCase):
    def test_build_rule(self):
        b = rules.build_rule
        self.assertEqual(b("node_modules", {"package.json"}, set()), ("build-node", ""))
        self.assertIsNone(b("node_modules", {"index.js"}, set()))
        self.assertEqual(b("bin", {"app.csproj"}, set())[0], "build-output")
        self.assertEqual(b("obj", {"lib.fsproj"}, set())[0], "build-output")
        self.assertIsNone(b("bin", {"package.json"}, set()))
        self.assertEqual(b("target", {"cargo.toml"}, set())[1], "Rust build output (target)")
        self.assertEqual(b("target", {"pom.xml"}, set())[1], "Maven build output (target)")
        self.assertEqual(b("build", {"build.gradle.kts"}, set())[1], "Gradle build output (build)")
        self.assertEqual(b(".gradle", {"build.gradle"}, set())[0], "build-output")
        self.assertIsNone(b("build", {"package.json"}, set()))
        for name in (".next", ".nuxt", ".svelte-kit", ".parcel-cache", ".turbo", ".angular"):
            self.assertEqual(b(name, {"package.json"}, set())[0], "build-output")
        self.assertEqual(b("Library", set(), {"assets", "projectsettings"})[1], "Unity Library")
        self.assertIsNone(b("Library", set(), {"assets"}))
        self.assertEqual(b("Intermediate", {"game.uproject"}, set())[1], "Unreal Intermediate")
        self.assertEqual(b("DerivedDataCache", {"game.uproject"}, set())[0], "build-output")
        for name in ("__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"):
            self.assertEqual(b(name, set(), set()), ("py-cache", ""))

    def test_virtual_environment_parts(self):
        v = rules.venv_only
        self.assertTrue(v({"pyvenv.cfg"}, {"lib", "scripts", "include"}))
        self.assertTrue(v({"pyvenv.cfg", ".gitignore", "cachedir.tag"}, {"lib", "lib64", "bin", "share"}))
        self.assertFalse(v({"pyvenv.cfg"}, {"lib"}))  # no Scripts or bin
        self.assertFalse(v({"pyvenv.cfg", "main.py"}, {"lib", "scripts"}))
        self.assertFalse(v({"pyvenv.cfg", "pipx_metadata.json"}, {"lib", "scripts"}))
        self.assertFalse(v({"pyvenv.cfg"}, {"lib", "scripts", ".git"}))
        self.assertFalse(v({"pyvenv.cfg"}, {"lib", "scripts", "src"}))  # pip install -e git+... clones into src

    def test_sync_markers(self):
        s = rules.is_synced_root
        for files, dirs in [({".dropbox"}, set()), (set(), {".dropbox.cache"}), (set(), {".stfolder"}),
                            (set(), {".sync"}), (set(), {".debris"}), ({".owncloudsync.log"}, set()),
                            (set(), {".tmp.drivedownload"}), ({"._sync_4f2a.db"}, set()), ({".sync_9.db"}, set())]:
            self.assertTrue(s(files, dirs), (files, dirs))
        self.assertFalse(s({"sync.db", "notes.txt"}, {"sync"}))

    def test_dropbox_folders(self):
        base = tempfile.mkdtemp(prefix="disk-cleanup-test-")
        try:
            good, bad = os.path.join(base, "info.json"), os.path.join(base, "bad.json")
            with open(good, "w", encoding="utf-8") as f:
                json.dump({"personal": {"path": "C:\\Users\\you\\Dropbox", "host": 1},
                           "business": {"path": "D:\\Dropbox (Team)"}, "other": "x"}, f)
            with open(bad, "w", encoding="utf-8") as f:
                f.write("{not json")
            self.assertEqual(sorted(rules.dropbox_folders([good, bad, os.path.join(base, "missing.json")])),
                             ["C:\\Users\\you\\Dropbox", "D:\\Dropbox (Team)"])
        finally:
            shutil.rmtree(base)

    def test_programs_and_projects(self):
        p = rules.holds_program
        self.assertTrue(p({"game.exe", "engine.dll"}, set()))
        self.assertFalse(p({"setup.exe", "notes.txt"}, set()))
        self.assertTrue(p({"shooter.exe"}, {"engine", "shootergame"}))  # Unreal: the .dll files sit in Engine
        self.assertFalse(p({"readme.txt"}, {"engine"}))
        self.assertTrue(p(set(), {".egstore", "content"}))  # Epic's install record
        self.assertTrue(p({"goggame-1207664643.info"}, set()))
        for name in ("unins000.exe", "uninstall-postgresql.exe", "uninst.exe", "Uninstall.exe".lower()):
            self.assertTrue(p({name}, set()), name)
        for files, dirs in [({"package.json"}, set()), ({"app.sln"}, set()), ({"x.uproject"}, set()),
                            ({"requirements.txt"}, set()), (set(), {".git"}), ({".git"}, set()),
                            (set(), {".hg"}), (set(), {".svn"}),
                            (set(), {"assets", "projectsettings"}), ({"settings.gradle.kts"}, set())]:
            self.assertTrue(rules.is_project(files, dirs), (files, dirs))
        self.assertFalse(rules.is_project({"readme.md"}, {"assets"}))

    def test_suggested_keeper(self):
        env = rules.Env(profile="C:\\Users\\you", local="C:\\Users\\you\\AppData\\Local",
                        roaming="C:\\Users\\you\\AppData\\Roaming", locallow="C:\\Users\\you\\AppData\\LocalLow",
                        temps=["C:\\Users\\you\\AppData\\Local\\Temp"], downloads="C:\\Users\\you\\Downloads",
                        system_root="C:\\Windows", system_drive="C:\\", program_files=["C:\\Program Files"],
                        program_data="C:\\ProgramData", synced=[], out_dir="C:\\Users\\you\\disk-cleanup")
        pick = lambda *copies: min(copies, key=lambda c: rules.keep_key(env, c[0], c[1]))[0]  # noqa: E731
        self.assertEqual(pick(("C:\\Users\\you\\Downloads\\a.jpg", 1), ("D:\\Photos\\2019\\trips\\a.jpg", 9)),
                         "D:\\Photos\\2019\\trips\\a.jpg")
        self.assertEqual(pick(("C:\\Users\\you\\Desktop\\a.jpg", 1), ("D:\\b\\a.jpg", 9)), "D:\\b\\a.jpg")
        self.assertEqual(pick(("D:\\p\\a (1).jpg", 1), ("D:\\p\\a.jpg", 9)), "D:\\p\\a.jpg")
        self.assertEqual(pick(("D:\\p\\a - Copy.jpg", 1), ("D:\\p\\longer\\a.jpg", 9)), "D:\\p\\longer\\a.jpg")
        self.assertEqual(pick(("D:\\p\\Copy of a.jpg", 1), ("D:\\q\\a.jpg", 9)), "D:\\q\\a.jpg")
        self.assertEqual(pick(("D:\\p\\a.jpg", 5), ("D:\\q\\a.jpg", 2)), "D:\\q\\a.jpg")
        self.assertEqual(pick(("D:\\pp\\a.jpg", 5), ("D:\\q\\a.jpg", 5)), "D:\\q\\a.jpg")
        self.assertEqual(pick(("D:\\q\\a.jpg", 5), ("D:\\p\\a.jpg", 5)), "D:\\p\\a.jpg")

    def test_large_label_follows_the_setting(self):
        self.assertEqual(rules.label("large-old"), "Large files not changed in 6 months (pick the ones to remove)")
        self.assertEqual(rules.label("large-old", 30), "Large files not changed in 30 days (pick the ones to remove)")
        self.assertEqual(rules.label("temp", 30), "Temporary files older than 7 days")


class Locations(unittest.TestCase):
    def test_temp_guard(self):
        pc_like = dict(profile="C:\\Users\\you", local="C:\\Users\\you\\AppData\\Local",
                       roaming="C:\\Users\\you\\AppData\\Roaming", locallow="C:\\Users\\you\\AppData\\LocalLow",
                       downloads="C:\\Users\\you\\Downloads", system_root="C:\\Windows", system_drive="C:\\",
                       program_files=["C:\\Program Files"], program_data="C:\\ProgramData",
                       synced=["C:\\Users\\you\\OneDrive"], out_dir="C:\\Users\\you\\disk-cleanup")
        env = rules.Env(temps=["C:\\", "D:\\", "C:\\Users", "C:\\Users\\you", "C:\\Windows\\Temp", "D:\\Data",
                               "C:\\Users\\you\\OneDrive\\Temp", "C:\\Users\\you\\AppData\\Local",
                               "C:\\Users\\you\\AppData\\Local\\Temp", "c:\\users\\you\\appdata\\local\\temp",
                               "C:\\Users\\you\\AppData\\Local\\Temp\\2", "D:\\tmp"], **pc_like)
        self.assertEqual(env.temps, ["C:\\Users\\you\\AppData\\Local\\Temp", "C:\\Users\\you\\AppData\\Local\\Temp\\2",
                                     "D:\\tmp"])

    def test_from_system(self):
        env = rules.Env.from_system()
        self.assertTrue(os.path.isdir(env.profile))
        self.assertTrue(env.temps)
        self.assertTrue(all("~" not in t for t in env.temps), "short names are expanded")
        self.assertTrue(os.path.isdir(env.downloads))
        self.assertEqual(env.out_dir, os.path.join(env.profile, "disk-cleanup"))
        self.assertTrue(rules.is_under(env.local, env.profile) or os.path.isdir(env.local))
        self.assertTrue(env.system_drive.endswith("\\"))
        self.assertTrue(env.program_files)


if __name__ == "__main__":
    unittest.main()
