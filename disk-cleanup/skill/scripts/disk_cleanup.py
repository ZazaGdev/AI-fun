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
import os
import re
import sys
import time

import rules
import scan
import winsys

SHORT = {"downloads": "Old installers and unfinished downloads"}  # labels too long for the summary


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


def plural(n, word):
    return "%s %s%s" % (num(n), word, "" if n == 1 else "s")


def duration(s):
    s = int(round(s))
    if s < 60:
        return "%d s" % s
    if s < 3600:
        return "%d min %d s" % (s // 60, s % 60)
    return "%d h %d min" % (s // 3600, s % 3600 // 60)


def day(ts):
    return datetime.date.fromtimestamp(ts).isoformat()


def and_list(words):
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]


def close_note(g, running):
    """' (close Chrome first)' when an item's process is running."""
    apps = sorted({rules.PROCESS_NAMES.get(i["process"].lower(), i["process"]) for i in g["items"]
                   if i.get("process") and i["process"].lower() in running})
    return " (close %s first)" % and_list(apps) if apps else ""


def count_text(g):
    return plural(g["count"], "item")


def group_line(g, running):
    label = SHORT.get(g["id"], g["label"])
    return "%4d. %-41s%8s   %11s   %s%s" % (g["n"], label, size_text(g["size"]), count_text(g),
                                           rules.SAFETY[g["safety"]], close_note(g, running))


def summary(report, running, txt_path, json_path):
    st, groups = report["stats"], report["groups"]
    out = ["Scan of %s finished in %s: %s in %s." % (report["root"], duration(st["seconds"]),
                                                     plural(st["files"], "file"), plural(st["folders"], "folder")), ""]
    if groups:
        out += ["Can be removed: about %s in %s." % (size_text(sum(g["size"] for g in groups)),
                                                    plural(len(groups), "group")), ""]
        out += [group_line(g, running) for g in groups]
        out += ["", "Safe: comes back by itself. Easy to get back: reinstall, rebuild or download again.",
                "Your call: your own files; pick them one by one by number."]
    else:
        out.append("Nothing was found that can be removed.")
    if report["windows"]:
        out += ["", "Not offered, Windows handles these:"]
        out += ["   %-44s%8s   %s" % (w["label"], size_text(w["size"]), w["tool"]) for w in report["windows"]]
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
                          "folders that hold a folder this tool never removes")}


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
            out += ["      " + p for p in w["paths"]]
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


def progress(files, folders, seconds):
    print("Still scanning: %s in %s so far (%s)." % (plural(files, "file"), plural(folders, "folder"),
                                                    duration(seconds)), file=sys.stderr, flush=True)


def scan_root(path):
    """The folder to scan as a full path; C: means C:\\. A quoted C:\\ often arrives as C:" ."""
    path = path.strip().strip('"').strip()
    if re.match(r"^[A-Za-z]:$", path):
        path += "\\"
    return os.path.abspath(path)


def cmd_scan(a, env=None, win=None):
    path = scan_root(a.path)
    if not os.path.isdir(path):
        print("Not a folder: " + path, file=sys.stderr)
        return 2
    if env is None:
        winsys.set_low_priority()
        path = os.path.abspath(winsys.long_path(path))
        env = rules.Env.from_system(os.path.abspath(a.out) if a.out else None)
    win = win or winsys.WinSys()
    print("Scanning %s. This only reads; on a whole drive it can take several minutes." % path, flush=True)
    sc = scan.Scanner(env, win, path, workers=a.workers, dupe_min_mb=a.dupe_min_mb, large_mb=a.large_mb,
                      large_days=a.large_days, progress=progress)
    report = sc.run()
    os.makedirs(env.out_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(report["created_ts"]))
    js, txt = (os.path.join(env.out_dir, "scan-%s.%s" % (stamp, x)) for x in ("json", "txt"))
    running = win.processes()
    with open(js, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    with open(txt, "w", encoding="utf-8", errors="replace") as f:
        f.write(text_report(report, running) + "\n")
    print(summary(report, running, txt, js))
    return 0


def not_negative(text):
    v = float(text)
    if v < 0:
        raise argparse.ArgumentTypeError("must be 0 or more")
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
