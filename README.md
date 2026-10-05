# AI-fun

Small side projects for working with AI tools: Claude Code skills, prompts, scripts
and experiments. Each project has its own folder and its own README.

## Projects

| Project | What it is |
| --- | --- |
| [api-bill](api-bill/) | What your Claude Code sessions would cost on the API. A skill and a paste-in prompt. |

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
