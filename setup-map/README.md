# setup-map

Draws your [Claude Code](https://docs.claude.com/en/docs/claude-code) setup as an
interactive 3D map: skills, plugins, agents, MCP servers, hooks, commands, output
styles, rules and memory around a glowing core, and a second view of every project
Claude Code has worked in on your computer, sized by how much you use it, brightest
for the ones you used lately, with idle ones faded. Click anything to see what it is,
or search for it by name. It maps everything from whichever folder you run it in.

![The setup map, built from a made-up sample setup](screenshot.png)

![The By project view of the same sample](screenshot-projects.png)

The screenshots come from a made-up sample setup, not a real one.

Two ways to use it:

- [`skill/`](skill/): an installable Claude Code skill.
- [`prompt.md`](prompt.md): a prompt you paste into Claude Code, no install, in two
  versions (see below).

All of them run the same fixed script and page template, so they give exactly the same
page, with your own setup in it.

## What it touches

- Reads `~/.claude` (skills, agents, commands, output styles, rules, plugins, hooks,
  memory folders), `~/.claude.json` (MCP server names and the folders Claude Code was
  opened in) and each project's own `.claude` folder, `CLAUDE.md` and `.mcp.json`.
- Finds your projects from Claude Code's session history in `~/.claude/projects`. From
  each session file it reads only the working folder path (`cwd`) and the file's date,
  to know where you worked, how often and when. It never reads what was said in a
  session.
- Takes only names, short descriptions (the `description` line at the top of a skill
  or agent file) and counts. It never copies settings values, environment variables,
  hook commands, URLs or the contents of your memory files.
- Writes one local HTML file, `~/setup-map/setup-map.html`. The prompts also save the
  script and template they run in `~/setup-map/tool/`. Nothing else is written.
- Sends nothing anywhere. Option 2 of the prompt downloads two files from
  raw.githubusercontent.com, after asking you; Option 1 downloads nothing. When you open the page, it loads
  three.js from jsDelivr and its fonts from Google Fonts; your setup stays inside the
  file.

The page shows your project and skill names, so think before you share it.

## Install the skill

Copy the `skill` folder to `~/.claude/skills/setup-map`, so you end up with
`~/.claude/skills/setup-map/SKILL.md`. The folder must be named `setup-map`. Python 3
is required. Start a new Claude Code session.

```sh
git clone https://github.com/ZazaGdev/AI-fun.git
cp -r AI-fun/setup-map/skill ~/.claude/skills/setup-map
```

## Use

In Claude Code, from any folder, type:

```
/setup-map
```

Projects are every folder Claude Code has worked in, taken from its session history
and from `~/.claude.json`. Folders that no longer exist, temp folders and git
worktrees are left out. A folder inside another project's repo counts as part of it,
unless it has its own `.claude` folder; then it shows as `project/folder`. Projects
untouched for 60 days or more are faded, not hidden. Claude Code deletes old session
files after its cleanup period (30 days by default), so a project you have not opened
since then shows "no recent sessions".

To add projects Claude Code has never been opened in, name the folder that holds them:

```
/setup-map ~/code
```

That adds its subfolders, three levels deep, that have a `.git`, `.claude`,
`CLAUDE.md` or `.mcp.json`.

You can also run the script directly, on Windows, macOS or Linux:

```sh
python ~/.claude/skills/setup-map/scripts/setup_map.py --open
```

Options: `--out <file>` writes the page somewhere else; `--projects-json <file>` also
reads a JSON list of projects kept elsewhere, in the form
`{"projects": [{"name": "...", "path": "..."}], "scanRoots": ["..."]}`, where every
folder in a scan root counts as a project.

In the page: drag to orbit, scroll to zoom, click a node or a chip to open its list,
switch between Global and By project at the top, and press H to hide the overlay.

## Or just paste the prompt

[`prompt.md`](prompt.md) has two prompts. Option 1 is the simple one: paste it into
Claude Code and it writes the map's two files from the prompt itself and runs them,
with nothing downloaded. Option 2 is shorter: it asks first, then downloads the same
two files from this repo and runs them. Python 3 is the only requirement for either.
