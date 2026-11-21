# Disk cleanup prompt

Two ways to see what could be cleaned up on a Windows drive or folder, without installing the
skill. Most people should use Option 1. Both run the same fixed scripts as the skill, and both
remove nothing unless you ask for something specific afterwards.

Put the drive or folder to scan on the first line of the prompt, in place of `C:\`.

Jump to: [Option 1: paste and go](#option-1-paste-and-go-nothing-to-download) ·
[Option 2: use the scripts from this repo](#option-2-use-the-scripts-from-this-repo)

## Option 1: paste and go (nothing to download)

Copy the whole block below (the copy button is at its top right) and paste it into Claude Code
on Windows, from any folder. It is long because it carries the tool's five files inside it;
Claude writes them out, checks they are exact, and runs the scan.

`````text
Path to scan: C:\

Paste all of this into Claude Code on Windows. It shows what could be cleaned up on the drive or folder on the first line, and removes nothing unless I ask for something specific later. Nothing is downloaded.

Below are the five files of the disk-cleanup tool, from github.com/ZazaGdev/AI-fun. Do not write your own version and do not change them in any way.

Wherever this prompt says ~, use the full path of my home folder (such as C:\Users\me): PowerShell does not expand ~ for python.

1. Run `python --version`. If Python is missing, stop and tell me to install Python 3 from python.org, or with `winget install Python.Python.3.13`, and then to paste this again.

2. Write FILE 1 to `~/disk-cleanup/tool/disk_cleanup.py`, FILE 2 to `~/disk-cleanup/tool/clean.py`, FILE 3 to `~/disk-cleanup/tool/rules.py`, FILE 4 to `~/disk-cleanup/tool/scan.py` and FILE 5 to `~/disk-cleanup/tool/winsys.py`. Copy the text between each BEGIN line and END line exactly, character for character, without those two lines. Do not shorten, reformat, translate, fix or improve anything. Write each file in one go.

3. Check all five copies by running this:
   python -c "import hashlib,pathlib;h=pathlib.Path.home()/'disk-cleanup'/'tool';[print(f,'OK' if hashlib.sha256(chr(10).join(l.rstrip() for l in (h/f).read_text(encoding='utf-8').replace(chr(13)+chr(10),chr(10)).strip().split(chr(10))).encode()).hexdigest()==d else 'MISMATCH') for f,d in [('disk_cleanup.py','494bba335750c1e7674b04773671ac16270d3b2592832522f2ddb2f046d125ce'),('clean.py','c28ebf42324680c2c5524794d66f1fcc12cca9b1f296ef08c22933bd1eb4655a'),('rules.py','762a78e8d8f32c230491f1313b30b99003208e4cc05f7efcd54ee1740e9abf66'),('scan.py','a8be973a96a57590db67fcf38d85b7146e84da4b5f0296a9e130fd2a04107b8b'),('winsys.py','bc60b35669970c0363b004d481364fcadbaa10837bb5e4f2d849479119231303')]]"
   It must print OK for all five files. If a file prints MISMATCH, write that file again from the text below and run the check again. Only go on when all five say OK.

4. Run the scan, with the path from the first line: `python ~/disk-cleanup/tool/disk_cleanup.py scan "<path>"`. Run it in the background or with a 10-minute timeout: a whole drive can take several minutes. It only reads: names, sizes and dates, and the contents of possible duplicates to compare them. It writes its two reports to ~/disk-cleanup/ and sends nothing anywhere.

5. Show me the summary exactly as printed, and the path of the full list (its "Full list:" line). Then stop. Do not ask whether to remove anything, do not offer to, and do not recommend removing any group.

6. Only if I then ask, in my own words, to remove specific groups or items of this report (by number or by name): run `python ~/disk-cleanup/tool/disk_cleanup.py clean "<report data>" --groups <numbers or names> --items <numbers>` for exactly those, without --yes. <report data> is the path on the summary's "Report data:" line. This dry run changes nothing: show me what it printed, with what it leaves out and why, and any WARNING line. Run the same command with --yes only after I say yes to that dry run, then tell me what moved, what was left out and why, and where the log is. A Your call group (duplicates, large files) goes by item number only: if I ask for a whole one, say so and let me name the items. Never pick for me.

