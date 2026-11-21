---
name: disk-cleanup
description: Use when the user wants to know what could be cleaned up on a Windows drive or folder, asks how to free up disk space or what they can delete, says a drive is full, or types /disk-cleanup [path]. Scans the drive or folder, which only reads, and shows what could be cleaned up, grouped by kind with sizes and how safe each group is. It removes nothing by itself; only when the user later asks for specific groups or items of that list does it move exactly those to the Recycle Bin.
---

# Disk cleanup

`$DC` below is `python "$HOME/.claude/skills/disk-cleanup/scripts/disk_cleanup.py"`. If
`python --version` fails or opens the Microsoft Store, try `py -3 --version`; if that works, use
`py -3` in place of `python`. Windows only, Python 3.8 or newer.

1. If no path was given (`/disk-cleanup D:\`), ask which drive or folder to scan, suggesting
   `C:\`.
2. Run `$DC scan "<path>"` in the background, with the path written with forward slashes inside
   double quotes, such as `"D:/"` or `"C:/Users/me/My Files"`. A path that holds a `$` or a
   backtick goes in single quotes instead, since both shells change those inside double quotes;
   the same goes for the report path below. Do not run it in the foreground with a timeout: on a
   large or slow drive it can take longer than 10 minutes. Wait for it to finish before showing
   anything. Then check that its first line, `Scanning <folder>.`, names the folder that was
   asked for. It only reads, writes its two reports to `~/disk-cleanup/`, and prints a summary.
3. Show the summary exactly as printed, in a code block, with nothing shortened, reworded or
   left out: its group and item numbers are how the user would name things later. Give the
   path of the full list too (its `Full list:` line).
4. Stop there. Do not ask whether to remove anything, do not offer to, and do not recommend
   removing any group.
5. Only if the user then asks, in their own words, to remove specific groups or items of this
   report (by number or by name):
   - Run `$DC clean "<report data>" --groups <numbers or names> --items <numbers>` for exactly
     those, without `--yes`, in the background like the scan, and wait for it to finish.
     `<report data>` is the path on the summary's `Report data:` line, written with forward
     slashes, and the numbers go comma-separated, such as `--items 412,415`. This dry run
     changes nothing.
   - Check that it lists exactly the groups and items the user named, and if it does not, say
     so plainly. Show what it printed: what would move, item by item, what is left out and why,
     and any WARNING line.
   - Run the same command with `--yes` only after the user says yes to that dry run, again in
     the background. Then report what moved, what was left out and why, and where the log is.
   - A Your call group (duplicates, large files) goes by item number only. If the user asks for
     a whole one, say so and let them name the items.

Hard rules:

- This skill being started, or a general request such as "clean up my PC", is never a request
  to remove anything. Only a later reply that names groups or items is.
- Group and item numbers belong to the report they were printed with. A report more than 24
  hours old needs a new scan before any clean. After any new scan, show the new summary and let
  the user name the groups or items again from it. Never carry numbers over.
- Remove things only through `$DC clean`, and only what the user named. Never with `del`, `rm`,
  `Remove-Item`, `rmdir` or any other command, never as administrator, and never by editing a
  report or writing one.
- Never close or stop a program, and never pick items for the user.
- Never empty the Recycle Bin, and never act on the Not offered list: those are for Windows' own
  tools, which the summary names.
- The reports hold the user's own file names. Never upload, publish or paste them anywhere
  outside this chat.
