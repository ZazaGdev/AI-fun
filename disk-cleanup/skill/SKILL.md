---
name: disk-cleanup
description: Use when the user wants to know what could be cleaned up on a Windows drive or folder, asks how to free up disk space or what they can delete, says a drive is full, or types /disk-cleanup [path]. Scans the drive or folder, which only reads, and shows what could be cleaned up, grouped by kind with sizes and how safe each group is. It removes nothing by itself; only when the user later asks for specific groups or items of that list does it move exactly those to the Recycle Bin.
---

# Disk cleanup

`$DC` below is `python "$HOME/.claude/skills/disk-cleanup/scripts/disk_cleanup.py"`. Windows
only, Python 3.8 or newer.

1. If no path was given (`/disk-cleanup D:\`), ask which drive or folder to scan, suggesting
   `C:\`.
2. Run `$DC scan '<path>'`, with the path in single quotes (in Git Bash a `"C:\"` never ends),
   in the background or with a 10-minute timeout: a whole drive can take several minutes. It
   only reads, writes its two reports to `~/disk-cleanup/`, and prints a summary.
3. Show the summary exactly as printed, and the path of the full list (its `Full list:` line).
4. Stop there. Do not ask whether to remove anything, do not offer to, and do not recommend
   removing any group.
5. Only if the user then asks, in their own words, to remove specific groups or items of this
   report (by number or by name):
   - Run `$DC clean '<report data>' --groups <numbers or names> --items <numbers>` for exactly
     those, without `--yes`. `<report data>` is the path on the summary's `Report data:` line,
     and the numbers go comma-separated, such as `--items 412,415`. Run it like the scan, in the
     background or with a 10-minute timeout. This dry run changes nothing. Show what it printed:
     what would move, what is left out and why, and any WARNING line.
   - Run the same command with `--yes` only after the user says yes to that dry run. Then report
     what moved, what was left out and why, and where the log is.
   - A Your call group (duplicates, large files) goes by item number only. If the user asks for
     a whole one, say so and let them name the items. Never pick for them.

Hard rules:

- This skill being started, or a general request such as "clean up my PC", is never a request
  to remove anything. Only a later reply that names groups or items is.
- If the report is more than 24 hours old, scan again before any clean.
- Remove things only through `$DC clean`, and only what the user named. Never with `del`, `rm`,
  `Remove-Item`, `rmdir` or any other command, never as administrator, and never by editing
  the report.
- Never empty the Recycle Bin, and never act on the Not offered list: those are for Windows' own
  tools, which the summary names.
- The reports hold the user's own file names. Never upload, publish or paste them anywhere
  outside this chat.
