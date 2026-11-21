"""The scan on a made-up PC: every offered group finds its items and nothing else, protected
places are never offered, links are never followed and an unreadable folder does not stop it."""
import os
import time
import unittest

from fixture import KB, PC, FakeWin
from helpers import LO, RO, U, all_items, group, item_paths, rel, run_scan, skipped
import rules
import scan


class ScanDriveC(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pc = PC()
        cls.sc, cls.report = run_scan(cls.pc, cls.pc.C, win=FakeWin(bin_size=5 * KB, bin_items=2))

    @classmethod
    def tearDownClass(cls):
        cls.pc.cleanup()

    def paths(self, gid):
        return item_paths(self.pc, self.report, gid)

    def test_temp_offers_old_children_only(self):
        t = LO + "Temp\\"
        self.assertEqual(self.paths("temp"), {t + "old.tmp", t + "old-folder", t + "deep-old"})
        self.assertEqual(skipped(self.pc, self.report, "temp"),
                         {t + "linked-folder": rules.LINKS, t + "online-folder": rules.ONLINE})
        self.assertEqual(group(self.report, "temp")["safety"], "safe")

    def test_temp_folder_deeper_than_260_characters_is_read(self):
        self.assertGreater(len(self.pc.deep_file), 300)
        deep = next(i for i in group(self.report, "temp")["items"] if i["path"].endswith("deep-old"))
        self.assertEqual(deep["size"], 5 * KB)
        self.assertEqual(deep["kind"], "dir")

    def test_crash_dumps(self):
        self.assertEqual(self.paths("crash-dumps"), {LO + "CrashDumps\\app.exe.1234.dmp",
                                                     LO + "Microsoft\\Windows\\WER\\ReportArchive\\AppCrash_x"})
        self.assertEqual(group(self.report, "crash-dumps")["safety"], "safe")

    def test_browser_caches(self):
        ud = LO + "Google\\Chrome\\User Data\\"
        ff = LO + "Mozilla\\Firefox\\Profiles\\abc.default-release\\"
        self.assertEqual(self.paths("browser-cache"), {
            ud + "Default\\Cache", ud + "Default\\Code Cache", ud + "Default\\GPUCache", ud + "Profile 1\\Cache",
            ud + "ShaderCache", ff + "cache2", ff + "startupCache"})
        g = group(self.report, "browser-cache")
        self.assertEqual(g["safety"], "safe")
        default = next(i for i in g["items"] if i["path"].endswith("Default\\Cache"))
        self.assertEqual((default["note"], default["process"]), ("Chrome, Default profile", "chrome.exe"))
        self.assertEqual(default["size"], 4 * KB)
        self.assertTrue(all(i["process"] == "firefox.exe" for i in g["items"] if "Mozilla" in i["path"]))

    def test_app_caches_with_the_signature_rule(self):
        self.assertEqual(self.paths("app-cache"), {
            RO + "discord\\Cache", RO + "discord\\Code Cache", RO + "discord\\GPUCache",
            RO + "UnknownApp\\Cache", RO + "UnknownApp\\Code Cache", RO + "UnknownApp\\GPUCache",
            LO + "SomeVendor\\ElectronApp\\Code Cache", LO + "SomeVendor\\ElectronApp\\GPUCache"})
        g = group(self.report, "app-cache")
        by = {rel(self.pc, i["path"]): i for i in g["items"]}
        self.assertEqual(by[RO + "discord\\Cache"]["process"], "Discord.exe")
        self.assertEqual((by[RO + "UnknownApp\\GPUCache"]["note"], by[RO + "UnknownApp\\GPUCache"]["process"]),
                         ("UnknownApp", None))

    def test_gpu_and_dev_caches(self):
        self.assertEqual(self.paths("gpu-cache"), {LO + "NVIDIA\\DXCache"})
        self.assertEqual(group(self.report, "gpu-cache")["note"], "The first game start after this may be slower.")
        self.assertEqual(self.paths("dev-cache"), {LO + "npm-cache", U + ".nuget\\packages"})
        self.assertEqual(group(self.report, "dev-cache")["safety"], "redo")

    def test_downloads(self):
        self.assertEqual(self.paths("downloads"), {U + "Downloads\\old-setup.exe", U + "Downloads\\movie.mp4.crdownload"})
        g = group(self.report, "downloads")
        self.assertEqual(g["safety"], "redo")
        self.assertTrue(all(i["kind"] == "file" for i in g["items"]))

    def test_only_these_groups(self):
        self.assertEqual({g["id"] for g in self.report["groups"]},
                         {"temp", "crash-dumps", "browser-cache", "app-cache", "gpu-cache", "dev-cache", "downloads"})

    def test_never_offered(self):
        never = ["C\\Windows", "C\\Program Files", "C\\ProgramData", "C\\$Windows.~BT", "C\\$Recycle.Bin",
                 LO + "Packages", LO + "Programs", U + ".vscode", U + ".claude", U + "OneDrive", "C\\Users\\other",
                 "C\\Users\\Public", LO + "Google\\Chrome\\User Data\\System Profile", "outside"]
        listed = [s["path"] for g in self.report["groups"] + self.report["left_out"] for s in g["skipped"]]
        for p in [i["path"] for i in all_items(self.report)] + listed:
            r = rel(self.pc, p)
            for n in never:
                self.assertFalse(r == n or r.startswith(n + "\\"), r)
            self.assertNotIn("History", r)
            self.assertNotIn("Local Storage", r)

    def test_precious_is_never_counted(self):
        # the junction in the temp folder is not followed: its folder holds only a.txt (100 bytes)
        temp = next(g for g in self.report["groups"] if g["id"] == "temp")
        linked = next(s for s in temp["skipped"] if s["path"].endswith("linked-folder"))
        self.assertEqual(linked["size"], 100)
        self.assertTrue(os.path.exists(self.pc.precious))

    def test_not_offered_list(self):
        w = {x["id"]: x for x in self.report["windows"]}
        self.assertEqual(set(w), {"recycle-bin", "windows-update", "windows-temp", "system-dumps", "system-wer",
                                  "old-windows", "thumbnails", "inet-cache"})
        self.assertEqual(w["recycle-bin"]["size"], 5 * KB)
        self.assertEqual(w["windows-update"]["size"], 2 * KB)
        self.assertEqual(w["system-dumps"]["size"], 3 * KB)
        self.assertEqual([rel(self.pc, p) for p in w["system-dumps"]["paths"]], ["C\\Windows\\Minidump"])
        self.assertEqual(w["old-windows"]["size"], 2 * KB)
        self.assertEqual(w["thumbnails"]["size"], KB)
        self.assertEqual(w["inet-cache"]["tool"], "Disk Cleanup (run cleanmgr), Temporary Internet Files")

    def test_access_denied_folder_is_counted_and_the_scan_finishes(self):
        un = self.report["unreadable"]
        self.assertEqual((un["count"], un["denied"]), (1, 1))
        self.assertEqual([rel(self.pc, p) for p in un["examples"]], [U + "Documents\\locked"])

    def test_numbers_follow_display_order(self):
        groups = self.report["groups"]
        self.assertEqual([g["n"] for g in groups], list(range(1, len(groups) + 1)))
        keys = [(rules.SAFETY_ORDER.index(g["safety"]), -g["size"]) for g in groups]
        self.assertEqual(keys, sorted(keys))
        nums = [i["n"] for i in all_items(self.report)]
        self.assertEqual(nums, list(range(1, len(nums) + 1)))
        for g in groups:
            sizes = [i["size"] for i in g["items"]]
            self.assertEqual(sizes, sorted(sizes, reverse=True))
            self.assertEqual(g["size"], sum(sizes))
            self.assertEqual(g["count"], len(sizes))

    def test_report_shape(self):
        r = self.report
        self.assertEqual((r["tool"], r["version"]), ("disk-cleanup", 1))
        self.assertEqual(r["root"], self.pc.C)
        self.assertEqual(r["profile"], self.pc.profile)
        self.assertEqual(r["settings"], {"dupe_min_mb": 1, "large_mb": 500, "large_days": 180})
        self.assertLess(abs(r["created_ts"] - time.time()), 600)
        item = all_items(r)[0]
        self.assertEqual(list(item)[:6], ["n", "path", "kind", "size", "mtime", "note"])

    def test_four_worker_threads(self):
        self.assertEqual(len(self.sc.threads), 4)


class ScanOtherRoots(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pc = PC()

    @classmethod
    def tearDownClass(cls):
        cls.pc.cleanup()

    def test_one_worker_finds_the_same(self):
        _, a = run_scan(self.pc, self.pc.C, workers=1)
        _, b = run_scan(self.pc, self.pc.C, workers=4)
        strip = lambda r: sorted((g["id"], sorted(i["path"] for i in g["items"])) for g in r["groups"])  # noqa: E731
        self.assertEqual(strip(a), strip(b))

    def test_workers_are_clamped(self):
        self.assertEqual(scan.Scanner(self.pc.env(), FakeWin(), self.pc.C, workers=9).workers, 4)
        self.assertEqual(scan.Scanner(self.pc.env(), FakeWin(), self.pc.C, workers=0).workers, 1)
        sc, _ = run_scan(self.pc, self.pc.D, workers=2)
        self.assertEqual(len(sc.threads), 2)

    def test_root_inside_appdata_measures_known_places_only(self):
        _, r = run_scan(self.pc, self.pc.local)
        ids = {g["id"] for g in r["groups"]}
        self.assertTrue({"temp", "browser-cache", "gpu-cache", "crash-dumps"} <= ids)
        self.assertNotIn("downloads", ids)
        self.assertNotIn("recycle-bin", {w["id"] for w in r["windows"]})
        self.assertEqual(r["stats"]["files"] > 0, True)

    def test_root_inside_windows_offers_nothing(self):
        _, r = run_scan(self.pc, os.path.join(self.pc.C, "Windows"))
        self.assertEqual(r["groups"], [])
        self.assertEqual({w["id"] for w in r["windows"]}, {"windows-update", "windows-temp", "system-dumps"})

    def test_another_users_profile_is_not_read(self):
        _, r = run_scan(self.pc, os.path.join(self.pc.C, "Users", "other"))
        self.assertEqual((r["groups"], r["stats"]["files"]), ([], 0))

    def test_drive_d_offers_nothing_yet_and_reads_no_link(self):
        _, r = run_scan(self.pc, self.pc.D)
        self.assertEqual(r["groups"], [])
        self.assertEqual([w["id"] for w in r["windows"]], ["recycle-bin"])

    def test_temp_pointing_at_a_drive_root_is_not_used(self):
        # (a TEMP not named like a temp folder is refused too; see test_rules, since this fixture
        # itself lives in a temp folder)
        env = self.pc.env(temps=[self.pc.C, self.pc.D, self.pc.profile, os.path.join(self.pc.C, "Users"),
                                 os.path.join(self.pc.C, "Windows", "Temp"), os.path.join(self.pc.profile, "OneDrive")])
        self.assertEqual(env.temps, [])
        _, r = run_scan(self.pc, self.pc.C, env=env)
        self.assertIsNone(group(r, "temp"))

    def test_temp_folder_that_is_also_tmp_is_never_offered(self):
        inner = os.path.join(self.pc.local, "Temp", "old-folder")
        env = self.pc.env(temps=[os.path.join(self.pc.local, "Temp"), inner])
        _, r = run_scan(self.pc, self.pc.C, env=env)
        self.assertNotIn(LO + "Temp\\old-folder", item_paths(self.pc, r, "temp"))

    def test_progress_is_printed_while_it_runs(self):
        seen = []
        sc = scan.Scanner(self.pc.env(), FakeWin(), self.pc.C, progress=lambda *a: seen.append(a), every=0.01)
        slow = sc.plan

        def plan():
            time.sleep(0.3)
            slow()
        sc.plan = plan
        sc.run()
        self.assertTrue(seen)
        self.assertEqual(len(seen[0]), 3)


if __name__ == "__main__":
    unittest.main()
