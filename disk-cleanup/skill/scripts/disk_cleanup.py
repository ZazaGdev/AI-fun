"""disk-cleanup: scan a Windows drive or folder and list what can be removed, grouped by kind,
with sizes and how safe each group is.

Usage:
  python disk_cleanup.py scan <path> [--out DIR] [--workers N] [--dupe-min-mb 1] [--large-mb 500] [--large-days 180]

scan only reads. It writes scan-YYYYMMDD-HHMMSS.json and scan-YYYYMMDD-HHMMSS.txt into --out
(default %USERPROFILE%\\disk-cleanup) and prints a summary. Windows only, Python 3.8 or newer.
Exit codes: 0 done, 2 bad arguments, 3 not Windows.
"""
import argparse
import datetime
import json
import math
import os
import re
import sys
import time

import rules
import scan
import winsys

# labels too long for the summary's column, as in the plan's sample
SHORT = {"downloads": "Old installers and unfinished downloads", "duplicates": "Duplicate files (pick which copies)"}
PICK_SHOWN, SETS_SHOWN, PARTS_SHOWN = 10, 3, 20


def size_text(n):
    """1024-based like File Explorer: 512 KB, 14.2 MB, 3.1 GB."""
    if n is None:
        return "size unknown (needs admin)"
    if n < 1024:
        return "1 byte" if n == 1 else "%d bytes" % n
    for unit in ("KB", "MB", "GB", "TB"):
        n /= 1024.0
        if n < 1024 or unit == "TB":
            return "%d %s" % (round(n), unit) if unit == "KB" else "%.1f %s" % (n, unit)


def num(n):
    return "{:,}".format(n)


def plural(n, word, many=None):
    return "%s %s" % (num(n), word if n == 1 else many or word + "s")


def duration(s):
    s = int(round(s))
    if s < 60:
        return "%d s" % s
    if s < 3600:
        return "%d min %d s" % (s // 60, s % 60)
    return "%d h %d min" % (s // 3600, s % 3600 // 60)


def day(ts):
    """The date of a file time. Windows cannot convert times before 1970 or after 3000 the usual way."""
    try:
        return datetime.date.fromtimestamp(ts).isoformat()
    except (OSError, OverflowError, ValueError):
        try:
            return (datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=ts)).date().isoformat()
        except (OverflowError, ValueError):
            return "unknown date"


def and_list(words):
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]


def close_note(g, running):
    """' (close Chrome first)' when an item's process is running."""
    apps = sorted({rules.PROCESS_NAMES.get(i["process"].lower(), i["process"]) for i in g["items"]
                   if i.get("process") and i["process"].lower() in running})
    return " (close %s first)" % and_list(apps) if apps else ""


def sets_of(g):
    """A duplicates group's items as [(set number, [items])], in their order."""
    out = []
    for i in g["items"]:
        if not out or out[-1][0] != i["set"]:
            out.append((i["set"], []))
        out[-1][1].append(i)
    return out


def count_text(g):
    if g["id"] == "duplicates":
        return "%s, %s" % (plural(len(sets_of(g)), "set"), plural(g["count"], "copy", "copies"))
    return plural(g["count"], "item")


def pad(label, width):
    """A label padded to its column, with at least two spaces before what follows."""
    return label + " " * max(2, width - len(label))


def group_line(g, running):
    label = SHORT.get(g["id"], g["label"].replace(" (pick the ones to remove)", ""))
    return "%4d. %s%8s   %11s   %s%s" % (g["n"], pad(label, 41), size_text(g["size"]), count_text(g),
                                         rules.SAFETY[g["safety"]], close_note(g, running))


def pick_lines(g):
    """The first items of a Your call group (of duplicates, the first sets) with their numbers,
    so they can be picked in the chat."""
    out = []
    if g["id"] == "duplicates":
        sets = sets_of(g)
        for sn, items in sets[:SETS_SHOWN]:
            head = "set %d: " % sn
            for k, i in enumerate(items):
                out.append("        %s#%d  %s  %s%s" % (head if k == 0 else " " * len(head), i["n"], size_text(i["size"]),
                                                         i["path"], "  (suggested keep)" if i.get("suggest_keep") else ""))
        if len(sets) > SETS_SHOWN:
            out.append("        and %s more sets in the full list" % num(len(sets) - SETS_SHOWN))
        return out
    out += ["        #%d  %s  %s  %s" % (i["n"], size_text(i["size"]), day(i["mtime"]), i["path"])
            for i in g["items"][:PICK_SHOWN]]
    if len(g["items"]) > PICK_SHOWN:
        out.append("        and %s more in the full list" % num(len(g["items"]) - PICK_SHOWN))
    return out


def part_lines(w, shown=None):
    """The programs or synced folders found, largest first."""
    parts = w.get("parts") or []
    out = ["        %8s  %s" % (size_text(p["size"]), p["path"]) for p in parts[:shown]]
    if shown and len(parts) > shown:
        out.append("        and %s more in the full list" % num(len(parts) - shown))
    return out


