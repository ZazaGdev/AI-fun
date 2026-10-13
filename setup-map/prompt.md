# Setup map prompt

The same result as the `setup-map` skill, without installing anything. Copy the block
below (the copy button is at its top right), paste it into Claude Code, and change the
projects folder on its first line if your projects are not in the folder you started
Claude Code in.

## ⬇️ COPY FROM HERE

```text
Projects folder: the current folder

Draw my Claude Code setup as one interactive 3D web page. Use only Python's standard
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
   - Memory: one node per folder `projects/<slug>/memory/` with its count of `*.md`
     files (not counting `MEMORY.md`). Never read the memory files themselves. The
     slug is the project's absolute path with every character that is not a letter or
     digit replaced by `-`; show the matching project's name when one matches.
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

2. **Projects:** the projects folder and its subfolders, three levels deep, skipping
   hidden folders and `node_modules`, `dist`, `build` and virtual environments. A
   folder is a project when it has `.git`, `.claude`, `CLAUDE.md` or `.mcp.json`. For
   each, its own setup: `.claude/agents/**/*.md` (with a `name` in frontmatter),
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
   - Global view: one glowing hub per kind (skills, plugins, agents, MCP servers,
     hooks, commands, output styles, rules, memory), each in its own neon colour,
     spread evenly around the core and joined to it by a faint curved line. Each item
     is a small node in a loose cloud past its hub, joined to it by a fainter line.
     Label each hub with its kind and count.
   - By project view: projects around the core on a wider shell; those with a setup of
     their own sit closer and brighter, the rest further out and dimmed with "no own
     setup" under the name. Around each project, one small circle per kind it has, in
     that kind's colour, with its count under it ("2 agents").
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

4. **Tell me:** the page path, the count of each kind, how many projects have a setup
   of their own, and anything you could not read.

The page shows my project, skill and memory folder names, so never publish or upload
it unless I ask.
```

## ⬆️ COPY UNTIL HERE
