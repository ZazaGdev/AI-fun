"""Where things are on this PC, and what disk-cleanup may offer from them.

Env holds the locations, read once from the environment. The rest is the rule tables: the
areas the scan never offers anything from, the groups it may offer with how safe each one
is, and the Windows-managed places it only lists, with the Windows tool to use instead.
"""
import os
import re

DAY = 86400.0
MB = 1024 * 1024
REPARSE = 0x400  # junction, symlink or mount point: never followed, never offered
PLACEHOLDER = 0x400000 | 0x40000 | 0x1000  # cloud placeholder: reading it downloads it
TEMP_DAYS, PROJECT_DAYS, EMPTY_DAYS = 7, 14, 30

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
    "build-node": ("node_modules folders", "redo", "npm install brings it back."),
    "build-output": ("Other build output", "redo", ""),
    "py-cache": ("Python caches", "safe", ""),
    "py-venv": ("Python virtual environments", "redo", "Reinstall packages with pip install -r requirements.txt."),
    "duplicates": ("Duplicate files (pick which copies to remove)", "check", ""),
    "empty": ("Empty folders", "safe", ""),
    "large-old": ("Large files not changed in 6 months (pick the ones to remove)", "check", ""),
}
GROUP_ORDER = list(GROUPS)
BUILD_GROUPS = ("build-node", "build-output", "py-venv")  # the 14-day project rule applies to these

# why a candidate is listed as skipped instead of offered
LINKS = "contains links to other folders"
ONLINE = "contains online-only files"
PARTLY = "parts of it could not be read"
HOLDS = "holds a folder this tool never removes"
RECENT = "project changed in the last 14 days"
RECENT_VENV = "changed in the last 14 days"

# what the walker does with a folder it meets, besides walking it
SKIP, WINDOWS, PROGRAM, APPDATA, SYNCED, DOT, KNOWN = "skip", "windows", "program", "appdata", "synced", "dot", "known"
INSIDE = "inside"  # it is, or is inside, something a pattern rule offers as one item

ROOT_SKIP = {"$recycle.bin", "system volume information", "recovery", "config.msi", "$winreagent", "$sysreset"}
VCS = {".git", ".hg", ".svn"}
OLD_WINDOWS = ("Windows.old", "$Windows.~BT", "$Windows.~WS")
PROGRAM_NAMES = {"program files", "program files (x86)", "steamapps", "steamlibrary", "epic games", "gog games",
                 "xboxgames", "riot games", "ea games", "ubisoft game launcher"}
# sync clients' default folders in the profile; besides the plan's four, the defaults of Google Drive's
# mirror mode, Box, Nextcloud, MEGA and Syncthing, left out because removing there removes everywhere
SYNCED_NAMES = ("Dropbox", "iCloudDrive", "iCloud Photos", "Google Drive", "My Drive", "Box", "Nextcloud", "MEGA", "Sync")
SHELL_FOLDERS = ("Desktop", "Documents", "Downloads", "Music", "Pictures", "Videos", "Favorites", "Links", "Contacts",
                 "Searches", "Saved Games", "3D Objects")

MARKERS = {"package.json", "cargo.toml", "pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle",
           "settings.gradle.kts", "pyproject.toml", "requirements.txt"}
MARKER_EXTS = {".csproj", ".fsproj", ".vbproj", ".sln", ".uproject"}
JS_BUILD = {".next": "Next.js build output", ".nuxt": "Nuxt build output", ".svelte-kit": "SvelteKit build output",
            ".parcel-cache": "Parcel cache", ".turbo": "Turborepo cache", ".angular": "Angular cache"}
PY_CACHES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
CONTENT = set(".jpg .jpeg .png .gif .heic .webp .bmp .tif .tiff .raw .cr2 .nef .arw .dng "
              ".mp4 .mov .avi .mkv .wmv .m4v .webm .mts .mp3 .wav .flac .m4a .aac .ogg .wma "
              ".pdf .doc .docx .xls .xlsx .ppt .pptx .odt .rtf .epub .zip .rar .7z .tar .gz .tgz "
              ".exe .msi .iso .img".split())
