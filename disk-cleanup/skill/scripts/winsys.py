"""Windows calls for disk-cleanup, through ctypes and winreg only.

Known folders, long names, drive type, volume GUID, Recycle Bin settings and usage, the
running processes, and the one call in disk-cleanup that removes anything: moving paths to
the Recycle Bin with SHFileOperationW. No other file in the tool moves, deletes or
overwrites a file the user owns.
"""
import ctypes
import os
import re
import uuid

FO_DELETE = 3
# FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI | FOF_WANTNUKEWARNING
RECYCLE_FLAGS = 0x40 | 0x10 | 0x4 | 0x400 | 0x4000
DRIVE_FIXED = 3
BELOW_NORMAL = 0x4000
DOWNLOADS = "{374DE290-123F-4565-9164-39C4925E467B}"
BITBUCKET = r"Software\Microsoft\Windows\CurrentVersion\Explorer\BitBucket\Volume"
POLICIES = r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer"
SYNC_ROOTS = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\SyncRootManager"
ONEDRIVE = r"Software\Microsoft\OneDrive\Accounts"
_64 = ctypes.sizeof(ctypes.c_void_p) == 8
_PACK = 8 if _64 else 1  # shellapi.h packs its structs to 8 bytes on 64-bit Windows and 1 on 32-bit


class SHFILEOPSTRUCTW(ctypes.Structure):
    _pack_ = _PACK
    _fields_ = [("hwnd", ctypes.c_void_p), ("wFunc", ctypes.c_uint), ("pFrom", ctypes.c_void_p),
                ("pTo", ctypes.c_void_p), ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", ctypes.c_int),
                ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", ctypes.c_void_p)]


class SHQUERYRBINFO(ctypes.Structure):
    _pack_ = _PACK
    _fields_ = [("cbSize", ctypes.c_ulong), ("i64Size", ctypes.c_longlong), ("i64NumItems", ctypes.c_longlong)]


class GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort), ("Data3", ctypes.c_ushort),
                ("Data4", ctypes.c_ubyte * 8)]


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", ctypes.c_ulong), ("cntUsage", ctypes.c_ulong), ("th32ProcessID", ctypes.c_ulong),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", ctypes.c_ulong),
                ("cntThreads", ctypes.c_ulong), ("th32ParentProcessID", ctypes.c_ulong),
                ("pcPriClassBase", ctypes.c_long), ("dwFlags", ctypes.c_ulong), ("szExeFile", ctypes.c_wchar * 260)]


_API = []


def _api():
    """kernel32, shell32 and ole32 with their prototypes, loaded on first use."""
    if not _API:
        k, sh, ole = (ctypes.WinDLL(n, use_last_error=True) for n in ("kernel32", "shell32", "ole32"))
        P, W, U = ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_ulong
        for fn, args, res in [
            (k.GetLongPathNameW, [W, W, U], U),
            (k.GetDriveTypeW, [W], ctypes.c_uint),
            (k.GetVolumeNameForVolumeMountPointW, [W, W, U], ctypes.c_int),
            (k.CreateToolhelp32Snapshot, [U, U], P),
            (k.Process32FirstW, [P, ctypes.POINTER(PROCESSENTRY32W)], ctypes.c_int),
            (k.Process32NextW, [P, ctypes.POINTER(PROCESSENTRY32W)], ctypes.c_int),
            (k.CloseHandle, [P], ctypes.c_int),
            (k.GetCurrentProcess, [], P),
            (k.SetPriorityClass, [P, U], ctypes.c_int),
            (sh.SHGetKnownFolderPath, [ctypes.POINTER(GUID), U, P, ctypes.POINTER(P)], ctypes.c_long),
            (sh.SHQueryRecycleBinW, [W, ctypes.POINTER(SHQUERYRBINFO)], ctypes.c_long),
            (sh.SHFileOperationW, [ctypes.POINTER(SHFILEOPSTRUCTW)], ctypes.c_int),
            (ole.CoTaskMemFree, [P], None),
        ]:
            fn.argtypes, fn.restype = args, res
        _API.extend([k, sh, ole])
    return _API


