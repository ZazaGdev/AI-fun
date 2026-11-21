"""The disk-cleanup clean step: the safety core. A scan report is only a list of choices. Every
chosen item is checked again against the disk and the current rules (still_matches), then against
what the Recycle Bin can take, and only what passes is moved there, through winsys.recycle, the
one removal call in the tool. Printing and the log are in disk_cleanup.py.
"""
import json
import math
import os
import stat

import rules
import winsys
from rules import DAY, MB, PLACEHOLDER, REPARSE, birth, ext, ncase, under
from scan import file_hash

MAX_AGE = 24 * 3600  # a report older than this is refused
BATCH = 200          # paths per Recycle Bin call
MAX_PATH = 260

# why a chosen item is left out
BROKEN = "its entry in the report is broken"
NOT_USUAL = "its path is not in its usual form"
OUTSIDE_ROOT = "it is not inside the scanned folder"
PROTECTED = "it is in a place this tool never takes anything from"
GONE = "it is not there any more"
IS_LINK = "it is itself a link to another place"
CHANGED = "it changed after the scan"
NO_RULE = "it no longer fits the rule it was offered by"
NOT_EMPTY = "it is not an old empty folder any more"
KEEP_ONE = "keep at least one copy: every copy of this file was selected"
NO_COPY = "no other copy of it is left as it was"
NO_BIN = "Windows can't put this in the Recycle Bin"
IN_USE = "in use or access denied"


class Refused(Exception):
    """The report or the selection cannot be used (exit 2); the message says why."""


def load(path, env, now):
    """The report, after the checks that refuse it as a whole: this tool's version 1, made in the
    last 24 hours, for this user's profile, of a folder that is still there."""
    try:
        with open(path, encoding="utf-8") as f:
            r = json.load(f)
    except (OSError, ValueError) as e:
        raise Refused("Cannot read the report %s: %s" % (path, e))
    if not (isinstance(r, dict) and r.get("tool") == "disk-cleanup" and r.get("version") == 1
            and isinstance(r.get("groups"), list)):
        raise Refused("This is not a disk-cleanup report: " + path)
    ts = r.get("created_ts")
    if not isinstance(ts, (int, float)) or not math.isfinite(ts) or now - ts > MAX_AGE or ts - now > 300:
        raise Refused("This report is more than 24 hours old, so things may have changed. Scan again.")
    profile = r.get("profile")
    if not isinstance(profile, str) or ncase(os.path.abspath(profile)) not in env.n_profiles:
        raise Refused("This report was made for another user. Scan again.")
    root = r.get("root")
    if not isinstance(root, str) or not winsys.canonical(root) or not os.path.isdir(ext(root)):
        raise Refused("The folder this report scanned is not there any more. Scan again.")
    return r


def numbers(text, what):
    """'12, 17' as [12, 17]; Refused for anything that is not a whole number."""
    out = []
    for t in (text or "").split(","):
        t = t.strip()
        if t:
            if not t.isdigit():
                raise Refused("Not %s number: %s" % (what, t))
            out.append(int(t))
    return out


