"""The command line: the scan command, its reports, the printed summary and the exit codes."""
import contextlib
import glob
import io
import json
import os
import unittest
from unittest import mock

from fixture import KB, PC, FakeWin
from helpers import run_scan
import disk_cleanup as dc
import rules


def run(argv, **kw):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = dc.main(argv, **kw)
        except SystemExit as e:
            code = e.code
    return code, out.getvalue(), err.getvalue()


class Formats(unittest.TestCase):
    def test_sizes_are_1024_based(self):
        self.assertEqual(dc.size_text(0), "0 bytes")
        self.assertEqual(dc.size_text(1), "1 byte")
        self.assertEqual(dc.size_text(512 * 1024), "512 KB")
        self.assertEqual(dc.size_text(int(14.2 * 1024 ** 2)), "14.2 MB")
        self.assertEqual(dc.size_text(int(3.1 * 1024 ** 3)), "3.1 GB")
        self.assertEqual(dc.size_text(None), "size unknown (needs admin)")

    def test_numbers_and_times(self):
        self.assertEqual(dc.num(1203), "1,203")
        self.assertEqual(dc.plural(1, "item"), "1 item")
        self.assertEqual(dc.plural(1203, "item"), "1,203 items")
        self.assertEqual(dc.duration(130), "2 min 10 s")
        self.assertEqual(dc.duration(9), "9 s")

    def test_dates_before_1970_and_far_ahead(self):
        self.assertEqual(dc.day(-315619200), "1960-01-01")
        self.assertEqual(dc.day(1e13), "unknown date")
        self.assertRegex(dc.day(33000000000), r"^3015-")

    def test_scan_root(self):
        self.assertEqual(dc.scan_root("C:"), "C:\\")
        self.assertEqual(dc.scan_root('C:"'), "C:\\")
        self.assertEqual(dc.scan_root(' "D:\\" '), "D:\\")
        self.assertEqual(dc.scan_root("\\\\?\\C:\\Users"), "C:\\Users")
        self.assertEqual(dc.scan_root("\\\\?\\c:"), "c:\\")
        self.assertEqual(dc.scan_root("\\\\?\\UNC\\server\\share\\x"), "\\\\server\\share\\x")
        for device in ("\\\\.\\C:", "\\\\.\\PhysicalDrive0", "\\\\?\\Volume{0b5d0c55-1111-2222-3333-444455556666}\\",
                       "\\\\?\\GLOBALROOT\\Device\\HarddiskVolumeShadowCopy1"):
            self.assertIsNone(dc.scan_root(device), device)

    def test_labels_never_run_into_their_size(self):
        g = {"n": 1, "id": "x", "label": "A label far longer than the column it is printed in", "safety": "safe",
             "size": 92, "count": 1, "items": []}
        self.assertIn("printed in  92 bytes", dc.group_line(g, set()))
        report = {"root": "C:\\", "stats": {"files": 1, "folders": 1, "seconds": 1}, "groups": [], "left_out": [],
                  "windows": [{"id": "synced", "label": rules.NOT_OFFERED["synced"][0], "size": 92,
                               "tool": rules.NOT_OFFERED["synced"][1], "paths": ["C:\\x"]}],
                  "unreadable": {"count": 0, "denied": 0, "examples": []}}
        self.assertIn("Google Drive)  92 bytes   Removing", dc.summary(report, set(), "a.txt", "a.json"))

    def test_group_line_matches_the_plan(self):
        g = {"n": 1, "id": "temp", "label": "Temporary files older than 7 days", "safety": "safe",
             "size": int(2.1 * 1024 ** 3), "count": 1203, "items": []}
        self.assertEqual(dc.group_line(g, set()),
                         "   1. Temporary files older than 7 days          2.1 GB   1,203 items   Safe")
        g = {"n": 2, "id": "browser-cache", "label": "Browser caches", "safety": "safe", "size": int(1.4 * 1024 ** 3),
             "count": 3, "items": [{"process": "chrome.exe"}, {"process": "msedge.exe"}, {"process": None}]}
        self.assertEqual(dc.group_line(g, {"chrome.exe"}),
                         "   2. Browser caches                             1.4 GB       3 items   Safe (close Chrome first)")
        self.assertTrue(dc.group_line(g, {"chrome.exe", "msedge.exe"}).endswith("(close Chrome and Edge first)"))


