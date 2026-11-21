"""The Windows calls, read-only. Nothing here moves anything to the Recycle Bin: the one real
move is the opt-in test in the clean tests."""
import ctypes
import os
import re
import shutil
import subprocess
import tempfile
import unittest

import fixture  # noqa: F401  (puts the scripts on the path)
import winsys


class FakeReg:
    """A made-up registry with winreg's calls: {(hive, key): ([subkeys], [(name, data)])}."""
    HKEY_LOCAL_MACHINE, HKEY_CURRENT_USER = "HKLM", "HKCU"

    def __init__(self, tree):
        self.tree = tree

    class Key:
        def __init__(self, at):
            self.at = at

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def OpenKey(self, hive, key):
        if (hive, key) not in self.tree:
            raise FileNotFoundError(2, "no such key")
        return self.Key((hive, key))

    def EnumKey(self, h, i):
        keys = self.tree[h.at][0]
        if i >= len(keys):
            raise OSError(259, "no more")
        return keys[i]

    def EnumValue(self, h, i):
        values = self.tree[h.at][1]
        if i >= len(values):
            raise OSError(259, "no more")
        return values[i] + (1,)


class SyncRoots(unittest.TestCase):
    def test_sync_roots_from_the_registry(self):
        srm, od = winsys.SYNC_ROOTS, winsys.ONEDRIVE
        reg = FakeReg({
            ("HKLM", srm): (["GoogleDrive!S-1-5-21!x", "Box!S-1-5-21!y", "Broken!z"], []),
            ("HKLM", srm + "\\GoogleDrive!S-1-5-21!x\\UserSyncRoots"): ([], [("S-1-5-21-1", "C:\\Users\\you\\My Drive")]),
            ("HKLM", srm + "\\Box!S-1-5-21!y\\UserSyncRoots"): ([], [("S-1-5-21-1", "D:\\Box"), ("S-1-5-21-2", "E:\\Box")]),
            ("HKCU", od): (["Personal", "Business1"], []),
            ("HKCU", od + "\\Personal"): ([], [("UserFolder", "C:\\Users\\you\\OneDrive"), ("cid", "abc")]),
            ("HKCU", od + "\\Business1\\ScopeIdToMountPointPathCache"): ([], [("s1", "C:\\Users\\you\\Contoso\\Docs")]),
        })
        self.assertEqual(winsys.sync_roots(reg), ["C:\\Users\\you\\My Drive", "D:\\Box", "E:\\Box",
                                                  "C:\\Users\\you\\OneDrive", "C:\\Users\\you\\Contoso\\Docs"])
        self.assertEqual(winsys.sync_roots(FakeReg({})), [])

    def test_sync_roots_reads_the_real_registry(self):
        self.assertIsInstance(winsys.sync_roots(), list)


class PathForms(unittest.TestCase):
    """Every way of spelling a path that Windows tools may read as another place."""

    @classmethod
    def setUpClass(cls):
        cls.base = os.path.realpath(tempfile.mkdtemp(prefix="disk-cleanup-test-"))  # %TEMP% may hold a short name
        j, b = os.path.join, cls.base
        os.makedirs(j(b, "plain"))
        os.makedirs(j(b, "real"))
        for p in (j(b, "plain", "file.txt"), j(b, "real", "x.txt")):
            open(p, "w").close()
        os.makedirs("\\\\?\\" + j(b, "spaced "))
        open("\\\\?\\" + j(b, "dotted."), "w").close()
        cls.long = j(b, "A folder with a rather long name")
        os.makedirs(cls.long)
        cls.link = j(b, "link")
        subprocess.run(["cmd", "/c", "mklink", "/J", cls.link, j(b, "real")], capture_output=True, check=True)
        buf = ctypes.create_unicode_buffer(1024)
        ctypes.windll.kernel32.GetShortPathNameW(cls.long, buf, 1024)
        cls.short = buf.value

    @classmethod
    def tearDownClass(cls):
        os.rmdir(cls.link)  # the link only
        shutil.rmtree("\\\\?\\" + cls.base)

    def test_table(self):
        j, b = os.path.join, self.base
        rows = [  # (what, path, odd_name, canonical)
            ("plain", j(b, "plain", "file.txt"), False, True),
            ("through a junction", j(self.link, "x.txt"), False, False),
            ("\\\\?\\ prefix", "\\\\?\\" + j(b, "plain", "file.txt"), True, False),
            ("..", j(b, "plain", "..", "plain", "file.txt"), True, False),
            ("forward slash", b + "/plain/file.txt", True, False),
            ("trailing space", j(b, "spaced "), True, False),
            ("trailing dot", j(b, "dotted."), True, False),
        ]
        for what, path, odd, canon in rows:
            self.assertEqual(winsys.odd_name(path), odd, what)
            self.assertEqual(winsys.canonical(path), canon, what)
            if canon:
                self.assertTrue(winsys.from_list([path]).startswith(path), what)
            else:
                with self.assertRaises(ValueError, msg=what):
                    winsys.from_list([path])

    def test_short_name(self):
        if "~" not in os.path.basename(self.short):
            self.skipTest("8.3 names are switched off on this volume")
        self.assertFalse(winsys.odd_name(self.short))
        self.assertFalse(winsys.canonical(self.short))
        self.assertTrue(winsys.canonical(self.long))
        with self.assertRaises(ValueError):
            winsys.from_list([self.short])


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
        base = os.path.realpath(tempfile.mkdtemp(prefix="disk-cleanup-test-"))
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
