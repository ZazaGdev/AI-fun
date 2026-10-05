# API bill prompt

The same result as the `api-bill` skill, without installing anything. Copy the block
below (the copy button is at its top right), paste it into Claude Code and change the
time frame on its first line if you want another one (`24h`, `7d`, `2w`, `30d`, `6m`,
`1y` or `all`).

## ⬇️ COPY FROM HERE

```text
Time frame: 30d

Work out what my Claude Code sessions in this time frame would cost if I had paid for
them on the Claude API at Anthropic's list prices. Use only Python's standard library
and do it in one script you write to a temporary folder. Do not send my logs or any
results anywhere.

1. **Prices.** Fetch `https://platform.claude.com/docs/en/about-claude/pricing.md`
   (the public pricing page, as Markdown). From the "Model pricing" table take, per
   model, the USD per million tokens for: base input, 5-minute cache write, 1-hour
   cache write, cache read and output. From the "Fast mode pricing" section take the
   fast-mode input and output price per model; fast-mode cache prices are the base
   cache prices scaled by fast input divided by base input. Take the web search price
   per 1,000 searches. Never guess or hard-code a rate. If the page cannot be fetched,
   stop and tell me.

2. **Usage.** Read every `*.jsonl` file under `~/.claude/projects/`, recursively, so
   subagent logs under `<project>/<session>/subagents/` count too and belong to their
   parent project. Each line is JSON. Keep lines whose `message.usage` and
   `message.model` are set, skipping the model `<synthetic>`. A reply can appear in
   several lines: count each `(message.id, requestId)` pair once. Use the line's
   `timestamp` (ISO, UTC) and keep only replies inside the time frame, counted back
   from now (`all` means everything; a month is 30.44 days).

3. **Price each reply** at the rate of the model that wrote it. Map the model id to
   the pricing table by dropping a trailing `[...]`, a leading `claude-`, any
   `anthropic.`/`us.anthropic.` prefix and a date suffix (`claude-haiku-4-5-20251001`
   is Haiku 4.5; old ids like `claude-3-5-haiku` are Haiku 3.5). From `usage`:
   - `input_tokens` at the input rate, `output_tokens` at the output rate,
     `cache_read_input_tokens` at the cache read rate;
   - `cache_creation.ephemeral_5m_input_tokens` and `ephemeral_1h_input_tokens` at the
     5-minute and 1-hour write rates; if both are missing, put all of
     `cache_creation_input_tokens` at the 5-minute rate;
   - `speed == "fast"` means fast-mode rates;
   - `server_tool_use.web_search_requests` at the web search price.
   A model with no list price is left out of the total and listed as unpriced.

4. **Tell me:** the total API cost for the time frame, the number of sessions
   (distinct `sessionId`) and replies, the split by cache reads, cache writes, output,
   fresh input and web searches (tokens and dollars each), cost by model, the top six
   projects (the project is the log's folder name under `~/.claude/projects/`), any
   unpriced models, and the date the prices were fetched.

5. **Card.** Write the same figures as one self-contained HTML page to
   `~/api-bill/api-bill-<timeframe>-<date>.html` and give me the path: the total in
   large type, the itemised split as a receipt, bars for cost by model and by
   project, a bar chart of cost per day, and a table of the prices used. Make it
   readable on a phone and in dark mode. If you can publish Artifacts in this
   session, offer to publish the card as a private page. It shows my project names,
   so never make it public.

Do not compare with my subscription price. This is what the same work would cost on
the API, nothing more.
```

## ⬆️ COPY UNTIL HERE