def known_folder(guid):
    """The path of a Windows known folder, such as Downloads, or None."""
    k, sh, ole = _api()
    g = GUID.from_buffer_copy(uuid.UUID(guid).bytes_le)
    p = ctypes.c_void_p()
    hr = sh.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(p))
    try:
        return ctypes.wstring_at(p.value) if hr == 0 and p.value else None
    finally:
        if p.value:
            ole.CoTaskMemFree(p)


def long_path(path):
    """`path` with 8.3 short names (C:\\Users\\JOHNSM~1) expanded; unchanged if that fails."""
    if not path:
        return path
    k = _api()[0]
    size = 1024
    for _ in range(2):
        buf = ctypes.create_unicode_buffer(size)
        n = k.GetLongPathNameW(path, buf, size)
        if n == 0:
            return path
        if n < size:
            return buf.value
        size = n + 1
    return path


def drive_of(path):
    """The root a path lives on, as Windows wants it: C:\\ or \\\\server\\share\\."""
    drive = os.path.splitdrive(os.path.abspath(path))[0]
    return drive + "\\" if drive else None


def drive_type(root):
    """3 for a fixed disk (GetDriveTypeW)."""
    return _api()[0].GetDriveTypeW(root)


def volume_guid(root):
    """The {GUID} of the volume mounted at `root`, as the BitBucket registry keys name it."""
    buf = ctypes.create_unicode_buffer(64)
    if not _api()[0].GetVolumeNameForVolumeMountPointW(root, buf, 64):
        return None
    m = re.search(r"\{[0-9A-Fa-f-]{36}\}", buf.value)
    return m.group(0) if m else None


def _reg(hive, key, name):
    import winreg
    try:
        with winreg.OpenKey(hive, key) as h:
            return winreg.QueryValueEx(h, name)[0]
    except OSError:
        return None


def recycle_settings(root):
    """How the Recycle Bin behaves on the volume at `root`: max_mb (MaxCapacity, or None when
    unknown), nuke (the bin is switched off for that volume) and policy (switched off by policy)."""
    import winreg
    guid = volume_guid(root)
    key = BITBUCKET + "\\" + guid if guid else None
    max_mb = _reg(winreg.HKEY_CURRENT_USER, key, "MaxCapacity") if key else None
    nuke = _reg(winreg.HKEY_CURRENT_USER, key, "NukeOnDelete") if key else None
    policy = any(_reg(h, POLICIES, "NoRecycleFiles") for h in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE))
    return {"max_mb": max_mb if isinstance(max_mb, int) else None, "nuke": bool(nuke), "policy": bool(policy)}


def _subkeys(reg, hive, key):
    try:
        with reg.OpenKey(hive, key) as h:
            out, i = [], 0
            while True:
                try:
                    out.append(reg.EnumKey(h, i))
                except OSError:
                    return out
                i += 1
    except OSError:
        return []


def _values(reg, hive, key):
    """(name, data) of every value of a key; [] when it is not there."""
    try:
        with reg.OpenKey(hive, key) as h:
            out, i = [], 0
            while True:
                try:
                    name, data, _ = reg.EnumValue(h, i)
                except OSError:
                    return out
                out.append((name, data))
                i += 1
    except OSError:
        return []


def sync_roots(reg=None):
    """Folders that sync clients told Windows about: every UserSyncRoots value under
    SyncRootManager (whatever the user), and every OneDrive account's UserFolder and mount points.
    Read-only; a missing key is skipped. Tests pass a fake winreg as `reg`."""
    if reg is None:
        import winreg as reg
    out = []
    for sub in _subkeys(reg, reg.HKEY_LOCAL_MACHINE, SYNC_ROOTS):
        out += [d for _, d in _values(reg, reg.HKEY_LOCAL_MACHINE, SYNC_ROOTS + "\\" + sub + "\\UserSyncRoots")]
    for account in _subkeys(reg, reg.HKEY_CURRENT_USER, ONEDRIVE):
        key = ONEDRIVE + "\\" + account
        out += [d for n, d in _values(reg, reg.HKEY_CURRENT_USER, key) if n.lower() == "userfolder"]
        out += [d for _, d in _values(reg, reg.HKEY_CURRENT_USER, key + "\\ScopeIdToMountPointPathCache")]
    return [p for p in out if isinstance(p, str) and p.strip()]