DISK_IMAGES = set(".iso .img .vhd .vhdx .vmdk .vdi .qcow2".split())
COPY_NAME = re.compile(r"( \(\d+\)| - copy( \(\d+\))?)$|^copy of ", re.I)

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
    "programs": ("Installed programs and games", "Settings > Apps > Installed apps, or the game's launcher"),
    "synced": ("Synced folders (OneDrive, Dropbox, iCloud, Google Drive)",
               "Removing files here removes them on your other devices too. To free space, right-click the "
               "folder in File Explorer and choose Free up space"),
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
    OSError when one of those folders is not there (every one is looked at, even past a link)."""
    stop, p, chain_ = ncase(os.path.abspath(root)), os.path.abspath(path), []
    while ncase(p) != stop and os.path.dirname(p) != p:
        chain_.append(p)
        p = os.path.dirname(p)
    return any([os.stat(ext(q), follow_symlinks=False).st_file_attributes & REPARSE for q in reversed(chain_)])


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


def names(path):
    """Lower-case names of the files and of the folders directly in `path`. Links and online-only
    files count: they still mark a program or a project. Two empty sets when it cannot be read."""
    files, dirs = set(), set()
    try:
        with os.scandir(ext(path)) as it:
            for e in it:
                (dirs if e.is_dir(follow_symlinks=False) else files).add(e.name.lower())
    except OSError:
        pass
    return files, dirs


def where(*paths):
    """Each location through ncase, and also where it really is when a link leads there (the
    profile on another drive behind a junction, say), so the real place is protected too."""
    out = set()
    for p in paths:
        if p:
            out.add(ncase(p))
            try:
                out.add(ncase(os.path.realpath(p)))
            except (OSError, ValueError):
                pass
    return out


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
        self.n_profile = n(self.profile)
        self.n_profiles, self.n_profiles_dirs = where(self.profile), where(self.profiles_dir)
        self.n_downloads = n(self.downloads) if self.downloads else None
        self.n_desktop = n(j(self.profile, "Desktop"))
        self.n_out = n(self.out_dir) if self.out_dir else None
        self.n_roots = {n(p) for p in self.drive_roots + [self.system_drive]}
        self.n_windows = where(self.system_root, *[j(self.system_drive, x) for x in OLD_WINDOWS])
        self.n_programs = where(*self.program_files + [j(self.local, "Programs")])
        self.n_appdata = where(j(self.profile, "AppData"), self.local, self.roaming, self.locallow, self.program_data)
        self.n_synced = where(*self.synced)
        self.n_never_inside = where(j(self.local, "Packages"), j(self.local, "Docker"))
        self.n_shell = where(self.downloads, *[j(self.profile, x) for x in SHELL_FOLDERS])
        self.temps = [t for t in unique(full(p) for p in temps) if self.usable_temp(t)]
        self.n_temps = {n(p) for p in self.temps}
        # folders never offered themselves, and a candidate holding one is skipped instead (HOLDS)
        self.never = (self.n_appdata | self.n_windows | self.n_programs | self.n_synced | self.n_temps
                      | self.n_profiles | self.n_profiles_dirs | {x for x in (self.n_downloads, self.n_out) if x})

    def is_root(self, n):
        """`n` (through ncase) is a drive root."""
        return n in self.n_roots or os.path.dirname(n) == n

    def usable_temp(self, t):
        """A TEMP or TMP that points somewhere odd (a drive root, the profile, Windows, a synced
        folder, a folder not named like a temp folder) is not used: its children could be anything."""
        n = ncase(t)
        if self.is_root(n) or any(under(p, n) for p in self.n_profiles):
            return False
        if n in {ncase(p) for p in (self.local, self.roaming, self.locallow, self.downloads, self.profiles_dir) if p}:
            return False
        if any(under(n, q) for q in self.n_windows | self.n_synced | self.n_programs | where(self.program_data)):
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
    None means walk it. Besides the plan's areas, any folder named AppData and a Windows or
    ProgramData folder at any drive root (an old system disk) are left alone too."""
    n, low = ncase(path), name.lower()
    if ((at_root and low in ROOT_SKIP) or n == env.n_out or low in VCS
            or (at_profiles and n not in env.n_profiles)):
        return SKIP
    if n in env.n_windows or (at_root and low == "windows"):
        return WINDOWS
    if n in env.n_programs or low in PROGRAM_NAMES:
        return PROGRAM
    if n in env.n_appdata or low == "appdata" or (at_root and low == "programdata"):
        return APPDATA
    if n in env.n_synced or (at_profile and low.startswith("onedrive")):
        return SYNCED
    if (at_root or at_profile) and low.startswith("."):
        return DOT
    if n in env.n_temps:
        return KNOWN
    return None


def holds_program(files):
    """At least one .exe and one .dll among the lower-case file names directly in a folder: an
    installed or portable program."""
    exts = {os.path.splitext(f)[1] for f in files}
    return ".exe" in exts and ".dll" in exts


def is_project(files, dirs):
    """A project marker among the lower-case file and folder names directly in a folder."""
    return (bool(files & MARKERS) or any(os.path.splitext(f)[1] in MARKER_EXTS for f in files)
            or ".git" in files or ".git" in dirs or {"assets", "projectsettings"} <= dirs)


