"""The disk-cleanup scan: walk one folder with at most 4 threads, sort what it meets into the
areas in rules.py, measure what the rules offer, and build the report. It only reads.
"""
import datetime
import fnmatch
import os
import queue
import stat
import threading
import time

import rules
from rules import PLACEHOLDER, REPARSE, ext, ncase

MAX_WORKERS = 4


def clamp_workers(n):
    """--workers is clamped to 1..4."""
    return max(1, min(MAX_WORKERS, int(n)))


def drive_label(root):
    drive, rest = os.path.splitdrive(root)
    return drive if drive and rest in ("", "\\") else root


def unnest(cands):
    """Drop repeats and anything inside another candidate; the outer one stays."""
    out, kept = [], set()
    for c in sorted(cands, key=lambda c: len(c["path"])):
        n = ncase(c["path"])
        up, inside = n, n in kept
        while not inside and os.path.dirname(up) != up:
            up = os.path.dirname(up)
            inside = up in kept
        if not inside:
            kept.add(n)
            out.append(c)
    return out


class Measure:
    """What one subtree holds, read by one worker with its own stack."""
    __slots__ = ("size", "files", "folders", "newest", "links", "online", "bad", "holds")

    def __init__(self):
        self.size = self.files = self.folders = self.bad = 0
        self.newest = 0.0
        self.links = self.online = self.holds = False

    def skip_reason(self):
        return (rules.LINKS if self.links else rules.ONLINE if self.online else rules.PARTLY if self.bad
                else rules.HOLDS if self.holds else None)


