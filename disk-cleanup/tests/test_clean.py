"""The clean step on a made-up PC: what it refuses, what a dry run changes (nothing), what --yes
moves (exactly what was picked, through a fake Recycle Bin), and every check it makes again. One
opt-in test moves one tiny made-up file to the real Recycle Bin."""
import contextlib
import glob
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import unittest
import uuid
from unittest import mock

from fixture import KB, PC, FakeWin, ext
from helpers import LO, U, rel
import clean
import disk_cleanup as dc
import rules
import winsys

SMALL = ["--dupe-min-mb", "0.01"]
CODE = U + "code\\"


def setUpModule():
    # the large-file rule's least size, 200 KB here so the fixture can stay small (its large files are
    # 300 KB); the scan's --large-mb can only raise it, and clean holds every report to it
    patch = mock.patch.object(rules, "LARGE_MB_MIN", 0.2)
    patch.start()
    unittest.addModuleCleanup(patch.stop)


def run(argv, **kw):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = dc.main(argv, **kw)
        except SystemExit as e:
            code = e.code
    return code, out.getvalue(), err.getvalue()


def scan_report(pc, root=None):
    """Scan the made-up PC and return (report path, report)."""
    for f in glob.glob(os.path.join(pc.out, "scan-*")):
        os.remove(f)  # the made-up PC's own report folder
    code, out, err = run(["scan", root or pc.C] + SMALL, env=pc.env(), win=FakeWin())
    assert code == 0, err
    js = glob.glob(os.path.join(pc.out, "scan-*.json"))[0]
    with open(js, encoding="utf-8") as f:
        return js, json.load(f)


def number(pc, report, rel_path):
    """The item number of a path in the report."""
    return next(i["n"] for g in report["groups"] for i in g["items"] if rel(pc, i["path"]) == rel_path)


def group_n(report, gid):
    return next(g["n"] for g in report["groups"] if g["id"] == gid)


def save(report, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f)
    return path


def snapshot(pc):
    """Every file and folder of the made-up PC with its size and modified time, report and bin
    folders left out."""
    out, mine = {}, [os.path.normcase(pc.p(x)) for x in ("out", "bin")]
    for top, dirs, files in os.walk(ext(pc.base)):
        for name in dirs + files:
            full = os.path.join(top, name)
            if any(rules.under(os.path.normcase(full[4:]), m) for m in mine):
                continue
            st = os.stat(full, follow_symlinks=False)
            out[full[4:]] = (st.st_size, st.st_mtime)
    return out


def left_reasons(out):
    """{item number: reason} from a clean run's printed left-out list."""
    got = {}
    for line in out.splitlines():
        if line.startswith("   #") and line.endswith(")"):
            n = line[4:line.index(" ", 4)]
            got[int(n)] = line[line.rindex("  (") + 3:-1]
    return got


