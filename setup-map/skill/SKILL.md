---
name: setup-map
description: Use when the user wants to see their Claude Code setup as a picture, asks for a setup map, a map or overview of their skills, plugins, agents, MCP servers, hooks, commands, rules and memory, wants to see which projects have their own setup, or types /setup-map (optionally with a projects folder). Builds one local 3D HTML page from ~/.claude and the projects folder.
---

# Setup map

`$MAP` below is `python "$HOME/.claude/skills/setup-map/scripts/setup_map.py"`.

1. Take the projects folder from the request. If none is given, use the folder this
   session was started in. The script looks in that folder and its subfolders, three
   levels deep, for projects (a `.git`, `.claude`, `CLAUDE.md` or `.mcp.json`).
2. Run `$MAP "<projects folder>" --open`. It reads `~/.claude`, `~/.claude.json`
   and each project's own `.claude` folder, writes the page to
   `~/setup-map/setup-map.html`, opens it in the browser, and prints the counts.
   - Add `--out <file>` only if the user asks for another place.
   - Add `--projects-json <file>` only if the user keeps a JSON list of their projects
     (`{"projects": [{"name", "path"}], "scanRoots": [...]}`) and names it.
3. Reply with the page path, the counts line, how many projects have a setup of their
   own, and anything the script printed as "not shown".

The page holds the names of the user's projects, skills and memory folders. Never
publish it, upload it or commit it unless the user asks, and then only privately.