def build_rule(name, files, dirs):
    """(group, note) when folder `name`, in a folder holding these lower-case file and folder
    names, is build output or a cache a pattern rule offers as one item; else None."""
    low, exts = name.lower(), {os.path.splitext(f)[1] for f in files}
    if low == "node_modules" and "package.json" in files:
        return "build-node", ""
    if low in ("bin", "obj") and exts & {".csproj", ".fsproj", ".vbproj"}:
        return "build-output", ".NET build output (%s)" % name
    if low == "target" and "cargo.toml" in files:
        return "build-output", "Rust build output (target)"
    if low == "target" and "pom.xml" in files:
        return "build-output", "Maven build output (target)"
    if low in ("build", ".gradle") and files & {"build.gradle", "build.gradle.kts"}:
        return "build-output", "Gradle build output (%s)" % name
    if low in JS_BUILD and "package.json" in files:
        return "build-output", "%s (%s)" % (JS_BUILD[low], name)
    if low == "library" and {"assets", "projectsettings"} <= dirs:
        return "build-output", "Unity Library"
    if low in ("intermediate", "deriveddatacache") and ".uproject" in exts:
        return "build-output", "Unreal %s" % name
    if low in PY_CACHES:
        return "py-cache", ""
    return None


def chain(env, path):
    """`path` and the folders above it, from its drive root down."""
    out = [os.path.abspath(path)]
    while not env.is_root(ncase(out[-1])) and os.path.dirname(out[-1]) != out[-1]:
        out.append(os.path.dirname(out[-1]))
    return out[::-1]


def context(env, path):
    """How the walker treats folder `path`, worked out from its drive root down the way the walk
    would meet it. Returns (kind, projects): kind None when it is walked, else the area it is in;
    projects are the folders above it that start project areas."""
    folders, projects = chain(env, path), ()
    for parent, p in zip(folders, folders[1:]):
        np = ncase(parent)
        files, dirs = names(parent)
        at_root, at_profile = env.is_root(np), np in env.n_profiles
        if holds_program(files) and not (at_root or at_profile):
            return PROGRAM, projects
        if "pyvenv.cfg" in files:
            return INSIDE, projects
        if is_project(files, dirs):
            projects += (parent,)
        name = os.path.basename(p)
        kind = dir_kind(env, p, name, at_root, at_profile, np in env.n_profiles_dirs)
        if kind:
            return kind, projects
        if build_rule(name, files, dirs):
            return INSIDE, projects
    return None, projects


def protected(env, path):
    """True when `path` is in a place nothing is ever offered from, whatever rule points there:
    Windows, programs, ProgramData, synced folders, another user's profile, Packages, Docker."""
    n = ncase(os.path.abspath(path))
    if any(under(n, d) for d in env.n_profiles_dirs) and not any(under(n, p) for p in env.n_profiles):
        return True
    return any(under(n, q) for q in env.n_windows | env.n_programs | env.n_synced | env.n_never_inside
               | where(env.program_data))


def may_offer_empty(env, path, root):
    """An empty folder may be offered unless it is the scan root, directly in a drive root, the
    profile or directly in it, a shell folder such as Documents or Music, or never removed."""
    n, up = ncase(path), ncase(os.path.dirname(path))
    return not (n == ncase(root) or env.is_root(up) or n in env.n_profiles or up in env.n_profiles
                or n in env.n_shell or n in env.never)


def keep_key(env, path, mtime):
    """Sort key for the copy of a duplicate set to suggest keeping, smallest first: a copy outside
    Downloads, Desktop and the temp folders; then one whose name does not look like a copy; then
    the oldest; then the shortest path; then alphabetical."""
    n = ncase(path)
    passing = any(under(n, q) for q in {env.n_downloads, env.n_desktop} | env.n_temps if q)
    copy = bool(COPY_NAME.search(os.path.splitext(os.path.basename(path))[0]))
    return (passing, copy, mtime, len(path), n)


def label(gid, large_days=180):
    """A group's label; the large-file one says the --large-days in use."""
    text = GROUPS[gid][0]
    return text.replace("6 months", "%g days" % large_days) if gid == "large-old" and large_days != 180 else text


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
    ext_, age = os.path.splitext(name)[1].lower(), now - mtime
    return (ext_ in INSTALLERS and age > 30 * DAY) or (ext_ in PARTIALS and age > 7 * DAY)


def windows_places(env):
    """The Windows-managed places listed under Not offered, as (id, paths). The Recycle Bin, the
    programs and the synced folders are found by the scan itself."""
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