class Refusals(unittest.TestCase):
    """Dry runs and refusals on one made-up PC: nothing here may change it."""

    @classmethod
    def setUpClass(cls):
        cls.pc = PC()
        cls.js, cls.report = scan_report(cls.pc)
        cls.before = snapshot(cls.pc)

    @classmethod
    def tearDownClass(cls):
        try:
            assert snapshot(cls.pc) == cls.before, "a refusal or dry run changed the made-up PC"
        finally:
            cls.pc.cleanup()

    def clean(self, *args, win=None, env=None):
        return run(["clean", self.js] + list(args), env=env or self.pc.env(), win=win or FakeWin())

    def edited(self, change):
        r = json.loads(json.dumps(self.report))
        change(r)
        return save(r, os.path.join(self.pc.out, "edited-%s.json" % uuid.uuid4().hex[:8]))

    def test_dry_run_changes_nothing(self):
        win = FakeWin()
        dup = number(self.pc, self.report, U + "Pictures\\Backup\\beach.jpg")
        code, out, err = self.clean("--groups", "1,2,3,temp,dev-cache", "--items", str(dup), win=win)
        self.assertEqual(code, 0, err)
        self.assertTrue(out.startswith("Dry run: nothing has been changed.\n"))
        self.assertIn("Would move to the Recycle Bin:", out)
        self.assertRegex(out, r"In all: about [\d.]+ KB in \d+ items\.")
        self.assertTrue(out.rstrip().endswith("To go ahead, run the same command with --yes."))
        self.assertEqual(win.calls, [])
        self.assertEqual(snapshot(self.pc), self.before)
        downloads = number(self.pc, self.report, U + "Downloads\\old-setup.exe")
        out = self.clean("--items", str(downloads))[1]
        self.assertIn("\n   Old installers and unfinished downloads     ", out)  # the summary's short label

    def test_it_needs_groups_or_items(self):
        code, _, err = self.clean()
        self.assertEqual(code, 2)
        self.assertIn("--groups", err)

    def test_your_call_groups_are_picked_item_by_item(self):
        for g in ("duplicates", "large-old", str(group_n(self.report, "duplicates"))):
            code, _, err = self.clean("--groups", g)
            self.assertEqual((code, err.strip()), (2, "Pick the items to remove from this group by number, with --items."), g)

    def test_not_offered_groups_are_refused(self):
        for g in ("programs", "synced", "recycle-bin", "windows-temp"):
            code, _, err = self.clean("--groups", g)
            self.assertEqual(code, 2, g)
            self.assertIn("is not offered", err)

    def test_unknown_names_and_numbers_are_refused(self):
        self.assertIn("The groups in this report are: 1 ", self.clean("--groups", "nope")[2])
        for args in (["--groups", "nope"], ["--groups", "99"], ["--items", "99999"], ["--items", "1", "--skip", "99999"],
                     ["--items", "x"], ["--items", "-1"], ["--items", "²"], ["--groups", "²"],
                     ["--groups", "empty"]):  # (empty folders are not listed at all)
            self.assertEqual(self.clean(*args)[0], 2, args)

    def test_an_item_below_a_folder_that_cannot_be_read_is_left_out(self):
        clip = self.pc.p(U + "Documents\\locked\\sub\\clip.mp4")  # behind the fixture's deny rule
        st = os.stat(clip)
        n = number(self.pc, self.report, U + "Videos\\old-trip.mp4")

        def point(r):
            for g in r["groups"]:
                for i in g["items"]:
                    if i["n"] == n:
                        i.update(path=clip, size=st.st_size, mtime=st.st_mtime)
        code, out, _ = run(["clean", self.edited(point), "--items", str(n)], env=self.pc.env(), win=FakeWin())
        self.assertEqual(left_reasons(out), {n: clean.NO_RULE})

    def test_a_zero_mb_recycle_bin_takes_nothing(self):
        out = self.clean("--groups", "temp", win=FakeWin(max_mb=0))[1]
        self.assertIn("Would move to the Recycle Bin:\n   Nothing.", out)
        self.assertEqual(set(left_reasons(out).values()), {clean.NO_BIN})

    def test_a_report_older_than_a_day_is_refused(self):
        def age(r):
            r["created_ts"] -= 25 * 3600
        code, _, err = run(["clean", self.edited(age), "--groups", "temp"], env=self.pc.env(), win=FakeWin())
        self.assertEqual(code, 2)
        self.assertIn("Scan again", err)

    def test_other_unusable_reports_are_refused(self):
        def gone_root(r):
            r["root"] = self.pc.p("C-gone")

        def other_tool(r):
            r["tool"] = "other"

        def future(r):
            r["created_ts"] += 3600
        for change in (gone_root, other_tool, future):
            self.assertEqual(run(["clean", self.edited(change), "--groups", "temp"], env=self.pc.env(), win=FakeWin())[0],
                             2, change.__name__)
        other_profile = self.pc.env(profile=self.pc.p("C\\Users\\other"))
        self.assertEqual(self.clean("--groups", "temp", env=other_profile)[0], 2)
        self.assertEqual(run(["clean", self.pc.p("missing.json"), "--groups", "temp"], env=self.pc.env(), win=FakeWin())[0], 2)

    def test_a_group_this_tool_does_not_offer_is_refused_even_when_edited_in(self):
        def rename(r):
            r["groups"][0]["id"] = "programs-copy"
        code, _, err = run(["clean", self.edited(rename), "--groups", "1"], env=self.pc.env(), win=FakeWin())
        self.assertEqual(code, 2)
        self.assertIn("not a group this tool offers", err)

    def test_edited_paths_are_checked_again_and_left_out(self):
        temp = next(g for g in self.report["groups"] if g["id"] == "temp")
        nums = [i["n"] for i in temp["items"]][:4]
        short = self.pc.p(LO + "Temp")
        targets = [self.pc.precious, self.pc.p("C\\Windows\\Temp\\wintemp.tmp"),
                   self.pc.p(LO + "Packages\\SomeApp_1\\LocalCache\\Cache\\x"),
                   os.path.join(short, "old-folder", "..", "old.tmp")]

        def point(r):
            for i, t in zip(next(g for g in r["groups"] if g["id"] == "temp")["items"], targets):
                i["path"] = t
        code, out, err = run(["clean", self.edited(point), "--items", ",".join(map(str, nums))],
                             env=self.pc.env(), win=FakeWin())
        self.assertEqual(code, 0, err)
        why = left_reasons(out)
        self.assertEqual([why[n] for n in nums], [clean.OUTSIDE_ROOT, clean.PROTECTED, clean.PROTECTED, clean.NOT_USUAL])
        self.assertIn("Would move to the Recycle Bin:\n   Nothing.", out)

    def test_a_short_name_path_is_left_out(self):
        import ctypes
        buf = ctypes.create_unicode_buffer(1024)
        ctypes.windll.kernel32.GetShortPathNameW(self.pc.p(LO + "Temp\\old-folder"), buf, 1024)
        if "~" not in os.path.basename(buf.value):
            self.skipTest("8.3 names are switched off on this volume")
        n = number(self.pc, self.report, LO + "Temp\\old-folder")

        def point(r):
            for g in r["groups"]:
                for i in g["items"]:
                    if i["n"] == n:
                        i["path"] = buf.value  # the same folder, by its short name
        code, out, _ = run(["clean", self.edited(point), "--items", str(n)], env=self.pc.env(), win=FakeWin())
        self.assertEqual(left_reasons(out)[n], clean.NOT_USUAL)

    def test_a_browser_cache_is_left_out_while_its_browser_runs(self):
        g = next(g for g in self.report["groups"] if g["id"] == "browser-cache")
        chrome = [i["n"] for i in g["items"] if "Google" in i["path"]]

        def drop_process(r):  # the process is worked out again from the rules, not taken from the report
            for i in next(g for g in r["groups"] if g["id"] == "browser-cache")["items"]:
                i["process"] = None
        code, out, _ = run(["clean", self.edited(drop_process), "--groups", "browser-cache"], env=self.pc.env(),
                           win=FakeWin(running={"chrome.exe"}))
        why = left_reasons(out)
        self.assertEqual({why.get(n) for n in chrome}, {"close Chrome first"})
        self.assertTrue(all(why.get(i["n"]) is None for i in g["items"] if "Mozilla" in i["path"]))

    def test_recycle_bin_room_warning(self):
        win = FakeWin(max_mb=1, bin_size=1024 * KB - 2 * KB, bin_items=9)
        code, out, _ = self.clean("--groups", "browser-cache", win=win)
        self.assertEqual(code, 0)
        self.assertRegex(out, r"\nWARNING: The Recycle Bin on .+ has room for 2 KB, and this moves [\d.]+ KB\. Windows "
                              r"will permanently delete the oldest items already in it to make room\.\n")
        self.assertNotIn("WARNING", self.clean("--groups", "browser-cache", win=FakeWin(max_mb=1))[1])

    def test_what_the_recycle_bin_cannot_take_is_left_out(self):
        for win in (FakeWin(drive=2), FakeWin(nuke=True), FakeWin(policy=True)):
            out = self.clean("--groups", "temp", win=win)[1]
            self.assertIn("Would move to the Recycle Bin:\n   Nothing.", out)
            self.assertIn(clean.NO_BIN, out)


