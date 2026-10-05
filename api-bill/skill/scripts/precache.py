"""Usage from before the oldest kept session log, estimated from /stats' running totals.

Claude Code deletes old session logs, but keeps running totals in
~/.claude/stats-cache.json (what /stats shows). Those totals add up every log line,
and a reply is written as several lines (thinking, text, each tool call) that each
repeat its full usage, so they count tokens several times over. The overcount is
measured on the days where both the cache and the logs exist and divided out.

The cache has per-model totals per token type, but per day only one total per model
(and only for recent months), and its cache writes have no 5-minute/1-hour split.
So the estimate prices writes at the 5-minute rate (a lower bound), splits each
model's days by that model's overall type mix, and spreads usage from before the
per-day totals start over the active days by message count.
"""

import datetime as dt
import json
from collections import defaultdict
from pathlib import Path

STATS = Path.home() / ".claude" / "stats-cache.json"
TYPES = (("in", "inputTokens", "input"), ("out", "outputTokens", "output"),
         ("rd", "cacheReadInputTokens", "read"), ("wr", "cacheCreationInputTokens", "write_5m"))


def day_of(t):
    return t.astimezone().date().isoformat()


def load(rows, prices, model_key):
    """Per-day, per-model raw token counts for the days the logs no longer cover.

    Returns (estimate, None), or (None, why) when there is nothing to estimate from."""
    try:
        c = json.loads(STATS.read_text(encoding="utf-8"))
    except OSError:
        return None, "there is no ~/.claude/stats-cache.json (it appears once /stats has run)"
    except ValueError:
        return None, "~/.claude/stats-cache.json could not be read"
    usage, last = c.get("modelUsage") or {}, c.get("lastComputedDate")
    if not usage or not last:
        return None, "~/.claude/stats-cache.json has no usage totals yet"
    cutoff = min(day_of(r["t"]) for r in rows)  # first day with any log left
    dmt = defaultdict(lambda: defaultdict(int))
    for e in c.get("dailyModelTokens") or []:
        for m, v in (e.get("tokensByModel") or {}).items():
            dmt[e["date"]][model_key(m)] += v
    act = {e["date"]: e for e in c.get("dailyActivity") or []}

    logs = defaultdict(lambda: defaultdict(int))
    for r in rows:
        logs[day_of(r["t"])][model_key(r["model"])] += r["in"] + r["out"] + r["rd"] + r["w5"] + r["w1"]

    # overcount: cache tokens / logged tokens on the full days both cover
    first_full = (dt.date.fromisoformat(cutoff) + dt.timedelta(days=1)).isoformat()
    both = [d for d in dmt if first_full <= d <= last]
    cache_sum = sum(sum(dmt[d].values()) for d in both)
    log_sum = sum(sum(logs[d].values()) for d in both)
    if not cache_sum or not log_sum:
        return None, "no day has both a session log and a /stats total, so its overcount cannot be measured"
    ratio = cache_sum / log_sum

    totals, mix, ids = defaultdict(int), defaultdict(lambda: defaultdict(int)), {}
    for m, u in usage.items():
        k = model_key(m)
        ids.setdefault(k, m)
        for short, field, _ in TYPES:
            mix[k][short] += u.get(field) or 0
        mix[k]["search"] += u.get("webSearchRequests") or 0
    for k in mix:
        totals[k] = sum(mix[k][s] for s, _, _ in TYPES)

    raw = defaultdict(lambda: defaultdict(float))  # day -> model -> raw cache tokens
    for d, models in dmt.items():
        for k, v in models.items():
            if d < cutoff:
                raw[d][k] += v
            elif d == cutoff:  # partly logged: only what the logs miss
                raw[d][k] += max(0.0, v - logs[d].get(k, 0) * ratio)
    dmt_start = min(dmt) if dmt else last
    early = [d for d in act if d < min(dmt_start, cutoff) and d not in dmt]
    weight = sum(act[d].get("messageCount") or 0 for d in early)
    for k, total in totals.items():
        rest = total - sum(dmt[d].get(k, 0) for d in dmt)
        if rest <= 0 or not early:
            continue
        for d in early:
            share = (act[d].get("messageCount") or 0) / weight if weight else 1 / len(early)
            raw[d][k] += rest * share

    sessions = {d: act[d].get("sessionCount") or 0 for d in act if d < cutoff}
    first = min([d for d in raw if any(raw[d].values())] + [cutoff])
    return {"raw": raw, "mix": mix, "totals": totals, "ids": ids, "ratio": ratio, "cutoff": cutoff,
            "first": first, "sessions": sessions, "names": {k: v["name"] for k, v in prices["models"].items()}}, None


def frame(est, prices, since_day):
    """The estimate's share of a time frame starting on since_day (local ISO date)."""
    days = [d for d, v in (est or {}).get("raw", {}).items() if d >= since_day and any(v.values())]
    if not days:
        return None
    ratio, split, tok, models, unpriced, searches = est["ratio"], defaultdict(float), defaultdict(int), \
        defaultdict(float), {}, 0
    for k in est["totals"]:
        raw = sum(est["raw"][d].get(k, 0) for d in days)
        if not raw or not est["totals"][k]:
            continue
        real = raw / ratio
        p = prices["models"].get(k)
        if not p:
            unpriced[est["ids"][k]] = round(real)
            continue
        cost = 0.0
        for short, _, rate in TYPES:
            n = real * est["mix"][k][short] / est["totals"][k]
            tok[{"in": "input", "out": "output", "rd": "read", "wr": "write"}[short]] += round(n)
            split[short] += n * p[rate] / 1e6
            cost += n * p[rate] / 1e6
        s = real * est["mix"][k]["search"] / est["totals"][k]
        if s and prices.get("web_search_per_1k"):
            split["search"] += s * prices["web_search_per_1k"] / 1000
            cost += s * prices["web_search_per_1k"] / 1000
            searches += round(s)
        models[k] += cost
    return {"cost": sum(split.values()), "split": dict(split), "tokens": dict(tok), "models": dict(models),
            "unpriced": unpriced, "searches": searches, "from": min(days), "to": est["cutoff"],
            "ratio": round(ratio, 2),
            "sessions": sum(n for d, n in est["sessions"].items() if d >= since_day)}
