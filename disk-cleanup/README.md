# disk-cleanup

Shows what could be cleaned up on a Windows drive or folder, such as `C:\` or `D:\`: temp
files, browser and app caches, package-manager caches, old installers, build folders of
projects you have not touched in a while, duplicate files and large old files. Each kind is
one group, with its size and how safe it is to clean up. It removes nothing unless you ask.

Two ways to use it:

- [`skill/`](skill/): an installable Claude Code skill.
- [`prompt.md`](prompt.md): a prompt you paste into Claude Code, no install, in two versions.

All of them run the same fixed scripts. Windows only, Python 3.8 or newer, nothing but
Python's standard library.

## The three rules

1. **It only reports.** The scan reads and lists. Nothing is removed unless you ask, after
   seeing the list, for particular groups or items in your own words. Even then it only moves
   them to the Recycle Bin, and anything Windows cannot put in the Recycle Bin is skipped and
   reported, never deleted for good.
2. **It lists only what is easy to get back or is clearly yours to judge.** Temp files older
   than 7 days, browser, app and graphics caches, package-manager caches, your own crash dumps,
   old installers and unfinished downloads in Downloads, and the rebuildable build folders of
   projects unchanged for 14 days are listed as groups. Duplicate files and files of 500 MB or
   more unchanged for 6 months are listed one by one, and only ever go one by one: the same file
   in two places is often on purpose.
3. **It never offers Windows' own folders, installed programs and games, OneDrive and other
   synced folders, anything in use, or anything outside the folder you named.** Those are only
   listed, each with the Windows tool to use instead.

Empty folders are not listed at all: apps and games often need theirs, and they free nothing.

## What it lists

| Group | What | How safe |
| --- | --- | --- |
| Temporary files older than 7 days | each item in your temp folders, file or folder, unchanged for 7 days | Safe |
| Crash dumps and error reports | your own crash dumps and Windows error reports | Safe |
| Browser caches | the caches of Chrome, Edge, Brave, Vivaldi, Chromium, Opera and Firefox | Safe |
| App caches | the caches of Discord, Slack, Teams, VS Code, Cursor, Steam's web view and other Electron apps | Safe |
| Graphics shader caches | NVIDIA, AMD, Intel and DirectX shader caches | Safe |
| Python caches | `__pycache__`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache` | Safe |
| Package manager caches | npm, Yarn, pip, uv, NuGet, Gradle, Cargo, Go, Playwright, Electron, node-gyp, Cypress and Bun downloads | Easy to get back |
| Old installers and unfinished downloads in Downloads | installers unchanged for 30 days, unfinished downloads unchanged for 7 | Easy to get back |
| node_modules folders | next to a `package.json`, in projects unchanged for 14 days | Easy to get back |
| Other build output | .NET `bin` and `obj`, Rust and Maven `target`, Gradle `build`, Next.js and similar caches, Unity `Library`, Unreal `Intermediate` | Easy to get back |
| Python virtual environments | folders holding only a virtual environment, in projects unchanged for 14 days | Easy to get back |
| Duplicate files (each copy listed) | photos, videos, music, documents, archives and installers that exist twice or more, with one copy marked as the one to keep | Your call |
| Large files not changed in 6 months | photos, videos, documents, archives, installers and disk images of 500 MB or more | Your call |

A project counts as changed when any file in it, or in the repo or solution around it, was
changed or created in the last 14 days. Build folders of such projects are left out, and the
summary says so.

## What it never offers

These are listed with their size and the Windows tool that handles them:

- the Recycle Bin, when you scan a whole drive;
- Windows Update leftovers, Delivery Optimization files, Windows temporary files, system crash
  dumps and error reports, a previous Windows installation, the thumbnail cache and Temporary
  Internet Files;
- installed programs and games (Program Files, game libraries, any folder holding a program);
- synced folders: OneDrive, Dropbox, iCloud, Google Drive and other sync clients' folders,
  because removing a file there removes it on your other devices too.

It also never reads other users' profiles, your AppData beyond the caches above, version
control folders, or anything behind a junction or symbolic link. Online-only files are never
opened, since that would download them.

## What it touches

- Reads the names, sizes and dates of the files and folders in the drive or folder you name.
  It reads file contents only to compare possible duplicates.
- Writes two reports to `~/disk-cleanup/`: `scan-YYYYMMDD-HHMMSS.txt`, the full list, and
  `scan-YYYYMMDD-HHMMSS.json`, the same data for the clean step.
- Moves only the items you ask for to the Recycle Bin, and writes a log of that run,
  `clean-YYYYMMDD-HHMMSS.txt`, next to the report.
- Sends nothing anywhere. Option 2 of the prompt downloads the five scripts from this repo,
  after asking you; Option 1 downloads nothing.

The reports list your own file names, so think before you share them.

## Install the skill

Copy the `skill` folder to `~/.claude/skills/disk-cleanup`, so you end up with
`~/.claude/skills/disk-cleanup/SKILL.md`. The folder must be named `disk-cleanup`. Start a new
Claude Code session.

```powershell
git clone https://github.com/ZazaGdev/AI-fun.git
Copy-Item -Recurse AI-fun\disk-cleanup\skill "$HOME\.claude\skills\disk-cleanup"
```

