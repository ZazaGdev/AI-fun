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
        code, out, err = run(["scan", self.pc.C], env=self.pc.env(), win=FakeWin(running={"chrome.exe"}))
        self.assertEqual(code, 0, err)
        lines = out.splitlines()
        self.assertEqual(lines[0], "Scanning %s. This only reads; on a whole drive it can take several minutes."
                         % self.pc.C)
        self.assertTrue(lines[1].startswith("Scan of %s finished in " % self.pc.C))
        self.assertRegex(out, r"Can be removed: about [\d.]+ KB in 7 groups\.")
        self.assertIn("Safe (close Chrome first)", out)
        self.assertIn("Not offered, Windows handles these:", out)
        self.assertIn("Safe: comes back by itself. Easy to get back: reinstall, rebuild or download again.", out)
        self.assertIn("Left out: 2 folders that contain links to other folders (100 bytes).", out)
        self.assertIn("Left out: 1 folder that holds online-only files (0 bytes).", out)
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
        self.assertEqual(len(report["groups"]), 7)
        with open(txt[0], encoding="utf-8") as f:
            text = f.read()
        for g in report["groups"]:
            for i in g["items"]:
                self.assertIn("#%d  " % i["n"], text)
                self.assertIn(i["path"], text)
        self.assertIn("contains online-only files", text)
        self.assertIn("1960-01-01  " + self.pc.ancient, text)
        self.assertIn(os.path.join(self.pc.C, "Windows", "Minidump"), text)
        self.assertIn(os.path.join(self.pc.profile, "Documents", "locked"), text)
        self.assertNotIn("\u2014", out + text)
        self.assertNotIn("\u2013", out + text)

    def test_bad_arguments_exit_2(self):
        self.assertEqual(run(["scan", os.path.join(self.pc.base, "missing")], env=self.pc.env(), win=FakeWin())[0], 2)
        self.assertEqual(run(["scan"], env=self.pc.env(), win=FakeWin())[0], 2)
        self.assertEqual(run([], env=self.pc.env(), win=FakeWin())[0], 2)
        self.assertEqual(run(["scan", self.pc.C, "--large-mb", "-1"], env=self.pc.env(), win=FakeWin())[0], 2)
        self.assertEqual(run(["clean-up", "x"], env=self.pc.env(), win=FakeWin())[0], 2)

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
