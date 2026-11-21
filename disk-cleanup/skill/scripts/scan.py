"""The disk-cleanup scan: walk one folder with at most 4 threads, sort what it meets into the
areas in rules.py, measure what the rules offer, compare possible duplicates, and build the
report. It only reads.

Every age rule goes by the newer of a file's modified and created times (a file extracted or
copied today keeps an old modified time); items keep their modified time as `mtime`.
"""
import datetime
import fnmatch
import hashlib
import os
import queue
import stat
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait

import rules
from rules import DAY, MB, PLACEHOLDER, REPARSE, birth, ext, ncase

MAX_WORKERS = 4
PART = 64 * 1024      # the first hash reads this much from each end of a file
BLOCK = 1024 * 1024   # the full hash reads in blocks of this size
NAME, IS_DIR, ATTRS, SIZE, MTIME, BTIME = range(6)  # the fields of a listing() entry


def clamp_workers(n):
    """--workers is clamped to 1..4."""
    return max(1, min(MAX_WORKERS, int(n)))


def drive_label(root):
    drive, rest = os.path.splitdrive(root)
    return drive if drive and rest in ("", "\\") else root


def tidy(v):
    """A threshold as given, without a .0 when it is a whole number."""
    return int(v) if float(v).is_integer() else v


def unnest(cands):
    """Drop repeats and anything inside another candidate; the outer one stays, and on a tie the
    group that comes first in rules.GROUPS."""
    out, kept = [], set()
    for c in sorted(cands, key=lambda c: (len(c["path"]), rules.GROUP_ORDER.index(c["group"]))):
        n = ncase(c["path"])
        up, inside = n, n in kept
        while not inside and os.path.dirname(up) != up:
            up = os.path.dirname(up)
            inside = up in kept
        if not inside:
            kept.add(n)
            out.append(c)
    return out


def file_hash(path, size, partial):
    """SHA-256 of a file, or of its first and last 64 KiB when partial. None when it cannot be
    read (locked, gone, no permission)."""
    h = hashlib.sha256()
    try:
        with open(ext(path), "rb") as f:
            if partial:
                h.update(f.read(PART))
                if size > PART:
                    f.seek(max(PART, size - PART))
                    h.update(f.read(PART))
            else:
                block = f.read(BLOCK)
                while block:
                    h.update(block)
                    block = f.read(BLOCK)
    except OSError:
        return None
    return h.hexdigest()


