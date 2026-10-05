# api-bill

Works out what your [Claude Code](https://docs.claude.com/en/docs/claude-code)
sessions would cost if you paid for them on the Claude API, at Anthropic's list
prices. It shows the API cost only: it does not ask for or compare with your
subscription price.

It reads the Claude Code session logs on your own machine (`~/.claude/projects`),
prices every reply at the live per-model rate from Anthropic's public pricing page,
and writes an HTML card to `~/api-bill/` with the total, an itemised split, cost by
model, by project and per day, and the prices it used. When the Claude Code session
can publish Artifacts, the card is also published as a private claude.ai page that
only you can see.

Two ways to use it:

- [`skill/`](skill/): an installable Claude Code skill. Runs fixed, tested code.
- [`prompt.md`](prompt.md): a single prompt you paste into Claude Code, no install.
  Claude writes the code fresh each time, so the card's look can vary.

## What it touches

- Reads your local Claude Code logs. They never leave your machine.
- Fetches one public page: Anthropic's pricing page, for the current rates.
- Writes its card and the last fetched prices to `~/api-bill/`.
- The card loads its fonts from Google Fonts when you open it.
- Nothing else is sent anywhere.

## Install the skill

Copy the `skill` folder to `~/.claude/skills/api-bill`, so you end up with
`~/.claude/skills/api-bill/SKILL.md`. The folder must be named `api-bill`. Python 3
is required. Start a new Claude Code session.

```sh
git clone https://github.com/ZazaGdev/AI-fun.git
cp -r AI-fun/api-bill/skill ~/.claude/skills/api-bill
```

## Use

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

## Or just paste the prompt

Open [`prompt.md`](prompt.md), copy everything below the line into Claude Code and
set the time frame on its first line. It reads your local logs for that time frame,
prices every reply at the live list prices and makes the same kind of card.
