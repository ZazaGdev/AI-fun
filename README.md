# AI-fun

Small, free tools for people who use [Claude Code](https://docs.claude.com/en/docs/claude-code)
every day. Each one looks at something already on your own machine, such as your
session logs or your setup, and shows it back to you in a form you can read at a
glance. Every project comes two ways: a Claude Code skill you install once, and a
single prompt you paste into Claude Code without installing anything. They run
locally, use only Python's standard library, and keep your data on your machine.
Each project has its own folder and its own README.

## Projects

| Project | What it is |
| --- | --- |
| [api-bill](api-bill/) | What your Claude Code sessions would cost on the API at list prices, as a cost card with the split by model, project and day. A skill and a paste-in prompt. |
| [setup-map](setup-map/) | Your whole Claude Code setup as an interactive 3D map: skills, plugins, agents, MCP servers, hooks, rules and memory, plus which projects have a setup of their own. A skill and a paste-in prompt. |

## Adding a project

1. Make one top-level folder named after the project, in lower case with hyphens.
2. Put everything for it inside that folder, using these names where they apply:
   - `README.md`: what it does, how to install and use it, and what it reads, writes
     or sends over the network. Required.
   - `skill/`: a Claude Code skill, installed by copying it to
     `~/.claude/skills/<project>`.
   - `prompt.md`: a prompt to paste into Claude Code or another assistant.
   - anything else the project needs, such as `scripts/`.
3. Add one row to the table above.
4. Keep personal data out: no API keys, no local paths, no private links.

## Licence

MIT, see [LICENSE](LICENSE). It covers every project in this repo.