def select(report, groups, items, skip):
    """The chosen items as [(group id, item)], in report order. Refused for an unknown group or
    number, a group this tool does not offer, or a Your call group named as a whole."""
    by_n, by_id, every = {}, {}, {}
    for g in report["groups"]:
        if not (isinstance(g, dict) and isinstance(g.get("n"), int) and isinstance(g.get("id"), str)
                and isinstance(g.get("items"), list)):
            raise Refused("This report is broken: a group has no number, name or items. Scan again.")
        by_n[g["n"]], by_id[g["id"]] = g, g
        for i in g["items"]:
            if isinstance(i, dict) and isinstance(i.get("n"), int):
                every[i["n"]] = (g["id"], i)
    listing = ", ".join("%d %s" % (g["n"], g["id"]) for g in report["groups"]) or "none"
    chosen = {}
    for token in groups:
        if token in rules.NOT_OFFERED:
            raise Refused("%s is not offered: Windows handles it. See the Not offered list." % token)
        g = by_n.get(int(token)) if token.isdigit() else by_id.get(token)
        if g is None:
            raise Refused("Unknown group: %s. The groups in this report are: %s." % (token, listing))
        if g["id"] not in rules.GROUPS:
            raise Refused("%s is not a group this tool offers." % g["id"])
        if rules.GROUPS[g["id"]][1] == "check":
            raise Refused("Pick the items to remove from this group by number, with --items.")
        chosen.update((i["n"], (g["id"], i)) for i in g["items"] if isinstance(i, dict) and isinstance(i.get("n"), int))
    span = "1 to %d" % max(every) if every else "none"
    for n in items + skip:
        if n not in every:
            raise Refused("Unknown item number: %d. The item numbers in this report run %s." % (n, span))
        if every[n][0] not in rules.GROUPS:
            raise Refused("Item %d is in %s, which is not a group this tool offers." % (n, every[n][0]))
    chosen.update((n, every[n]) for n in items)
    for n in skip:
        chosen.pop(n, None)
    return [chosen[n] for n in sorted(chosen)]


def unnest(chosen):
    """Drop repeated paths and any item inside another chosen item, which goes with it."""
    kept, out = set(), []
    for gid, item in sorted(chosen, key=lambda c: len(str(c[1].get("path", "")))):
        p = item.get("path")
        if isinstance(p, str):
            n = up = ncase(p)
            inside = n in kept
            while not inside and os.path.dirname(up) != up:
                up = os.path.dirname(up)
                inside = up in kept
            if inside:
                continue
            kept.add(n)
        out.append((gid, item))
    order = {id(item): k for k, (_, item) in enumerate(chosen)}
    return sorted(out, key=lambda c: order[id(c[1])])


class Tree:
    """What a folder holds now, read again."""
    __slots__ = ("files", "size", "latest", "links", "online", "bad", "holds")

    def __init__(self):
        self.files = self.size = 0
        self.latest = 0.0
        self.links = self.online = self.bad = self.holds = False

    def problem(self):
        return (rules.LINKS if self.links else rules.ONLINE if self.online else rules.PARTLY if self.bad
                else rules.HOLDS if self.holds else None)


def tree(path, never):
    t, stack = Tree(), [path]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(ext(d)) as it:
                entries = [(e.name, e.is_dir(follow_symlinks=False), e.stat(follow_symlinks=False)) for e in it]
        except OSError:
            t.bad = True
            continue
        for name, isdir, st in entries:
            a = st.st_file_attributes
            if a & REPARSE:
                t.links = True
            elif a & PLACEHOLDER:
                t.online = True
            else:
                t.latest = max(t.latest, st.st_mtime, birth(st))
                if isdir:
                    p = os.path.join(d, name)
                    t.holds = t.holds or ncase(p) in never
                    stack.append(p)
                else:
                    t.files += 1
                    t.size += st.st_size
    return t


def newest_change(folder):
    """The newest change (modified or created) among a project's files, as the scan counts them:
    not inside build folders, caches, virtual environments, version-control folders or links.
    None when part of it cannot be read."""
    newest, stack = 0.0, [folder]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(ext(d)) as it:
                entries = [(e.name, e.is_dir(follow_symlinks=False), e.stat(follow_symlinks=False)) for e in it]
        except OSError:
            return None
        files = {n.lower() for n, isdir, _ in entries if not isdir}
        dirs = {n.lower() for n, isdir, _ in entries if isdir}
        if d != folder and "pyvenv.cfg" in files:
            continue  # a virtual environment is judged on its own
        for name, isdir, st in entries:
            if st.st_file_attributes & (REPARSE | PLACEHOLDER):
                continue
            if not isdir:
                newest = max(newest, st.st_mtime, birth(st))
            elif name.lower() not in rules.VCS and name.lower() != "node_modules" and not rules.build_rule(name, files, dirs):
                stack.append(os.path.join(d, name))
    return newest


