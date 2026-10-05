"""What this PC's Claude Code sessions would cost at API list prices.

Reads ~/.claude/projects/**/*.jsonl, prices every assistant reply at the live
per-model rates from Anthropic's pricing page, and writes an HTML
card to ~/api-bill/. Nothing is sent anywhere except the one GET of
the public pricing page.

Usage:
    python apibill.py <timeframe> [--open]
    timeframe: 24h, 7d, 2w, 30d, 6m, 1y or all
"""

import argparse
import datetime as dt
import glob
import json
import os
import re
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

import precache

PRICING_URL = "https://platform.claude.com/docs/en/about-claude/pricing.md"
HOME = Path.home()
OUT = HOME / "api-bill"
PRICES = OUT / "prices.json"
TEMPLATE = Path(__file__).resolve().parent.parent / "card.tpl.html"
DAYS_PER_MONTH = 30.44
TABS = ["24h", "7d", "30d", "all"]


def money(x):
    return f"${x:,.2f}" if x < 100 else f"${x:,.0f}"


# ---------- prices ----------

def key_for(name):
    """'Claude Opus 5.5 ([retired...])' -> 'opus-5-5'."""
    name = re.sub(r"\(.*?\)|<sup>.*?</sup>", "", name).strip()
    name = re.sub(r"^Claude\s+", "", name, flags=re.I)
    return re.sub(r"[\s.]+", "-", name.strip()).lower()


def dollars(cell):
    m = re.search(r"\$([\d.,]+)", cell)
    return float(m.group(1).replace(",", "")) if m else None


def parse_pricing(md):
    models, fast = {}, {}
    sec = md.split("## Model pricing", 1)[1].split("\n## ", 1)[0]
    for line in sec.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 6 or not cells[0].lower().startswith("claude"):
            continue
        vals = [dollars(c) for c in cells[1:]]
        if None in vals:
            continue
        inp, w5, w1, rd, out = vals
        models[key_for(cells[0])] = {"name": re.sub(r"\(.*?\)", "", cells[0]).strip(),
                                     "input": inp, "write_5m": w5, "write_1h": w1, "read": rd, "output": out}
    if "### Fast mode pricing" in md:
        fsec = md.split("### Fast mode pricing", 1)[1].split("\n#", 1)[0]
        for line in fsec.splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) == 3 and cells[0].lower().startswith("claude"):
                inp, out = dollars(cells[1]), dollars(cells[2])
                for part in cells[0].split("/"):
                    if inp and out:
                        fast[key_for(part)] = {"input": inp, "output": out}
    m = re.search(r"\$([\d.]+) per 1,000 searches", md)
    if not models:
        raise ValueError("no model rows found in the pricing table")
    return {"models": models, "fast": fast, "web_search_per_1k": float(m.group(1)) if m else None}


def load_prices():
    """Live prices; on failure the last saved ones, flagged as stale."""
    try:
        req = urllib.request.Request(PRICING_URL, headers={"User-Agent": "api-bill/1.0"})
        md = urllib.request.urlopen(req, timeout=20).read().decode("utf-8")
        p = parse_pricing(md)
        p["fetched"] = dt.date.today().isoformat()
        p["stale"] = False
        OUT.mkdir(parents=True, exist_ok=True)
        PRICES.write_text(json.dumps(p, indent=2), encoding="utf-8")
        return p
    except Exception as e:  # noqa: BLE001 - any failure falls back the same way
        if PRICES.exists():
            p = json.loads(PRICES.read_text(encoding="utf-8"))
            p["stale"] = True
            p["error"] = str(e)[:200]
            return p
        sys.exit(f"Could not fetch {PRICING_URL} ({e}) and no saved prices exist. Try again when online.")


def model_key(model_id):
    """'claude-haiku-4-5-20251001[1m]' -> 'haiku-4-5'; 'claude-3-5-haiku-2024' -> 'haiku-3-5'."""
    m = re.sub(r"\[.*?\]$", "", model_id.lower())
    m = re.sub(r"^(anthropic\.|us\.anthropic\.)?claude-", "", m)
    m = re.sub(r"(-v\d+(:\d+)?)?$", "", m)
    m = re.sub(r"-\d{8}$", "", m)
    old = re.match(r"^(\d+(?:-\d+)?)-([a-z]+)$", m)
    if old:
        m = f"{old.group(2)}-{old.group(1)}"
    return m


# ---------- usage ----------