class ScanCommand(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pc = PC()

    @classmethod
    def tearDownClass(cls):
        cls.pc.cleanup()

    def test_scan_writes_both_reports_and_prints_the_summary(self):
        for f in glob.glob(os.path.join(self.pc.out, "scan-*")):
            os.remove(f)  # the fixture's own report folder
        code, out, err = run(["scan", self.pc.C, "--dupe-min-mb", "0.01", "--large-mb", "0.2"], env=self.pc.env(),
                             win=FakeWin(running={"chrome.exe"}))
        self.assertEqual(code, 0, err)
        lines = out.splitlines()
        self.assertEqual(lines[0], "Scanning %s. This only reads; on a whole drive it can take several minutes."
                         % self.pc.C)
        self.assertTrue(lines[1].startswith("Scan of %s finished in " % self.pc.C))
        self.assertRegex(out, r"Can be removed: about [\d.]+ KB in 14 groups\.")
        self.assertIn("Safe (close Chrome first)", out)
        self.assertIn("Not offered, Windows handles these:", out)
        self.assertIn("Safe: comes back by itself. Easy to get back: reinstall, rebuild or download again.", out)
        self.assertIn("Your call: your own files; pick them one by one by number.", out)
        self.assertRegex(out, r"Duplicate files \(pick which copies\) +40 KB   1 set, 3 copies   Your call")
        self.assertRegex(out, r"\n        set 1: #\d+  20 KB  .*\\Pictures\\beach\.jpg  \(suggested keep\)\n"
                              r"               #\d+  20 KB  .*\\Downloads\\beach \(1\)\.jpg\n")
        self.assertRegex(out, r"Large files not changed in 6 months +600 KB +2 items   Your call\n"
                              r"        #\d+  300 KB  \d{4}-\d\d-\d\d  .*\.mp4\n")
        self.assertRegex(out, r"Installed programs and games +\d+ bytes   Settings > Apps > Installed apps.*\n"
                              r" +\d+ bytes  .*\\C\\Program Files\n")
        self.assertIn("Left out: 3 folders that contain links to other folders (4 KB).", out)
        self.assertIn("Left out: 5 build folders of projects changed in the last 14 days (16 KB).", out)
        self.assertIn("Left out: 1 build folder changed in the last 14 days (2 KB).", out)
        self.assertIn("Left out: 3 folders that hold online-only files (100 bytes).", out)
        self.assertIn("Left out: 3 folders with a pyvenv.cfg that also hold other files (0 bytes).", out)
        self.assertIn("Left out: 2 items whose names Windows tools cannot handle safely (200 bytes).", out)
        self.assertIn("Could not read 1 folder (no permission). They were skipped.", out)
        js = glob.glob(os.path.join(self.pc.out, "scan-*.json"))
        txt = glob.glob(os.path.join(self.pc.out, "scan-*.txt"))
        self.assertEqual((len(js), len(txt)), (1, 1))
        self.assertRegex(os.path.basename(js[0]), r"^scan-\d{8}-\d{6}\.json$")
        self.assertTrue(out.rstrip().endswith("For the clean step: " + js[0]))
        self.assertIn("Full list: " + txt[0], out)
        with open(js[0], encoding="utf-8") as f:
            report = json.load(f)
        self.assertEqual((report["tool"], report["version"]), ("disk-cleanup", 1))
        self.assertEqual(len(report["groups"]), 14)
        with open(txt[0], encoding="utf-8") as f:
            text = f.read()
        for g in report["groups"]:
            for i in g["items"]:
                self.assertIn("#%d  " % i["n"], text)
                self.assertIn(i["path"], text)
        self.assertIn("contains online-only files", text)
        self.assertIn("1960-01-01  " + self.pc.ancient, text)
        self.assertIn("   set 1, 20 KB each:\n", text)
        self.assertRegex(text, r"      #\d+  20 KB  \d{4}-\d\d-\d\d  .*\\Pictures\\beach\.jpg  suggested keep\n")
        self.assertIn("project changed in the last 14 days", text)
        self.assertIn(os.path.join(self.pc.profile, "OneDrive"), text)
        self.assertIn(os.path.join(self.pc.C, "Windows", "Minidump"), text)
        self.assertIn(os.path.join(self.pc.profile, "Documents", "locked"), text)
        self.assertNotIn("\u2014", out + text)
        self.assertNotIn("\u2013", out + text)

    def test_bad_arguments_exit_2(self):
        self.assertEqual(run(["scan", os.path.join(self.pc.base, "missing")], env=self.pc.env(), win=FakeWin())[0], 2)
        self.assertEqual(run(["scan"], env=self.pc.env(), win=FakeWin())[0], 2)
        self.assertEqual(run([], env=self.pc.env(), win=FakeWin())[0], 2)
        self.assertEqual(run(["scan", self.pc.C, "--large-mb", "-1"], env=self.pc.env(), win=FakeWin())[0], 2)
        for flag, value in (("--dupe-min-mb", "nan"), ("--large-mb", "inf"), ("--large-days", "nan"),
                            ("--large-days", "-inf"), ("--large-mb", "lots")):
            self.assertEqual(run(["scan", self.pc.C, flag, value], env=self.pc.env(), win=FakeWin())[0], 2, value)
        self.assertEqual(run(["scan", "\\\\.\\C:"], env=self.pc.env(), win=FakeWin())[0], 2)
        self.assertEqual(run(["clean-up", "x"], env=self.pc.env(), win=FakeWin())[0], 2)

    def test_a_root_spelled_another_way_scans_the_real_folder(self):
        def items(argv_root):
            code, out, err = run(["scan", argv_root, "--dupe-min-mb", "0.01"], env=self.pc.env(), win=FakeWin())
            self.assertEqual(code, 0, err)
            js = max(glob.glob(os.path.join(self.pc.out, "scan-*.json")), key=os.path.getmtime)
            with open(js, encoding="utf-8") as f:
                r = json.load(f)
            os.remove(js)  # the fixture's own report folder
            return out, sorted((g["id"], i["path"]) for g in r["groups"] for i in g["items"])
        plain_out, plain = items(self.pc.profile)
        link = self.pc.junction("P\\home", self.pc.profile)
        for spelled in (link, "\\\\?\\" + self.pc.profile):
            out, got = items(spelled)
            self.assertEqual(got, plain, spelled)
            self.assertTrue(out.startswith("Scanning %s. This only reads" % self.pc.profile), spelled)
        self.assertIn("(%s leads there: it is a link or a short name.)" % link, items(link)[0])
        self.assertNotIn("leads there", plain_out)

    def test_report_folder_that_cannot_be_made_exits_2_before_scanning(self):
        blocker = os.path.join(self.pc.base, "not-a-folder")
        with open(blocker, "w") as f:
            f.write("x")
        code, out, err = run(["scan", self.pc.C], env=self.pc.env(out_dir=blocker), win=FakeWin())
        self.assertEqual(code, 2)
        self.assertNotIn("Scan", out)
        self.assertIn("Cannot write the reports to " + blocker, err)

    def test_not_windows_exits_3(self):
        with mock.patch.object(dc.os, "name", "posix"):
            code, out, _ = run(["scan", "C:\\"])
        self.assertEqual((code, out), (3, "disk-cleanup runs on Windows only.\n"))

    def test_summary_without_anything_to_remove(self):
        _, report = run_scan(self.pc, os.path.join(self.pc.C, "Windows"))
        s = dc.summary(report, set(), "a.txt", "a.json")
        self.assertIn("Nothing was found that can be removed.", s)
        self.assertIn("System crash dumps", s)
        self.assertNotIn("Can be removed", s)

    def test_your_call_groups_show_their_first_items(self):
        GB = 1024 ** 3
        dup = [{"n": 300 + k, "path": "D:\\%s\\trip%d.mp4" % ("Videos" if k % 2 == 0 else "Backup", k // 2),
                "size": int(1.2 * GB), "mtime": 0, "set": k // 2 + 1, "suggest_keep": k % 2 == 0} for k in range(10)]
        large = [{"n": 420 + k, "path": "D:\\VMs\\old-%d.vhdx" % k, "size": int(6.1 * GB), "mtime": 1730548800}
                 for k in range(12)]  # 2024-11-02 at noon UTC, the same date in every time zone
        report = {"root": "D:\\", "stats": {"files": 812345, "folders": 98765, "seconds": 130}, "left_out": [],
                  "groups": [{"n": 8, "id": "duplicates", "label": rules.GROUPS["duplicates"][0], "safety": "check",
                              "size": int(3.3 * GB), "count": 10, "items": dup, "skipped": []},
                             {"n": 9, "id": "large-old", "label": rules.label("large-old"), "safety": "check",
                              "size": 15 * GB, "count": 12, "items": large, "skipped": []}],
                  "windows": [{"id": "programs", "label": "Installed programs and games", "size": 25 * GB,
                               "tool": rules.NOT_OFFERED["programs"][1], "paths": [],
                               "parts": [{"path": "D:\\Games\\G%d" % k, "size": GB} for k in range(25)]}],
                  "unreadable": {"count": 42, "denied": 42, "examples": []}}
        s = dc.summary(report, set(), "C:\\Users\\you\\disk-cleanup\\scan-20261121-140500.txt",
                       "C:\\Users\\you\\disk-cleanup\\scan-20261121-140500.json")
        self.assertIn("Scan of D:\\ finished in 2 min 10 s: 812,345 files in 98,765 folders.\n", s)
        self.assertIn("\n   8. Duplicate files (pick which copies)        3.3 GB   5 sets, 10 copies   Your call\n"
                      "        set 1: #300  1.2 GB  D:\\Videos\\trip0.mp4  (suggested keep)\n"
                      "               #301  1.2 GB  D:\\Backup\\trip0.mp4\n", s)
        self.assertIn("        set 3: #304", s)
        self.assertNotIn("set 4:", s)
        self.assertIn("        and 2 more sets in the full list\n", s)
        self.assertIn("\n   9. Large files not changed in 6 months       15.0 GB      12 items   Your call\n"
                      "        #420  6.1 GB  2024-11-02  D:\\VMs\\old-0.vhdx\n", s)
        self.assertIn("#429  6.1 GB", s)
        self.assertNotIn("#430", s)
        self.assertIn("        and 2 more in the full list\n", s)
        self.assertIn("        %8s  %s\n        and 5 more in the full list\n" % ("1.0 GB", "D:\\Games\\G19"), s)
        self.assertNotIn("G20", s)
        self.assertIn("Could not read 42 folders (no permission). They were skipped.", s)
        self.assertTrue(s.endswith("For the clean step: C:\\Users\\you\\disk-cleanup\\scan-20261121-140500.json"))

    def test_progress_lines(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            dc.progress("walk", 1203, 98, 75)
            dc.progress("hash", 12, 40, 130)
        self.assertEqual(err.getvalue(), "Still scanning: 1,203 files in 98 folders so far (1 min 15 s).\n"
                                         "Comparing possible duplicates: 12 of 40 files (2 min 10 s).\n")

    def test_unknown_size_prints_needs_admin(self):
        report = {"root": "C:\\", "stats": {"files": 1, "folders": 1, "seconds": 1}, "groups": [], "left_out": [],
                  "windows": [{"id": "windows-temp", "label": "Windows temporary files", "size": None,
                               "tool": rules.NOT_OFFERED["windows-temp"][1], "paths": ["C:\\Windows\\Temp"]}],
                  "unreadable": {"count": 0, "denied": 0, "examples": []}}
        line = "   %-44s%s   %s" % ("Windows temporary files", "size unknown (needs admin)",
                                    rules.NOT_OFFERED["windows-temp"][1])
        self.assertIn(line + "\n", dc.summary(report, set(), "a.txt", "a.json"))
        self.assertEqual(dc.size_text(2 * KB), "2 KB")


if __name__ == "__main__":
    unittest.main()