def odd_name(path):
    """True for a path that Windows tools may read as another one: a \\\\?\\ or \\\\.\\ prefix, a /, a
    . or .. part, a part ending in a space or a dot, or anything os.path.abspath would change."""
    if not path or "\0" in path or path.startswith(("\\\\?\\", "\\\\.\\")) or "/" in path:
        return True
    if os.path.abspath(path) != path:
        return True
    return any(p in (".", "..") or p.endswith((" ", ".")) for p in os.path.splitdrive(path)[1].split("\\") if p)


def canonical(path):
    """True when `path` is the one plain spelling of what it names: not odd_name, no 8.3 short
    name, and no junction or symlink on the way (its realpath is itself)."""
    if odd_name(path):
        return False
    try:
        real = os.path.realpath(path)
    except (OSError, ValueError):
        return False
    return os.path.normcase(real) == os.path.normcase(path) and os.path.normcase(long_path(path)) == os.path.normcase(path)


def recycle_usage(root):
    """(bytes, items) in the Recycle Bin of the drive at `root`, or (None, None)."""
    info = SHQUERYRBINFO()
    info.cbSize = ctypes.sizeof(SHQUERYRBINFO)
    if _api()[1].SHQueryRecycleBinW(root, ctypes.byref(info)) != 0:
        return None, None
    return info.i64Size, info.i64NumItems


def processes():
    """Lower-case exe names of the running processes."""
    k = _api()[0]
    snap = k.CreateToolhelp32Snapshot(2, 0)  # TH32CS_SNAPPROCESS
    if not snap or snap == ctypes.c_void_p(-1).value:
        return set()
    names = set()
    try:
        pe = PROCESSENTRY32W()
        pe.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        ok = k.Process32FirstW(snap, ctypes.byref(pe))
        while ok:
            names.add(pe.szExeFile.lower())
            ok = k.Process32NextW(snap, ctypes.byref(pe))
    finally:
        k.CloseHandle(snap)
    return names


def set_low_priority():
    """Run below normal priority, so the PC stays usable during a long scan."""
    k = _api()[0]
    return bool(k.SetPriorityClass(k.GetCurrentProcess(), BELOW_NORMAL))


def from_list(paths):
    """The double-null-terminated list SHFileOperationW reads. Refuses anything that is not a
    plain full path in its one canonical spelling (the call reads * and ? as wildcards, and Win32
    path rules would turn an odd spelling into another folder), and any drive root."""
    for p in paths:
        if (not os.path.isabs(p) or any(c in p for c in "*?\0") or os.path.splitdrive(p)[0] == ""
                or os.path.dirname(p) == p or not canonical(p)):
            raise ValueError("not a path that can go to the Recycle Bin: %r" % p)
    return "\0".join(paths) + "\0"


def recycle(paths):
    """Move `paths` to the Recycle Bin in one SHFileOperationW call, with no dialogs except the
    one Windows shows before it would delete something for good. Returns (code, aborted).
    The caller checks afterwards which paths are really gone."""
    if not paths:
        return 0, False
    buf = ctypes.create_unicode_buffer(from_list(paths))
    op = SHFILEOPSTRUCTW()
    op.wFunc, op.pFrom, op.fFlags = FO_DELETE, ctypes.addressof(buf), RECYCLE_FLAGS
    code = _api()[1].SHFileOperationW(ctypes.byref(op))
    return code, bool(op.fAnyOperationsAborted)


class WinSys:
    """Every Windows call the scan and the clean make. Tests swap in a fake with the same methods."""
    processes = staticmethod(processes)
    drive_type = staticmethod(drive_type)
    recycle_settings = staticmethod(recycle_settings)
    recycle_usage = staticmethod(recycle_usage)
    recycle = staticmethod(recycle)