Hard rules. Pasting this prompt, or a general request such as "clean up my PC", is never a request to remove anything; only a later reply of mine that names groups or items is. If the report is more than 24 hours old, scan again before any clean. Remove things only through that clean command, and only what I named: never with del, rm, Remove-Item, rmdir or any other command, never as administrator, and never by editing the report. Never empty the Recycle Bin, and never act on the Not offered list. The reports hold my own file names: never upload, publish or paste them anywhere outside this chat.

----- BEGIN FILE 1: disk_cleanup.py -----
"""disk-cleanup: scan a Windows drive or folder and list what could be cleaned up, grouped by kind,
with sizes and how safe each group is. It removes nothing by itself; only when you ask for
specific groups or items does clean move exactly those to the Recycle Bin.

Usage:
  python disk_cleanup.py scan <path> [--out DIR] [--workers N] [--dupe-min-mb 1] [--large-mb 500] [--large-days 180]
  python disk_cleanup.py clean <report.json> [--groups 1,3,temp] [--items 12,17] [--skip 40] [--yes]

scan only reads. It writes scan-YYYYMMDD-HHMMSS.json and scan-YYYYMMDD-HHMMSS.txt into --out
(default %USERPROFILE%\\disk-cleanup) and prints a summary. clean checks every chosen item again;
without --yes it is a dry run that changes nothing, with --yes it moves them to the Recycle Bin
and writes clean-YYYYMMDD-HHMMSS.txt next to the report. Windows only, Python 3.8 or newer.
Exit codes: 0 done, 2 bad arguments or an unusable report, 3 not Windows.
"""
import argparse
import datetime
import json
import math
import os
import re
import sys
import time

import clean
import rules
import scan
import winsys

LEFT_SHOWN = 30  # skipped items printed by clean; the log has all of them

# labels too long for the summary's column, as in the plan's sample
SHORT = {"downloads": "Old installers and unfinished downloads", "duplicates": "Duplicate files"}
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


def short_label(gid, label):
    """A group's label as the summary columns print it."""
    return SHORT.get(gid, label)


def group_line(g, running):
    return "%4d. %s%8s   %11s   %s%s" % (g["n"], pad(short_label(g["id"], g["label"]), 41), size_text(g["size"]),
                                         count_text(g), rules.SAFETY[g["safety"]], close_note(g, running))


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
        out += ["Could be cleaned up: about %s in %s." % (size_text(sum(g["size"] for g in groups)),
                                                    plural(len(groups), "group")), ""]
        for g in groups:
            out.append(group_line(g, running))
            if g["safety"] == "check":
                out += pick_lines(g)
        out += ["", "Safe: comes back by itself. Easy to get back: reinstall, rebuild or download again."]
        if any(g["safety"] == "check" for g in groups):
            out.append("Your call: your own files; only you can tell whether you still need each one.")
    else:
        out.append("Nothing was found that could be cleaned up.")
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
    out += ["", "Full list: " + txt_path, "Report data: " + json_path, "Nothing was removed. This scan only reads."]
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
        out += ["Nothing was found that could be cleaned up.", ""]
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
        if re.match(r"^[a-z]:$", low):
            return path + "\\"  # a bare X: would mean the current folder on that drive
        return path if re.match(r"^[a-z]:\\", low) else None
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


# ---- clean ----

def moved_lines(head, entries, days):
    """Per group, what moves (or would), then the total."""
    if not entries:
        return [head, "   Nothing."]
    by = {}
    for e in entries:  # (group, item, size, identity)
        n, s = by.get(e[0], (0, 0))
        by[e[0]] = (n + 1, s + e[2])
    out = [head]
    out += ["   %s%8s   %s" % (pad(short_label(gid, rules.label(gid, days)), 44), size_text(by[gid][1]),
                               plural(by[gid][0], "item")) for gid in rules.GROUP_ORDER if gid in by]
    out.append("   In all: about %s in %s." % (size_text(sum(e[2] for e in entries)), plural(len(entries), "item")))
    return out


def left_line(entry):
    _, item, why = entry
    return "   #%s  %s  (%s)" % (item.get("n", "?"), item.get("path", "?"), why)