def summary(report, running, txt_path, json_path):
    st, groups = report["stats"], report["groups"]
    out = ["Scan of %s finished in %s: %s in %s." % (report["root"], duration(st["seconds"]),
                                                     plural(st["files"], "file"), plural(st["folders"], "folder")), ""]
    if groups:
        out += ["Can be removed: about %s in %s." % (size_text(sum(g["size"] for g in groups)),
                                                    plural(len(groups), "group")), ""]
        for g in groups:
            out.append(group_line(g, running))
            if g["safety"] == "check":
                out += pick_lines(g)
        out += ["", "Safe: comes back by itself. Easy to get back: reinstall, rebuild or download again."]
        if any(g["safety"] == "check" for g in groups):
            out.append("Your call: your own files; pick them one by one by number.")
    else:
        out.append("Nothing was found that can be removed.")
    if report["windows"]:
        out += ["", "Not offered, Windows handles these:"]
        for w in report["windows"]:
            out.append("   %s%8s   %s" % (pad(w["label"], 44), size_text(w["size"]), w["tool"]))
            out += part_lines(w, PARTS_SHOWN)
    left = left_out_lines(report)
    un = report["unreadable"]
    if left or un["count"]:
        out.append("")
        out += left
        if un["count"]:
            why = " (no permission)" if un["denied"] == un["count"] else ""
            out.append("Could not read %s%s. They were skipped." % (plural(un["count"], "folder"), why))
    out += ["", "Full list: " + txt_path, "For the clean step: " + json_path]
    return "\n".join(out)


LEFT_OUT = {rules.LINKS: ("folder that contains links to other folders", "folders that contain links to other folders"),
            rules.ONLINE: ("folder that holds online-only files", "folders that hold online-only files"),
            rules.PARTLY: ("folder that could not be read in full", "folders that could not be read in full"),
            rules.HOLDS: ("folder that holds a folder this tool never removes",
                          "folders that hold a folder this tool never removes"),
            rules.RECENT: ("build folder of a project changed in the last 14 days",
                           "build folders of projects changed in the last 14 days"),
            rules.RECENT_OWN: ("build folder changed in the last 14 days", "build folders changed in the last 14 days"),
            rules.OUTSIDE: ("build folder of a project partly outside the scanned folder",
                            "build folders of projects partly outside the scanned folder"),
            rules.NOT_ONLY_VENV: ("folder with a pyvenv.cfg that also holds other files",
                                  "folders with a pyvenv.cfg that also hold other files"),
            rules.ODD: ("item whose name Windows tools cannot handle safely",
                        "items whose names Windows tools cannot handle safely")}


def left_out_lines(report):
    """'Left out: 4 build folders of projects changed in the last 14 days (2.0 GB).', one per reason."""
    by = {}
    for g in report["groups"] + report["left_out"]:
        for s in g["skipped"]:
            n, size = by.get(s["reason"], (0, 0))
            by[s["reason"]] = (n + 1, size + s["size"])
    out = []
    for r, (n, size) in sorted(by.items(), key=lambda kv: (-kv[1][1], kv[0])):
        one, many = LEFT_OUT.get(r, ("item: " + r, "items: " + r))
        out.append("Left out: %s %s (%s)." % (num(n), one if n == 1 else many, size_text(size)))
    return out


def item_line(i, indent="   "):
    return "%s#%d  %s  %s  %s%s" % (indent, i["n"], size_text(i["size"]), day(i["mtime"]), i["path"],
                                    "  " + i["note"] if i.get("note") else "")


def text_report(report, running):
    st = report["stats"]
    out = ["disk-cleanup scan of " + report["root"],
           "Made %s. The scan only read the disk; nothing was changed." % report["created"].replace("T", " "),
           "%s in %s, %s." % (plural(st["files"], "file"), plural(st["folders"], "folder"), duration(st["seconds"])),
           ""]
    for g in report["groups"]:
        out.append("%d. %s: %s, %s, %s%s" % (g["n"], g["label"], size_text(g["size"]), count_text(g),
                                              rules.SAFETY[g["safety"]], close_note(g, running)))
        if g["note"]:
            out.append("   " + g["note"])
        if g["id"] == "duplicates":
            for sn, items in sets_of(g):
                out.append("   set %d, %s each:" % (sn, size_text(items[0]["size"])))
                out += [item_line(i, "      ") + ("  suggested keep" if i.get("suggest_keep") else "") for i in items]
        else:
            out += [item_line(i) for i in g["items"]]
        out += skipped_lines(g)
        out.append("")
    if not report["groups"]:
        out += ["Nothing was found that can be removed.", ""]
    for g in report["left_out"]:
        out.append("%s: nothing offered." % g["label"])
        out += skipped_lines(g)
        out.append("")
    if report["windows"]:
        out.append("Not offered, Windows handles these:")
        for w in report["windows"]:
            out += ["   %s: %s" % (w["label"], size_text(w["size"])), "      " + w["tool"]]
            out += part_lines(w) if w.get("parts") else ["      " + p for p in w["paths"]]
        out.append("")
    un = report["unreadable"]
    if un["count"]:
        out.append("Could not read %s. They were skipped.%s" % (
            plural(un["count"], "folder"), " The first 50:" if un["count"] > 50 else ""))
        out += ["   " + p for p in un["examples"]]
        out.append("")
    return "\n".join(out)