class Moves(unittest.TestCase):
    """--yes, each case on a made-up PC of its own."""

    def setUp(self):
        self.pc = PC()
        self.bin = self.pc.p("bin")

    def tearDown(self):
        self.pc.cleanup()

    def clean(self, js, *args, **kw):
        win = FakeWin(bin_dir=self.bin, **kw)
        code, out, err = run(["clean", js] + list(args), env=self.pc.env(), win=win)
        self.assertEqual(code, 0, err)
        return out, win

    def test_yes_moves_exactly_the_picked_items_and_honours_skip(self):
        js, report = scan_report(self.pc)
        temp = next(g for g in report["groups"] if g["id"] == "temp")
        skip = number(self.pc, report, LO + "Temp\\old.tmp")
        before = snapshot(self.pc)
        out, win = self.clean(js, "--groups", "temp,crash-dumps", "--skip", str(skip), "--yes")
        crash = next(g for g in report["groups"] if g["id"] == "crash-dumps")
        want = {i["path"] for i in temp["items"] + crash["items"] if i["n"] != skip}
        self.assertEqual(set(win.moved), want)
        after = snapshot(self.pc)
        self.assertTrue(os.path.exists(self.pc.p(LO + "Temp\\old.tmp")))
        changed = {p for p in before if p not in after}
        self.assertEqual({p for p in changed if not any(rules.is_under(p, w) for w in want)}, set())
        self.assertTrue(out.startswith("Moved to the Recycle Bin:\n"))
        self.assertIn("The space comes back when you empty the Recycle Bin. Until then you can restore anything from it.", out)
        log = out.rstrip().splitlines()[-1].split(": ", 1)[1]
        self.assertTrue(os.path.basename(log).startswith("clean-") and os.path.dirname(log) == os.path.dirname(js))
        with open(log, encoding="utf-8") as f:
            text = f.read()
        for p in want:
            self.assertIn(p, text)

    def test_what_clean_prints_names_each_item_so_a_new_report_shows_its_own_files(self):
        # item numbers are positions in one report: after a new scan the same numbers name other files
        js, first = scan_report(self.pc)
        first_js = save(first, os.path.join(self.pc.out, "first-report.json"))
        large = next(g for g in first["groups"] if g["id"] == "large-old")["items"][-1]
        copies = [i for g in first["groups"] if g["id"] == "duplicates" for i in g["items"] if not i["suggest_keep"]]
        picks = [i["n"] for i in [large] + copies]
        out1, _ = self.clean(first_js, "--items", ",".join(map(str, picks)))
        for i in [large] + copies:
            self.assertIn("\n      #%d  %s  %s\n" % (i["n"], dc.size_text(i["size"]), i["path"]), out1)
        self.pc.age(self.pc.file(LO + "Temp\\crossed-7-days.tmp", KB), 8)  # a day later: one more temp file
        js, second = scan_report(self.pc)
        out2, win = self.clean(js, "--items", ",".join(map(str, picks)))
        self.assertNotEqual(out1, out2)  # the dry run the user says yes to shows the other files
        now = {i["n"]: i for g in second["groups"] for i in g["items"]}
        for n in picks:
            self.assertIn("\n      #%d  %s  %s\n" % (n, dc.size_text(now[n]["size"]), now[n]["path"]), out2)
        self.assertEqual(win.calls, [])

    def test_a_group_named_whole_shows_its_first_ten_and_the_log_lists_all(self):
        for k in range(12):
            self.pc.age(self.pc.file(LO + "Temp\\many-%02d.tmp" % k, KB), 400)
        js, report = scan_report(self.pc)
        dup = next(i for g in report["groups"] if g["id"] == "duplicates" for i in g["items"]
                   if rel(self.pc, i["path"]) == U + "Pictures\\Backup\\beach.jpg")
        for args in ([], ["--yes"]):
            out, win = self.clean(js, "--groups", "temp", "--items", str(dup["n"]), *args)
            m = re.search(r"\n   Temporary files older than 7 days +\S+ \S+ +(\d+) items\n((?:      .*\n)*)", out)
            rows = m.group(2).splitlines()
            self.assertEqual(len(rows), 11, out)
            self.assertTrue(all(re.match(r"      #\d+  \S+ \S+  .+\\Temp\\", r) for r in rows[:10]), rows)
            self.assertEqual(rows[10], "      and %d more" % (int(m.group(1)) - 10))
            self.assertIn("\n      #%d  20 KB  %s\n" % (dup["n"], dup["path"]), out)  # named with --items
        log = out.rstrip().splitlines()[-1].split(": ", 1)[1]
        with open(log, encoding="utf-8") as f:
            text = f.read()
        self.assertNotRegex(text, r"and \d+ more")
        for p in win.moved:
            item = next(i for g in report["groups"] for i in g["items"] if i["path"] == p)
            self.assertIn("\n      #%d  %s  %s\n" % (item["n"], dc.size_text(item["size"]), p), text)

    def forged(self, gid, items, **settings):
        """A report no scan wrote, with only the keys clean reads, made now."""
        report = {"tool": "disk-cleanup", "version": 1, "created_ts": time.time(), "root": self.pc.C,
                  "profile": self.pc.profile, "groups": [{"n": 1, "id": gid, "items": items}]}
        if settings:
            report["settings"] = settings
        return save(report, os.path.join(self.pc.out, "forged-%s.json" % uuid.uuid4().hex[:8]))

    def test_a_report_cannot_lower_the_large_file_rule(self):
        small = self.pc.p(U + "Documents\\report.docx")                           # 2 KB, 400 days old
        today = self.pc.file(U + "Pictures\\made-a-minute-ago.jpg", 300 * KB)     # large enough, but new
        items = []
        for n, p in enumerate((small, today), 1):
            st = os.stat(p)
            items.append({"n": n, "path": p, "kind": "file", "size": st.st_size, "mtime": st.st_mtime})
        js = self.forged("large-old", items, large_mb=0, large_days=0)
        out, win = self.clean(js, "--items", "1,2", "--yes")
        self.assertEqual((win.moved, left_reasons(out)), ([], {1: clean.NO_RULE, 2: clean.NO_RULE}))

    def test_a_duplicate_counts_only_a_copy_in_a_place_it_could_be_offered_from(self):
        places = [("C\\$Recycle.Bin\\S-1-5-21-1\\$R0AB12C.jpg", clean.NO_COPY),  # in the Recycle Bin
                  (U + "OneDrive\\copy.jpg", clean.NO_COPY),                      # a synced folder
                  (CODE + "old-app\\assets\\copy.jpg", clean.NO_COPY),            # inside a project
                  (LO + "copy.jpg", clean.NO_COPY),                               # AppData
                  (U + "Documents\\copy.jpg", None)]                              # the user's own folder: it stays
        items = []
        for n, (where, _) in enumerate(places, 1):
            data = os.urandom(40 * KB)
            photo, copy = self.pc.file(U + "Pictures\\photo-%d.jpg" % n, data=data), self.pc.file(where, data=data)
            st = os.stat(photo)
            items.append({"n": n, "path": photo, "kind": "file", "size": st.st_size, "mtime": st.st_mtime, "set": n,
                          "hash": hashlib.sha256(data).hexdigest(), "same_as": [copy], "suggest_keep": False})
        out, win = self.clean(self.forged("duplicates", items), "--items", "1,2,3,4,5", "--yes")
        self.assertEqual(left_reasons(out), {n: why for n, (_, why) in enumerate(places, 1) if why})
        self.assertEqual(win.moved, [self.pc.p(U + "Pictures\\photo-5.jpg")])

    def test_every_copy_picked_keeps_one(self):
        js, report = scan_report(self.pc)
        copies = [i["n"] for g in report["groups"] if g["id"] == "duplicates" for i in g["items"]]
        out, win = self.clean(js, "--items", ",".join(map(str, copies)), "--yes")
        self.assertEqual(win.moved, [])
        self.assertEqual(set(left_reasons(out).values()), {clean.KEEP_ONE})
        # two of three is fine: one copy stays
        out, win = self.clean(js, "--items", ",".join(map(str, copies[1:])), "--yes")
        self.assertEqual(len(win.moved), 2)
        self.assertTrue(os.path.exists(self.pc.p(U + "Pictures\\beach.jpg")))

    def test_a_duplicate_whose_other_copies_went_or_changed_stays(self):
        js, report = scan_report(self.pc)
        n = number(self.pc, report, U + "Pictures\\beach.jpg")
        os.remove(self.pc.p(U + "Downloads\\beach (1).jpg"))  # a file of the made-up PC
        with open(self.pc.p(U + "Pictures\\Backup\\beach.jpg"), "ab") as f:
            f.write(b"!")
        out, win = self.clean(js, "--items", str(n), "--yes")
        self.assertEqual(win.moved, [])
        self.assertEqual(left_reasons(out), {n: clean.NO_COPY})

    def test_a_large_file_changed_after_the_scan_stays(self):
        js, report = scan_report(self.pc)
        n = number(self.pc, report, U + "Videos\\old-trip.mp4")
        with open(self.pc.p(U + "Videos\\old-trip.mp4"), "ab") as f:
            f.write(b"!")
        out, win = self.clean(js, "--items", str(n), "--yes")
        self.assertEqual((win.moved, left_reasons(out)), ([], {n: clean.CHANGED}))

    def test_an_item_that_became_a_junction_stays(self):
        js, report = scan_report(self.pc)
        n = number(self.pc, report, LO + "Temp\\old-folder")
        os.rename(self.pc.p(LO + "Temp\\old-folder"), self.pc.p(LO + "Temp\\moved-away"))
        self.pc.junction(LO + "Temp\\old-folder", self.pc.outside)
        out, win = self.clean(js, "--items", str(n), "--yes")
        self.assertEqual((win.moved, left_reasons(out)), ([], {n: clean.IS_LINK}))
        self.assertTrue(os.path.exists(self.pc.precious))

    def test_every_rule_is_checked_again(self):
        js, report = scan_report(self.pc)
        n = lambda p: number(self.pc, report, p)  # noqa: E731
        venv, node, nopkg = n(CODE + "py-app\\.venv"), n(CODE + "old-app\\node_modules"), n(CODE + "dotnet-app\\bin")
        dup, temp_dir = n(U + "Pictures\\beach.jpg"), n(LO + "Temp\\deep-old")
        setup, cache = n(U + "Downloads\\old-setup.exe"), n(CODE + "py-app\\__pycache__")
        self.pc.file(CODE + "py-app\\.venv\\notes.txt")                  # someone's own file in the venv
        self.pc.file(CODE + "old-app\\src\\new.js", age=0)               # the project changed today
        os.remove(self.pc.p(CODE + "dotnet-app\\App.csproj"))            # bin is no longer next to a project file
        self.pc.dir(U + "Pictures\\.stfolder")                           # Pictures became a Syncthing folder
        self.pc.set_offline(self.pc.p(LO + "Temp\\deep-old"))            # the temp folder went online-only
        self.pc.file(U + "Downloads\\helper.dll")                        # Downloads now holds a program
        os.rename(self.pc.p(CODE + "py-app\\__pycache__"), self.pc.p(CODE + "py-app\\pycache-kept"))
        out, win = self.clean(js, "--items", ",".join(map(str, (venv, node, nopkg, dup, temp_dir, setup, cache))),
                              "--yes")
        self.assertEqual(win.moved, [])
        self.assertEqual(left_reasons(out), {venv: clean.NO_RULE, node: rules.RECENT, nopkg: clean.NO_RULE,
                                             dup: clean.NO_RULE, temp_dir: rules.ONLINE, setup: clean.NO_RULE,
                                             cache: clean.GONE})

    def test_each_project_is_read_once_per_run(self):
        js, report = scan_report(self.pc)
        both = [number(self.pc, report, CODE + "dotnet-app\\" + x) for x in ("bin", "obj")]
        calls, real = [], clean.newest_change

        def counted(folder):
            calls.append(folder)
            return real(folder)
        with mock.patch.object(clean, "newest_change", counted):
            out, _ = self.clean(js, "--items", "%d,%d" % tuple(both))
        self.assertEqual(len(calls), 1)
        self.assertEqual(left_reasons(out), {})
        self.pc.file(CODE + "dotnet-app\\Changed.cs", age=0)
        out, _ = self.clean(js, "--items", "%d,%d" % tuple(both))
        self.assertEqual(left_reasons(out), {both[0]: rules.RECENT, both[1]: rules.RECENT})

    def test_something_new_at_a_moved_path_is_never_touched(self):
        js, report = scan_report(self.pc)
        n = number(self.pc, report, LO + "Temp\\old.tmp")
        path = self.pc.p(LO + "Temp\\old.tmp")

        class Replacing(FakeWin):
            def recycle(self, paths):
                done = FakeWin.recycle(self, paths)
                if len(self.calls) == 1:  # an app writes a new file there before the check
                    with open(ext(paths[0]), "w") as f:
                        f.write("new")
                return done
        win = Replacing(bin_dir=self.bin)
        code, out, err = run(["clean", js, "--items", str(n), "--yes"], env=self.pc.env(), win=win)
        self.assertEqual(code, 0, err)
        self.assertEqual(win.calls, [[path]])  # moved once, never tried again
        with open(path) as f:
            self.assertEqual(f.read(), "new")
        self.assertEqual(left_reasons(out), {})

    def test_a_copy_inside_another_chosen_folder_does_not_count_as_kept(self):
        js, report = scan_report(self.pc)
        dup = number(self.pc, report, U + "Pictures\\beach.jpg")
        folder = number(self.pc, report, LO + "Temp\\old-folder")
        with open(self.pc.p(U + "Pictures\\beach.jpg"), "rb") as f:
            photo = f.read()
        copy = self.pc.file(LO + "Temp\\old-folder\\beach-copy.jpg", data=photo)
        for g in report["groups"]:
            for i in g["items"]:
                if i["n"] == dup:
                    i["same_as"] = [copy]  # edited: its only other copy sits in a chosen folder
        save(report, js)
        out, win = self.clean(js, "--items", "%d,%d" % (dup, folder), "--yes")
        self.assertEqual(win.moved, [])
        # every chosen folder is in a place no copy counts in (here AppData), so the photo has none to keep
        self.assertEqual(left_reasons(out), {dup: clean.NO_COPY, folder: clean.NO_RULE})  # (old-folder is new now)

    def test_an_item_in_use_is_tried_again_then_left_out(self):
        js, report = scan_report(self.pc)
        temp = [i for g in report["groups"] if g["id"] == "temp" for i in g["items"]]
        stuck = temp[0]["path"]
        out, win = self.clean(js, "--groups", "temp", "--yes", stuck=[stuck])
        self.assertEqual(set(win.moved), {i["path"] for i in temp[1:]})
        self.assertEqual(left_reasons(out), {temp[0]["n"]: clean.IN_USE})
        self.assertEqual(win.calls[-1], [stuck])  # tried once more on its own
        self.assertTrue(os.path.exists(stuck))

    def test_moves_go_in_batches_of_200(self):
        for k in range(450):
            self.pc.age(self.pc.file(LO + "Temp\\batch-%03d.tmp" % k), 400)
        js, report = scan_report(self.pc)
        temp = [i for g in report["groups"] if g["id"] == "temp" for i in g["items"]]
        out, win = self.clean(js, "--groups", "temp", "--yes")
        self.assertEqual([len(c) for c in win.calls], [200, 200, len(temp) - 400])
        self.assertEqual(len(win.moved), len(temp))

    def test_what_the_recycle_bin_cannot_take_stays(self):
        self.pc.file(LO + "Temp\\big.bin", 1536 * KB)
        self.pc.file(LO + "Temp\\" + "n" * 200 + ".tmp")
        for name in ("big.bin", "n" * 200 + ".tmp"):
            self.pc.age(self.pc.p(LO + "Temp\\" + name), 400)
        js, report = scan_report(self.pc)
        big, longp = number(self.pc, report, LO + "Temp\\big.bin"), number(self.pc, report, LO + "Temp\\" + "n" * 200 + ".tmp")
        self.assertGreaterEqual(len(self.pc.p(LO + "Temp\\" + "n" * 200 + ".tmp")), 260)
        out, win = self.clean(js, "--items", "%d,%d" % (big, longp), "--yes", max_mb=1)
        self.assertEqual((win.moved, left_reasons(out)), ([], {big: clean.NO_BIN, longp: clean.NO_BIN}))

    def test_an_item_inside_another_picked_item_goes_with_it(self):
        js, report = scan_report(self.pc)
        outer = number(self.pc, report, LO + "Temp\\deep-old")
        crash = next(g for g in report["groups"] if g["id"] == "crash-dumps")["items"][0]
        crash["path"] = self.pc.deep_file  # edited to point inside the outer item
        save(report, js)
        out, win = self.clean(js, "--items", "%d,%d" % (outer, crash["n"]), "--yes")
        self.assertEqual(win.moved, [self.pc.p(LO + "Temp\\deep-old")])
        self.assertEqual(win.calls, [[self.pc.p(LO + "Temp\\deep-old")]])


@unittest.skipUnless(os.environ.get("DISK_CLEANUP_REAL_RECYCLE") == "1",
                     "moves one tiny made-up file to the real Recycle Bin; set DISK_CLEANUP_REAL_RECYCLE=1 to run it")
class RealRecycleBin(unittest.TestCase):
    def test_one_tiny_made_up_file_goes_to_the_recycle_bin(self):
        base = os.path.realpath(tempfile.mkdtemp(prefix="disk-cleanup-test-"))
        try:
            path = os.path.join(base, "disk-cleanup-test-%s.txt" % uuid.uuid4().hex[:12])
            with open(path, "w") as f:
                f.write("made up by the disk-cleanup tests")
            drive = winsys.drive_of(path)
            before = winsys.recycle_usage(drive)[1]
            code, _ = winsys.recycle([path])
            self.assertEqual(code, 0)
            self.assertFalse(os.path.exists(path))
            self.assertGreaterEqual(winsys.recycle_usage(drive)[1], before + 1)
        finally:
            shutil.rmtree(base)


if __name__ == "__main__":
    unittest.main()