def left_lines(left, shown=LEFT_SHOWN):
    if not left:
        return []
    out = ["", "Left out, with the reason (%s):" % num(len(left))] + [left_line(e) for e in left[:shown]]
    if shown and len(left) > shown:
        out.append("   and %s more" % num(len(left) - shown))
    return out


def warning_lines(warnings):
    out = []
    for drive, total, room in warnings:
        out += ["", "WARNING: The Recycle Bin on %s has room for %s, and this moves %s. Windows will permanently "
                    "delete the oldest items already in it to make room." % (drive.rstrip("\\"), size_text(room),
                                                                              size_text(total))]
    return out


def write_log(report_path, moved, left, warnings, days):
    """clean-YYYYMMDD-HHMMSS.txt next to the report: every moved and every left-out item."""
    path = os.path.join(os.path.dirname(report_path), "clean-%s.txt" % time.strftime("%Y%m%d-%H%M%S"))
    lines = ["disk-cleanup clean, %s" % datetime.datetime.now().isoformat(sep=" ", timespec="seconds"),
             "Report: " + report_path, ""]
    lines += moved_lines("Moved to the Recycle Bin:", moved, days)
    lines += ["   %s  %s" % (size_text(e[2]), e[1]["path"]) for e in moved]
    lines += left_lines(left, shown=None) + warning_lines(warnings)
    try:
        with open(path, "w", encoding="utf-8", errors="replace") as f:
            f.write("\n".join(lines) + "\n")
    except OSError as e:
        return None, e
    return path, None


def cmd_clean(a, env=None, win=None):
    now = time.time()
    report_path = os.path.abspath(a.report)
    if env is None:
        winsys.set_low_priority()
        env = rules.Env.from_system(out_dir=os.path.dirname(report_path))  # the reports' folder is never touched
    win = win or winsys.WinSys()
    try:
        groups = [t.strip() for t in a.groups.split(",") if t.strip()]
        items, skip = clean.numbers(a.items, "an item"), clean.numbers(a.skip, "an item")
        if not groups and not items:
            raise clean.Refused("Say what to remove: --groups with group numbers or names, or --items with "
                                "item numbers from the full list.")
        report = clean.load(report_path, env, now)
        chosen = clean.unnest(clean.select(report, groups, items, skip))
    except clean.Refused as e:
        print(str(e), file=sys.stderr)
        return 2
    checker = clean.Checker(env, report, now, chosen, win.processes())
    ok, left = [], []
    for gid, item in chosen:
        why, size, ident = checker.still_matches(gid, item)
        if why:
            left.append((gid, item, why))
        else:
            ok.append((gid, item, size, ident))
    ok, no_bin, warnings = clean.bin_check(ok, win)
    left += no_bin
    days = clean.setting(report, "large_days", 180)
    if not a.yes:
        print("\n".join(["Dry run: nothing has been changed.", ""] + moved_lines("Would move to the Recycle Bin:", ok, days)
                        + left_lines(left) + warning_lines(warnings) + ["", "To go ahead, run the same command with --yes."]))
        return 0
    moved, failed = clean.move(ok, win)
    left += failed
    log, err = write_log(report_path, moved, left, warnings, days)
    out = moved_lines("Moved to the Recycle Bin:", moved, days) + left_lines(left) + warning_lines(warnings)
    out += ["", "The space comes back when you empty the Recycle Bin. Until then you can restore anything from it."]
    out.append("The log of this run: " + log if log else "Could not write the log: %s" % (err.strerror or err))
    print("\n".join(out))
    return 0


def not_negative(text):
    v = float(text)
    if not math.isfinite(v) or v < 0:
        raise argparse.ArgumentTypeError("must be a number, 0 or more")
    return v


