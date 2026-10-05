# AI-fun

Small things for working with AI tools. Skills live in `skills/`, standalone prompts
in `prompts/`.

## Skills

### api-bill

A [Claude Code](https://docs.claude.com/en/docs/claude-code) skill that works out what
your Claude Code sessions would cost if you paid for them on the Claude API, at
Anthropic's list prices. It shows the API cost only: it does not ask for or compare
with your subscription price.

It reads the Claude Code session logs on your own machine (`~/.claude/projects`),
prices every reply at the live per-model rate from Anthropic's public pricing page,
and writes an HTML card to `~/api-bill/` with the total, an itemised split, cost by
model, by project and per day, and the prices it used. When the Claude Code session can publish
Artifacts, the card is also published as a private claude.ai page that only you can see.

**What it touches**

- Reads your local Claude Code logs. They never leave your machine.
- Fetches one public page: Anthropic's pricing page, for the current rates.
- Writes its card and the last fetched prices to `~/api-bill/`.
- The card loads its fonts from Google Fonts when you open it.
- Nothing else is sent anywhere.

**Install**

Copy the `skills/api-bill` folder into `~/.claude/skills/`, so you end up with
`~/.claude/skills/api-bill/SKILL.md`. Python 3 is required. Start a new Claude Code
session.

```sh
git clone https://github.com/ZazaGdev/AI-fun.git
cp -r AI-fun/skills/api-bill ~/.claude/skills/
```

**Use**

In Claude Code, type:

```
/api-bill 7d
/api-bill 30d
/api-bill 6m
```

Time frames: `24h`, `7d`, `2w`, `30d`, `6m`, `1y` or `all`. The default is `30d`.

You can also run the script directly:

```sh
python ~/.claude/skills/api-bill/scripts/apibill.py 30d --open
```

The script opens the card the Windows way and falls back to your default browser on
other systems.

**Or just paste a prompt**

If you would rather not install a skill, [prompts/api-bill-prompt.md](prompts/api-bill-prompt.md)
is a single prompt you paste into Claude Code. It asks Claude to do the same job
from scratch: read your local logs for a time frame, price every reply at the live
list prices and make the same kind of card. The skill runs fixed, tested code; the
prompt has Claude write the code fresh each time, so the card's look can vary.

## Licence

MIT, see [LICENSE](LICENSE).