def read_rows():
    files = glob.glob(str(HOME / ".claude" / "projects" / "**" / "*.jsonl"), recursive=True)
    rows = {}  # one row per reply; its log lines stream, so keep each field's largest value
    for f in files:
        proj = os.path.basename(os.path.dirname(f))
        if proj == "subagents":  # <project>/<session>/subagents/x.jsonl
            proj = Path(f).parents[2].name
        proj = re.sub(r"^[A-Za-z]--", "", proj)  # "C--Users-me-code-app" -> "Users-me-code-app"
        try:
            fh = open(f, encoding="utf-8", errors="ignore")
        except OSError:
            continue
        with fh:
            for line in fh:
                if '"usage"' not in line:
                    continue
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                msg = d.get("message") or {}
                u, model = msg.get("usage"), msg.get("model", "")
                if not u or not model or model == "<synthetic>":
                    continue
                ts = d.get("timestamp")
                if not ts:
                    continue
                cc = u.get("cache_creation") or {}
                w5, w1 = cc.get("ephemeral_5m_input_tokens"), cc.get("ephemeral_1h_input_tokens")
                if w5 is None and w1 is None:
                    w5, w1 = u.get("cache_creation_input_tokens") or 0, 0
                stu = u.get("server_tool_use") or {}
                k = (msg.get("id"), d.get("requestId"))
                counts = {"in": u.get("input_tokens") or 0, "out": u.get("output_tokens") or 0,
                          "rd": u.get("cache_read_input_tokens") or 0, "w5": w5 or 0, "w1": w1 or 0,
                          "search": stu.get("web_search_requests") or 0}
                if k in rows:
                    r = rows[k]
                    for f2, v in counts.items():
                        r[f2] = max(r[f2], v)
                    continue
                rows[k] = {"t": dt.datetime.fromisoformat(ts.replace("Z", "+00:00")), "model": model, "proj": proj,
                           "session": d.get("sessionId"), "fast": u.get("speed") == "fast", **counts}
    return list(rows.values())


def rates_for(row, prices):
    key = model_key(row["model"])
    base = prices["models"].get(key)
    if not base:
        return key, None
    if not row["fast"]:
        return key, base
    f = prices["fast"].get(key)
    if not f:
        return key + " (fast)", None
    scale = f["input"] / base["input"]  # caching multipliers stack on the fast input price
    return key + " (fast)", {"input": f["input"], "output": f["output"], "read": base["read"] * scale,
                              "write_5m": base["write_5m"] * scale, "write_1h": base["write_1h"] * scale}


def parse_frame(s):
    s = s.lower().strip()
    if s in ("all", "ever", "alltime"):
        return None, "All time"
    m = re.fullmatch(r"(\d+)\s*(h|d|w|m|mo|y)", s)
    if not m:
        sys.exit(f"Unknown time frame '{s}'. Use 24h, 7d, 2w, 30d, 6m, 1y or all.")
    n, u = int(m.group(1)), m.group(2)
    days = {"h": n / 24, "d": n, "w": 7 * n, "m": DAYS_PER_MONTH * n, "mo": DAYS_PER_MONTH * n, "y": 365 * n}[u]
    word = {"h": "hour", "d": "day", "w": "week", "m": "month", "mo": "month", "y": "year"}[u]
    return days, f"Last {n} {word}{'s' if n != 1 else ''}"