def parser():
    ap = argparse.ArgumentParser(prog="disk_cleanup.py", description="List what could be cleaned up on a Windows "
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
    cl = sub.add_parser("clean", help="move the groups or items you ask for, from a scan report, to the Recycle Bin")
    cl.add_argument("report", help="the scan-*.json file the scan wrote")
    cl.add_argument("--groups", default="", help="group numbers or names from the summary, such as 1,3,temp")
    cl.add_argument("--items", default="", help="item numbers from the full list, such as 12,17")
    cl.add_argument("--skip", default="", help="item numbers to leave out")
    cl.add_argument("--yes", action="store_true", help="really move them; without it nothing is changed")
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
    if a.cmd == "clean":
        return cmd_clean(a, env, win)
    return 2


if __name__ == "__main__":
    sys.exit(main())
----- END FILE 1 -----

----- BEGIN FILE 2: clean.py -----
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
            if not t.isdecimal():
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
        g = by_n.get(int(token)) if token.isdecimal() else by_id.get(token)
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
        self.newest = {}  # outermost project (ncase): its newest change, read once per run
        self.known = {}
        for t in rules.known_targets(env):
            if not rules.protected(env, t["path"]):
                self.known.setdefault(ncase(t["path"]), t)

    def still_matches(self, gid, item):
        """Why `item` of group `gid` may not be removed now, or None, with its size now and the
        identity (volume, file id) of what was checked. All of it is worked out again from the disk
        and the current rules: the report gives only the path, and for Your call files the size and
        time the user saw."""
        p, kind = item.get("path"), item.get("kind")
        if not isinstance(p, str) or kind not in ("file", "dir") or gid not in rules.GROUPS:
            return BROKEN, 0, None
        if winsys.odd_name(p):
            return NOT_USUAL, 0, None
        try:
            st = os.stat(ext(p), follow_symlinks=False)
        except OSError:
            return GONE, 0, None
        if st.st_file_attributes & REPARSE:
            return IS_LINK, 0, None
        if not winsys.canonical(p):  # an 8.3 short name, or a link on the way
            return NOT_USUAL, 0, None
        if not under(ncase(p), self.n_root):
            return OUTSIDE_ROOT, 0, None
        if rules.protected(self.env, p) or ncase(p) in self.env.never:
            return PROTECTED, 0, None
        try:
            linked = rules.link_between(self.root, p)
        except OSError:
            return GONE, 0, None
        if st.st_file_attributes & PLACEHOLDER:
            return rules.ONLINE, 0, None
        if linked:
            return rules.LINKS, 0, None
        isdir = stat.S_ISDIR(st.st_mode)
        if isdir != (kind == "dir") or not (isdir or stat.S_ISREG(st.st_mode)):
            return CHANGED, 0, None
        t = tree(p, self.env.never) if isdir else None
        if t and t.problem():
            return t.problem(), 0, None
        latest = max(st.st_mtime, birth(st), t.latest if t else 0.0)
        why = getattr(self, "rule_" + gid.replace("-", "_"))(gid, p, item, st, latest)
        return (why, 0, None) if why else (None, t.size if t else st.st_size, (st.st_dev, st.st_ino))

    def chosen(self, path):
        """`path` or a folder above it is chosen in this run, so it goes too."""
        n = ncase(path)
        while n not in self.selected:
            if os.path.dirname(n) == n:
                return False
            n = os.path.dirname(n)
        return True

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
        newest = 0.0
        if projects:  # the outermost project holds the others; it is read once per run
            key = ncase(projects[0])
            if key not in self.newest:
                self.newest[key] = newest_change(projects[0])
            newest = self.newest[key]
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
            if self.chosen(q):
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
        cap = s["max_mb"] * MB if s["max_mb"] is not None else None  # (0 MB is a real, tiny bin)
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


def still_there(path, ident):
    """True when what was checked (volume and file id) is still at `path`, or when that cannot be
    told; False when the path is gone or holds something else now."""
    try:
        st = os.stat(ext(path), follow_symlinks=False)
    except FileNotFoundError:
        return False
    except OSError:
        return True
    return (st.st_dev, st.st_ino) == ident


def move(ok, win):
    """Move the checked items to the Recycle Bin, up to 200 paths a call. An item counts as moved
    only when what was checked is no longer at its path. One still there is tried once more on
    its own; something new at the path is never touched. Returns (moved, left)."""
    moved, left = [], []
    for start in range(0, len(ok), BATCH):
        batch = ok[start:start + BATCH]
        try:
            win.recycle([e[1]["path"] for e in batch])
        except ValueError:
            pass  # a path the call refuses: each one is tried on its own below
        for e in batch:
            if still_there(e[1]["path"], e[3]):
                try:
                    win.recycle([e[1]["path"]])
                except ValueError:
                    pass
            (left if still_there(e[1]["path"], e[3]) else moved).append(e)
    return moved, [(e[0], e[1], IN_USE) for e in left]
----- END FILE 2 -----

----- BEGIN FILE 3: rules.py -----
"""Where things are on this PC, and what disk-cleanup may offer from them.

Env holds the locations, read once from the environment. The rest is the rule tables: the
areas the scan never offers anything from, the groups it may offer with how safe each one
is, and the Windows-managed places it only lists, with the Windows tool to use instead.
"""
import fnmatch
import json
import os
import re

import winsys
from winsys import odd_name  # noqa: F401  (the scan and clean use it from here)

DAY = 86400.0
MB = 1024 * 1024
REPARSE = 0x400  # junction, symlink or mount point: never followed, never offered
PLACEHOLDER = 0x400000 | 0x40000 | 0x1000  # cloud placeholder: reading it downloads it
TEMP_DAYS, PROJECT_DAYS = 7, 14

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
    "duplicates": ("Duplicate files (each copy listed)", "check", ""),
    "large-old": ("Large files not changed in 6 months", "check", ""),
}  # (no group of empty folders: apps and games often need theirs, and they free nothing)
GROUP_ORDER = list(GROUPS)
BUILD_GROUPS = ("build-node", "build-output", "py-venv")  # the 14-day project rule applies to these

