"""The Windows calls, read-only. Nothing here moves anything to the Recycle Bin: the one real
move is the opt-in test in the clean tests."""
import ctypes
import os
import re
import shutil
import tempfile
import unittest

import fixture  # noqa: F401  (puts the scripts on the path)
import winsys


class Structs(unittest.TestCase):
    def test_sizes_match_shellapi(self):
        big = ctypes.sizeof(ctypes.c_void_p) == 8
        self.assertEqual(ctypes.sizeof(winsys.SHFILEOPSTRUCTW), 56 if big else 30)
        self.assertEqual(ctypes.sizeof(winsys.SHQUERYRBINFO), 24 if big else 20)
        self.assertEqual(ctypes.sizeof(winsys.GUID), 16)

    def test_flags(self):
        self.assertEqual(winsys.RECYCLE_FLAGS, 0x40 | 0x10 | 0x4 | 0x400 | 0x4000)
        self.assertEqual(winsys.FO_DELETE, 3)

    def test_from_list_is_double_null_terminated(self):
        self.assertEqual(winsys.from_list(["C:\\a\\b.txt", "D:\\c"]), "C:\\a\\b.txt\0D:\\c\0")

    def test_from_list_refuses_what_is_not_a_plain_full_path(self):
        for bad in ["C:\\", "D:\\", "relative\\x", "C:x", "C:\\a\\*.txt", "C:\\a?b", "\\\\?\\C:\\x", "C:\\a\0b"]:
            with self.assertRaises(ValueError, msg=bad):
                winsys.from_list(["C:\\fine.txt", bad])

    def test_recycle_with_nothing_does_nothing(self):
        self.assertEqual(winsys.recycle([]), (0, False))


class Calls(unittest.TestCase):
    def test_known_folder_downloads(self):
        self.assertTrue(os.path.isdir(winsys.known_folder(winsys.DOWNLOADS)))

    def test_long_path_expands_short_names(self):
        base = tempfile.mkdtemp(prefix="disk-cleanup-test-")
        try:
            folder = os.path.join(base, "A folder with a rather long name")
            os.makedirs(folder)
            buf = ctypes.create_unicode_buffer(1024)
            ctypes.windll.kernel32.GetShortPathNameW(folder, buf, 1024)
            if "~" not in os.path.basename(buf.value):
                self.skipTest("8.3 names are switched off on this volume")
            self.assertEqual(os.path.normcase(winsys.long_path(buf.value)), os.path.normcase(folder))
            self.assertEqual(winsys.long_path(os.path.join(base, "missing~1")), os.path.join(base, "missing~1"))
        finally:
            shutil.rmtree(base)

    def test_system_drive(self):
        root = os.environ.get("SystemDrive", "C:") + "\\"
        self.assertEqual(winsys.drive_type(root), winsys.DRIVE_FIXED)
        self.assertRegex(winsys.volume_guid(root), r"^\{[0-9A-Fa-f-]{36}\}$")
        s = winsys.recycle_settings(root)
        self.assertEqual(set(s), {"max_mb", "nuke", "policy"})
        size, items = winsys.recycle_usage(root)
        self.assertIsInstance(size, int)
        self.assertIsInstance(items, int)
        self.assertEqual(winsys.drive_of("c:\\Users\\x"), "c:\\")
        self.assertEqual(winsys.drive_of("\\\\server\\share\\x"), "\\\\server\\share\\")

    def test_processes(self):
        names = winsys.processes()
        self.assertTrue(any(re.match(r"pythonw?(\d|\.\d+)*\.exe$|py\.exe$", n) for n in names))
        self.assertTrue(all(n == n.lower() for n in names))

    def test_winsys_object_has_every_call(self):
        for name in ("processes", "drive_type", "recycle_settings", "recycle_usage", "recycle"):
            self.assertTrue(callable(getattr(winsys.WinSys(), name)))


if __name__ == "__main__":
    unittest.main()