def summarise(rows, prices, days, label, now, first, est=None):
    since = now - dt.timedelta(days=days) if days else first
    span = days if days else max((now - first).total_seconds() / 86400, 1 / 24)
    split = defaultdict(float)
    tok = defaultdict(int)
    by_model, by_proj, by_day = defaultdict(float), defaultdict(float), defaultdict(float)
    unpriced, sessions, searches = defaultdict(int), set(), 0
    for r in rows:
        if r["t"] < since:
            continue
        key, p = rates_for(r, prices)
        if not p:
            unpriced[r["model"] + (" (fast)" if r["fast"] else "")] += 1
            continue
        parts = {"in": r["in"] * p["input"], "out": r["out"] * p["output"], "rd": r["rd"] * p["read"],
                 "wr": r["w5"] * p["write_5m"] + r["w1"] * p["write_1h"]}
        c = sum(parts.values()) / 1e6
        if r["search"] and prices.get("web_search_per_1k"):
            s = r["search"] * prices["web_search_per_1k"] / 1000
            split["search"] += s
            c += s
            searches += r["search"]
        for k, v in parts.items():
            split[k] += v / 1e6
        by_model[key] += c
        by_proj[r["proj"]] += c
        by_day[r["t"].astimezone().date().isoformat()] += c
        sessions.add(r["session"])
        tok["input"] += r["in"]
        tok["output"] += r["out"]
        tok["read"] += r["rd"]
        tok["write"] += r["w5"] + r["w1"]
        tok["msgs"] += 1
    logged_sessions = len(sessions)
    pre = precache.frame(est, prices, since.astimezone().date().isoformat())
    if pre:  # days with no logs left, estimated from /stats' running totals
        for k, v in pre["split"].items():
            split[k] += v
        for k, v in pre["models"].items():
            by_model[k] += v
        for k, v in pre["tokens"].items():
            tok[k] += v
        searches += pre["searches"]
        pre = {**pre, "cost": round(pre["cost"], 2), "split": {k: round(v, 2) for k, v in pre["split"].items()},
               "models": {k: round(v, 2) for k, v in pre["models"].items()}}
    total = sum(split.values())
    names = {k: v["name"] for k, v in prices["models"].items()}
    return {
        "label": label, "days": span, "cost": round(total, 2),
        "split": {k: round(split[k], 2) for k in ("in", "out", "rd", "wr", "search")},
        "models": {k: round(v, 2) for k, v in sorted(by_model.items(), key=lambda x: -x[1])},
        "model_names": {k: names.get(k.replace(" (fast)", ""), k) + (" fast" if "(fast)" in k else "")
                        for k in by_model},
        "projects": {k: round(v, 2) for k, v in sorted(by_proj.items(), key=lambda x: -x[1])[:6]},
        "daily": sorted([d, round(v, 2)] for d, v in by_day.items()),
        "sessions": logged_sessions + (pre["sessions"] if pre else 0), "tokens": dict(tok), "searches": searches,
        "est": pre,
        "unpriced": dict(sorted(unpriced.items(), key=lambda x: -x[1])),
        "since": since.astimezone().date().isoformat(),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("timeframe", nargs="?", default="30d")
    ap.add_argument("--open", action="store_true", help="open the local card in the browser")
    a = ap.parse_args()

    days, label = parse_frame(a.timeframe)

    prices = load_prices()
    rows = read_rows()
    if not rows:
        sys.exit("No Claude Code usage found in ~/.claude/projects.")
    now = dt.datetime.now(dt.timezone.utc)
    first = first_log = min(r["t"] for r in rows)
    est, est_skip = precache.load(rows, prices, model_key)
    if est:
        first = min(first, dt.datetime.fromisoformat(est["first"]).astimezone())

    frames = {}
    tabs = TABS if a.timeframe.lower() in TABS else [a.timeframe.lower()] + TABS
    for tf in tabs:
        d, lab = parse_frame(tf)
        frames[tf] = summarise(rows, prices, d, lab, now, first, est)
    cur = frames[a.timeframe.lower()]

    seen_keys = {model_key(r["model"]) for r in rows} | set(est["totals"] if est else ())
    data = {
        "frames": frames, "order": list(frames), "current": a.timeframe.lower(),
        "first": first.astimezone().date().isoformat(), "first_log": first_log.astimezone().date().isoformat(),
        "est_skip": est_skip, "generated": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "prices": {"fetched": prices["fetched"], "stale": prices.get("stale", False), "url": PRICING_URL,
                   "models": {k: v for k, v in prices["models"].items() if k in seen_keys},
                   "fast": {k: v for k, v in prices["fast"].items() if k in seen_keys},
                   "web_search_per_1k": prices.get("web_search_per_1k")},
    }
    OUT.mkdir(parents=True, exist_ok=True)
    html = TEMPLATE.read_text(encoding="utf-8").replace("__DATA__", json.dumps(data).replace("</", "<\\/"))
    card = OUT / f"api-bill-{a.timeframe.lower()}-{dt.date.today().isoformat()}.html"
    card.write_text(html, encoding="utf-8")

    lines = [
        f"{cur['label']} (since {cur['since']}): {money(cur['cost'])} at API list prices",
        f"{cur['sessions']} sessions, {cur['tokens'].get('msgs', 0):,} replies.",
        "By model: " + ", ".join(f"{cur['model_names'][k]} {money(v)}" for k, v in cur["models"].items()),
        f"Prices fetched {prices['fetched']}" + (" (STALE: live page could not be fetched, last saved prices used)"
                                                 if prices.get("stale") else " from the live pricing page") + ".",
    ]
    if cur["unpriced"]:
        lines.append("Unpriced (no list price found, left out): "
                     + ", ".join(f"{m} ({n} replies)" for m, n in cur["unpriced"].items()))
    if cur["est"]:
        e = cur["est"]
        lines.append(f"Includes an estimate of {money(e['cost'])} for {e['from']} to {e['to']} from /stats' running "
                     f"totals (session logs for those days are deleted): its token counts divided by {e['ratio']}, "
                     "its overcount measured on days both exist; cache writes at the 5-minute rate, so a lower bound.")
        if e["unpriced"]:
            lines.append("Unpriced in the estimate (no list price found, left out): "
                         + ", ".join(f"{m} ({n:,} tokens)" for m, n in e["unpriced"].items()))
    elif est_skip:
        lines.append(f"No estimate for days whose session logs Claude Code may have deleted: {est_skip}.")
    lines.append(f"Card: {card}")
    print("\n".join(lines))
    if a.open:
        try:
            os.startfile(card)  # type: ignore[attr-defined]
        except AttributeError:
            import webbrowser
            webbrowser.open(card.as_uri())


if __name__ == "__main__":
    main()