class Scanner:
    """One scan of `root`. run() returns the report as a dict, ready to write as JSON."""

    def __init__(self, env, win, root, workers=MAX_WORKERS, dupe_min_mb=1, large_mb=500, large_days=180,
                 now=None, progress=None, every=15.0):
        self.env, self.win, self.root = env, win, os.path.abspath(root)
        self.workers = clamp_workers(workers)
        self.settings = {"dupe_min_mb": dupe_min_mb, "large_mb": large_mb, "large_days": large_days}
        self.now = time.time() if now is None else now
        self.progress, self.every = progress, every
        self.lock = threading.Lock()
        self.tasks = queue.Queue()
        self.pending = 0
        self.idle = threading.Event()
        self.errors = []
        self.files = self.folders = 0
        self.unread, self.denied, self.examples = 0, 0, []
        self.cands = []      # what the rules offer, or list as skipped
        self.windows = {}    # Not offered id: {"size", "paths"}
        self.threads = []    # names of the worker threads that ran

    # ---- the work queue: tasks are "list one folder" or "measure one subtree" ----

    def put(self, fn, *args):
        with self.lock:
            self.pending += 1
        self.tasks.put((fn, args))

    def work(self):
        while True:
            task = self.tasks.get()
            if task is None:
                return
            fn, args = task
            try:
                if not self.errors:
                    fn(*args)
            except Exception as e:  # a bug, not a folder that cannot be read: stop the scan and say so
                with self.lock:
                    self.errors.append(e)
            finally:
                with self.lock:
                    self.pending -= 1
                    if not self.pending:
                        self.idle.set()

    def run(self):
        start = time.time()
        self.put(self.plan)
        threads = [threading.Thread(target=self.work, name="disk-cleanup-%d" % i, daemon=True)
                   for i in range(self.workers)]
        for t in threads:
            t.start()
        self.threads = [t.name for t in threads]
        while not self.idle.wait(self.every):
            if self.progress:
                self.progress(self.files, self.folders, time.time() - start)
        for _ in threads:
            self.tasks.put(None)
        for t in threads:
            t.join()
        if self.errors:
            raise self.errors[0]
        return self.report(time.time() - start)

    # ---- reading ----

    def unreadable(self, path, err):
        with self.lock:
            self.unread += 1
            self.denied += isinstance(err, PermissionError)
            if len(self.examples) < 50:
                self.examples.append(path)

    def listing(self, path, count=True):
        """(entry, stat) for everything directly in a folder, or None when it cannot be read."""
        try:
            with os.scandir(ext(path)) as it:
                return [(e, e.stat(follow_symlinks=False)) for e in it]
        except OSError as err:
            if count:
                self.unreadable(path, err)
            return None

    def measure(self, path, count=True):
        """Size and number of the files in a subtree (links and online-only files not counted),
        its newest change, and whether it holds links, online-only files, unreadable folders or
        a folder that is never removed. None when `path` itself cannot be read."""
        m, stack, top = Measure(), [path], True
        while stack:
            d = stack.pop()
            entries = self.listing(d, count)
            if entries is None:
                if top:
                    return None
                m.bad += 1
                continue
            top, files = False, 0
            for e, st in entries:
                a = st.st_file_attributes
                if a & REPARSE:
                    m.links = True
                elif e.is_dir(follow_symlinks=False):
                    p = os.path.join(d, e.name)
                    m.holds = m.holds or ncase(p) in self.env.never
                    m.folders += 1
                    m.newest = max(m.newest, st.st_mtime)
                    stack.append(p)
                elif a & PLACEHOLDER:
                    m.online = True
                else:
                    files += 1
                    m.size += st.st_size
                    m.newest = max(m.newest, st.st_mtime)
            m.files += files
            with self.lock:  # as it goes, so the progress line moves during a big subtree
                self.files += files
                self.folders += 1
        return m

    def add(self, group, path, kind, size, mtime, note="", process=None, skip=None, project=None):
        with self.lock:
            self.cands.append({"group": group, "path": path, "kind": kind, "size": size, "mtime": mtime,
                               "note": note, "process": process, "skip": skip, "project": project})

    # ---- tasks ----

    def plan(self):
        """The first task: queue the known locations, the Windows-managed places and the walk."""
        env, root = self.env, self.root
        for t in rules.known_targets(env):
            if rules.protected(env, t["path"]):
                continue
            if t["children"]:
                if rules.is_under(t["path"], root) or rules.is_under(root, t["path"]):
                    self.put(self.children, t)
            elif rules.is_under(t["path"], root):
                self.put(self.known, t)
        for wid, paths in rules.windows_places(env):
            paths = [p for p in paths if rules.is_under(p, root)]
            if paths:
                self.put(self.windows_place, wid, paths)
        if env.is_root(ncase(root)):
            size, _ = self.win.recycle_usage(root)
            with self.lock:
                self.windows["recycle-bin"] = {"size": size, "paths": [root]}
        if rules.context(env, root) is None:
            self.put(self.list_dir, root)

    def candidate(self, group, path, st, note="", process=None, min_age=0.0, project=None):
        """Measure a folder a rule offers as one item."""
        if ncase(path) in self.env.never:
            return
        m = self.measure(path)
        if m is None:
            return
        mtime = max(st.st_mtime, m.newest)
        if min_age and self.now - mtime <= min_age:
            return
        self.add(group, path, "dir", m.size, mtime, note, process, m.skip_reason(), project)

    def linked(self, t):
        """A known location reached through a link (it, or a folder between it and the scan root)
        is listed as skipped: what is behind the link is not inside the scan root."""
        if rules.link_between(self.root, t["path"]):
            self.add(t["group"], t["path"], "dir", 0, 0.0, t["note"], t["process"], rules.LINKS)
            return True
        return False

    def known(self, t):
        """A known location offered as one folder."""
        try:
            if self.linked(t):
                return
            st = os.stat(ext(t["path"]), follow_symlinks=False)
        except OSError:
            return  # not on this PC
        if stat.S_ISDIR(st.st_mode):
            self.candidate(t["group"], t["path"], st, t["note"], t["process"])

    def children(self, t):
        """A known folder whose direct children are offered one by one (temp files, crash dumps)."""
        try:
            if rules.is_under(t["path"], self.root) and self.linked(t):
                return
            st = os.stat(ext(t["path"]), follow_symlinks=False)
        except OSError:
            return
        if st.st_file_attributes & REPARSE or not stat.S_ISDIR(st.st_mode):
            return
        entries = self.listing(t["path"])
        if entries is None:
            return
        files = 0
        for e, st in entries:
            p, a = os.path.join(t["path"], e.name), st.st_file_attributes
            if a & REPARSE or ncase(p) in self.env.never or not rules.is_under(p, self.root):
                continue
            if e.is_dir(follow_symlinks=False):
                self.put(self.candidate, t["group"], p, st, t["note"], t["process"], t["min_age"])
            elif not a & PLACEHOLDER:
                files += 1
                if not t["min_age"] or self.now - st.st_mtime > t["min_age"]:
                    self.add(t["group"], p, "file", st.st_size, st.st_mtime, t["note"], t["process"])
        with self.lock:
            self.files += files
            self.folders += 1

    def windows_place(self, wid, paths):
        """Size of a Windows-managed place for the Not offered list; None when Windows does not
        let a normal user read it."""
        total, found, unknown = 0, [], False
        for p in paths:
            folder, name = os.path.split(p)
            if "*" in name:
                entries = self.listing(folder, count=False) or []
                hits = [st.st_size for e, st in entries if fnmatch.fnmatch(e.name.lower(), name.lower())
                        and not e.is_dir(follow_symlinks=False)]
                if hits:
                    found.append(p)
                    total += sum(hits)
                continue
            try:
                st = os.stat(ext(p), follow_symlinks=False)
            except FileNotFoundError:
                continue
            except OSError:
                found.append(p)
                unknown = True
                continue
            found.append(p)
            if st.st_file_attributes & REPARSE:
                continue
            if stat.S_ISDIR(st.st_mode):
                m = self.measure(p, count=False)
                unknown = unknown or m is None
                total += m.size if m else 0
            else:
                total += st.st_size
        if found:
            with self.lock:
                self.windows[wid] = {"size": None if unknown else total, "paths": found}

    def list_dir(self, path):
        """One folder of the walk: count its files, apply the file rules, then queue or pass by
        each folder in it according to its area."""
        env = self.env
        entries = self.listing(path)
        if entries is None:
            return
        n = ncase(path)
        at_root, at_profile, at_profiles = env.is_root(n), n == env.n_profile, n == env.n_profiles_dir
        downloads, files = n == env.n_downloads, 0
        for e, st in entries:
            a = st.st_file_attributes
            if a & REPARSE:
                continue
            p = os.path.join(path, e.name)
            if e.is_dir(follow_symlinks=False):
                if rules.dir_kind(env, p, e.name, at_root, at_profile, at_profiles) is None:
                    self.put(self.list_dir, p)
            elif not a & PLACEHOLDER:
                files += 1
                if downloads and rules.downloads_item(e.name, st.st_mtime, self.now):
                    self.add("downloads", p, "file", st.st_size, st.st_mtime)
        with self.lock:
            self.files += files
            self.folders += 1

    # ---- the report ----

    def report(self, seconds):
        by = {}
        for c in unnest(self.cands):
            by.setdefault(c["group"], []).append(c)
        order = lambda c: (-c["size"], ncase(c["path"]))  # noqa: E731
        groups, left_out = [], []
        for gid, (label, safety, note) in rules.GROUPS.items():
            cs = by.get(gid, [])
            items = sorted((c for c in cs if not c["skip"]), key=order)
            skipped = [{"path": c["path"], "size": c["size"], "reason": c["skip"]}
                       for c in sorted((c for c in cs if c["skip"]), key=order)]
            if items:
                groups.append({"id": gid, "label": label, "safety": safety, "note": note,
                               "size": sum(c["size"] for c in items), "count": len(items),
                               "items": items, "skipped": skipped})
            elif skipped:
                left_out.append({"id": gid, "label": label, "skipped": skipped})
        groups.sort(key=lambda g: (rules.SAFETY_ORDER.index(g["safety"]), -g["size"]))
        out, n = [], 0
        for gn, g in enumerate(groups, 1):
            items = []
            for c in g["items"]:
                n += 1
                items.append({"n": n, "path": c["path"], "kind": c["kind"], "size": c["size"], "mtime": c["mtime"],
                              "note": c["note"], "process": c["process"]})
            out.append(dict({"n": gn}, **dict(g, items=items)))
        windows = []
        for wid, (label, tool) in rules.NOT_OFFERED.items():
            w = self.windows.get(wid)
            if w:
                windows.append({"id": wid, "label": label.format(drive_label(self.root)), "size": w["size"],
                                "tool": tool, "paths": w["paths"]})
        return {"tool": "disk-cleanup", "version": 1,
                "created": datetime.datetime.fromtimestamp(self.now).isoformat(timespec="seconds"),
                "created_ts": self.now, "root": self.root, "profile": self.env.profile, "settings": self.settings,
                "groups": out, "left_out": left_out, "windows": windows,
                "unreadable": {"count": self.unread, "denied": self.denied, "examples": self.examples},
                "stats": {"files": self.files, "folders": self.folders, "seconds": round(seconds, 1)}}
