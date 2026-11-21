"""The scan on a made-up PC: every offered group finds its items and nothing else, protected
places are never offered, links are never followed and an unreadable folder does not stop it."""
import msvcrt
import os
import time
import unittest
from unittest import mock

from fixture import KB, PC, FakeWin
from helpers import LO, RO, U, all_items, group, item_paths, rel, run_scan, skipped
import rules
import scan

SMALL = dict(dupe_min_mb=0.01, large_mb=0.2)  # 10 KB and 200 KB, so the fixture can stay small
CODE = U + "code\\"


def listed(report):
    """Every path the report names, offered or skipped."""
    return [i["path"] for i in all_items(report)] + [s["path"] for g in report["groups"] + report["left_out"]
                                                       for s in g["skipped"]]


class ScanDriveC(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pc = PC()
        cls.sc, cls.report = run_scan(cls.pc, cls.pc.C, win=FakeWin(bin_size=5 * KB, bin_items=2), **SMALL)

    @classmethod
    def tearDownClass(cls):
        cls.pc.cleanup()

    def paths(self, gid):
        return item_paths(self.pc, self.report, gid)

    def nothing_under(self, *prefixes, skipped_too=True):
        for p in listed(self.report) if skipped_too else [i["path"] for i in all_items(self.report)]:
            r = rel(self.pc, p)
            for n in prefixes:
                self.assertFalse(r == n or r.startswith(n + "\\"), r)

    def test_temp_offers_old_children_only(self):
        t = LO + "Temp\\"
        self.assertEqual(self.paths("temp"), {t + "old.tmp", t + "ancient.tmp", t + "old-folder", t + "deep-old"})
        self.assertEqual(skipped(self.pc, self.report, "temp"), {
            t + "linked-folder": rules.LINKS, t + "online-folder": rules.ONLINE, t + "offline-child": rules.ONLINE,
            t + "holds-offline": rules.ONLINE, t + "spaced-folder ": rules.ODD, t + "dotted-file.": rules.ODD})
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
        self.assertEqual((default["note"], default["process"]), ("Chrome, Default", "chrome.exe"))
        self.assertEqual(default["size"], 4 * KB)
        fire = [i for i in g["items"] if "Mozilla" in i["path"]]
        self.assertTrue(all(i["process"] == "firefox.exe" and i["note"] == "Firefox, abc.default-release" for i in fire))

    def test_app_caches_with_the_signature_rule(self):
        self.assertEqual(self.paths("app-cache"), {
            RO + "discord\\Cache", RO + "discord\\Code Cache", RO + "discord\\GPUCache",
            RO + "UnknownApp\\Cache", RO + "UnknownApp\\Code Cache", RO + "UnknownApp\\GPUCache",
            LO + "SomeVendor\\ElectronApp\\Code Cache", LO + "SomeVendor\\ElectronApp\\GPUCache"})
        by = {rel(self.pc, i["path"]): i for i in group(self.report, "app-cache")["items"]}
        self.assertEqual(by[RO + "discord\\Cache"]["process"], "Discord.exe")
        self.assertEqual((by[RO + "UnknownApp\\GPUCache"]["note"], by[RO + "UnknownApp\\GPUCache"]["process"]),
                         ("UnknownApp", None))

    def test_gpu_and_dev_caches(self):
        self.assertEqual(self.paths("gpu-cache"), {LO + "NVIDIA\\DXCache"})
        self.assertEqual(group(self.report, "gpu-cache")["note"], "The first game start after this may be slower.")
        self.assertEqual(self.paths("dev-cache"), {LO + "npm-cache", U + ".nuget\\packages"})
        self.assertEqual(group(self.report, "dev-cache")["safety"], "redo")

    def test_known_location_behind_a_junction_is_not_offered(self):
        # .gradle is a junction to a folder outside the scan root: its caches are listed, never measured
        self.assertEqual(skipped(self.pc, self.report, "dev-cache"), {U + ".gradle\\caches": rules.LINKS})
        self.assertEqual([s["size"] for s in group(self.report, "dev-cache")["skipped"]], [0])
        self.assertFalse(any("gradle" in i["path"] for i in all_items(self.report)))
        self.assertTrue(os.path.exists(self.pc.big_jar))

    def test_downloads(self):
        self.assertEqual(self.paths("downloads"), {U + "Downloads\\old-setup.exe", U + "Downloads\\movie.mp4.crdownload"})
        g = group(self.report, "downloads")
        self.assertEqual(g["safety"], "redo")
        self.assertTrue(all(i["kind"] == "file" for i in g["items"]))

    def test_node_modules_by_project_age(self):
        self.assertEqual(self.paths("build-node"), {CODE + "old-app\\node_modules"})
        # the monorepo's only recent change is inside one of its packages: its node_modules stays;
        # copied-app's files were copied in today with old modified times
        self.assertEqual(skipped(self.pc, self.report, "build-node"), {
            CODE + "new-app\\node_modules": rules.RECENT, CODE + "mono\\node_modules": rules.RECENT,
            CODE + "copied-app\\node_modules": rules.RECENT, CODE + "linked-app\\node_modules": rules.LINKS})
        g = group(self.report, "build-node")
        self.assertEqual((g["safety"], g["note"]), ("redo", "npm install brings it back."))

    def test_node_modules_without_package_json_beside_it_is_left_alone(self):
        # npm's own bundled packages in a Node.js zip, and global packages under a custom prefix
        self.nothing_under(U + "scoop", U + "npm-global")

    def test_other_build_output(self):
        self.assertEqual(self.paths("build-output"), {CODE + "dotnet-app\\bin", CODE + "dotnet-app\\obj",
                                                      CODE + "rust-app\\target"})
        notes = {rel(self.pc, i["path"]): i["note"] for i in group(self.report, "build-output")["items"]}
        self.assertEqual(notes[CODE + "dotnet-app\\bin"], ".NET build output (bin)")
        self.assertEqual(notes[CODE + "rust-app\\target"], "Rust build output (target)")
        # the solution around the project was committed 8 days ago, so its projects count as changed
        shop = CODE + "sln\\src\\Shop\\"
        self.assertEqual(skipped(self.pc, self.report, "build-output"),
                         {shop + "bin": rules.RECENT, shop + "obj": rules.RECENT})

    def test_python_caches_and_virtual_environments(self):
        self.assertEqual(self.paths("py-cache"), {CODE + "py-app\\__pycache__", CODE + "py-app\\.pytest_cache"})
        self.assertEqual(group(self.report, "py-cache")["safety"], "safe")
        self.assertEqual(self.paths("py-venv"), {CODE + "py-app\\.venv", U + "envs\\old-env", CODE + "tool-proj\\tools\\venv"})
        self.assertEqual(skipped(self.pc, self.report, "py-venv"), {
            U + "envs\\new-env": rules.RECENT_OWN, U + "Documents\\thesis-env": rules.NOT_ONLY_VENV,
            U + "pipx\\venvs\\black": rules.NOT_ONLY_VENV, CODE + "old-tool": rules.NOT_ONLY_VENV})
        g = group(self.report, "py-venv")
        self.assertEqual((g["safety"], g["note"]),
                         ("redo", "Reinstall packages with pip install -r requirements.txt."))

    def test_folders_with_a_pyvenv_cfg_and_other_files_are_never_entered(self):
        mixed = [U + "Documents\\thesis-env", U + "pipx\\venvs\\black", CODE + "old-tool"]
        for p in listed(self.report):
            r = rel(self.pc, p)
            self.assertFalse(any(r.startswith(m + "\\") for m in mixed), r)
        self.assertTrue(all(s["size"] == 0 for s in group(self.report, "py-venv")["skipped"]
                            if s["reason"] == rules.NOT_ONLY_VENV))
        # a shell folder holding nothing but a virtual environment is never offered either
        self.nothing_under(U + "Saved Games")

    def test_duplicates_are_listed_copy_by_copy(self):
        g = group(self.report, "duplicates")
        self.assertEqual(g["safety"], "check")
        self.assertEqual([rel(self.pc, i["path"]) for i in g["items"]],
                         [U + "Pictures\\beach.jpg", U + "Downloads\\beach (1).jpg", U + "Pictures\\Backup\\beach.jpg"])
        self.assertEqual([i["suggest_keep"] for i in g["items"]], [True, False, False])
        self.assertEqual({i["set"] for i in g["items"]}, {1})
        self.assertEqual(len({i["hash"] for i in g["items"]}), 1)
        self.assertEqual(len(g["items"][0]["hash"]), 64)
        first = g["items"][0]
        self.assertEqual(sorted(first["same_as"]), sorted(i["path"] for i in g["items"][1:]))
        self.assertEqual((g["size"], g["count"]), (2 * 20 * KB, 3))

    def test_duplicates_never_hard_links_projects_or_synced_folders(self):
        paths = item_paths(self.pc, self.report, "duplicates")
        for p in paths:
            self.assertFalse("hard" in p or "OneDrive" in p or "Dropbox" in p or "code" in p or "cloudy" in p, p)

    def test_svn_and_mercurial_working_copies_are_projects(self):
        # their identical images are not duplicates and SVN's versioned empty folders are not offered
        self.nothing_under(CODE + "svn-site", CODE + "hg-site")

    def test_online_only_folders_are_never_entered(self):
        self.nothing_under(U + "cloudy")
        self.assertFalse(any("cloudy" in p for p, _, _ in self.sc.dupes))  # its identical pair was never seen

    def test_ages_use_the_newer_of_modified_and_created(self):
        self.assertNotIn(LO + "Temp\\extracted-today.txt", self.paths("temp"))
        self.assertNotIn(U + "Downloads\\copied-setup.exe", self.paths("downloads"))
        self.assertNotIn(U + "Videos\\copied-movie.mp4", self.paths("large-old"))
        self.assertNotIn(U + "Documents\\made-today", self.paths("empty"))

    def test_a_stray_marker_in_the_profile_does_not_make_it_a_project(self):
        self.assertEqual(rules.context(self.pc.env(), self.pc.p(U + "Pictures"))[1], ())
        self.assertIn(U + "Pictures\\Backup\\beach.jpg", self.paths("duplicates"))

    def test_large_old_files(self):
        self.assertEqual(self.paths("large-old"), {U + "Videos\\old-trip.mp4", CODE + "old-app\\assets\\intro.mp4"})
        g = group(self.report, "large-old")
        self.assertEqual(g["safety"], "check")
        self.assertTrue(all(i["kind"] == "file" and i["size"] == 300 * KB for i in g["items"]))

    def test_empty_folders(self):
        # nested old empty folders: only the top one; Music is a shell folder; new-empty is too new;
        # made-today was created today; Dropbox's and inetpub's empty folders are never walked
        self.assertEqual(self.paths("empty"), {U + "Documents\\old-empty"})
        self.assertEqual(group(self.report, "empty")["safety"], "safe")

    def test_only_these_groups(self):
        self.assertEqual({g["id"] for g in self.report["groups"]}, set(rules.GROUPS))

    def test_never_offered(self):
        self.nothing_under("C\\Windows", "C\\Program Files", "C\\ProgramData", "C\\$Windows.~BT", "C\\$Recycle.Bin",
                           "C\\inetpub", LO + "Packages", LO + "Programs", U + ".vscode", U + ".claude", U + "OneDrive",
                           U + "Dropbox (Personal)", "C\\Users\\other", "C\\Users\\Public",
                           LO + "Google\\Chrome\\User Data\\System Profile", "outside", U + ".gradle\\caches\\modules-2",
                           CODE + "repo", U + "Pictures\\hard1.jpg", U + "Pictures\\hard2.jpg", U + "Music",
                           U + "Documents\\new-empty", U + "Documents\\locked")
        for p in listed(self.report):
            self.assertNotIn("History", p)
            self.assertNotIn("Local Storage", p)

    def test_precious_is_never_counted(self):
        # the junctions are not followed: the temp folder holding one has only a.txt (100 bytes),
        # the node_modules holding the other only index.js (4 KB)
        sizes = {rel(self.pc, s["path"]): s["size"] for g in self.report["groups"] + self.report["left_out"]
                 for s in g["skipped"]}
        self.assertEqual(sizes[LO + "Temp\\linked-folder"], 100)
        self.assertEqual(sizes[CODE + "linked-app\\node_modules"], 4 * KB)
        self.assertTrue(os.path.exists(self.pc.precious))

    def test_not_offered_list(self):
        w = {x["id"]: x for x in self.report["windows"]}
        self.assertEqual(set(w), {"recycle-bin", "windows-update", "windows-temp", "system-dumps", "system-wer",
                                  "old-windows", "thumbnails", "inet-cache", "programs", "synced"})
        self.assertEqual(w["recycle-bin"]["size"], 5 * KB)
        self.assertEqual(w["windows-update"]["size"], 2 * KB)
        self.assertEqual(w["system-dumps"]["size"], 3 * KB)
        self.assertEqual([rel(self.pc, p) for p in w["system-dumps"]["paths"]], ["C\\Windows\\Minidump"])
        self.assertEqual(w["old-windows"]["size"], 2 * KB)
        self.assertEqual(w["thumbnails"]["size"], KB)
        self.assertEqual(w["inet-cache"]["tool"], "Disk Cleanup (run cleanmgr), Temporary Internet Files")

    def test_programs_and_synced_folders_are_only_listed(self):
        w = {x["id"]: x for x in self.report["windows"]}
        self.assertEqual({rel(self.pc, p["path"]) for p in w["programs"]["parts"]},
                         {"C\\Program Files", "C\\Program Files (x86)", LO + "Programs"})
        self.assertEqual(w["programs"]["size"], sum(p["size"] for p in w["programs"]["parts"]))
        self.assertEqual([(rel(self.pc, p["path"]), p["size"]) for p in w["synced"]["parts"]],
                         [(U + "Dropbox (Personal)", 50 * KB), (U + "OneDrive", 40 * KB)])
        self.assertTrue(w["synced"]["tool"].startswith("Removing files here removes them on your other devices too."))

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
            self.assertEqual(g["count"], len(sizes))
            if g["id"] != "duplicates":
                self.assertEqual(sizes, sorted(sizes, reverse=True))
                self.assertEqual(g["size"], sum(sizes))

    def test_report_shape(self):
        r = self.report
        self.assertEqual((r["tool"], r["version"]), ("disk-cleanup", 1))
        self.assertEqual(r["root"], self.pc.C)
        self.assertEqual(r["profile"], self.pc.profile)
        self.assertEqual(r["settings"], {"dupe_min_mb": 0.01, "large_mb": 0.2, "large_days": 180})
        self.assertLess(abs(r["created_ts"] - time.time()), 600)
        item = all_items(r)[0]
        self.assertEqual(list(item)[:7], ["n", "path", "kind", "size", "mtime", "note", "process"])

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
        _, a = run_scan(self.pc, self.pc.C, workers=1, **SMALL)
        _, b = run_scan(self.pc, self.pc.C, workers=4, **SMALL)
        strip = lambda r: sorted((g["id"], [i["path"] for i in g["items"]]) for g in r["groups"])  # noqa: E731
        self.assertEqual(strip(a), strip(b))

    def test_workers_are_clamped(self):
        self.assertEqual(scan.Scanner(self.pc.env(), FakeWin(), self.pc.C, workers=9).workers, 4)
        self.assertEqual(scan.Scanner(self.pc.env(), FakeWin(), self.pc.C, workers=0).workers, 1)
        sc, _ = run_scan(self.pc, self.pc.D, workers=2)
        self.assertEqual(len(sc.threads), 2)

    def test_hashing_uses_the_same_number_of_threads(self):
        seen = []
        real = scan.ThreadPoolExecutor

        def pool(max_workers):
            seen.append(max_workers)
            return real(max_workers=max_workers)
        with mock.patch.object(scan, "ThreadPoolExecutor", pool):
            run_scan(self.pc, self.pc.C, workers=3, **SMALL)
        self.assertEqual(seen, [3])

    def test_root_inside_appdata_measures_known_places_only(self):
        _, r = run_scan(self.pc, self.pc.local, **SMALL)
        ids = {g["id"] for g in r["groups"]}
        self.assertTrue({"temp", "browser-cache", "gpu-cache", "crash-dumps"} <= ids)
        self.assertFalse(ids & {"downloads", "build-node", "duplicates", "large-old", "empty"})
        w = {x["id"]: x for x in r["windows"]}
        self.assertNotIn("recycle-bin", w)
        self.assertEqual([rel(self.pc, p) for p in w["programs"]["paths"]], [LO + "Programs"])

    def test_root_inside_windows_offers_nothing(self):
        _, r = run_scan(self.pc, os.path.join(self.pc.C, "Windows"), **SMALL)
        self.assertEqual(r["groups"], [])
        self.assertEqual({w["id"] for w in r["windows"]}, {"windows-update", "windows-temp", "system-dumps"})

    def test_another_users_profile_is_not_read(self):
        _, r = run_scan(self.pc, os.path.join(self.pc.C, "Users", "other"), **SMALL)
        self.assertEqual((r["groups"], r["stats"]["files"]), ([], 0))

    def test_drive_d(self):
        _, r = run_scan(self.pc, self.pc.D, **SMALL)
        # the dotfiles .git and the stray installer files in the root do not make D a project or a program
        self.assertEqual([g["id"] for g in r["groups"]], ["duplicates"])
        self.assertEqual(item_paths(self.pc, r, "duplicates"), {"D\\Backup\\photo.jpg", "D\\Backup\\old\\photo.jpg"})
        w = {x["id"]: x for x in r["windows"]}
        self.assertEqual(set(w), {"recycle-bin", "programs", "synced"})
        self.assertEqual({rel(self.pc, p) for p in w["programs"]["paths"]},
                         {"D\\Games\\SomeGame", "D\\Games\\Shooter", "D\\PostgreSQL\\16", "D\\GOGLib\\Witcher",
                          "D\\Amazon Games", "D\\SteamLibrary"})
        self.assertEqual({rel(self.pc, p) for p in w["synced"]["paths"]}, {"D\\Dropbox", "D\\PhoneSync", "D\\WorkCloud"})

    def test_root_inside_a_program_folder(self):
        _, r = run_scan(self.pc, os.path.join(self.pc.D, "Games", "SomeGame", "data"), **SMALL)
        self.assertEqual(r["groups"], [])
        self.assertEqual([rel(self.pc, p) for p in {x["id"]: x for x in r["windows"]}["programs"]["paths"]],
                         ["D\\Games\\SomeGame\\data"])

    def test_root_that_is_or_is_inside_a_rule_target_offers_nothing(self):
        for root in (CODE + "old-app\\node_modules", CODE + "old-app\\node_modules\\dep", CODE + "py-app\\.venv",
                     CODE + "py-app\\.venv\\Lib", CODE + "dotnet-app\\bin\\Debug",
                     U + "scoop\\apps\\nodejs\\20.11.0\\node_modules\\npm", U + "Documents\\thesis-env\\data"):
            _, r = run_scan(self.pc, self.pc.p(root), **SMALL)
            self.assertEqual(r["groups"], [], root)

    def test_root_inside_a_sync_folder_is_only_listed(self):
        _, r = run_scan(self.pc, self.pc.p("D\\PhoneSync\\DCIM"), **SMALL)
        self.assertEqual(r["groups"], [])
        self.assertEqual([rel(self.pc, p) for p in {x["id"]: x for x in r["windows"]}["synced"]["paths"]],
                         ["D\\PhoneSync\\DCIM"])

    def test_venv_whose_project_reaches_above_the_root_is_left_out(self):
        # the project (tool-proj) starts above the scanned folder, so its recent changes may lie outside it
        _, r = run_scan(self.pc, self.pc.p(CODE + "tool-proj\\tools"), **SMALL)
        self.assertIsNone(group(r, "py-venv"))
        self.assertEqual(skipped(self.pc, r, "py-venv"), {CODE + "tool-proj\\tools\\venv": rules.OUTSIDE})

    def test_build_output_of_a_solution_that_starts_above_the_root_is_left_out(self):
        _, r = run_scan(self.pc, self.pc.p(CODE + "sln\\src"), **SMALL)
        self.assertIsNone(group(r, "build-output"))
        shop = CODE + "sln\\src\\Shop\\"
        self.assertEqual(skipped(self.pc, r, "build-output"), {shop + "bin": rules.OUTSIDE, shop + "obj": rules.OUTSIDE})

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
        self.assertEqual((seen[0][0], len(seen[0])), ("walk", 4))

    def test_own_dates_when_no_project_has_any(self):
        sc = scan.Scanner(self.pc.env(), FakeWin(), self.pc.C)
        now = sc.now
        for path, latest in ((self.pc.p(U + "node_modules"), now - 2 * rules.DAY),
                             (self.pc.p(U + "old\\node_modules"), now - 90 * rules.DAY)):
            sc.add("build-node", path, "dir", 1, latest, latest=latest)
        sc.apply_recency()
        self.assertEqual([c["skip"] for c in sc.cands], [rules.RECENT_OWN, None])


class Changes(unittest.TestCase):
    """Cases that change the made-up PC for one test, each on a PC of its own."""

    def setUp(self):
        self.pc = PC()

    def tearDown(self):
        self.pc.cleanup()

    def test_downloads_holding_a_program_is_a_program(self):
        self.pc.file(U + "Downloads\\helper.dll")
        _, r = run_scan(self.pc, self.pc.C, **SMALL)
        self.assertIsNone(group(r, "downloads"))
        programs = {x["id"]: x for x in r["windows"]}["programs"]["paths"]
        self.assertIn(U + "Downloads", {rel(self.pc, p) for p in programs})
        self.assertNotIn(U + "Downloads\\beach (1).jpg", item_paths(self.pc, r, "duplicates"))

    def test_a_locked_copy_drops_out_of_its_set(self):
        path = self.pc.p(U + "Pictures\\Backup\\beach.jpg")
        f = open(path, "r+b")
        try:
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 20 * KB)
            _, r = run_scan(self.pc, self.pc.C, **SMALL)
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 20 * KB)
        finally:
            f.close()
        self.assertEqual(item_paths(self.pc, r, "duplicates"), {U + "Pictures\\beach.jpg", U + "Downloads\\beach (1).jpg"})

    def test_the_real_place_of_a_linked_program_folder_is_protected(self):
        # Program Files is reached through a junction; scanning the drive it really lives on must not
        # walk it as the user's own files
        self.pc.file("P\\RealApps\\tool\\data.iso", 300 * KB)
        self.pc.age(self.pc.p("P\\RealApps\\tool\\data.iso"), 400)
        self.pc.junction("C\\Apps", self.pc.p("P\\RealApps"))
        env = self.pc.env(program_files=[self.pc.p("C\\Program Files"), self.pc.p("C\\Apps")],
                          drive_roots=[self.pc.C, self.pc.D, self.pc.p("P")])
        _, r = run_scan(self.pc, self.pc.p("P"), env=env, **SMALL)
        self.assertEqual(r["groups"], [])
        self.assertEqual([rel(self.pc, p) for p in {x["id"]: x for x in r["windows"]}["programs"]["paths"]],
                         ["P\\RealApps"])

    def test_a_pyvenv_cfg_in_the_profile_hides_nothing_measured_on_its_own(self):
        # python -m venv . typed in a fresh terminal: the profile is listed once and never walked,
        # but the AppData places, measured on their own, are still offered
        self.pc.file(U + "pyvenv.cfg", data=b"home = C:\\Python313\n")
        _, r = run_scan(self.pc, self.pc.C, **SMALL)
        self.assertTrue({"temp", "browser-cache", "app-cache", "gpu-cache", "crash-dumps", "dev-cache"}
                        <= {g["id"] for g in r["groups"]})
        self.assertEqual(skipped(self.pc, r, "py-venv").get(U.rstrip("\\")), rules.NOT_ONLY_VENV)
        self.assertEqual(sum(s["path"] == self.pc.profile for g in r["groups"] + r["left_out"] for s in g["skipped"]), 1)
        self.assertIsNone(group(r, "downloads"))  # the profile itself is not walked

    def test_an_online_only_root_is_never_listed(self):
        old = self.pc.p(U + "OneDrive\\Old")
        self.pc.set_offline(old)
        sc = scan.Scanner(self.pc.env(), FakeWin(), old, **SMALL)
        seen, real = [], sc.listing
        sc.listing = lambda path, count=True: seen.append(path) or real(path, count)
        r = sc.run()
        self.assertNotIn(os.path.normcase(old), [os.path.normcase(p) for p in seen])
        self.assertEqual([(rel(self.pc, p["path"]), p["size"]) for p in {x["id"]: x for x in r["windows"]}["synced"]["parts"]],
                         [(U + "OneDrive\\Old", 0)])

    def test_a_copy_with_a_name_windows_tools_misread_is_listed_not_offered(self):
        with open(self.pc.p(U + "Pictures\\beach.jpg"), "rb") as f:
            photo = f.read()
        self.pc.file(U + "Pictures\\Odd \\beach.jpg", data=photo)  # a folder name ending in a space
        _, r = run_scan(self.pc, self.pc.C, **SMALL)
        self.assertEqual(skipped(self.pc, r, "duplicates"), {U + "Pictures\\Odd \\beach.jpg": rules.ODD})
        self.assertEqual(len(group(r, "duplicates")["items"]), 3)


if __name__ == "__main__":
    unittest.main()
