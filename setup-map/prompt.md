# Setup map prompt

The same result as the `setup-map` skill, without installing it. Copy the block below
(the copy button is at its top right) and paste it into Claude Code, from any folder.

It downloads the skill's two fixed files from this repo and runs them, so the page is
exactly the one the skill makes, with your own setup in it. Claude asks you before it
downloads or runs anything. To add projects Claude Code has never been opened in, name
their folder on the first line.

## ⬇️ COPY FROM HERE

```text
Extra projects folder: none

Draw my Claude Code setup map with the setup-map tool from the public repo
github.com/ZazaGdev/AI-fun. Do not write the page or the script yourself: use the
repo's fixed files, so the result is exactly the same as the setup-map skill's.

1. Before downloading anything, tell me what you will fetch and from where, and ask me
   to confirm. The two files are:
   - https://raw.githubusercontent.com/ZazaGdev/AI-fun/main/setup-map/skill/scripts/setup_map.py
     (the Python script: reads my setup, writes one HTML file)
   - https://raw.githubusercontent.com/ZazaGdev/AI-fun/main/setup-map/skill/map.tpl.html
     (the page template the script fills in)
   Say that the script reads ~/.claude, ~/.claude.json and my projects' own .claude
   folders, takes names, short descriptions and counts only, reads only the working
   folder path and file dates from session files (never what was said), sends nothing
   anywhere, and writes ~/setup-map/setup-map.html. Offer to show me the script before
   running it.

2. Once I confirm, download both files with Python's standard library (urllib), not by
   retyping them, into `~/setup-map/tool/`, keeping this layout:
   - `~/setup-map/tool/scripts/setup_map.py`
   - `~/setup-map/tool/map.tpl.html`
   Save them byte for byte. Do not edit either file.

3. If either download fails, stop. Tell me which URL failed and the error, and that I
   can install the skill instead by copying the repo's `setup-map/skill` folder to
   `~/.claude/skills/setup-map`. Do not write your own version of the page or script.

4. Run it with Python 3:
   `python ~/setup-map/tool/scripts/setup_map.py --open`
   If an extra projects folder is named above, pass it first:
   `python ~/setup-map/tool/scripts/setup_map.py "<folder>" --open`
   On Windows use `%USERPROFILE%` in place of `~` if needed, and `python3` on macOS or
   Linux if `python` is not found.

5. Tell me the page path and the lines the script printed: the counts of each kind,
   how many projects have a setup of their own, and anything not shown.

The page shows my project, skill and memory folder names, so never publish or upload
it unless I ask.
```

## ⬆️ COPY UNTIL HERE