def skipped_lines(g):
    if not g["skipped"]:
        return []
    return ["   Left out:"] + ["      %s  %s  (%s)" % (size_text(s["size"]), s["path"], s["reason"])
                               for s in g["skipped"]]


def progress(kind, done, of, seconds):
    """The line on stderr every 15 seconds: files and folders seen, or duplicates compared."""
    if kind == "hash":
        text = "Comparing possible duplicates: %s of %s files (%s)." % (num(done), num(of), duration(seconds))
    else:
        text = "Still scanning: %s in %s so far (%s)." % (plural(done, "file"), plural(of, "folder"), duration(seconds))
    print(text, file=sys.stderr, flush=True)


def plain(path):
    """`path` without a \\\\?\\ prefix (\\\\?\\UNC\\ becomes \\\\), or None for a device path such as
    \\\\.\\C: or \\\\?\\Volume{...}, which has no plain form."""
    low = path.lower()
    if low.startswith("\\\\?\\unc\\"):
        return "\\\\" + path[8:]
    if low.startswith("\\\\?\\"):
        path, low = path[4:], low[4:]
        return path if re.match(r"^[a-z]:(\\|$)", low) else None
    return None if low.startswith("\\\\.\\") else path


def scan_root(path):
    """The folder to scan as a full plain path; C: means C:\\. A quoted C:\\ often arrives as C:" .
    None when it is a device path."""
    path = plain(path.strip().strip('"').strip())
    if path is None:
        return None
    if re.match(r"^[A-Za-z]:$", path):
        path += "\\"
    return plain(os.path.abspath(path))  # (again: abspath turns //?/C:/x into \\?\C:\x)


def cmd_scan(a, env=None, win=None):
    given = scan_root(a.path)
    if given is None:
        print("Not a folder that can be scanned: " + a.path, file=sys.stderr)
        return 2
    path = plain(os.path.realpath(given))  # the real folder, so every area compares as it should
    if path is None or not os.path.isdir(path):
        print("Not a folder: " + given, file=sys.stderr)
        return 2
    if env is None:
        winsys.set_low_priority()
        env = rules.Env.from_system(os.path.abspath(a.out) if a.out else None)
    win = win or winsys.WinSys()
    try:  # before the scan, so a bad --out does not cost a whole scan
        os.makedirs(env.out_dir, exist_ok=True)
    except OSError as e:
        return cannot_write(env.out_dir, e)
    print("Scanning %s. This only reads; on a whole drive it can take several minutes." % path, flush=True)
    if os.path.normcase(path) != os.path.normcase(given):
        print("(%s leads there: it is a link or a short name.)" % given, flush=True)
    sc = scan.Scanner(env, win, path, workers=a.workers, dupe_min_mb=a.dupe_min_mb, large_mb=a.large_mb,
                      large_days=a.large_days, progress=progress)
    report = sc.run()
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(report["created_ts"]))
    js, txt = (os.path.join(env.out_dir, "scan-%s.%s" % (stamp, x)) for x in ("json", "txt"))
    running = win.processes()
    try:
        with open(js, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=1)
        with open(txt, "w", encoding="utf-8", errors="replace") as f:
            f.write(text_report(report, running) + "\n")
    except OSError as e:
        return cannot_write(env.out_dir, e)
    print(summary(report, running, txt, js))
    return 0


def cannot_write(folder, err):
    print("Cannot write the reports to %s: %s" % (folder, err.strerror or err), file=sys.stderr)
    return 2


def not_negative(text):
    v = float(text)
    if not math.isfinite(v) or v < 0:
        raise argparse.ArgumentTypeError("must be a number, 0 or more")
    return v


def parser():
    ap = argparse.ArgumentParser(prog="disk_cleanup.py", description="List what can be removed from a Windows "
                                 "drive or folder, grouped by kind, with sizes and how safe each group is.")
    sub = ap.add_subparsers(dest="cmd")
    sub.required = True
    sc = sub.add_parser("scan", help="read a drive or folder and write the cleanup list; changes nothing")
    sc.add_argument("path", help="the drive or folder to scan, such as C:\\ or D:\\Projects")
    sc.add_argument("--out", help="folder for the reports (default %%USERPROFILE%%\\disk-cleanup)")
    sc.add_argument("--workers", type=int, default=scan.MAX_WORKERS, help="threads that read the disk, 1 to 4")
    sc.add_argument("--dupe-min-mb", type=not_negative, default=1.0, help="smallest file to compare for duplicates")
    sc.add_argument("--large-mb", type=not_negative, default=500.0, help="smallest file to list as large")
    sc.add_argument("--large-days", type=not_negative, default=180.0, help="days unchanged for a large file")
    return ap


def main(argv=None, env=None, win=None):
    if os.name != "nt":
        print("disk-cleanup runs on Windows only.")
        return 3
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")
    a = parser().parse_args(argv)
    if a.cmd == "scan":
        return cmd_scan(a, env, win)
    return 2


if __name__ == "__main__":
    sys.exit(main())
