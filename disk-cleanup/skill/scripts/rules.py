"""Where things are on this PC, and what disk-cleanup may offer from them.

Env holds the locations, read once from the environment. The rest is the rule tables: the
areas the scan never offers anything from, the groups it may offer with how safe each one
is, and the Windows-managed places it only lists, with the Windows tool to use instead.
"""
import os

DAY = 86400.0
MB = 1024 * 1024
REPARSE = 0x400  # junction, symlink or mount point: never followed, never offered
PLACEHOLDER = 0x400000 | 0x40000 | 0x1000  # cloud placeholder: reading it downloads it
TEMP_DAYS = 7

SAFETY = {"safe": "Safe", "redo": "Easy to get back", "check": "Your call"}
SAFETY_ORDER = ("safe", "redo", "check")

# id: (label, safety, note)
GROUPS = {
    "temp": ("Temporary files older than 7 days", "safe", ""),
    "crash-dumps": ("Crash dumps and error reports", "safe", ""),
    "browser-cache": ("Browser caches", "safe", ""),
    "app-cache": ("App caches", "safe", ""),
    "gpu-cache": ("Graphics shader caches", "safe", "The first game start after this may be slower."),
    "dev-cache": ("Package manager caches", "redo", ""),
    "downloads": ("Old installers and unfinished downloads in Downloads", "redo", ""),
}

# why a candidate is listed as skipped instead of offered
LINKS = "contains links to other folders"
ONLINE = "contains online-only files"
PARTLY = "parts of it could not be read"
HOLDS = "holds a folder this tool never removes"

# what the walker does with a folder it meets, besides walking it
SKIP, WINDOWS, PROGRAM, APPDATA, SYNCED, DOT, KNOWN = "skip", "windows", "program", "appdata", "synced", "dot", "known"

ROOT_SKIP = {"$recycle.bin", "system volume information", "recovery", "config.msi", "$winreagent", "$sysreset"}
VCS = {".git", ".hg", ".svn"}
OLD_WINDOWS = ("Windows.old", "$Windows.~BT", "$Windows.~WS")
# sync clients' default folders in the profile; besides the plan's four, the defaults of Google Drive's
# mirror mode, Box, Nextcloud, MEGA and Syncthing, left out because removing there removes everywhere
SYNCED_NAMES = ("Dropbox", "iCloudDrive", "iCloud Photos", "Google Drive", "My Drive", "Box", "Nextcloud", "MEGA", "Sync")

CHROMIUM = (("Google\\Chrome", "Chrome", "chrome.exe"), ("Google\\Chrome Beta", "Chrome Beta", "chrome.exe"),
            ("Microsoft\\Edge", "Edge", "msedge.exe"), ("BraveSoftware\\Brave-Browser", "Brave", "brave.exe"),
            ("Vivaldi", "Vivaldi", "vivaldi.exe"), ("Chromium", "Chromium", "chrome.exe"))
OPERA = (("Opera Software\\Opera Stable", "Opera"), ("Opera Software\\Opera GX Stable", "Opera GX"))
APP_CACHES = ("Cache", "Code Cache", "GPUCache")
# (base, folder, app, process, more cache folders). Spotify's Data folder is left out: it may hold downloaded songs.
APPS = (("roaming", "discord", "Discord", "Discord.exe", ()),
        ("roaming", "Slack", "Slack", "slack.exe", ()),
        ("roaming", "Microsoft\\Teams", "Teams", "Teams.exe", ()),
        ("roaming", "Code", "VS Code", "Code.exe", ("CachedData", "CachedExtensionVSIXs")),
        ("roaming", "Code - Insiders", "VS Code Insiders", "Code - Insiders.exe", ("CachedData", "CachedExtensionVSIXs")),
        ("roaming", "Cursor", "Cursor", "Cursor.exe", ("CachedData",)),
        ("local", "Steam\\htmlcache", "Steam", "steam.exe", ()))