def folder_area(env, folder):
    """The area of the files directly in `folder` as the walk decides when it lists it: (kind,
    projects), kind None when its files go to the file rules."""
    kind, projects, _ = rules.context(env, folder, strict=True)
    if kind:
        return kind, projects
    got = rules.names(folder)
    if got is None:
        return rules.SKIP, projects
    files, dirs = got
    n = ncase(folder)
    exempt = env.is_root(n) or n in env.n_profiles
    if rules.is_synced_root(files, dirs):
        return rules.SYNCED, projects
    if rules.holds_program(files, dirs):
        return (rules.SKIP if exempt else rules.PROGRAM), projects
    if "pyvenv.cfg" in files:
        return rules.SKIP, projects
    if rules.is_project(files, dirs) and not exempt:
        projects += (folder,)
    return None, projects


def empty_now(env, path, since):
    """True when `path` is still an old empty folder as the scan finds one: nothing but folders
    anywhere inside, each one walked by the scan and unchanged (modified or created) since `since`."""
    stack = [path]
    while stack:
        d = stack.pop()
        try:
            st = os.stat(ext(d), follow_symlinks=False)
            with os.scandir(ext(d)) as it:
                entries = [(e.name, e.is_dir(follow_symlinks=False), e.stat(follow_symlinks=False)) for e in it]
        except OSError:
            return False
        if max(st.st_mtime, birth(st)) >= since:
            return False
        dirs, nd = {n.lower() for n, _, _ in entries}, ncase(d)
        for name, isdir, est in entries:
            sub = os.path.join(d, name)
            if (not isdir or est.st_file_attributes & (REPARSE | PLACEHOLDER) or name.lower() == "node_modules"
                    or rules.dir_kind(env, sub, name, env.is_root(nd), nd in env.n_profiles, nd in env.n_profiles_dirs)
                    or rules.build_rule(name, set(), dirs)):
                return False
            stack.append(sub)
    return True


def setting(report, key, default):
    v = (report.get("settings") if isinstance(report.get("settings"), dict) else {}).get(key, default)
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v >= 0 else default


