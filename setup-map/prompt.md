# Setup map prompt

The same result as the `setup-map` skill, without installing anything. Copy the block
below (the copy button is at its top right) and paste it into Claude Code, from any
folder. It maps your global setup and every project Claude Code has worked in. To add
projects Claude Code has never been opened in, name their folder on the first line.

## ⬇️ COPY FROM HERE

```text
Extra projects folder: none

Draw my whole Claude Code setup as one interactive 3D web page: my global setup, and
every project Claude Code has worked in on this computer, wherever I run this from.
Projects come from Claude Code's own records: the session folders under
`~/.claude/projects/` and the `projects` list in `~/.claude.json`. Use only Python's standard
library to read the setup, in one script you write to a temporary folder. Read names,
kinds, the one-line `description` from each file's frontmatter, and counts only. Never
copy settings values, env, commands, URLs or file bodies into the page. Do not send
anything anywhere.

1. **Global setup** (from `~/.claude`, on Windows `%USERPROFILE%\.claude`):
   - Skills: `skills/*/SKILL.md`, name and description from the frontmatter.
   - Agents: `agents/*.md`. Commands: `commands/*.md`, shown as `/name`.
   - Output styles: `output-styles/*.md`; mark the one named by `outputStyle` in
     `settings.json` as active.
   - Rules: `CLAUDE.md`, each file it imports with a line starting `@`, and `rules/*.md`.
   - Memory: one node per project that has a `projects/<slug>/memory/` folder with
     `*.md` files in it (not counting `MEMORY.md`), named after that project (the one
     its sessions' `cwd` belongs to, from step 2), with the count of distinct file
     names. Several folders belonging to the same project make one node. Skip folders
     with no memory files. Never read the memory files themselves.
   - Plugins: the enabled ones in `enabledPlugins` of `settings.json`, read at their
     `installPath` in `plugins/installed_plugins.json`: description from
     `.claude-plugin/plugin.json`, and the names of their skills, agents and commands.
   - MCP servers: `mcpServers` keys in `~/.claude.json` (user scope) and under each
     entry of its `projects` (local scope), each project's `.mcp.json`, and each
     enabled plugin's `.mcp.json`. Names only.
   - Hooks: from `settings.json`, each plugin's `hooks/hooks.json` and each project's
     `.claude/settings.json`. Show the script file name the command runs (or "inline
     <event> hook") and the event. Never show the command itself.
   - Model: `model` in `settings.json`.

2. **Projects:** every folder Claude Code has worked in.
   - Each folder under `~/.claude/projects/` holds the session files (`*.jsonl`) of
     one working folder. Take that folder's real path from the `cwd` field of the first
     lines of a session file; do not decode the folder name. Count the session files,
     and take the newest file's modified time as the date it was last used. Read only
     `cwd` and file times, never anything that was said in a session.
   - Add every key of the `projects` list in `~/.claude.json`, and, if an extra
     projects folder is named above, its subfolders three levels deep that have
     `.git`, `.claude`, `CLAUDE.md` or `.mcp.json`.
   - Treat paths that resolve to the same folder as one. Skip folders that no longer
     exist, the home folder, drive roots, `~/.claude`, anything in the system temp
     folder, and git worktrees (a `.git` file instead of a `.git` folder).
   - A folder inside another project's git repo is part of that project, and its
     sessions count for it, unless it has its own `.claude` folder: then it is a
     project of its own named `parent/sub`, for example `my-app/server`. A folder
     that only holds projects and is not a git repo does not swallow them.
   For each project, its sessions, last-used date and its own setup: `.claude/agents/**/*.md` (with a `name` in frontmatter),
   `.claude/skills/*/SKILL.md`, `.claude/commands/**/*.md`, hooks in
   `.claude/settings.json` and `.claude/settings.local.json`, MCP servers from its
   `.mcp.json` and its `~/.claude.json` entry, `CLAUDE.md`, `.claude/CLAUDE.md` and
   `.claude/rules/*.md`.

3. **Page.** Write one self-contained file, `~/setup-map/setup-map.html`, with the data
   above embedded as JSON, then open it in my browser and give me the path. Start it
   with `<!doctype html>`, `<meta charset="utf-8">` and a viewport meta tag. Load
   three.js 0.160.0 from `https://cdn.jsdelivr.net/npm/three@0.160.0/` through an
   import map, with OrbitControls, CSS2DRenderer and UnrealBloomPass. Build all text
   with DOM calls (`textContent`), never `innerHTML`, so a name cannot inject markup.
   - Look: near-black space with a faint starfield, soft bloom, slow auto-rotation.
     A glowing coral core labelled "Claude Code" in the middle.
   - The page opens on the Global view, and that view must show the global setup
     from step 1, never only projects.
   - Global view: one glowing hub per kind (skills, plugins, agents, MCP servers,
     hooks, commands, output styles, rules, memory), each in its own neon colour,
     spread evenly around the core and joined to it by a faint curved line. Each item
     is a small node in a loose cloud past its hub, joined to it by a fainter line.
     Label each hub with its kind and count.
   - By project view: every project around the core on a wider shell. A project's
     node grows with its number of sessions and glows brighter the more recently it was
     used. Projects used in the last 60 days sit closer; the rest sit further out,
     faded, but still shown. Under each name: "used today", "used 3 days ago", "idle
     90 days" or "no recent sessions". Around each project, one small circle per kind
     of its own setup, in that kind's colour, with its count under it ("2 agents").
   - Links stay quiet until you point at something: hovering or clicking a node lights
     its path to the core. One faint dot drifts slowly along each link.
   - HUD: title and "N pieces, model, style" at top left; a Global / By project toggle
     and a search box at the top; a row of chips at the bottom, one per kind with its
     count. Clicking a chip or node flies the camera there and opens a side panel
     listing the items with their descriptions. A "where this was read from" link
     lists the folders each kind was read from. Hover shows a small tooltip. Drag to
     orbit, scroll to zoom, H hides the HUD, Escape closes the panel.
   - Search finds projects, skills, agents, hooks and the rest, flies to the match and
     opens its panel.
   - It must work when opened by double-clicking the file.

4. **Tell me:** the page path, the count of each kind, how many projects there are,
   how many were used in the last 60 days, how many have a setup of their own, and
   anything you could not read.

The page shows my project, skill and memory folder names, so never publish or upload
it unless I ask.
```

## ⬆️ COPY UNTIL HERE