GPU = (("local", "NVIDIA\\DXCache", "NVIDIA"), ("local", "NVIDIA\\GLCache", "NVIDIA"),
       ("locallow", "NVIDIA\\PerDriverVersion\\DXCache", "NVIDIA"), ("local", "AMD\\DxCache", "AMD"),
       ("local", "AMD\\DxcCache", "AMD"), ("local", "AMD\\GLCache", "AMD"), ("local", "AMD\\VkCache", "AMD"),
       ("local", "D3DSCache", "DirectX"), ("local", "Intel\\ShaderCache", "Intel"))
DEV = (("local", "npm-cache", "npm"), ("local", "Yarn\\Cache", "Yarn"), ("local", "pip\\Cache", "pip"),
       ("local", "uv\\cache", "uv"), ("local", "NuGet\\v3-cache", "NuGet"), ("profile", ".nuget\\packages", "NuGet"),
       ("profile", ".gradle\\caches", "Gradle"), ("profile", ".cargo\\registry\\cache", "Cargo"),
       ("local", "go-build", "Go"), ("local", "ms-playwright", "Playwright browsers"),
       ("local", "electron\\Cache", "Electron"), ("local", "node-gyp\\Cache", "node-gyp"),
       ("local", "Cypress\\Cache", "Cypress"), ("profile", ".bun\\install\\cache", "Bun"))
CRASH = ("CrashDumps", "Microsoft\\Windows\\WER\\ReportArchive", "Microsoft\\Windows\\WER\\ReportQueue")
PROCESS_NAMES = {"chrome.exe": "Chrome", "msedge.exe": "Edge", "brave.exe": "Brave", "vivaldi.exe": "Vivaldi",
                 "opera.exe": "Opera", "firefox.exe": "Firefox", "discord.exe": "Discord", "slack.exe": "Slack",
                 "teams.exe": "Teams", "code.exe": "VS Code", "code - insiders.exe": "VS Code Insiders",
                 "cursor.exe": "Cursor", "steam.exe": "Steam"}

INSTALLERS = {".exe", ".msi", ".msix", ".msixbundle", ".appx", ".appxbundle", ".msp"}
PARTIALS = {".crdownload", ".part", ".partial", ".download", ".opdownload"}

# id: (label, tool to use instead). The Recycle Bin label takes the drive.
NOT_OFFERED = {
    "recycle-bin": ("Recycle Bin on {}", "Empty it from the Recycle Bin on the desktop when you are sure"),
    "windows-update": ("Windows Update leftovers",
                       "Settings > System > Storage > Temporary files > Windows Update Cleanup"),
    "delivery-opt": ("Delivery Optimization files",
                     "Settings > System > Storage > Temporary files > Delivery Optimization Files"),
    "windows-temp": ("Windows temporary files", "Settings > System > Storage > Temporary files > Temporary files"),
    "system-dumps": ("System crash dumps",
                     "Disk Cleanup (run cleanmgr), Clean up system files, System error memory dump files"),
    "system-wer": ("System error reports", "Disk Cleanup (run cleanmgr), Clean up system files, Windows error reports"),
    "old-windows": ("Previous Windows installation",
                    "Settings > System > Storage > Temporary files > Previous Windows installation(s)"),
    "thumbnails": ("Thumbnail cache", "Disk Cleanup (run cleanmgr), Thumbnails"),
    "inet-cache": ("Temporary Internet Files", "Disk Cleanup (run cleanmgr), Temporary Internet Files"),
}


def ncase(path):
    return os.path.normcase(path)


def under(n, q):
    """For paths already put through ncase: n is q or inside it, on separator boundaries."""
    return n == q or n.startswith(q if q.endswith(os.sep) else q + os.sep)


def is_under(path, prefix):
    """True when `path` is `prefix` or inside it. Case-insensitive, on separator boundaries,
    right for drive roots (c:\\)."""
    return under(ncase(os.path.abspath(path)), ncase(os.path.abspath(prefix)))


def ext(path):
    """The extended-length form of a full path (\\\\?\\C:\\... or \\\\?\\UNC\\server\\share\\...), so
    folders deeper than 260 characters read on PCs without long-path support. Only for reading;
    paths are stored, compared and printed plain."""
    if path.startswith("\\\\?\\"):
        return path
    if path.startswith("\\\\"):
        return "\\\\?\\UNC\\" + path[2:]
    return "\\\\?\\" + path