# why a candidate is listed as skipped instead of offered
LINKS = "contains links to other folders"
ONLINE = "contains online-only files"
PARTLY = "parts of it could not be read"
HOLDS = "holds a folder this tool never removes"
RECENT = "project changed in the last 14 days"
RECENT_OWN = "changed in the last 14 days"
OUTSIDE = "its project is partly outside the scanned folder"
NOT_ONLY_VENV = "holds files that are not part of a virtual environment"
ODD = "its name is one Windows tools cannot handle safely"

# what the walker does with a folder it meets, besides walking it
SKIP, WINDOWS, PROGRAM, APPDATA, SYNCED, DOT, KNOWN = "skip", "windows", "program", "appdata", "synced", "dot", "known"
INSIDE = "inside"  # it is, or is inside, something a pattern rule offers as one item

ROOT_SKIP = {"$recycle.bin", "system volume information", "recovery", "config.msi", "$winreagent", "$sysreset"}
ROOT_WINDOWS = {"windows", "inetpub"}  # Windows-managed when directly in a drive root
VCS = {".git", ".hg", ".svn"}
OLD_WINDOWS = ("Windows.old", "$Windows.~BT", "$Windows.~WS")
PROGRAM_NAMES = {"program files", "program files (x86)", "steamapps", "steamlibrary", "epic games", "gog games",
                 "xboxgames", "riot games", "ea games", "ubisoft game launcher", "amazon games"}
UNINSTALLERS = ("unins*.exe", "uninst*.exe", "uninstall*.exe")
# what a folder of a sync client holds directly (Dropbox, Syncthing, Resilio, MEGA, ownCloud, Google Drive)
SYNC_MARKERS = {".dropbox", ".dropbox.cache", ".stfolder", ".sync", ".debris", ".owncloudsync.log",
                ".tmp.drivedownload", ".tmp.driveupload"}
SYNC_DBS = (".sync_*.db", "._sync_*.db")  # Nextcloud and ownCloud
VENV_FILES = {"pyvenv.cfg", ".gitignore", "cachedir.tag", ".lock", "pip-selfcheck.json", "selfcheck.json"}
VENV_DIRS = {"lib", "lib64", "scripts", "bin", "include", "share", "etc", "man"}
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


def birth(st):
    """When a file or folder was made: st_birthtime where Python has it, else st_ctime, which is
    the creation time on Windows."""
    return getattr(st, "st_birthtime", st.st_ctime)


def subdirs(path):
    """Names of the folders directly in `path`, links and online-only folders left out; [] when it
    cannot be read."""
    try:
        with os.scandir(path) as it:
            return [e.name for e in it if e.is_dir(follow_symlinks=False)
                    and not e.stat(follow_symlinks=False).st_file_attributes & (REPARSE | PLACEHOLDER)]
    except OSError:
        return []