class Measure:
    """What one subtree holds, read by one worker with its own stack."""
    __slots__ = ("size", "files", "folders", "newest", "latest", "links", "online", "bad", "holds")

    def __init__(self):
        self.size = self.files = self.folders = self.bad = 0
        self.newest = self.latest = 0.0  # newest modified time; newest of modified and created times
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
        self.settings = {"dupe_min_mb": tidy(dupe_min_mb), "large_mb": tidy(large_mb), "large_days": tidy(large_days)}
        self.dupe_min = max(1, int(dupe_min_mb * MB))  # an empty file is never a duplicate
        self.large_min, self.large_age = int(large_mb * MB), large_days * DAY
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
        self.areas = {"programs": [], "synced": []}  # (path, size) found by the walk
        self.recency = {}    # project folder (ncase): newest change the walk saw in it
        self.dupes = []      # (path, size, mtime) of user-area files that may have copies
        self.large = []      # (path, size, mtime, latest) of large files not changed for large_days
        self.zero = {}       # user-area folders with no files and only walked folders: ncase -> (path, mtime, latest, children)
        self.sets = []       # duplicate sets: (size, hash, [(path, mtime), ...])
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

    def tell(self, *what):
        if self.progress:
            self.progress(*what)

    def run(self):
        start = time.time()
        self.put(self.plan)
        threads = [threading.Thread(target=self.work, name="disk-cleanup-%d" % i, daemon=True)
                   for i in range(self.workers)]
        for t in threads:
            t.start()
        self.threads = [t.name for t in threads]
        while not self.idle.wait(self.every):
            self.tell("walk", self.files, self.folders, time.time() - start)
        for _ in threads:
            self.tasks.put(None)
        for t in threads:
            t.join()
        if self.errors:
            raise self.errors[0]
        self.apply_recency()
        self.find_duplicates(start)
        self.find_large()
        self.find_empty()
        return self.report(time.time() - start)

    # ---- reading ----

    def unreadable(self, path, err):
        with self.lock:
            self.unread += 1
            self.denied += isinstance(err, PermissionError)
            if len(self.examples) < 50:
                self.examples.append(path)

    def listing(self, path, count=True):
        """(name, is_dir, attributes, size, mtime, birth time) for everything directly in a folder,
        or None when it cannot be read. Plain tuples, so a folder of millions of entries stays small."""
        try:
            out = []
            with os.scandir(ext(path)) as it:
                for e in it:
                    st = e.stat(follow_symlinks=False)
                    out.append((e.name, e.is_dir(follow_symlinks=False), st.st_file_attributes, st.st_size,
                                st.st_mtime, birth(st)))
            return out
        except OSError as err:
            if count:
                self.unreadable(path, err)
            return None

    def measure(self, path, count=True):
        """Size and number of the files in a subtree (links and online-only files not counted, and
        online-only folders never entered), its newest change, and whether it holds links,
        online-only files, unreadable folders or a folder that is never removed. None when `path`
        itself cannot be read."""
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
            for name, isdir, a, size, mt, bt in entries:
                if a & REPARSE:
                    m.links = True
                elif a & PLACEHOLDER:
                    m.online = True
                else:
                    m.newest, m.latest = max(m.newest, mt), max(m.latest, mt, bt)
                    if isdir:
                        p = os.path.join(d, name)
                        m.holds = m.holds or ncase(p) in self.env.never
                        m.folders += 1
                        stack.append(p)
                    else:
                        files += 1
                        m.size += size
            m.files += files
            with self.lock:  # as it goes, so the progress line moves during a big subtree
                self.files += files
                self.folders += 1
        return m

    def add(self, group, path, kind, size, mtime, note="", process=None, skip=None, projects=(), latest=None):
        """Record a candidate. A name Windows tools may read as another path is listed, never offered."""
        if not skip and rules.odd_name(path):
            skip = rules.ODD
        with self.lock:
            self.cands.append({"group": group, "path": path, "kind": kind, "size": size, "mtime": mtime,
                               "note": note, "process": process, "skip": skip, "projects": projects,
                               "latest": mtime if latest is None else latest})

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
        programs = os.path.join(env.local, "Programs")  # inside AppData, which is not walked
        try:
            if rules.is_under(programs, root) and not rules.link_between(root, programs):
                self.put(self.area, "programs", programs)
        except OSError:
            pass
        if env.is_root(ncase(root)):
            size, _ = self.win.recycle_usage(root)
            with self.lock:
                self.windows["recycle-bin"] = {"size": size, "paths": [root]}
        kind, projects, _ = rules.context(env, root)
        if kind is None:
            try:
                st = os.stat(ext(root))
                mtime, btime = st.st_mtime, birth(st)
            except OSError:
                mtime = btime = self.now
            self.put(self.list_dir, root, projects, mtime, btime, True)
        elif kind in (rules.PROGRAM, rules.SYNCED):
            self.put(self.area, "programs" if kind == rules.PROGRAM else "synced", root)

    def candidate(self, group, path, mtime, btime, note="", process=None, min_age=0.0, projects=()):
        """Measure a folder a rule offers as one item."""
        if ncase(path) in self.env.never:
            return
        m = self.measure(path)
        if m is None:
            return
        newest, latest = max(mtime, m.newest), max(mtime, btime, m.latest)
        if min_age and self.now - latest <= min_age:
            return
        self.add(group, path, "dir", m.size, newest, note, process, m.skip_reason(), projects, latest)

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
        if st.st_file_attributes & PLACEHOLDER:  # online-only: never entered
            self.add(t["group"], t["path"], "dir", 0, st.st_mtime, t["note"], t["process"], rules.ONLINE)
        elif stat.S_ISDIR(st.st_mode):
            self.candidate(t["group"], t["path"], st.st_mtime, birth(st), t["note"], t["process"])

    def children(self, t):
        """A known folder whose direct children are offered one by one (temp files, crash dumps)."""
        try:
            if rules.is_under(t["path"], self.root) and self.linked(t):
                return
            st = os.stat(ext(t["path"]), follow_symlinks=False)
        except OSError:
            return
        if st.st_file_attributes & (REPARSE | PLACEHOLDER) or not stat.S_ISDIR(st.st_mode):
            return
        entries = self.listing(t["path"])
        if entries is None:
            return
        files = 0
        for name, isdir, a, size, mt, bt in entries:
            p = os.path.join(t["path"], name)
            if a & REPARSE or ncase(p) in self.env.never or not rules.is_under(p, self.root):
                continue
            if isdir and a & PLACEHOLDER:
                self.add(t["group"], p, "dir", 0, mt, t["note"], t["process"], rules.ONLINE)
            elif isdir:
                self.put(self.candidate, t["group"], p, mt, bt, t["note"], t["process"], t["min_age"])
            elif not a & PLACEHOLDER:
                files += 1
                if not t["min_age"] or self.now - max(mt, bt) > t["min_age"]:
                    self.add(t["group"], p, "file", size, mt, t["note"], t["process"], latest=max(mt, bt))
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
                hits = [e[SIZE] for e in entries if fnmatch.fnmatch(e[NAME].lower(), name.lower())
                        and not e[IS_DIR] and not e[ATTRS] & (REPARSE | PLACEHOLDER)]
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
            if st.st_file_attributes & (REPARSE | PLACEHOLDER):
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

    def area(self, kind, path):
        """A program or a synced folder: one size for the Not offered list, never walked for
        rules. A synced folder counts its local files only."""
        m = self.measure(path, count=False)
        with self.lock:
            self.areas[kind].append((path, m.size if m else None))

    def list_dir(self, path, projects=(), mtime=0.0, btime=0.0, top=False):
        """One folder of the walk. Its own names first decide what it is (a synced folder, a
        program, a virtual environment, the start of a project); then its files go to the file
        rules, and each folder in it is walked, measured or passed by according to its area."""
        env = self.env
        entries = self.listing(path)
        if entries is None:
            return
        n = ncase(path)
        at_root, at_profile = env.is_root(n), n in env.n_profiles
        files = {e[NAME].lower() for e in entries if not e[IS_DIR]}
        dirs = {e[NAME].lower() for e in entries if e[IS_DIR]}
        if rules.is_synced_root(files, dirs):
            self.area("synced", path)
            return
        own = True  # whether its own files go to the file rules
        if rules.holds_program(files, dirs):
            if not (at_root or at_profile):
                self.area("programs", path)
                return
            own = False  # stray installer files in a drive root or the profile: walk on, offer none of them
        if "pyvenv.cfg" in files:
            if top:  # (a scan of the environment itself cannot see its project's dates)
                return
            if rules.venv_only(files, dirs):
                self.candidate("py-venv", path, mtime, btime, projects=projects)
            else:  # someone's own files live here too: never offered, never walked
                self.add("py-venv", path, "dir", 0, mtime, skip=rules.NOT_ONLY_VENV, latest=max(mtime, btime))
            return
        if rules.is_project(files, dirs) and not (at_root or at_profile):
            projects += (path,)
        user, downloads = not projects, own and n == env.n_downloads
        count, newest, dupes, large = 0, 0.0, [], []
        for name, isdir, a, size, mt, bt in entries:
            if isdir or a & (REPARSE | PLACEHOLDER):
                continue
            count += 1
            latest = max(mt, bt)
            newest = max(newest, latest)
            if not own:
                continue
            p, x = os.path.join(path, name), os.path.splitext(name)[1].lower()
            if downloads and rules.downloads_item(name, latest, self.now):
                self.add("downloads", p, "file", size, mt, latest=latest)
                continue
            if user and x in rules.CONTENT and size >= self.dupe_min:
                dupes.append((p, size, mt))
            if (x in rules.CONTENT or x in rules.DISK_IMAGES) and size >= self.large_min \
                    and self.now - latest > self.large_age:
                large.append((p, size, mt, latest))
        children, clean = [], not files  # files counts links and online-only files too
        for name, isdir, a, size, dm, db in entries:
            if not isdir:
                continue
            p = os.path.join(path, name)
            if a & (REPARSE | PLACEHOLDER):  # a link, or an online-only folder: never entered
                clean = False
                continue
            kind = rules.dir_kind(env, p, name, at_root, at_profile, n in env.n_profiles_dirs)
            rule = rules.build_rule(name, files, dirs) if kind is None else None
            if rule:
                group, note = rule
                self.put(self.candidate, group, p, dm, db, note, None, 0.0, () if group == "py-cache" else projects)
                clean = False
            elif kind is None and name.lower() != "node_modules":  # no package.json beside it: left alone
                self.put(self.list_dir, p, projects, dm, db)
                children.append(ncase(p))
            else:
                if kind in (rules.PROGRAM, rules.SYNCED):
                    self.put(self.area, "programs" if kind == rules.PROGRAM else "synced", p)
                clean = False
        with self.lock:
            self.files += count
            self.folders += 1
            self.dupes += dupes
            self.large += large
            for pr in projects if newest else ():
                k = ncase(pr)
                self.recency[k] = max(self.recency.get(k, 0.0), newest)
            if user and clean:
                self.zero[n] = (path, mtime, max(mtime, btime), children)

    # ---- after the walk ----

    def apply_recency(self):
        """A build folder or virtual environment is listed as skipped when any project it is inside
        (its own, and every one around it, such as the solution or the repo) changed in the last
        14 days, or when one of them starts above the scan root, since the walk did not see all of
        it. With no project dates at all, it goes by its own dates."""
        since = self.now - rules.PROJECT_DAYS * DAY
        for c in self.cands:
            if c["group"] in rules.BUILD_GROUPS and not c["skip"]:
                dates = [self.recency[ncase(p)] for p in c["projects"] if ncase(p) in self.recency]
                if any(not rules.is_under(p, self.root) for p in c["projects"]):
                    c["skip"] = rules.OUTSIDE
                elif dates:
                    if max(dates) > since:
                        c["skip"] = rules.RECENT
                elif c["latest"] > since:
                    c["skip"] = rules.RECENT_OWN

    def find_duplicates(self, start):
        """Sets of identical files among the user-area candidates: the same size (hard links count
        as one file), then the same SHA-256 of both ends, then of the whole file, read by
        --workers threads. A file that cannot be read drops out."""
        by_size = {}
        for p, size, mtime in self.dupes:
            by_size.setdefault(size, []).append((p, mtime))
        sets = []
        for size, files in by_size.items():
            if len(files) < 2:
                continue
            one = {}
            for p, mtime in sorted(files, key=lambda f: ncase(f[0])):
                try:
                    st = os.stat(ext(p), follow_symlinks=False)
                except OSError:
                    continue
                one.setdefault((st.st_dev, st.st_ino), (p, mtime))
            if len(one) > 1:
                sets.append((size, None, list(one.values())))
        if sets:
            with ThreadPoolExecutor(max_workers=self.workers) as pool:
                for partial in (True, False):
                    sets = self.same_hash(pool, sets, partial, start)
        self.sets = sets

    def same_hash(self, pool, sets, partial, start):
        """Split each set of same-size files by their hash; sets of one fall away."""
        jobs = [(size, p, mtime) for size, _, files in sets for p, mtime in files]
        futures = [pool.submit(file_hash, p, size, partial) for size, p, mtime in jobs]
        left = set(futures)
        while left:
            _, left = wait(left, timeout=self.every)
            if left:
                self.tell("hash", len(futures) - len(left), len(futures), time.time() - start)
        by = {}
        for (size, p, mtime), f in zip(jobs, futures):
            h = f.result()
            if h:
                by.setdefault((size, h), []).append((p, mtime))
        return [(size, h, files) for (size, h), files in by.items() if len(files) > 1]

    def find_large(self):
        """Large files not changed for --large-days, each one an item to pick. A file that is in a
        duplicate set is listed there instead, so no file is in two groups."""
        in_sets = {ncase(p) for _, _, files in self.sets for p, _ in files}
        for p, size, mtime, latest in self.large:
            if ncase(p) not in in_sets:
                self.add("large-old", p, "file", size, mtime, latest=latest)

    def find_empty(self):
        """The top-most empty folders of user areas: no files anywhere inside, no links, nothing
        unreadable, every folder in them unchanged for 30 days, and allowed to be offered."""
        ok, since = {}, self.now - rules.EMPTY_DAYS * DAY
        for n in sorted(self.zero, key=lambda k: -k.count(os.sep)):  # the deepest first
            path, mtime, latest, children = self.zero[n]
            ok[n] = (latest < since and rules.may_offer_empty(self.env, path, self.root)
                     and all(ok.get(c, False) for c in children))
        for n, good in ok.items():
            path, mtime, latest, _ = self.zero[n]
            if good and not ok.get(ncase(os.path.dirname(path)), False):
                self.add("empty", path, "dir", 0, mtime, latest=latest)

    # ---- the report ----

    def duplicate_items(self):
        """Every copy of every set as an item, sets with the most space to gain first, the
        suggested keeper first in its set. A copy whose name Windows tools may misread is listed as
        skipped, and a set needs two other copies to be offered. Returns (items, space the extra
        copies take, skipped)."""
        sets, skipped = [], []
        for size, h, files in self.sets:
            plain = [f for f in files if not rules.odd_name(f[0])]
            skipped += [{"path": p, "size": size, "reason": rules.ODD} for p, _ in files if rules.odd_name(p)]
            if len(plain) > 1:
                sets.append((size, h, plain))
        order = sorted(sets, key=lambda s: (-s[0] * (len(s[2]) - 1), -s[0], ncase(min(p for p, _ in s[2]))))
        items = []
        for num, (size, h, files) in enumerate(order, 1):
            keep = min(files, key=lambda f: rules.keep_key(self.env, f[0], f[1]))
            copies = [keep] + sorted((f for f in files if f is not keep), key=lambda f: ncase(f[0]))
            for p, mtime in copies:
                items.append({"path": p, "kind": "file", "size": size, "mtime": mtime, "note": "", "process": None,
                              "set": num, "hash": h, "same_as": [q for q, _ in copies if q != p],
                              "suggest_keep": p == keep[0]})
        return items, sum(size * (len(files) - 1) for size, _, files in order), skipped

    def report(self, seconds):
        by = {}
        for c in unnest(self.cands):
            by.setdefault(c["group"], []).append(c)
        order = lambda c: (-c["size"], ncase(c["path"]))  # noqa: E731
        groups, left_out = [], []
        for gid in rules.GROUP_ORDER:
            label, (_, safety, note) = rules.label(gid, self.settings["large_days"]), rules.GROUPS[gid]
            if gid == "duplicates":
                items, size, skipped = self.duplicate_items()
            else:
                cs = by.get(gid, [])
                items = sorted((c for c in cs if not c["skip"]), key=order)
                size = sum(c["size"] for c in items)
                skipped = [{"path": c["path"], "size": c["size"], "reason": c["skip"]}
                           for c in sorted((c for c in cs if c["skip"]), key=order)]
            if items:
                groups.append({"id": gid, "label": label, "safety": safety, "note": note, "size": size,
                               "count": len(items), "items": items, "skipped": skipped})
            elif skipped:
                left_out.append({"id": gid, "label": label, "skipped": skipped})
        groups.sort(key=lambda g: (rules.SAFETY_ORDER.index(g["safety"]), -g["size"]))
        out, n = [], 0
        for gn, g in enumerate(groups, 1):
            items = []
            for c in g["items"]:
                n += 1
                item = {"n": n, "path": c["path"], "kind": c["kind"], "size": c["size"], "mtime": c["mtime"],
                        "note": c["note"], "process": c["process"]}
                item.update((k, c[k]) for k in ("set", "hash", "same_as", "suggest_keep") if k in c)
                items.append(item)
            out.append(dict({"n": gn}, **dict(g, items=items)))
        for wid, parts in self.areas.items():
            parts = sorted(parts, key=lambda a: (-(a[1] or 0), ncase(a[0])))
            sizes = [s for _, s in parts if s is not None]
            if parts:
                self.windows[wid] = {"size": sum(sizes) if sizes else None, "paths": [p for p, _ in parts],
                                     "parts": [{"path": p, "size": s} for p, s in parts]}
        windows = []
        for wid, (label, tool) in rules.NOT_OFFERED.items():
            w = self.windows.get(wid)
            if w:
                windows.append(dict({"id": wid, "label": label.format(drive_label(self.root)), "size": w["size"],
                                     "tool": tool}, **w))
        return {"tool": "disk-cleanup", "version": 1,
                "created": datetime.datetime.fromtimestamp(self.now).isoformat(timespec="seconds"),
                "created_ts": self.now, "root": self.root, "profile": self.env.profile, "settings": self.settings,
                "groups": out, "left_out": left_out, "windows": windows,
                "unreadable": {"count": self.unread, "denied": self.denied, "examples": self.examples},
                "stats": {"files": self.files, "folders": self.folders, "seconds": round(seconds, 1)}}