class Checker:
    """still_matches() for one clean run: the report's root and thresholds, the paths chosen in this
    run, the running processes, and the known locations as the rules give them now."""

    def __init__(self, env, report, now, chosen, processes):
        self.env, self.now, self.root = env, now, report["root"]
        self.n_root = ncase(self.root)
        self.large_min = setting(report, "large_mb", 500) * MB
        self.large_age = setting(report, "large_days", 180) * DAY
        self.selected = {ncase(i["path"]) for _, i in chosen if isinstance(i.get("path"), str)}
        self.processes = {p.lower() for p in processes}
        self.known = {}
        for t in rules.known_targets(env):
            if not rules.protected(env, t["path"]):
                self.known.setdefault(ncase(t["path"]), t)

    def still_matches(self, gid, item):
        """Why `item` of group `gid` may not be removed now, or None, with its size now. All of it
        is worked out again from the disk and the current rules: the report gives only the path,
        and for Your call files the size and time the user saw."""
        p, kind = item.get("path"), item.get("kind")
        if not isinstance(p, str) or kind not in ("file", "dir") or gid not in rules.GROUPS:
            return BROKEN, 0
        if winsys.odd_name(p):
            return NOT_USUAL, 0
        try:
            st = os.stat(ext(p), follow_symlinks=False)
        except OSError:
            return GONE, 0
        if st.st_file_attributes & REPARSE:
            return IS_LINK, 0
        if not winsys.canonical(p):  # an 8.3 short name, or a link on the way
            return NOT_USUAL, 0
        if not under(ncase(p), self.n_root):
            return OUTSIDE_ROOT, 0
        if rules.protected(self.env, p) or ncase(p) in self.env.never:
            return PROTECTED, 0
        try:
            linked = rules.link_between(self.root, p)
        except OSError:
            return GONE, 0
        if st.st_file_attributes & PLACEHOLDER:
            return rules.ONLINE, 0
        if linked:
            return rules.LINKS, 0
        isdir = stat.S_ISDIR(st.st_mode)
        if isdir != (kind == "dir") or not (isdir or stat.S_ISREG(st.st_mode)):
            return CHANGED, 0
        t = tree(p, self.env.never) if isdir else None
        if t and t.problem():
            return t.problem(), 0
        latest = max(st.st_mtime, birth(st), t.latest if t else 0.0)
        why = getattr(self, "rule_" + gid.replace("-", "_"))(gid, p, item, st, latest)
        return (why, 0) if why else (None, t.size if t else st.st_size)

    # ---- one per group: does the path still fit its rule, worked out now ----

    def child_of(self, gid, p, latest):
        c = self.known.get(ncase(os.path.dirname(p)))
        if not c or c["group"] != gid or not c["children"]:
            return NO_RULE
        if c["min_age"] and self.now - latest <= c["min_age"]:
            return NO_RULE
        return None

    def rule_temp(self, gid, p, item, st, latest):
        return self.child_of(gid, p, latest)

    rule_crash_dumps = rule_temp

    def rule_browser_cache(self, gid, p, item, st, latest):
        t = self.known.get(ncase(p))
        if not t or t["group"] != gid or t["children"] or not stat.S_ISDIR(st.st_mode):
            return NO_RULE
        exe = (t["process"] or "").lower()
        if exe and exe in self.processes:
            return "close %s first" % rules.PROCESS_NAMES.get(exe, t["process"])
        return None

    rule_app_cache = rule_gpu_cache = rule_dev_cache = rule_browser_cache

    def rule_downloads(self, gid, p, item, st, latest):
        parent = os.path.dirname(p)
        if (ncase(parent) != self.env.n_downloads or not stat.S_ISREG(st.st_mode)
                or folder_area(self.env, parent)[0] is not None
                or not rules.downloads_item(os.path.basename(p), latest, self.now)):
            return NO_RULE
        return None

    def recent(self, projects, latest):
        """The 14-day rule over every project the item is inside, read again now."""
        if any(not under(ncase(q), self.n_root) for q in projects):
            return rules.OUTSIDE
        newest = newest_change(projects[0]) if projects else 0.0
        if newest is None:
            return rules.PARTLY
        since = self.now - rules.PROJECT_DAYS * DAY
        if newest:
            return rules.RECENT if newest > since else None
        return rules.RECENT_OWN if latest > since else None

    def rule_build_node(self, gid, p, item, st, latest):
        got = rules.names(os.path.dirname(p))
        rule = got and rules.build_rule(os.path.basename(p), got[0], got[1])
        kind, projects, stop = rules.context(self.env, p, strict=True)
        if not rule or rule[0] != gid or kind != rules.INSIDE or ncase(stop or "") != ncase(p):
            return NO_RULE
        return None if gid == "py-cache" else self.recent(projects, latest)

    rule_build_output = rule_py_cache = rule_build_node

    def rule_py_venv(self, gid, p, item, st, latest):
        got = rules.names(p)
        if not got or "pyvenv.cfg" not in got[0] or not rules.venv_only(*got):
            return NO_RULE
        kind, projects, _ = rules.context(self.env, p, strict=True)
        return NO_RULE if kind else self.recent(projects, latest)

    def same_file(self, p, item, st):
        """A Your call file must be the one the user saw: the same size and modified time."""
        return (stat.S_ISREG(st.st_mode) and item.get("size") == st.st_size
                and isinstance(item.get("mtime"), (int, float)) and abs(item["mtime"] - st.st_mtime) < 1e-6)

    def rule_duplicates(self, gid, p, item, st, latest):
        if not self.same_file(p, item, st):
            return CHANGED
        kind, projects = folder_area(self.env, os.path.dirname(p))
        if kind or projects or os.path.splitext(p)[1].lower() not in rules.CONTENT or not st.st_size:
            return NO_RULE
        h = item.get("hash")
        if not isinstance(h, str) or file_hash(p, st.st_size, False) != h:
            return CHANGED
        chosen_copy = False
        for q in item.get("same_as") if isinstance(item.get("same_as"), list) else []:
            if not isinstance(q, str) or not winsys.canonical(q) or not under(ncase(q), self.n_root):
                continue
            try:
                sq = os.stat(ext(q), follow_symlinks=False)
            except OSError:
                continue
            if (sq.st_file_attributes & (REPARSE | PLACEHOLDER) or not stat.S_ISREG(sq.st_mode)
                    or sq.st_size != st.st_size or (sq.st_dev, sq.st_ino) == (st.st_dev, st.st_ino)
                    or file_hash(q, sq.st_size, False) != h):
                continue
            if ncase(q) in self.selected:
                chosen_copy = True
                continue
            return None  # a copy stays
        return KEEP_ONE if chosen_copy else NO_COPY

    def rule_large_old(self, gid, p, item, st, latest):
        if not self.same_file(p, item, st):
            return CHANGED
        x = os.path.splitext(p)[1].lower()
        if (folder_area(self.env, os.path.dirname(p))[0] is not None or not (x in rules.CONTENT or x in rules.DISK_IMAGES)
                or st.st_size < self.large_min or self.now - latest <= self.large_age):
            return NO_RULE
        return None

    def rule_empty(self, gid, p, item, st, latest):
        kind, projects, _ = rules.context(self.env, p, strict=True)
        if kind or projects or not rules.may_offer_empty(self.env, p, self.root):
            return NO_RULE
        return None if empty_now(self.env, p, self.now - rules.EMPTY_DAYS * DAY) else NOT_EMPTY