def dropbox_folders(info_files):
    """The folder of every Dropbox account named in Dropbox's info.json files. Read-only; a missing
    file or bad JSON is skipped."""
    out = []
    for f in info_files:
        try:
            with open(f, encoding="utf-8") as h:
                data = json.load(h)
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            out += [a["path"] for a in data.values() if isinstance(a, dict) and isinstance(a.get("path"), str)]
    return out


def names(path):
    """Lower-case names of the files and of the folders directly in `path`. Links and online-only
    files count: they still mark a program or a project. None when it cannot be read."""
    files, dirs = set(), set()
    try:
        with os.scandir(ext(path)) as it:
            for e in it:
                (dirs if e.is_dir(follow_symlinks=False) else files).add(e.name.lower())
    except OSError:
        return None
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
                      | self.n_profiles | self.n_profiles_dirs | self.n_shell
                      | {x for x in (self.n_downloads, self.n_out) if x})

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
            synced += [j(profile, x) for x in os.listdir(profile) if x.lower().startswith(("onedrive", "dropbox"))]
        except OSError:
            pass
        synced += [full(p) for p in winsys.sync_roots()]
        synced += [full(p) for p in dropbox_folders([j(roaming, "Dropbox", "info.json"), j(local, "Dropbox", "info.json")])]
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
    None means walk it. Besides the plan's areas, any folder named AppData and a Windows,
    inetpub or ProgramData folder at any drive root (an old system disk) are left alone too."""
    n, low = ncase(path), name.lower()
    if ((at_root and low in ROOT_SKIP) or n == env.n_out or low in VCS
            or (at_profiles and n not in env.n_profiles)):
        return SKIP
    if n in env.n_windows or (at_root and low in ROOT_WINDOWS):
        return WINDOWS
    if n in env.n_programs or low in PROGRAM_NAMES:
        return PROGRAM
    if n in env.n_appdata or low == "appdata" or (at_root and low == "programdata"):
        return APPDATA
    if n in env.n_synced or (at_profile and low.startswith(("onedrive", "dropbox"))):
        return SYNCED
    if (at_root or at_profile) and low.startswith("."):
        return DOT
    if n in env.n_temps:
        return KNOWN
    return None


def holds_program(files, dirs):
    """An installed or portable program, from the lower-case names directly in a folder: an .exe
    with a .dll or with an Engine folder (Unreal), an uninstaller, an .egstore folder (Epic), or a
    goggame-*.info file (GOG)."""
    exts = {os.path.splitext(f)[1] for f in files}
    exe = ".exe" in exts
    return ((exe and (".dll" in exts or "engine" in dirs)) or ".egstore" in dirs
            or any(fnmatch.fnmatch(f, p) for f in files for p in UNINSTALLERS + ("goggame-*.info",)))


def venv_only(files, dirs):
    """A folder holding pyvenv.cfg is a virtual environment to offer only when it holds nothing
    but the parts of one, with its Scripts or bin folder."""
    return files <= VENV_FILES and dirs <= VENV_DIRS and bool(dirs & {"scripts", "bin"})


def is_synced_root(files, dirs):
    """A folder a sync client keeps, known by the marker it holds directly."""
    return bool((files | dirs) & SYNC_MARKERS) or any(fnmatch.fnmatch(f, p) for f in files for p in SYNC_DBS)


def is_project(files, dirs):
    """A project marker among the lower-case file and folder names directly in a folder. A .git,
    .hg or .svn (folder, or a .git file of a worktree) marks one too."""
    return (bool(files & MARKERS) or any(os.path.splitext(f)[1] in MARKER_EXTS for f in files)
            or bool((files | dirs) & VCS) or {"assets", "projectsettings"} <= dirs)


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


def context(env, path, strict=False):
    """How the walker treats folder `path`, worked out from its drive root down the way the walk
    would meet it. Returns (kind, projects, stop): kind None when it is walked, else the area it is
    in; projects are the folders above it that start project areas; stop is the folder the area
    starts at (for INSIDE, the item a rule offers whole, which may be `path` itself). A folder
    above it that cannot be read counts as empty, or with strict (the clean step) as SKIP."""
    folders, projects = chain(env, path), ()
    for parent, p in zip(folders, folders[1:]):
        np = ncase(parent)
        got = names(parent)
        if got is None and strict:
            return SKIP, projects, parent
        files, dirs = got or (set(), set())
        at_root, at_profile = env.is_root(np), np in env.n_profiles
        if is_synced_root(files, dirs):
            return SYNCED, projects, parent
        if holds_program(files, dirs) and not (at_root or at_profile):
            return PROGRAM, projects, parent
        if "pyvenv.cfg" in files:
            return (INSIDE if venv_only(files, dirs) else SKIP), projects, parent
        if is_project(files, dirs) and not (at_root or at_profile):
            projects += (parent,)
        name = os.path.basename(p)
        kind = dir_kind(env, p, name, at_root, at_profile, np in env.n_profiles_dirs)
        if kind:
            return kind, projects, p
        try:
            if os.stat(ext(p), follow_symlinks=False).st_file_attributes & PLACEHOLDER:
                return SKIP, projects, p  # online-only: the walk never enters it
        except OSError:
            pass
        if build_rule(name, files, dirs) or name.lower() == "node_modules":
            return INSIDE, projects, p
    return None, projects, None


def protected(env, path):
    """True when `path` is in a place nothing is ever offered from, whatever rule points there:
    Windows, programs, ProgramData, synced folders, another user's profile, Packages, Docker."""
    n = ncase(os.path.abspath(path))
    if any(under(n, d) for d in env.n_profiles_dirs) and not any(under(n, p) for p in env.n_profiles):
        return True
    return any(under(n, q) for q in env.n_windows | env.n_programs | env.n_synced | env.n_never_inside
               | where(env.program_data))


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
                out += [target("browser-cache", j(ud, prof, c), "%s, %s" % (app, prof), exe) for c in APP_CACHES]
        out += [target("browser-cache", j(ud, c), app, exe) for c in ("ShaderCache", "GrShaderCache", "GraphiteDawnCache")]
    out += [target("browser-cache", j(env.local, sub, "Cache"), app, "opera.exe") for sub, app in OPERA]
    ff = j(env.local, "Mozilla", "Firefox", "Profiles")
    for prof in subdirs(ff):
        out += [target("browser-cache", j(ff, prof, c), "Firefox, %s" % prof, "firefox.exe")
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
----- END FILE 3 -----

----- BEGIN FILE 4: scan.py -----
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
    group that comes first in rules.GROUPS. A folder listed because it holds a pyvenv.cfg and other
    files hides nothing: it is never walked, so only separately measured places sit below it."""
    out, kept = [], set()
    for c in sorted(cands, key=lambda c: (len(c["path"]), rules.GROUP_ORDER.index(c["group"]))):
        n = ncase(c["path"])
        up, inside = n, n in kept
        while not inside and os.path.dirname(up) != up:
            up = os.path.dirname(up)
            inside = up in kept
        if not inside:
            if c["skip"] != rules.NOT_ONLY_VENV:
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
        itself cannot be read. An online-only `path` is not entered at all."""
        m, stack, top = Measure(), [path], True
        try:
            if os.stat(ext(path), follow_symlinks=False).st_file_attributes & PLACEHOLDER:
                m.online = True
                return m
        except OSError:
            pass
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
        for name, isdir, a, size, dm, db in entries:
            if not isdir or a & (REPARSE | PLACEHOLDER):  # a link, or an online-only folder: never entered
                continue
            p = os.path.join(path, name)
            kind = rules.dir_kind(env, p, name, at_root, at_profile, n in env.n_profiles_dirs)
            rule = rules.build_rule(name, files, dirs) if kind is None else None
            if rule:
                group, note = rule
                self.put(self.candidate, group, p, dm, db, note, None, 0.0, () if group == "py-cache" else projects)
            elif kind is None and name.lower() != "node_modules":  # no package.json beside it: left alone
                self.put(self.list_dir, p, projects, dm, db)
            elif kind in (rules.PROGRAM, rules.SYNCED):
                self.put(self.area, "programs" if kind == rules.PROGRAM else "synced", p)
        with self.lock:
            self.files += count
            self.folders += 1
            self.dupes += dupes
            self.large += large
            for pr in projects if newest else ():
                k = ncase(pr)
                self.recency[k] = max(self.recency.get(k, 0.0), newest)

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
----- END FILE 4 -----

----- BEGIN FILE 5: winsys.py -----
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
    . or .. part, a part ending in a space or a dot, a : after the drive (a file's stream), or
    anything os.path.abspath would change."""
    if not path or "\0" in path or path.startswith(("\\\\?\\", "\\\\.\\")) or "/" in path:
        return True
    if ":" in os.path.splitdrive(path)[1]:
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
----- END FILE 5 -----
`````

[Back to top](#disk-cleanup-prompt)

## Option 2: use the scripts from this repo

A short prompt that downloads the tool's five files from this repo and runs them. Claude says
what it will download and asks first.

```text
Path to scan: C:\

Show me what could be cleaned up on the drive or folder on the first line, with the disk-cleanup tool from the public repo github.com/ZazaGdev/AI-fun. Do not write the tool yourself: use the repo's fixed files. Nothing is removed unless I ask for something specific later.

Wherever this prompt says ~, use the full path of my home folder (such as C:\Users\me): PowerShell does not expand ~ for python.

1. Run `python --version`. If Python is missing, stop and tell me to install Python 3 from python.org, or with `winget install Python.Python.3.13`, and then to paste this again.

2. Before downloading anything, tell me what you will fetch and from where, and ask me to confirm. The five files are:
   - https://raw.githubusercontent.com/ZazaGdev/AI-fun/main/disk-cleanup/skill/scripts/disk_cleanup.py
   - https://raw.githubusercontent.com/ZazaGdev/AI-fun/main/disk-cleanup/skill/scripts/clean.py
   - https://raw.githubusercontent.com/ZazaGdev/AI-fun/main/disk-cleanup/skill/scripts/rules.py
   - https://raw.githubusercontent.com/ZazaGdev/AI-fun/main/disk-cleanup/skill/scripts/scan.py
   - https://raw.githubusercontent.com/ZazaGdev/AI-fun/main/disk-cleanup/skill/scripts/winsys.py
   Say that the scan only reads names, sizes and dates in the folder, reads file contents only to compare possible duplicates, writes its two reports to ~/disk-cleanup/, and sends nothing anywhere, and that clean moves things to the Recycle Bin only when I ask for them. Offer to show me the scripts before running them.

3. Once I confirm, download the five files with Python's standard library (urllib), not by retyping them, into ~/disk-cleanup/tool/. Save them byte for byte and do not edit them. If a download fails, stop. Tell me which URL failed and the error, and that I can install the skill instead by copying the repo's disk-cleanup/skill folder to ~/.claude/skills/disk-cleanup.

4. Run the scan, with the path from the first line: `python ~/disk-cleanup/tool/disk_cleanup.py scan "<path>"`. Run it in the background or with a 10-minute timeout: a whole drive can take several minutes.

5. Show me the summary exactly as printed, and the path of the full list (its "Full list:" line). Then stop. Do not ask whether to remove anything, do not offer to, and do not recommend removing any group.

6. Only if I then ask, in my own words, to remove specific groups or items of this report (by number or by name): run `python ~/disk-cleanup/tool/disk_cleanup.py clean "<report data>" --groups <numbers or names> --items <numbers>` for exactly those, without --yes. <report data> is the path on the summary's "Report data:" line. This dry run changes nothing: show me what it printed, with what it leaves out and why, and any WARNING line. Run the same command with --yes only after I say yes to that dry run, then tell me what moved, what was left out and why, and where the log is. A Your call group (duplicates, large files) goes by item number only: if I ask for a whole one, say so and let me name the items. Never pick for me.

Hard rules. Pasting this prompt, or a general request such as "clean up my PC", is never a request to remove anything; only a later reply of mine that names groups or items is. If the report is more than 24 hours old, scan again before any clean. Remove things only through that clean command, and only what I named: never with del, rm, Remove-Item, rmdir or any other command, never as administrator, and never by editing the report. Never empty the Recycle Bin, and never act on the Not offered list. The reports hold my own file names: never upload, publish or paste them anywhere outside this chat.
```

[Back to top](#disk-cleanup-prompt)