def link_between(root, path):
    """True when a folder from just below `root` down to `path` itself is a junction, symlink or
    mount point, so `path` really lives somewhere else. `path` must be inside `root`. Raises
    OSError when one of those folders is not there."""
    stop, p, chain = ncase(os.path.abspath(root)), os.path.abspath(path), []
    while ncase(p) != stop and os.path.dirname(p) != p:
        chain.append(p)
        p = os.path.dirname(p)
    return any(os.stat(ext(q), follow_symlinks=False).st_file_attributes & REPARSE for q in reversed(chain))


def unique(paths):
    seen, out = set(), []
    for p in paths:
        if p and ncase(p) not in seen:
            seen.add(ncase(p))
            out.append(p)
    return out


def subdirs(path):
    """Names of the folders directly in `path`, links left out; [] when it cannot be read."""
    try:
        with os.scandir(path) as it:
            return [e.name for e in it if e.is_dir(follow_symlinks=False)
                    and not e.stat(follow_symlinks=False).st_file_attributes & REPARSE]
    except OSError:
        return []


class Env:
    """Every place the rules need, as full long-name paths. Tests build one by hand; drive_roots
    lists extra folders to treat as drive roots (the fixture's made-up drives)."""

    def __init__(self, profile, local, roaming, locallow, temps, downloads, system_root, system_drive,
                 program_files, program_data, synced, out_dir, profiles_dir=None, drive_roots=()):
        def full(p):
            return os.path.abspath(p) if p else None
        self.profile, self.local, self.roaming, self.locallow = full(profile), full(local), full(roaming), full(locallow)
        self.downloads = full(downloads)
        self.system_root, self.system_drive = full(system_root), full(system_drive)
        self.program_files = unique(full(p) for p in program_files)
        self.program_data = full(program_data)
        self.profiles_dir = full(profiles_dir) or os.path.dirname(self.profile)
        self.synced = unique(full(p) for p in synced)
        self.out_dir = full(out_dir)
        self.drive_roots = unique(full(p) for p in drive_roots)
        j, n = os.path.join, ncase
        self.n_profile, self.n_profiles_dir = n(self.profile), n(self.profiles_dir)
        self.n_downloads = n(self.downloads) if self.downloads else None
        self.n_out = n(self.out_dir) if self.out_dir else None
        self.n_roots = {n(p) for p in self.drive_roots + [self.system_drive]}
        self.n_windows = {n(self.system_root)} | {n(j(self.system_drive, x)) for x in OLD_WINDOWS}
        self.n_programs = {n(p) for p in self.program_files} | {n(j(self.local, "Programs"))}
        self.n_appdata = {n(p) for p in (j(self.profile, "AppData"), self.local, self.roaming, self.locallow,
                                         self.program_data) if p}
        self.n_synced = {n(p) for p in self.synced}
        self.n_never_inside = {n(j(self.local, x)) for x in ("Packages", "Docker")}
        self.temps = [t for t in unique(full(p) for p in temps) if self.usable_temp(t)]
        self.n_temps = {n(p) for p in self.temps}
        # folders never offered themselves, and a candidate holding one is skipped instead (HOLDS)
        self.never =(self.n_appdata | self.n_windows | self.n_programs | self.n_synced | self.n_temps
                      | {x for x in (self.n_profile, self.n_profiles_dir, self.n_downloads, self.n_out) if x})

    def is_root(self, n):
        """`n` (through ncase) is a drive root."""
        return n in self.n_roots or os.path.dirname(n) == n

    def usable_temp(self, t):
        """A TEMP or TMP that points somewhere odd (a drive root, the profile, Windows, a synced
        folder, a folder not named like a temp folder) is not used: its children could be anything."""
        n = ncase(t)
        if self.is_root(n) or under(self.n_profile, n):
            return False
        if n in {ncase(p) for p in (self.local, self.roaming, self.locallow, self.downloads, self.profiles_dir) if p}:
            return False
        if any(under(n, q) for q in self.n_windows | self.n_synced | {ncase(p) for p in self.program_files}
               | {ncase(self.program_data)}):
            return False
        return any(part in ("temp", "tmp") for part in n.split(os.sep))

    @classmethod
    def from_system(cls, out_dir=None):
        import winsys
        e = os.environ.get

        def full(p):
            return os.path.abspath(winsys.long_path(p)) if p else None
        j = os.path.join
        profile = full(e("USERPROFILE")) or full(os.path.expanduser("~"))
        local = full(e("LOCALAPPDATA")) or j(profile, "AppData", "Local")
        roaming = full(e("APPDATA")) or j(profile, "AppData", "Roaming")
        system_root = full(e("SystemRoot")) or "C:\\Windows"
        system_drive = (e("SystemDrive") or os.path.splitdrive(system_root)[0]) + "\\"
        synced = [full(e(v)) for v in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial")]
        try:
            synced += [j(profile, x) for x in os.listdir(profile) if x.lower().startswith("onedrive")]
        except OSError:
            pass
        return cls(profile=profile, local=local, roaming=roaming, locallow=j(profile, "AppData", "LocalLow"),
                   temps=[full(e("TEMP")), full(e("TMP")), j(local, "Temp")],
                   downloads=full(winsys.known_folder(winsys.DOWNLOADS)) or j(profile, "Downloads"),
                   system_root=system_root, system_drive=system_drive,
                   program_files=[full(e(v)) for v in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432")],
                   program_data=full(e("ProgramData")) or j(system_drive, "ProgramData"),
                   synced=synced + [j(profile, x) for x in SYNCED_NAMES],
                   out_dir=out_dir or j(profile, "disk-cleanup"))


def dir_kind(env, path, name, at_root, at_profile, at_profiles):
    """What the walker does with folder `path` (called `name`), from its name and place alone.
    at_root, at_profile, at_profiles: its parent is a drive root, the profile, the profiles folder.
    None means walk it."""
    n, low = ncase(path), name.lower()
    if (at_root and low in ROOT_SKIP) or n == env.n_out or low in VCS or (at_profiles and n != env.n_profile):
        return SKIP
    if n in env.n_windows:
        return WINDOWS
    if n in env.n_programs:
        return PROGRAM
    if n in env.n_appdata:
        return APPDATA
    if n in env.n_synced or (at_profile and low.startswith("onedrive")):
        return SYNCED
    if (at_root or at_profile) and low.startswith("."):
        return DOT
    if n in env.n_temps:
        return KNOWN
    return None


def chain(env, path):
    """`path` and the folders above it, from its drive root down."""
    out = [os.path.abspath(path)]
    while not env.is_root(ncase(out[-1])) and os.path.dirname(out[-1]) != out[-1]:
        out.append(os.path.dirname(out[-1]))
    return out[::-1]


def context(env, path):
    """How the walker treats folder `path`, worked out from its drive root down: the kind of
    the first area it is in, or None when it is walked."""
    folders = chain(env, path)
    for parent, p in zip(folders, folders[1:]):
        np = ncase(parent)
        kind = dir_kind(env, p, os.path.basename(p), env.is_root(np), np == env.n_profile, np == env.n_profiles_dir)
        if kind:
            return kind
    return None


def protected(env, path):
    """True when `path` is in a place nothing is ever offered from, whatever rule points there:
    Windows, programs, ProgramData, synced folders, another user's profile, Packages, Docker."""
    n = ncase(os.path.abspath(path))
    if under(n, env.n_profiles_dir) and not under(n, env.n_profile):
        return True
    return any(under(n, q) for q in env.n_windows | env.n_programs | env.n_synced | env.n_never_inside
               | {ncase(env.program_data)})


def target(group, path, note="", process=None, children=False, min_age=0.0):
    return {"group": group, "path": path, "note": note, "process": process, "children": children, "min_age": min_age}


def chromium_apps(env):
    """Folders one or two levels inside roaming and local that hold both Code Cache and GPUCache,
    the mark of an Electron or Chromium app. Never inside Packages, Programs or Microsoft, except
    Microsoft\\Teams, and never a temp folder."""
    found = []
    for base in (env.roaming, env.local):
        for a in subdirs(base):
            pa, low = os.path.join(base, a), a.lower()
            if low in ("packages", "programs") or ncase(pa) in env.n_temps:
                continue
            inner = subdirs(pa)
            if low == "microsoft":
                level2 = [os.path.join(pa, s) for s in inner if s.lower() == "teams"]
            else:
                level2 = [os.path.join(pa, s) for s in inner]
                if {"code cache", "gpucache"} <= {s.lower() for s in inner}:
                    found.append(pa)
            found += [p for p in level2 if {"code cache", "gpucache"} <= {s.lower() for s in subdirs(p)}]
    return found


def known_targets(env):
    """Every known location a rule offers, computed from `env` now. A target with children=True
    offers each thing directly inside it (older than min_age seconds), else the folder itself."""
    j = os.path.join
    base = {"local": env.local, "roaming": env.roaming, "locallow": env.locallow, "profile": env.profile}
    out = [target("temp", t, children=True, min_age=TEMP_DAYS * DAY) for t in env.temps]
    out += [target("crash-dumps", j(env.local, c), children=True) for c in CRASH]
    for sub, app, exe in CHROMIUM:
        ud = j(env.local, sub, "User Data")
        for prof in subdirs(ud):
            low = prof.lower()
            if low == "default" or low.startswith("profile ") or low == "guest profile":
                out += [target("browser-cache", j(ud, prof, c), "%s, %s profile" % (app, prof), exe) for c in APP_CACHES]
        out += [target("browser-cache", j(ud, c), app, exe) for c in ("ShaderCache", "GrShaderCache", "GraphiteDawnCache")]
    out += [target("browser-cache", j(env.local, sub, "Cache"), app, "opera.exe") for sub, app in OPERA]
    ff = j(env.local, "Mozilla", "Firefox", "Profiles")
    for prof in subdirs(ff):
        out += [target("browser-cache", j(ff, prof, c), "Firefox, %s profile" % prof, "firefox.exe")
                for c in ("cache2", "startupCache")]
    for b, sub, app, exe, extra in APPS:
        out += [target("app-cache", j(base[b], sub, c), app, exe) for c in APP_CACHES + extra]
    seen = {ncase(t["path"]) for t in out}
    for folder in chromium_apps(env):
        for c in APP_CACHES:
            p = j(folder, c)
            if ncase(p) not in seen:
                seen.add(ncase(p))
                out.append(target("app-cache", p, os.path.basename(folder)))
    out += [target("gpu-cache", j(base[b], sub), what) for b, sub, what in GPU]
    out += [target("dev-cache", j(base[b], sub), what) for b, sub, what in DEV]
    return out


def downloads_item(name, mtime, now):
    """A file directly in Downloads that the downloads rule offers."""
    ext, age = os.path.splitext(name)[1].lower(), now - mtime
    return (ext in INSTALLERS and age > 30 * DAY) or (ext in PARTIALS and age > 7 * DAY)


def windows_places(env):
    """The Windows-managed places listed under Not offered, as (id, paths). The Recycle Bin is
    asked for separately."""
    j, sr, lo = os.path.join, env.system_root, env.local
    return [("windows-update", [j(sr, "SoftwareDistribution", "Download")]),
            ("delivery-opt", [j(sr, "ServiceProfiles", "NetworkService", "AppData", "Local", "Microsoft", "Windows",
                                "DeliveryOptimization")]),
            ("windows-temp", [j(sr, "Temp")]),
            ("system-dumps", [j(sr, "Minidump"), j(sr, "MEMORY.DMP"), j(sr, "LiveKernelReports")]),
            ("system-wer", [j(env.program_data, "Microsoft", "Windows", "WER")]),
            ("old-windows", [j(env.system_drive, x) for x in OLD_WINDOWS]),
            ("thumbnails", [j(lo, "Microsoft", "Windows", "Explorer", "thumbcache_*.db")]),
            ("inet-cache", [j(lo, "Microsoft", "Windows", "INetCache")])]