## Use

In Claude Code, type:

```
/disk-cleanup C:\
```

or just ask what you could clean up on a drive. Claude runs the scan, which can take several
minutes on a whole drive, and shows the summary. That is all it does: it does not ask you to
remove anything.

## If you want something removed

Ask Claude in your own words, using the group or item numbers from the summary or the full
list, for example `move group 2 to the Recycle Bin` or `remove items 412 and 415`. Claude first
shows what would move and what it leaves out, and why. It moves them to the Recycle Bin only
after you say yes. Anything Windows cannot put in the Recycle Bin is skipped, never deleted for
good.

Every item is checked again against the disk before it moves: one that changed, moved, became
a link or no longer fits its rule is left out. Duplicates and large files go by item number
only, and a duplicate is moved only while another copy stays.

The space comes back when you empty the Recycle Bin. Until then you can restore anything from
it. If a run ever seems stuck, look for a Windows dialog asking whether to delete something for
good, and answer No.

## Run the script directly

In PowerShell:

```powershell
python "$HOME\.claude\skills\disk-cleanup\scripts\disk_cleanup.py" scan D:\
python "$HOME\.claude\skills\disk-cleanup\scripts\disk_cleanup.py" clean <report.json> --groups 2 --items 412,415
```

`scan` options: `--out <folder>` for the reports, `--workers <1-4>` for the threads that read
the disk (4 at most), and `--dupe-min-mb`, `--large-mb` and `--large-days` for the duplicate
and large-file thresholds (1, 500 and 180 by default).

`clean` takes group numbers or names with `--groups`, item numbers with `--items`, and item
numbers to leave out with `--skip`. Without `--yes` it is a dry run that changes nothing. It
refuses a report more than 24 hours old.

## A sample summary

Made up, from a scan of a second drive:

```
Scan of D:\ finished in 2 min 10 s: 812,345 files in 98,765 folders.

Could be cleaned up: about 38.2 GB in 9 groups.

   1. Temporary files older than 7 days          2.1 GB   1,203 items   Safe
   2. Browser caches                             1.4 GB       3 items   Safe (close Chrome first)
   3. Graphics shader caches                   921.6 MB       4 items   Safe
   4. Python caches                             38.0 MB     112 items   Safe
   5. node_modules folders                       9.7 GB      14 items   Easy to get back
   6. Other build output                         3.2 GB      21 items   Easy to get back
   7. Package manager caches                     2.6 GB       5 items   Easy to get back
   8. Duplicate files                            3.3 GB   60 sets, 120 copies   Your call
        set 1: #301  1.2 GB  D:\Videos\trip.mp4  (suggested keep)
               #302  1.2 GB  D:\Backup\Videos\trip.mp4
        set 2: #303  640.0 MB  D:\Photos\2023\album.zip  (suggested keep)
               #304  640.0 MB  C:\Users\you\Downloads\album.zip
        set 3: #305  410.0 MB  D:\Music\live-set.flac  (suggested keep)
               #306  410.0 MB  D:\Old PC\Music\live-set.flac
        and 57 more sets in the full list
   9. Large files not changed in 6 months       15.0 GB       3 items   Your call
        #420  6.1 GB  2024-11-02  D:\VMs\old-test.vhdx
        #421  5.4 GB  2023-12-09  D:\ISO\Windows10_22H2.iso
        #422  3.5 GB  2023-05-14  C:\Users\you\Videos\Recording 2023-05-14.mp4

Safe: comes back by itself. Easy to get back: reinstall, rebuild or download again.
Your call: your own files; only you can tell whether you still need each one.

Not offered, Windows handles these:
   Recycle Bin on D:                             1.1 GB   Empty it from the Recycle Bin on the desktop when you are sure
   Installed programs and games                212.0 GB   Settings > Apps > Installed apps, or the game's launcher
        188.0 GB  D:\SteamLibrary
         24.0 GB  D:\Games\Some Game

Left out: 4 build folders of projects changed in the last 14 days (2.0 GB).
Could not read 42 folders (no permission). They were skipped.

Full list: C:\Users\you\disk-cleanup\scan-20261121-140500.txt
Report data: C:\Users\you\disk-cleanup\scan-20261121-140500.json
Nothing was removed. This scan only reads.
```

## Or just paste the prompt

[`prompt.md`](prompt.md) has two prompts. Option 1 is the simple one: paste it into Claude Code
and it writes the tool's five scripts from the prompt itself, checks they are exact, and runs
the scan, with nothing downloaded. Option 2 is shorter: it asks first, then downloads the same
five scripts from this repo. Put the drive or folder to scan on the prompt's first line.

## Tests

From the repo root:

```powershell
python -m unittest discover -s disk-cleanup/tests -v
```

The tests build a made-up PC in a temp folder: drives, a profile, caches, projects, games,
sync folders, a junction and a folder you may not read. They check every rule on it and what
`clean` refuses. A fake Recycle Bin stands in for the real one. One test moves a single tiny
made-up file to the real Recycle Bin, and runs only when you set
`DISK_CLEANUP_REAL_RECYCLE=1`.
