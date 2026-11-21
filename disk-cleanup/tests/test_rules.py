"""Locations, path comparison, areas and the known-location rule tables."""
import os
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
        return rules.context(self.env, self.pc.p(rel_path))

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
        self.assertEqual(self.kind("out"), rules.SKIP)
        self.assertEqual(rules.dir_kind(self.env, self.pc.out, "out", False, False, False), rules.SKIP)

    def test_onedrive_named_folders_in_the_profile_are_synced(self):
        self.assertEqual(rules.dir_kind(self.env, self.pc.p(U + "OneDrive - Contoso"), "OneDrive - Contoso",
                                        False, True, False), rules.SYNCED)
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

    def test_chromium_apps(self):
        found = {rel(self.pc, p) for p in rules.chromium_apps(self.env)}
        self.assertEqual(found, {RO + "discord", RO + "UnknownApp", LO + "SomeVendor\\ElectronApp"})


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