def bin_check(ok, win):
    """Leave out what Windows can't put in the Recycle Bin: not a fixed drive, the bin switched
    off for the drive or by policy, bigger than the bin, or a path of 260 characters or more.
    Returns (ok, left, warnings), with a WARNING when a drive's bin has no room for the rest."""
    by_drive, left, warnings = {}, [], []
    for e in ok:
        by_drive.setdefault(winsys.drive_of(e[1]["path"]), []).append(e)
    keep = []
    for drive, entries in sorted(by_drive.items()):
        s = win.recycle_settings(drive)
        usable = win.drive_type(drive) == winsys.DRIVE_FIXED and not s["nuke"] and not s["policy"]
        cap = s["max_mb"] * MB if s["max_mb"] else None
        fit = []
        for e in entries:
            if not usable or len(e[1]["path"]) >= MAX_PATH or (cap is not None and e[2] > cap):
                left.append((e[0], e[1], NO_BIN))
            else:
                fit.append(e)
        used = win.recycle_usage(drive)[0]
        total = sum(e[2] for e in fit)
        if fit and cap is not None and used is not None and total > cap - used:
            warnings.append((drive, total, max(0, cap - used)))
        keep += fit
    order = {id(e[1]): k for k, e in enumerate(ok)}
    return sorted(keep, key=lambda e: order[id(e[1])]), left, warnings


def gone(path):
    try:
        os.stat(ext(path), follow_symlinks=False)
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return False


def move(ok, win):
    """Move the checked items to the Recycle Bin, up to 200 paths a call. An item counts as moved
    only when its path is gone; one still there is tried once more on its own. Returns (moved,
    left)."""
    moved, left = [], []
    for start in range(0, len(ok), BATCH):
        batch = ok[start:start + BATCH]
        try:
            win.recycle([e[1]["path"] for e in batch])
        except ValueError:
            pass  # a path the call refuses: each one is tried on its own below
        for e in batch:
            if not gone(e[1]["path"]):
                try:
                    win.recycle([e[1]["path"]])
                except ValueError:
                    pass
            (moved if gone(e[1]["path"]) else left).append(e)
    return moved, [(e[0], e[1], IN_USE) for e in left]
