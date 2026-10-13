# Setup map prompt

Two ways to get the setup map without installing the skill. Most people should use
Option 1. Both give exactly the same page as the skill, with your own setup in it.

## Option 1: paste and go (nothing to download)

Copy the whole block below (the copy button is at its top right) and paste it into
Claude Code, from any folder. It is long because it carries the map's two files
inside it; Claude writes them out, checks they are exact, and runs them.

`````text
Paste all of this into Claude Code. It draws my Claude Code setup as a 3D map. Nothing is downloaded.

Below are the two files of the setup-map tool, from github.com/ZazaGdev/AI-fun. Do not write your own version and do not change them in any way: the page must look exactly as these files make it.

1. Write FILE 1 to `~/setup-map/tool/scripts/setup_map.py` and FILE 2 to `~/setup-map/tool/map.tpl.html` (on Windows, ~ is my user folder). Copy the text between each BEGIN line and END line exactly, character for character, without those two lines. Do not shorten, reformat, translate, fix or improve anything. Write each file in one go.

2. Check both copies by running this (python3 on macOS or Linux if python is not found):
   python -c "import hashlib,pathlib;h=pathlib.Path.home()/'setup-map'/'tool';[print(f,'OK' if hashlib.sha256(chr(10).join(l.rstrip() for l in (h/f).read_text(encoding='utf-8').replace(chr(13)+chr(10),chr(10)).strip().split(chr(10))).encode()).hexdigest()==d else 'MISMATCH') for f,d in [('scripts/setup_map.py','6eeab428a13224b94c402b9e50b204bd6a02e1238c1313aea421279241d20466'),('map.tpl.html','878f5689d79181cc1b669328e910db30a9ed06b19576e3c51211c5f12c0fb61d')]]"
   It must print OK for both files. If a file prints MISMATCH, write that file again from the text below and run the check again. Only go on when both say OK.

3. Run: `python ~/setup-map/tool/scripts/setup_map.py --open`
   It reads my global setup in ~/.claude and every project Claude Code has worked in on this computer, from its session history (only folder paths and file dates, never what was said) and ~/.claude.json. It takes names, short descriptions and counts only, sends nothing anywhere, writes ~/setup-map/setup-map.html and opens it.

4. Tell me the page path and the lines the script printed. The page shows my project, skill and memory folder names, so never publish or upload it unless I ask.

----- BEGIN FILE 1: setup_map.py -----
"""Draw your Claude Code setup as one 3D page: read ~/.claude and every project Claude
Code has been opened in, then write setup-map.html with the setup's shape baked in.

Reads names, kinds, one-line frontmatter descriptions and counts only. Never copies
settings values, env, commands, URLs or file contents beyond a frontmatter description.
Sends nothing anywhere. Writes one HTML file.

Usage:
  python setup_map.py [PROJECTS_DIR] [--out FILE] [--open] [--projects-json FILE]

Projects are every folder listed in ~/.claude.json (where Claude Code was opened),
skipping folders that are gone and git worktrees. A folder inside another project is
part of it, unless it has a .claude folder of its own.

PROJECTS_DIR  optional: a folder to look for more projects in, and its subfolders
              (3 levels deep).
--out         where to write the page. Default: ~/setup-map/setup-map.html
--open        open the page in the default browser afterwards.
--projects-json  a JSON file listing more projects, read if it is there:
                 {"projects": [{"name": ..., "path": ...}], "scanRoots": [folder, ...]}
                 Every folder in a scan root counts as a project.
"""
import argparse
import datetime
import glob
import json
import os
import re
import sys
import tempfile
import webbrowser
from pathlib import Path

HOME = os.path.expanduser("~")
CLAUDE = os.path.join(HOME, ".claude")
TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "map.tpl.html")
DESC_MAX = 2000  # full descriptions; the page folds long ones behind Read more
DEPTH = 3
SCRIPT = re.compile(r"[\w\-.]+\.(?:py|sh|js|mjs|cjs|ts|ps1|cmd|bat)")
SKIP = {"node_modules", "$recycle.bin", "system volume information", "worktrees", "dist", "build",
        "venv", "__pycache__", "library", "appdata", "applications", "program files", "program files (x86)", "windows"}
sources, unread = {}, []


def frontmatter(path):
    try:
        text = open(path, encoding="utf-8", errors="replace").read(4000)
    except OSError:
        return {}
    m = re.match(r"﻿?---\s*\n(.*?)\n---", text, re.S)
    out = {}
    if m:
        key = None
        for line in m.group(1).splitlines():
            if line.startswith((" ", "\t")) and key:
                # continuation of a folded (>) or literal (|) value
                out[key] = (out[key] + " " + line.strip()).strip()
                continue
            k, _, v = line.partition(":")
            if not v:
                key = None
                continue
            key, v = k.strip(), v.strip().strip('"')
            out[key] = "" if v in (">", "|", ">-", "|-") else v
    return out


def short(text):
    text = text or ""
    return text if len(text) <= DESC_MAX else text[: DESC_MAX - 1].rstrip() + "…"


def load_json(path, label=None):
    try:
        return json.load(open(path, encoding="utf-8-sig"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        unread.append(f"{label or path}: {type(e).__name__}")
        return {}


def real(p):
    try:
        return os.path.realpath(p).replace("\\", "/").rstrip("/").lower()
    except OSError:
        return p.lower()


def slug(path):
    """The folder name Claude Code gives a project under ~/.claude/projects."""
    return re.sub(r"[^A-Za-z0-9]", "-", os.path.abspath(path))


def md_items(folder, desc=None):
    return [{"name": os.path.basename(p)[:-3], "desc": short(frontmatter(p).get("description") or desc)}
            for p in sorted(glob.glob(os.path.join(folder, "*.md")))]


def hooks_from(cfg, origin):
    out = []
    for event, groups in (cfg.get("hooks") or {}).items():
        for g in groups or []:
            for h in g.get("hooks", []):
                names = SCRIPT.findall(h.get("command", "") or "")
                out.append({"name": names[-1] if names else f"inline {event} hook",
                            "desc": f"{origin}, runs on {event}", "event": event})
    return out


def merge(items):
    """One node per name; where it comes from is joined into its description."""
    out = {}
    for i in items:
        if i["name"] in out:
            if i["desc"] not in out[i["name"]]["desc"]:
                out[i["name"]]["desc"] += "; " + i["desc"]
            out[i["name"]]["count"] = out[i["name"]].get("count", 1) + i.get("count", 1)
        else:
            out[i["name"]] = dict(i)
    return list(out.values())


def looks_like_project(path):
    return any(os.path.exists(os.path.join(path, m)) for m in (".git", ".claude", "CLAUDE.md", ".mcp.json"))


def nested_name(parent, path):
    """A project inside another project, named by where it sits in it."""
    rel = os.path.relpath(os.path.realpath(path), os.path.realpath(parent["path"]))
    return parent["name"] + "/" + rel.replace(os.sep, "/")


def read_history():
    """One entry per folder under ~/.claude/projects: the working folder its sessions ran in,
    how many sessions there are and when the newest one was last written. Takes only the
    `cwd` field of a session's first lines and file times; never reads what was said."""
    out = []
    for d in sorted(glob.glob(os.path.join(CLAUDE, "projects", "*"))):
        files = glob.glob(os.path.join(d, "*.jsonl"))
        if not files:
            continue
        cwd = None
        for f in sorted(files, key=os.path.getmtime, reverse=True):
            try:
                with open(f, encoding="utf-8", errors="replace") as fh:
                    for _, line in zip(range(40), fh):
                        try:
                            cwd = json.loads(line).get("cwd")
                        except (ValueError, AttributeError):
                            continue
                        if cwd:
                            break
            except OSError:
                continue
            if cwd:
                break
        out.append({"slug": os.path.basename(d), "cwd": cwd, "sessions": len(files),
                    "last": max(os.path.getmtime(f) for f in files)})
    return out


def find_projects(root, projects_json, user_json, history):
    """Every folder Claude Code has worked in (its session history and the projects list in
    ~/.claude.json), plus a folder the user passes and its subfolders, plus an optional
    projects list. Returns the projects and a function giving the project a path belongs to."""
    found, seen = [], set()
    skip = {real(HOME), real(CLAUDE)}
    temp = real(tempfile.gettempdir())

    def add(path, name=None):
        if not path or not os.path.isdir(path):
            return
        r = real(path)
        if r in seen or r in skip or os.path.dirname(r) == r or r.startswith((real(CLAUDE) + "/", temp + "/")):
            return  # the home folder, a drive root, ~/.claude and throwaway temp folders are not projects
        if os.path.isfile(os.path.join(path, ".git")):
            return  # a git worktree: a second checkout of a project already on the map
        seen.add(r)
        found.append({"name": name or os.path.basename(os.path.abspath(path).rstrip("\\/")) or path, "path": path, "real": r})

    for h in history:
        add(h["cwd"])
    for path in user_json.get("projects") or {}:
        add(path)
    sources["projects"] = ("every folder Claude Code has worked in: the working folder of the sessions under "
                           "~/.claude/projects (paths and file times only) and the projects list in ~/.claude.json")
    if root:
        add(root)
        for top, dirs, _ in os.walk(root):
            depth = os.path.relpath(top, root).count(os.sep) + (top != root)
            dirs[:] = sorted((d for d in dirs if d.lower() not in SKIP and not d.startswith(".")), key=str.lower) if depth < DEPTH else []
            if top != root and looks_like_project(top):
                add(top)
        sources["projects"] += f"; plus folders under {root} ({DEPTH} levels deep) with a .git, .claude, CLAUDE.md or .mcp.json"
    if projects_json:
        cfg = load_json(projects_json, "projects list")
        if cfg:
            for scan in cfg.get("scanRoots") or []:
                try:
                    for d in sorted(os.scandir(scan), key=lambda d: d.name.lower()):
                        if d.is_dir() and not d.name.startswith("."):
                            add(d.path, d.name)
                except OSError:
                    unread.append(f"scan root {scan}: missing")
            for p in cfg.get("projects", []):
                add(p.get("path", ""), p.get("name"))
            sources["projects"] += f"; plus the projects listed in {projects_json}"

    # a folder inside another project's git repo is part of it, unless it has a setup of its own;
    # a plain folder that only holds projects (no .git) does not swallow them, nor does a repo hold another repo
    found.sort(key=lambda p: len(p["real"]))
    projects = []
    is_repo = lambda p: os.path.isdir(os.path.join(p["path"], ".git"))
    for p in found:
        parent = None if is_repo(p) else next(
            (q for q in reversed(projects) if is_repo(q) and p["real"].startswith(q["real"] + "/")), None)
        if parent and not os.path.isdir(os.path.join(p["path"], ".claude")):
            continue
        if parent:
            p["name"] = nested_name(parent, p["path"])
        projects.append(p)

    def owner(path):
        r = real(path) if path else ""
        return next((q for q in sorted(projects, key=lambda q: -len(q["real"]))
                     if r == q["real"] or r.startswith(q["real"] + "/")), None)

    # activity: sessions and last use, a worktree's or subfolder's counting for its project
    for h in history:
        q = owner(h["cwd"])
        if q:
            q["sessions"] = q.get("sessions", 0) + h["sessions"]
            q["lastTs"] = max(q.get("lastTs", 0), h["last"])
    projects.sort(key=lambda p: p["name"].lower())
    return projects, owner


def own_setup(path, name, user_json):
    cl = os.path.join(path, ".claude")
    own = {}
    # an agent file declares itself in front matter; reference docs kept beside agents do not
    own["agents"] = [{"name": fm["name"], "desc": short(fm.get("description"))}
                     for fm in (frontmatter(f) for f in sorted(glob.glob(os.path.join(cl, "agents", "**", "*.md"), recursive=True)))
                     if fm.get("name")]
    own["skills"] = [{"name": frontmatter(f).get("name") or os.path.basename(os.path.dirname(f)), "desc": short(frontmatter(f).get("description"))}
                     for f in sorted(glob.glob(os.path.join(cl, "skills", "*", "SKILL.md")))]
    own["commands"] = [{"name": "/" + os.path.relpath(f, os.path.join(cl, "commands"))[:-3].replace(os.sep, ":"), "desc": short(frontmatter(f).get("description"))}
                       for f in sorted(glob.glob(os.path.join(cl, "commands", "**", "*.md"), recursive=True))]
    own["hooks"] = merge(hooks_from(load_json(os.path.join(cl, "settings.json"), f"{name}/.claude/settings.json"), "Project hook")
                         + hooks_from(load_json(os.path.join(cl, "settings.local.json"), f"{name}/.claude/settings.local.json"), "Project hook, local"))
    for h in own["hooks"]:
        h.pop("count", None)
    mcps = [{"name": srv, "desc": "Shared in .mcp.json"} for srv in (load_json(os.path.join(path, ".mcp.json")).get("mcpServers") or {})]
    for k, v in (user_json.get("projects") or {}).items():
        if real(k) == real(path):
            mcps += [{"name": srv, "desc": "Local to this project"} for srv in (v.get("mcpServers") or {})]
    own["mcp"] = merge(mcps)
    for m in own["mcp"]:
        m.pop("count", None)
    rules = [{"name": "CLAUDE.md", "desc": "Project instructions"}] if os.path.exists(os.path.join(path, "CLAUDE.md")) else []
    if os.path.exists(os.path.join(cl, "CLAUDE.md")):
        rules.append({"name": ".claude/CLAUDE.md", "desc": "Project instructions"})
    rules += [{"name": os.path.basename(f)[:-3], "desc": short(frontmatter(f).get("description") or "Project rule file")}
              for f in sorted(glob.glob(os.path.join(cl, "rules", "*.md")))]
    own["rules"] = rules
    return {k: v for k, v in own.items() if v}


def collect(root=None, projects_json=None):
    settings = load_json(os.path.join(CLAUDE, "settings.json"), "~/.claude/settings.json")
    user_json = load_json(os.path.join(HOME, ".claude.json"), "~/.claude.json")
    history = read_history()
    projects, owner = find_projects(root, projects_json, user_json, history)

    # ---- skills, agents, commands, output styles ----
    skills = []
    for p in sorted(glob.glob(os.path.join(CLAUDE, "skills", "*", "SKILL.md"))):
        fm = frontmatter(p)
        skills.append({"name": fm.get("name") or os.path.basename(os.path.dirname(p)), "desc": short(fm.get("description"))})
    sources["skills"] = "~/.claude/skills/*/SKILL.md"
    agents = md_items(os.path.join(CLAUDE, "agents"))
    sources["agents"] = "~/.claude/agents"
    commands = [dict(i, name="/" + i["name"]) for i in md_items(os.path.join(CLAUDE, "commands"))]
    sources["commands"] = "~/.claude/commands"
    styles = md_items(os.path.join(CLAUDE, "output-styles"), "Output style")
    active = settings.get("outputStyle")
    for s in styles:
        if s["name"] == active:
            s["desc"] = "Active. " + s["desc"]
    sources["styles"] = "~/.claude/output-styles (active one from settings.json)"

    # ---- rules: global CLAUDE.md, what it imports, rules/*.md ----
    rules = []
    gclaude = os.path.join(CLAUDE, "CLAUDE.md")
    if os.path.exists(gclaude):
        rules.append({"name": "CLAUDE.md", "desc": "Global instructions loaded in every session"})
        for imp in re.findall(r"^@(\S+)", open(gclaude, encoding="utf-8", errors="replace").read(), re.M):
            rules.append({"name": os.path.basename(imp), "desc": "Imported by the global CLAUDE.md"})
    rules += md_items(os.path.join(CLAUDE, "rules"), "Rule file loaded in every session")
    sources["rules"] = "~/.claude/CLAUDE.md (and its @imports) + ~/.claude/rules"

    # ---- memory: one node per project memory folder, with its file count ----
    by_slug = {slug(p["path"]): p["name"] for p in projects}
    by_slug.update({h["slug"]: owner(h["cwd"])["name"] for h in history if owner(h["cwd"])})
    home_slug = slug(HOME) + "-"
    memory = {}
    for d in sorted(glob.glob(os.path.join(CLAUDE, "projects", "*", "memory"))):
        files = {os.path.basename(f) for f in glob.glob(os.path.join(d, "*.md"))} - {"MEMORY.md"}
        if files:
            s = os.path.basename(os.path.dirname(d))
            # the same project reached by another path (a second drive, a symlink) still ends in its folder name
            tail = max((p["name"] for p in projects if s.endswith("-" + re.sub(r"[^A-Za-z0-9]", "-", p["name"]))), key=len, default=None)
            name = by_slug.get(s) or tail or re.sub(r"^[A-Za-z]--", "", s[len(home_slug):] if s.startswith(home_slug) else s).lstrip("-") or s
            memory.setdefault(name, set()).update(files)
    memory = [{"name": k, "desc": f"{len(v)} memory file{'s' * (len(v) != 1)}", "count": len(v)} for k, v in memory.items()]
    sources["memory"] = "~/.claude/projects/*/memory/*.md (file counts only)"

    # ---- plugins: enabled ones, at their installed version ----
    installed = load_json(os.path.join(CLAUDE, "plugins", "installed_plugins.json"), "installed_plugins.json")
    installed = installed.get("plugins", installed)
    plugins, mcp, hooks = [], [], hooks_from(settings, "Global settings")
    for key, on in (settings.get("enabledPlugins") or {}).items():
        if not on:
            continue
        name, _, market = key.partition("@")
        recs = installed.get(key) or []
        rec = next((r for r in recs if r.get("scope") == "user"), recs[0] if recs else None)
        root_dir = rec and rec.get("installPath")
        if not root_dir or not os.path.isdir(root_dir):
            unread.append(f"plugin {key}: enabled but not found on disk")
            plugins.append({"name": name, "market": market, "desc": "", "skills": []})
            continue
        meta = load_json(os.path.join(root_dir, ".claude-plugin", "plugin.json"))
        psk = sorted({os.path.basename(os.path.dirname(p)) for p in glob.glob(os.path.join(root_dir, "skills", "*", "SKILL.md"))})
        pag = sorted(os.path.basename(p)[:-3] for p in glob.glob(os.path.join(root_dir, "agents", "*.md")))
        pcm = sorted(os.path.basename(p)[:-3] for p in glob.glob(os.path.join(root_dir, "commands", "*.md")))
        mj = load_json(os.path.join(root_dir, ".mcp.json"))
        for srv in (mj.get("mcpServers") or mj):
            if isinstance(srv, str):
                mcp.append({"name": srv, "desc": f"From the {name} plugin", "scope": "plugin"})
        hooks += hooks_from(load_json(os.path.join(root_dir, "hooks", "hooks.json")), f"From the {name} plugin")
        plugins.append({"name": name, "market": market, "desc": short(meta.get("description")),
                        "skills": psk, "agents": pag, "commands": pcm})
    sources["plugins"] = "enabledPlugins in settings.json, read at the install path in plugins/installed_plugins.json"

    # ---- MCP servers: user scope, local scope per project, project .mcp.json, plugins ----
    def add_mcp(name, desc, scope):
        for m in mcp:
            if m["name"] == name:
                if desc not in m["desc"]:
                    m["desc"] += "; " + desc
                return
        mcp.append({"name": name, "desc": desc, "scope": scope})

    for srv in user_json.get("mcpServers") or {}:
        add_mcp(srv, "User scope, every project", "user")
    for path, v in (user_json.get("projects") or {}).items():
        folder = os.path.basename(path.rstrip("/\\"))
        for srv in v.get("mcpServers") or {}:
            add_mcp(srv, f"Local to {folder}", "local")

    # ---- each project's own setup ----
    for p in projects:
        for srv in (load_json(os.path.join(p["path"], ".mcp.json"), f"{p['name']}/.mcp.json").get("mcpServers") or {}):
            add_mcp(srv, f"Shared in {p['name']}/.mcp.json", "project")
        hooks += hooks_from(load_json(os.path.join(p["path"], ".claude", "settings.json"), f"{p['name']}/.claude/settings.json"), f"Project {p['name']}")
        p["own"] = own_setup(p["path"], p["name"], user_json)
    sources["mcp"] = "~/.claude.json (user and per-project local), each project's .mcp.json, enabled plugins' .mcp.json"
    hooks = merge(hooks)
    sources["hooks"] = "settings.json, enabled plugins' hooks/hooks.json, each project's .claude/settings.json"
    sources["own"] = ("per project: .claude/agents/**/*.md, .claude/skills/*/SKILL.md, .claude/commands/**/*.md, "
                      ".claude/settings(.local).json hooks, .mcp.json and ~/.claude.json local MCP servers, CLAUDE.md and .claude/rules/*.md")
    unread.append("claude.ai connectors: account-level, not stored on this computer, so not shown")

    for p in projects:
        p["desc"] = "Project"
        p["sessions"] = p.get("sessions", 0)
        if p.get("lastTs"):
            p["last"] = datetime.date.fromtimestamp(p["lastTs"]).isoformat()
        if not p["own"]:
            del p["own"]
        for k in ("path", "real", "lastTs"):
            p.pop(k, None)

    return {
        "title": "Claude Code",
        "model": settings.get("model", ""),
        "outputStyle": active or "",
        "kinds": {"skills": skills, "plugins": plugins, "agents": agents, "mcp": mcp, "hooks": hooks,
                  "commands": commands, "styles": styles, "rules": rules, "memory": memory, "projects": projects},
        "sources": sources,
        "unread": unread,
    }


def render(data, out):
    page = open(TEMPLATE, encoding="utf-8").read()
    safe = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    page = page.replace("/*SETUP_DATA*/null", safe, 1)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(page)


def main():
    ap = argparse.ArgumentParser(description="Draw your Claude Code setup as one 3D HTML page.")
    ap.add_argument("projects", nargs="?", help="a folder to look for more projects in, with its subfolders")
    ap.add_argument("--out", default=os.path.join(HOME, "setup-map", "setup-map.html"))
    ap.add_argument("--open", action="store_true", help="open the page afterwards")
    ap.add_argument("--projects-json", help="JSON file listing more projects; read if present")
    a = ap.parse_args()
    root = a.projects and os.path.abspath(os.path.expanduser(a.projects))
    if root and not os.path.isdir(root):
        sys.exit(f"Not a folder: {root}")
    if not os.path.isdir(CLAUDE):
        sys.exit(f"No Claude Code setup found at {CLAUDE}")
    data = collect(root, a.projects_json)
    render(data, a.out)
    sys.stdout.reconfigure(encoding="utf-8")
    print(os.path.abspath(a.out))
    k = data["kinds"]
    print(", ".join(f"{len(v)} {key}" for key, v in k.items()))
    print(f"{sum(1 for p in k['projects'] if p.get('own'))} of {len(k['projects'])} projects have a setup of their own")
    for u in data["unread"]:
        print("not shown:", u)
    if a.open:
        webbrowser.open(Path(os.path.abspath(a.out)).as_uri())


if __name__ == "__main__":
    main()
----- END FILE 1 -----

----- BEGIN FILE 2: map.tpl.html -----
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Claude Code Setup Map</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@500;600;700;800&family=Space+Grotesk:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root {
  --bg: #02030a;
  --ink: #e8f1ff;
  --dim: #8a98b8;
  --glass: rgba(10, 16, 34, 0.62);
  --line: rgba(120, 170, 255, 0.22);
  --head: 'Orbitron', 'Segoe UI', sans-serif;
  --body: 'Space Grotesk', 'Segoe UI', sans-serif;
}
* { box-sizing: border-box; }
html, body { margin: 0; height: 100%; overflow: hidden; background: var(--bg); color: var(--ink); font-family: var(--body); }
canvas { display: block; cursor: grab; }
.hud { position: fixed; inset: 0; pointer-events: none; z-index: 10; }
.hud > * { pointer-events: auto; }
.hud > .strip { pointer-events: none; }
.strip > * { pointer-events: auto; }
body.clean .hud > *:not(.tip) { opacity: 0; pointer-events: none; }
.hud > * { transition: opacity .4s; }

.brand { position: absolute; top: 24px; left: 28px; pointer-events: none; }
.brand .src { pointer-events: auto; margin-top: 8px; padding: 0; border: 0; background: none; color: #9fe8ff; font: 500 12px var(--body); letter-spacing: .04em; text-decoration: underline; text-underline-offset: 3px; cursor: pointer; opacity: .8; }
.eyebrow { font: 600 11px/1 var(--head); letter-spacing: .28em; color: var(--dim); text-transform: uppercase; }
.brand h1 {
  margin: 10px 0 6px; font: 800 clamp(28px, 4.2vw, 54px)/1 var(--head); letter-spacing: .04em;
  background: linear-gradient(90deg, #fff 0%, #9fe8ff 45%, #ff9a6b 100%); -webkit-background-clip: text; background-clip: text; color: transparent;
  filter: drop-shadow(0 0 18px rgba(80, 200, 255, .45));
}
.brand .meta { color: var(--dim); font-size: 13px; letter-spacing: .04em; }

.strip {
  position: absolute; left: 16px; right: 16px; bottom: 22px;
  display: flex; gap: 10px; flex-wrap: wrap; justify-content: center;
}
.chip {
  --c: #fff; position: relative; min-width: 118px; padding: 10px 14px 12px; text-align: left; cursor: pointer;
  background: var(--glass); color: var(--ink); border: 1px solid color-mix(in srgb, var(--c) 45%, transparent);
  border-radius: 12px; backdrop-filter: blur(10px); font-family: var(--body);
  box-shadow: 0 0 24px -8px var(--c), inset 0 0 18px -12px var(--c); transition: transform .2s, box-shadow .2s;
}
.chip:hover { transform: translateY(-3px); box-shadow: 0 0 34px -4px var(--c), inset 0 0 22px -10px var(--c); }
.chip .n { display: block; font: 700 24px/1 var(--head); color: var(--c); text-shadow: 0 0 12px var(--c); }
.chip .l { display: block; margin-top: 4px; font-size: 12px; color: var(--dim); letter-spacing: .06em; }

.panel {
  --c: #fff; position: absolute; top: 24px; right: 24px; bottom: 130px; width: min(360px, calc(100vw - 32px));
  padding: 22px 20px; overflow: auto; background: var(--glass); backdrop-filter: blur(14px);
  border: 1px solid color-mix(in srgb, var(--c) 40%, transparent); border-radius: 16px;
  box-shadow: 0 0 40px -12px var(--c);
}
.panel[hidden], .tip[hidden] { display: none; }
.panel h2 { margin: 8px 0 14px; font: 700 22px/1.1 var(--head); color: var(--c); text-shadow: 0 0 14px var(--c); }
.panel ul { list-style: none; margin: 0; padding: 0; }
.panel li { padding: 10px 0; border-top: 1px solid var(--line); }
.panel li.on { background: color-mix(in srgb, var(--c) 14%, transparent); margin: 0 -10px; padding: 10px; border-radius: 8px; }
.panel li b { display: block; font-size: 14px; }
.panel li span { display: block; margin-top: 3px; color: var(--dim); font-size: 12.5px; line-height: 1.4; }
.panel li em { display: block; margin-top: 4px; color: var(--c); font-size: 12px; font-style: normal; opacity: .85; }
.panel .x { position: absolute; top: 12px; right: 12px; width: 30px; height: 30px; border: 0; border-radius: 8px; background: rgba(255,255,255,.06); color: var(--ink); font-size: 18px; cursor: pointer; }

.tip {
  --c: #fff; position: absolute; max-width: 280px; padding: 9px 12px; pointer-events: none;
  background: rgba(6, 10, 24, .88); border: 1px solid var(--c); border-radius: 10px; box-shadow: 0 0 18px -4px var(--c);
}
.tip b { display: block; color: var(--c); font: 600 13px/1.2 var(--head); letter-spacing: .03em; }
.tip span { display: block; margin-top: 4px; color: var(--dim); font-size: 12px; line-height: 1.35; }

.hint { position: absolute; top: 28px; left: 50%; transform: translateX(-50%); color: var(--dim); font-size: 11px; letter-spacing: .12em; text-transform: uppercase; opacity: .7; white-space: nowrap; }
.back { position: absolute; top: 24px; right: 24px; }
.back a { color: var(--dim); font: 600 11px var(--head); letter-spacing: .2em; text-decoration: none; }

.label3d { font: 600 12px var(--head); letter-spacing: .14em; text-transform: uppercase; color: #fff; text-shadow: 0 0 10px var(--c), 0 0 2px #000; pointer-events: none; white-space: nowrap; }
.label3d small { display: block; text-align: center; font: 500 10px var(--body); letter-spacing: .1em; color: var(--c); }

@media (max-width: 760px) {
  .hint { display: none; }
  .chip { min-width: 0; padding: 8px 10px; }
  .chip .n { font-size: 18px; }
  .panel { top: 16px; right: 16px; bottom: auto; height: 52vh; }
}

@media (max-width: 1100px) { .hint { display: none; } }
.panel > .eyebrow:first-of-type { padding-right: 38px; }

/* Global / By project switch, top centre */
.viewtoggle {
  position: absolute; top: 20px; left: 50%; transform: translateX(-50%); z-index: 2;
  display: flex; padding: 5px; gap: 4px; border-radius: 999px;
  background: rgba(10, 16, 34, .72); border: 1px solid rgba(120, 170, 255, .28); backdrop-filter: blur(12px);
  box-shadow: 0 0 30px -10px rgba(120, 190, 255, .6);
}
.viewtoggle button {
  min-width: 132px; min-height: 48px; padding: 0 22px; border: 0; border-radius: 999px; cursor: pointer;
  background: transparent; color: var(--dim); font: 700 14px var(--head); letter-spacing: .12em; text-transform: uppercase;
  transition: background .35s, color .35s, box-shadow .35s;
}
.viewtoggle button:hover { color: var(--ink); }
.viewtoggle button[aria-selected="true"] { color: #02030a; background: linear-gradient(90deg, #9fe8ff, #ffb48f); box-shadow: 0 0 22px -4px #9fe8ff; }
.viewtoggle ~ .hint, .hud:has(.viewtoggle) .hint { top: 84px; }
@media (max-width: 760px) {
  .viewtoggle { top: 12px; width: calc(100vw - 32px); }
  .viewtoggle button { flex: 1; min-width: 0; padding: 0 8px; font-size: 12px; }
  .hud:has(.viewtoggle) .brand { top: 82px; left: 16px; }
  .hud:has(.viewtoggle) .panel { top: 76px; }
}

/* By project: counts under each project name, and the project panel's counts */
.plabel { font-size: 11px; }
.plabel small { margin-top: 2px; font-size: 10px; letter-spacing: .04em; text-transform: none; color: var(--dim); }
.pcounts { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 4px; }
.pcounts span { padding: 8px 10px; border-radius: 10px; background: rgba(255, 255, 255, .04); border: 1px solid color-mix(in srgb, var(--k) 35%, transparent); color: var(--dim); font-size: 11px; }
.pcounts b { display: block; color: var(--k); font: 700 18px var(--head); }
.klabel {
  --k: #fff; display: flex; align-items: baseline; gap: 4px; padding: 2px 8px 3px; border-radius: 999px; white-space: nowrap; pointer-events: none;
  background: rgba(4, 8, 20, .82); border: 1px solid color-mix(in srgb, var(--k) 55%, transparent);
  color: #e8f1ff; font: 600 11px var(--body); letter-spacing: .02em;
}
.klabel b { color: var(--k); font: 800 15px/1 var(--head); }

/* search, under the view toggle */
.search { position: absolute; top: 86px; left: 50%; transform: translateX(-50%); width: min(420px, calc(100vw - 32px)); z-index: 3; }
.search input {
  width: 100%; height: 44px; padding: 0 16px; border-radius: 999px; outline: none;
  background: rgba(10, 16, 34, .72); border: 1px solid rgba(120, 170, 255, .28); color: var(--ink);
  font: 500 15px var(--body); backdrop-filter: blur(12px);
}
.search input:focus { border-color: #9fe8ff; box-shadow: 0 0 22px -6px #9fe8ff; }
.search input::placeholder { color: var(--dim); }
.sresults { list-style: none; margin: 6px 0 0; padding: 6px; border-radius: 14px; background: rgba(8, 12, 28, .94); border: 1px solid rgba(120, 170, 255, .25); backdrop-filter: blur(14px); }
.sresults[hidden] { display: none; }
.sresults button {
  display: flex; align-items: baseline; gap: 8px; width: 100%; min-height: 40px; padding: 8px 10px; border: 0; border-radius: 10px;
  background: transparent; color: var(--ink); text-align: left; cursor: pointer; font: 500 14px var(--body);
}
.sresults button:hover, .sresults button.top { background: rgba(159, 232, 255, .08); }
.sresults b { font-weight: 600; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.stag { flex: none; padding: 2px 8px; border-radius: 999px; font-size: 11px; color: var(--k); border: 1px solid color-mix(in srgb, var(--k) 50%, transparent); }
.swhere { flex: none; color: var(--dim); font-size: 11px; max-width: 34%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.hud:has(.search) .hint { top: auto; bottom: 104px; }
@media (max-width: 760px) {
  .search { top: 80px; }
  .hud:has(.search) .brand { top: 134px; }
  .hud:has(.search) .panel { top: 132px; height: auto; bottom: 150px; }
}

/* long descriptions fold to four lines; Read more opens the whole text in a centred dialog */
.panel li .desc { display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 4; line-clamp: 4; overflow: hidden; }
.panel li .more {
  margin-top: 4px; padding: 4px 0; min-height: 28px; border: 0; background: none; cursor: pointer;
  color: var(--c); font: 600 12px var(--body); letter-spacing: .03em;
}
.panel li .more:hover { text-decoration: underline; text-underline-offset: 3px; }
.panel li .more:focus-visible { outline: 2px solid var(--c); outline-offset: 2px; border-radius: 4px; }
.tip span { display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 4; line-clamp: 4; overflow: hidden; }

.modal-back { position: fixed; inset: 0; z-index: 50; display: grid; place-items: center; padding: 16px; background: rgba(2, 3, 10, .62); backdrop-filter: blur(3px); animation: fadeIn .2s ease-out; }
.modal {
  --c: #fff; position: relative; width: min(520px, 100%); max-height: min(80vh, 640px); overflow: auto; padding: 22px 22px 20px;
  background: linear-gradient(160deg, rgba(14, 22, 46, .97), rgba(6, 10, 24, .97)); color: var(--ink);
  border: 1px solid color-mix(in srgb, var(--c) 50%, transparent); border-radius: 16px; box-shadow: 0 0 50px -12px var(--c);
}
.modal .x { position: absolute; top: 12px; right: 12px; width: 34px; height: 34px; border: 0; border-radius: 8px; background: rgba(255,255,255,.08); color: var(--ink); font-size: 20px; cursor: pointer; }
.modal .mtags { display: flex; align-items: center; gap: 8px; padding-right: 44px; }
.modal h3 { margin: 12px 0 10px; font: 700 20px/1.2 var(--head); color: var(--c); word-break: break-word; }
.modal p { margin: 0; color: #c9d4ec; font-size: 15px; line-height: 1.55; white-space: pre-wrap; }
@keyframes fadeIn { from { opacity: 0; } }
/* the renderer sets each label's z-index every frame; a focused project's pills must win */
.klabel.focus { z-index: 100000 !important; box-shadow: 0 0 14px -2px var(--k); }
</style>
<script>window.SETUP_DATA = /*SETUP_DATA*/null;</script>
<script type="importmap">
{ "imports": {
  "three": "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js",
  "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/"
} }
</script>
</head>
<body>
<script type="module">
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { CSS2DRenderer, CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';
// Shared pieces: data, palette, scene, bloom, HUD.






const KINDS = [
  { key: 'skills', label: 'Skills', color: '#38e1ff' },
  { key: 'plugins', label: 'Plugins', color: '#a78bfa' },
  { key: 'agents', label: 'Agents', color: '#ff4fd8' },
  { key: 'mcp', label: 'MCP servers', color: '#3dffa8' },
  { key: 'hooks', label: 'Hooks', color: '#ffb547' },
  { key: 'commands', label: 'Commands', color: '#ff6b6b' },
  { key: 'styles', label: 'Output styles', color: '#e6ff5c' },
  { key: 'rules', label: 'Rules', color: '#dbe4ff' },
  { key: 'memory', label: 'Memory', color: '#ff9ad5' },
  { key: 'projects', label: 'Projects', color: '#4f7dff' },
];
const CLAUDE_COLOR = '#ff8a5c';

async function loadSetup() {
  return window.SETUP_DATA;
}

function kindsWithItems(data) {
  return KINDS.map(k => ({ ...k, items: data.kinds[k.key] || [] })).filter(k => k.items.length);
}

function makeStage({ bloom = 1.1, radius = 0.55, threshold = 0.08, camPos = [0, 30, 70] } = {}) {
  const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.setSize(innerWidth, innerHeight);
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  document.body.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  scene.background = new THREE.Color('#02030a');
  scene.fog = new THREE.FogExp2('#02030a', 0.0045);

  const camera = new THREE.PerspectiveCamera(50, innerWidth / innerHeight, 0.1, 2000);
  camera.position.set(...camPos);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.06;
  controls.autoRotate = true;
  controls.autoRotateSpeed = 0.35;
  controls.minDistance = 8;
  controls.maxDistance = 300;
  renderer.domElement.addEventListener('pointerdown', () => { controls.autoRotate = false; });

  const composer = new EffectComposer(renderer);
  composer.addPass(new RenderPass(scene, camera));
  const bloomPass = new UnrealBloomPass(new THREE.Vector2(innerWidth, innerHeight), bloom, radius, threshold);
  composer.addPass(bloomPass);
  composer.addPass(new OutputPass());

  const resizers = [];
  addEventListener('resize', () => {
    camera.aspect = innerWidth / innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(innerWidth, innerHeight);
    composer.setSize(innerWidth, innerHeight);
    resizers.forEach(f => f());
  });

  return { THREE, renderer, scene, camera, controls, composer, bloomPass, resizers };
}

function starfield(scene, count = 4000) {
  const g = new THREE.BufferGeometry();
  const pos = new Float32Array(count * 3), col = new Float32Array(count * 3);
  const c = new THREE.Color();
  for (let i = 0; i < count; i++) {
    const r = 300 + Math.random() * 500, t = Math.random() * Math.PI * 2, p = Math.acos(2 * Math.random() - 1);
    pos.set([r * Math.sin(p) * Math.cos(t), r * Math.cos(p), r * Math.sin(p) * Math.sin(t)], i * 3);
    c.setHSL(0.55 + Math.random() * 0.2, 0.6, 0.55 + Math.random() * 0.4);
    col.set([c.r, c.g, c.b], i * 3);
  }
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  g.setAttribute('color', new THREE.BufferAttribute(col, 3));
  const m = new THREE.PointsMaterial({ size: 1.4, vertexColors: true, transparent: true, opacity: 0.8, fog: false, sizeAttenuation: true });
  const pts = new THREE.Points(g, m);
  scene.add(pts);
  return pts;
}

// A soft round sprite texture for glows and particles.
let _glow;
function glowTexture() {
  if (_glow) return _glow;
  const cv = document.createElement('canvas');
  cv.width = cv.height = 128;
  const ctx = cv.getContext('2d');
  const grd = ctx.createRadialGradient(64, 64, 0, 64, 64, 64);
  grd.addColorStop(0, 'rgba(255,255,255,1)');
  grd.addColorStop(0.25, 'rgba(255,255,255,0.55)');
  grd.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.fillStyle = grd;
  ctx.fillRect(0, 0, 128, 128);
  return (_glow = new THREE.CanvasTexture(cv));
}

function glowSprite(color, scale, opacity = 0.9) {
  const s = new THREE.Sprite(new THREE.SpriteMaterial({
    map: glowTexture(), color, transparent: true, opacity, blending: THREE.AdditiveBlending, depthWrite: false,
  }));
  s.scale.setScalar(scale);
  return s;
}

// Fresnel rim shell: the "atmosphere" look on planets and cores.
function rimMaterial(color, power = 2.2, strength = 1.4) {
  return new THREE.ShaderMaterial({
    uniforms: { c: { value: new THREE.Color(color) }, p: { value: power }, s: { value: strength } },
    vertexShader: `varying vec3 vN; varying vec3 vV;
      void main(){ vec4 mv = modelViewMatrix * vec4(position,1.0); vN = normalize(normalMatrix*normal); vV = normalize(-mv.xyz); gl_Position = projectionMatrix*mv; }`,
    fragmentShader: `uniform vec3 c; uniform float p; uniform float s; varying vec3 vN; varying vec3 vV;
      void main(){ float f = pow(1.0 - max(dot(vN, vV), 0.0), p) * s; gl_FragColor = vec4(c * f, f); }`,
    transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.FrontSide,
  });
}

function ringLine(radius, color, opacity = 0.35, segments = 256) {
  const pts = [];
  for (let i = 0; i <= segments; i++) {
    const a = (i / segments) * Math.PI * 2;
    pts.push(new THREE.Vector3(Math.cos(a) * radius, 0, Math.sin(a) * radius));
  }
  return new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts),
    new THREE.LineBasicMaterial({ color, transparent: true, opacity, blending: THREE.AdditiveBlending, depthWrite: false }));
}

// ---------- HUD (built with DOM calls, text only, so names can never inject markup) ----------
// replaceChildren takes nodes, not nested arrays
const kidsOf = (...kids) => kids.flat(Infinity).filter(c => c != null && c !== false);

function el(tag, props = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === 'style') Object.entries(v).forEach(([sk, sv]) => n.style.setProperty(sk, sv));
    else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
    else if (k === 'class') n.className = v;
    else n.setAttribute(k, v);
  }
  for (const c of kids.flat(Infinity)) if (c != null && c !== false) n.append(c instanceof Node ? c : String(c));
  return n;
}

const OWN_WORDS = { agents: 'agent', skills: 'skill', commands: 'command', hooks: 'hook', mcp: 'MCP server', rules: 'rules file' };
function ownSummary(own) {
  return Object.entries(own).map(([k, v]) => `${v.length} ${OWN_WORDS[k] || k}${v.length === 1 ? '' : 's'}`).join(', ');
}

// A description folded to four lines; Read more appears only when the text is actually cut off,
// and opens the whole description in a small dialog in the middle of the screen.
// "Skills" -> "Skill", for the kind tag on a single item
const oneOf = label => ({ 'MCP servers': 'MCP server', 'Rules': 'Rules file', 'Output styles': 'Output style', 'Memory': 'Memory' }[label] || label.replace(/s$/, ''));
function descEl(text, meta) {
  const d = el('span', { class: 'desc' }, text);
  d._meta = meta;
  return d;
}
function addReadMore(root) {
  for (const d of root.querySelectorAll('.desc')) {
    if (d.nextElementSibling?.classList.contains('more') || d.scrollHeight <= d.clientHeight + 1) continue;
    const btn = el('button', { type: 'button', class: 'more', 'aria-haspopup': 'dialog' }, 'Read more');
    btn.onclick = () => openDescription(d._meta, d.textContent, btn);
    d.after(btn);
  }
}
function openDescription(meta, text, opener) {
  const back = el('div', { class: 'modal-back' });
  const close = () => {
    back.remove();
    removeEventListener('keydown', onKey, true);
    opener?.focus();
  };
  const onKey = e => {
    if (e.key === 'Escape') { e.stopPropagation(); e.preventDefault(); close(); }
  };
  const x = el('button', { type: 'button', class: 'x', 'aria-label': 'Close', onclick: close }, '×');
  const box = el('div', { class: 'modal', role: 'dialog', 'aria-modal': 'true', 'aria-label': meta.name, style: { '--c': meta.color } },
    x,
    el('div', { class: 'mtags' }, el('span', { class: 'stag', style: { '--k': meta.color } }, meta.kind), el('span', { class: 'swhere' }, meta.where)),
    el('h3', {}, meta.name),
    el('p', {}, text));
  back.append(box);
  back.addEventListener('click', e => { if (e.target === back) close(); });
  addEventListener('keydown', onKey, true);
  document.body.append(back);
  x.focus();
}

function hud(data, kinds, { subtitle = '' } = {}) {
  const tip = el('div', { class: 'tip', hidden: '' });
  const panel = el('aside', { class: 'panel', hidden: '' });
  const api = {
    onChip: null, onClose: null,
    showTip(x, y, title, body, color) {
      tip.hidden = false;
      tip.style.setProperty('--c', color || '#fff');
      tip.replaceChildren(el('b', {}, title), body ? el('span', {}, body) : null);
      tip.style.left = Math.min(x + 16, innerWidth - 300) + 'px';
      tip.style.top = (y + 16) + 'px';
    },
    hideTip() { tip.hidden = true; },
    openPanel(kind, focusName) {
      panel.hidden = false;
      panel.style.setProperty('--c', kind.color);
      const items = kind.items.map(it => el('li', { class: it.name === focusName ? 'on' : '' },
        el('b', {}, it.name),
        it.desc ? descEl(it.desc, { name: it.name, kind: oneOf(kind.label), color: kind.color, where: kind.key === 'projects' ? 'projects' : 'global' }) : null,
        it.own ? el('em', {}, ownSummary(it.own)) : null,
        it.skills && it.skills.length ? el('em', {}, `${it.skills.length} skill${it.skills.length === 1 ? '' : 's'}: ${it.skills.slice(0, 8).join(', ')}${it.skills.length > 8 ? '…' : ''}`) : null));
      panel.replaceChildren(...kidsOf(
        el('button', { class: 'x', 'aria-label': 'Close', onclick: () => api.closePanel() }, '×'),
        el('div', { class: 'eyebrow' }, `${kind.items.length} ${kind.label}`),
        el('h2', {}, kind.label),
        el('ul', {}, items)));
      addReadMore(panel);
      panel.querySelector('li.on')?.scrollIntoView({ block: 'center' });
    },
    openGroup(title, color, eyebrow, sections, focusName, head = null) {
      panel.hidden = false;
      panel.style.setProperty('--c', color);
      panel.replaceChildren(...kidsOf(
        el('button', { class: 'x', 'aria-label': 'Close', onclick: () => api.closePanel() }, '×'),
        el('div', { class: 'eyebrow' }, eyebrow),
        el('h2', {}, title),
        head,
        sections.map(sec => [
          el('div', { class: 'eyebrow', style: { color: sec.color, 'margin-top': '16px' } }, `${sec.items.length} ${sec.label}`),
          el('ul', {}, sec.items.map(it => el('li', { class: it.name === focusName ? 'on' : '' },
            el('b', {}, it.name), it.desc ? descEl(it.desc, { name: it.name, kind: sec.kind || sec.label, color: sec.color, where: sec.where || title }) : null)))])));
      panel.scrollTop = 0;
      addReadMore(panel);
      panel.querySelector('li.on')?.scrollIntoView({ block: 'center' });
    },
    view: 'global',
    // swap the chips, the piece count and the sources list to another view's kinds
    setView(view, viewKinds) {
      api.view = view;
      kinds = viewKinds;
      renderStrip();
      if (!panel.hidden) api.closePanel();
    },
    openSources() {
      if (api.view === 'project') return api.openProjectSources();
      panel.hidden = false;
      panel.style.setProperty('--c', '#9fe8ff');
      panel.replaceChildren(...kidsOf(
        el('button', { class: 'x', 'aria-label': 'Close', onclick: () => api.closePanel() }, '×'),
        el('div', { class: 'eyebrow' }, 'read from this PC at build time'),
        el('h2', {}, 'Data sources'),
        el('ul', {}, kinds.map(k => el('li', {}, el('b', {}, `${k.label}: ${k.items.length}`), el('span', {}, data.sources[k.key] || '')))),
        (data.unread || []).length ? el('h2', { style: { 'margin-top': '18px', 'font-size': '16px' } }, 'Not shown') : null,
        el('ul', {}, (data.unread || []).map(u => el('li', {}, el('span', {}, u))))));
    },
    openProjectSources() {
      const projects = data.kinds.projects || [];
      panel.hidden = false;
      panel.style.setProperty('--c', '#9fe8ff');
      panel.replaceChildren(...kidsOf(
        el('button', { class: 'x', 'aria-label': 'Close', onclick: () => api.closePanel() }, '×'),
        el('div', { class: 'eyebrow' }, 'read from this PC at build time'),
        el('h2', {}, 'Data sources'),
        el('ul', {},
          el('li', {}, el('b', {}, `Projects: ${projects.length}`), el('span', {}, data.sources.projects || '')),
          el('li', {}, el('b', {}, `With their own setup: ${projects.filter(p => p.own).length}`), el('span', {}, data.sources.own || '')),
          kinds.map(k => el('li', {}, el('b', {}, `${k.label}: ${k.items.length}`)))),
        el('h2', { style: { 'margin-top': '18px', 'font-size': '16px' } }, 'Per project'),
        el('ul', {}, projects.filter(p => p.own).map(p => el('li', {},
          el('b', {}, p.name), el('span', {}, ownSummary(p.own)))))));
    },
    closePanel() { panel.hidden = true; api.onClose && api.onClose(); },
  };
  const strip = el('nav', { class: 'strip' }), meta = el('div', { class: 'meta' });
  function renderStrip() {
    const total = kinds.reduce((n, k) => n + k.items.length, 0);
    meta.textContent = `${total} pieces · model ${data.model || 'default'} · style ${data.outputStyle || 'default'}`;
    strip.replaceChildren(...kinds.map(k => el('button', {
      class: 'chip', style: { '--c': k.color },
      onclick: () => { (k.open || api.openPanel)(k); api.onChip && api.onChip(k); },
    }, el('span', { class: 'n' }, k.items.length), el('span', { class: 'l' }, k.label))));
  }
  renderStrip();
  const root = el('div', { class: 'hud' },
    el('header', { class: 'brand' },
      el('div', { class: 'eyebrow' }, `SETUP MAP // ${subtitle}`),
      el('h1', {}, data.title || 'Claude Code'),
      meta,
      data.sources ? el('button', { class: 'src', onclick: () => api.openSources() }, 'where this was read from') : null),
    strip,
    panel, tip,
    el('div', { class: 'hint' }, 'drag to orbit · scroll to zoom · click to inspect · H hides the HUD'));
  document.body.appendChild(root);
  addEventListener('keydown', e => {
    if (e.target instanceof HTMLInputElement) return;
    if (e.key === 'h' || e.key === 'H') document.body.classList.toggle('clean');
    if (e.key === 'Escape') api.closePanel();
  });
  return api;
}

// Hover and click picking against objects carrying userData {kind, item}.
function picker(stage, targets, ui, { onHover, onClick } = {}) {
  const ray = new THREE.Raycaster(), mouse = new THREE.Vector2();
  let down = null;
  const pick = e => {
    mouse.set((e.clientX / innerWidth) * 2 - 1, -(e.clientY / innerHeight) * 2 + 1);
    ray.setFromCamera(mouse, stage.camera);
    return ray.intersectObjects(targets(), false)[0]?.object || null;
  };
  const cv = stage.renderer.domElement;
  cv.addEventListener('pointermove', e => {
    const o = pick(e);
    cv.style.cursor = o ? 'pointer' : 'grab';
    if (o) {
      const { kind, item } = o.userData;
      ui.showTip(e.clientX, e.clientY, item ? item.name : kind.label,
        item ? (item.desc || kind.label) : `${kind.items.length} ${kind.label.toLowerCase()}`, kind.color);
    } else ui.hideTip();
    onHover && onHover(o);
  });
  cv.addEventListener('pointerdown', e => { down = [e.clientX, e.clientY]; });
  cv.addEventListener('pointerup', e => {
    if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 5) return;
    const o = pick(e);
    if (o) { ui.hideTip(); ui.openPanel(o.userData.kind, o.userData.item?.name); onClick && onClick(o); }
  });
}

// Smoothly move the orbit target and camera.
function flyTo(stage, target, distance, ms = 1400) {
  const { camera, controls } = stage;
  const fromT = controls.target.clone(), fromP = camera.position.clone();
  const dir = fromP.clone().sub(fromT).normalize();
  const toP = target.clone().add(dir.multiplyScalar(distance));
  const t0 = performance.now();
  return new Promise(done => {
    (function step() {
      const t = Math.min(1, (performance.now() - t0) / ms), e = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
      controls.target.lerpVectors(fromT, target, e);
      camera.position.lerpVectors(fromP, toP, e);
      t < 1 ? requestAnimationFrame(step) : done();
    })();
  });
}




// Synapse, calm. The hub and the nodes carry the picture; links stay quiet until you point at something.
//   ?mode=dots    one faint dot drifts slowly along each link
//   ?mode=breath  nothing travels; nodes and links breathe softly, a little out of step per kind
// Two views share the core: Global (the user-level setup) and By project (each project's own setup).
const MODE = new URLSearchParams(location.search).get('mode') === 'breath' ? 'breath' : 'dots';
const data = await loadSetup();
const globalKinds = kindsWithItems(data).filter(k => k.key !== 'projects');
const projects = data.kinds.projects || [];
const stage = makeStage({ bloom: 0.55, radius: 0.45, threshold: 0.22, camPos: [0, 20, 108] });
const { scene, camera, controls, composer, renderer } = stage;
controls.autoRotateSpeed = 0.22;
const stars = starfield(scene, 2200);
stars.material.opacity = 0.55;
const ui = hud(data, globalKinds, { subtitle: 'NEURAL SYNAPSE' });

const labels = new CSS2DRenderer();
labels.setSize(innerWidth, innerHeight);
Object.assign(labels.domElement.style, { position: 'fixed', inset: '0', pointerEvents: 'none' });
document.body.appendChild(labels.domElement);
stage.resizers.push(() => labels.setSize(innerWidth, innerHeight));
const label = (text, sub, color) => new CSS2DObject(el('div', { class: 'label3d', style: { '--c': color } }, text, sub ? el('small', {}, sub) : null));

const world = new THREE.Group();
scene.add(world);
const rand = (s => () => (s = (s * 16807) % 2147483647) / 2147483647)(11);
const gauss = () => (rand() + rand() + rand() - 1.5) / 1.5;
const KIND_BY_KEY = Object.fromEntries(KINDS.map(k => [k.key, { ...k, one: k.label === 'MCP servers' ? 'MCP server' : k.label.replace(/s$/, '').replace(/^Rule$/, 'Rules file') }]));
const PROJECTS_KIND = { ...KIND_BY_KEY.projects, items: projects };

// ---- core (shared by both views) ----
const nucleus = new THREE.Mesh(new THREE.SphereGeometry(2.6, 64, 64), new THREE.MeshBasicMaterial({ color: '#ffc2a0' }));
world.add(nucleus);
world.add(new THREE.Mesh(new THREE.SphereGeometry(3.5, 64, 64), rimMaterial(CLAUDE_COLOR, 2.2, 1.4)));
const coreGlow = glowSprite(CLAUDE_COLOR, 15, 0.35);
world.add(coreGlow);
const coreLabel = label(data.title || 'Claude Code', 'core', CLAUDE_COLOR);
coreLabel.position.set(0, 5.2, 0);
world.add(coreLabel);

// ---- building blocks ----
const fib = (i, n) => {
  const y = 1 - (i + 0.5) / n * 2, r = Math.sqrt(1 - y * y), a = i * 2.399963;
  return new THREE.Vector3(Math.cos(a) * r, y * 0.8, Math.sin(a) * r).normalize();
};
const nerves = [], pickables = [], hubs = [], labels3d = [];
const nodeGeo = new THREE.SphereGeometry(1, 24, 24);
function nerve(from, to, color, kind, bend, weight, view) {
  const mid = from.clone().lerp(to, 0.5);
  const side = new THREE.Vector3(rand() - 0.5, rand() - 0.5, rand() - 0.5).multiplyScalar(bend);
  const curve = new THREE.CatmullRomCurve3([from, from.clone().lerp(mid, 0.5).add(side.clone().multiplyScalar(0.6)), mid.add(side), to]);
  const v = { pts: curve.getPoints(48), color: new THREE.Color(color), kind, weight, view, off: rand(), speed: 0.03 + rand() * 0.03, glow: 0 };
  nerves.push(v);
  return v;
}
function hubNode(view, kind, pos, color, size, text, sub, extra = {}) {
  const hub = new THREE.Mesh(nodeGeo, new THREE.MeshBasicMaterial({ color, transparent: true }));
  hub.scale.setScalar(size);
  hub.position.copy(pos);
  world.add(hub);
  const shell = new THREE.Mesh(nodeGeo, rimMaterial(color, 2.4, 1.1));
  shell.scale.setScalar(1.45);
  hub.add(shell);
  const lbl = label(text, sub, color);
  lbl.position.set(0, 2.1 / size + 0.6, 0);
  hub.add(lbl);
  labels3d.push({ lbl, view });
  hub.userData = { kind, view, size, shell, base: new THREE.Color(color), isHub: true, nerve: nerve(pos, new THREE.Vector3(), color, kind, 6, 1, view), phase: hubs.length * 0.7, ...extra };
  hubs.push(hub);
  pickables.push(hub);
  return hub;
}
function leafNode(view, kind, item, pos, color, size, hub) {
  const n = new THREE.Mesh(nodeGeo, new THREE.MeshBasicMaterial({ color: color.clone(), transparent: true }));
  n.scale.setScalar(size);
  n.position.copy(pos);
  n.userData = { kind, item, view, base: color, hub, phase: rand() * 6, nerve: nerve(pos, hub.position.clone(), kind.color, kind, 3, 0.5, view) };
  world.add(n);
  pickables.push(n);
  return n;
}

// ---- Global view: the user-level setup ----
globalKinds.forEach((k, i) => {
  const dir = fib(i, globalKinds.length);
  const hubPos = dir.clone().multiplyScalar(20);
  const hub = hubNode('global', k, hubPos, k.color, 1.05 + Math.sqrt(k.items.length) * 0.15, k.label, `${k.items.length}`);
  const cloud = 3 + Math.sqrt(k.items.length) * 1.3;
  k.items.forEach(item => {
    const p = hubPos.clone().add(dir.clone().multiplyScalar(6 + rand() * 5)).add(new THREE.Vector3(gauss(), gauss(), gauss()).multiplyScalar(cloud));
    leafNode('global', k, item, p, new THREE.Color(k.color).lerp(new THREE.Color('#ffffff'), 0.3),
      0.36 + (item.skills ? Math.min(0.35, item.skills.length * 0.02) : 0), hub);
  });
});

// ---- By project view: projects around the core, each labelled with what it has ----
// Projects with a setup of their own sit on an inner shell; the rest sit further out, dimmed.
// A project not used for 60 days or more is dimmed the same way and says how long it has been idle.
const withOwn = projects.filter(p => p.own), without = projects.filter(p => !p.own);
const STALE = 60;
const ageDays = p => p.last ? Math.max(0, Math.floor((Date.now() - new Date(p.last + 'T00:00:00')) / 864e5)) : null;
const isStale = p => ageDays(p) == null || ageDays(p) >= STALE;
const ageText = p => { const a = ageDays(p); return a == null ? 'no recent sessions' : a === 0 ? 'used today' : a === 1 ? 'used yesterday' : a < STALE ? `used ${a} days ago` : `idle ${a} days`; };
const sessionsText = p => `${p.sessions || 0} session${p.sessions === 1 ? '' : 's'}`;
const ownCount = p => Object.values(p.own || {}).reduce((n, l) => n + l.length, 0);
const COUNT_ORDER = ['agents', 'skills', 'hooks', 'commands', 'mcp', 'rules'];
const COUNT_WORD = { agents: 'agent', skills: 'skill', hooks: 'hook', commands: 'command', mcp: 'MCP', rules: 'rule' };
const SHOW_ZEROS = false;
const countParts = item => COUNT_ORDER.map(key => [key, (item.own?.[key] || []).length]).filter(([, n]) => SHOW_ZEROS || n)
  .map(([key, n]) => ({ key, n, text: `${n} ${COUNT_WORD[key]}${n === 1 || key === 'mcp' ? '' : 's'}` }));
// the counts now sit under the kind circles, so the project label is just its name
function projectLabel(item, color) {
  const sub = [item.own ? null : 'no own setup', isStale(item) ? ageText(item) : null].filter(Boolean).join(' · ');
  return new CSS2DObject(el('div', { class: 'label3d plabel', style: { '--c': color } }, item.name, sub ? el('small', {}, sub) : null));
}
[[withOwn, 56], [without, 84]].forEach(([list, R]) => list.forEach((item, i) => {
  const dir = fib(i, list.length);
  dir.y *= 1.35; // taller shell than the global one, so labels stack less
  const pos = dir.normalize().clone().multiplyScalar(R);
  const outside = !!item.outside;
  const color = new THREE.Color(outside ? '#8fa6ff' : PROJECTS_KIND.color).lerp(new THREE.Color('#ffffff'), 0.25);
  const n = hubNode('project', PROJECTS_KIND, pos, color, item.own ? 0.7 + Math.sqrt(ownCount(item)) * 0.12 : 0.42,
    item.name, '', { item, dimmed: !item.own || isStale(item) });
  // swap the plain label for one carrying the counts
  const plain = n.children.find(c => c.isCSS2DObject);
  const lbl = projectLabel(item, '#' + color.getHexString());
  lbl.position.copy(plain.position);
  n.remove(plain);
  n.add(lbl);
  labels3d.find(l => l.lbl === plain).lbl = lbl;

  // one circle per kind the project has, joined to the project, its count written under it
  const parts = countParts(item);
  const up = Math.abs(dir.y) > 0.9 ? new THREE.Vector3(1, 0, 0) : new THREE.Vector3(0, 1, 0);
  const t1 = new THREE.Vector3().crossVectors(dir, up).normalize(), t2 = new THREE.Vector3().crossVectors(dir, t1);
  parts.forEach((c, j) => {
    const sk = KIND_BY_KEY[c.key];
    const a = (j / parts.length) * Math.PI * 2 + i;
    // far enough out that a circle never sits on its project node, even seen side-on
    const cp = pos.clone().add(dir.clone().multiplyScalar(3.4))
      .add(t1.clone().multiplyScalar(Math.cos(a) * 4.6)).add(t2.clone().multiplyScalar(Math.sin(a) * 4.6));
    const size = 0.32 + Math.min(0.38, Math.sqrt(c.n) * 0.09); // grows a little with the count, capped
    const k = leafNode('project', PROJECTS_KIND, { name: c.text, desc: `${c.text} in ${item.name}` }, cp,
      new THREE.Color(sk.color).multiplyScalar(0.75), size, n); // about a quarter less glow than before
    k.userData.projectItem = item;
    k.userData.ownKey = c.key;
    const kl = new CSS2DObject(el('div', { class: 'klabel', style: { '--k': sk.color } },
      el('b', {}, c.n), c.text.replace(/^\d+ /, '')));
    kl.position.set(0, -(1 + 1.25 / size), 0);
    k.add(kl);
    labels3d.push({ lbl: kl, view: 'project', near: true });
  });
}));

function openProject(item, focusName = null) {
  const head = [
    el('div', { class: 'pcounts' }, COUNT_ORDER.map(key => el('span', { style: { '--k': KIND_BY_KEY[key].color } },
      el('b', {}, (item.own?.[key] || []).length), KIND_BY_KEY[key].label))),
  ];
  ui.openGroup(item.name, KIND_BY_KEY.projects.color, `${sessionsText(item)} · ${ageText(item)} · ${item.own ? 'its own setup' : 'no own setup'}`,
    item.own ? ownSections(item) : [], focusName, head);
}

// By project chips: totals of each kind across the projects' own setups
const projectKinds = ['agents', 'skills', 'commands', 'hooks', 'mcp', 'rules'].map(key => {
  const k = KIND_BY_KEY[key];
  const items = withOwn.flatMap(p => (p.own[key] || []).map(x => ({ name: x.name, desc: `${p.name}${x.desc ? '. ' + x.desc : ''}` })));
  return { ...k, items, open: kind => ui.openGroup(kind.label, kind.color, `${kind.items.length} across ${withOwn.filter(p => p.own[key]).length} projects`,
    withOwn.filter(p => p.own[key]).map(p => ({ label: p.name, kind: kind.one, color: kind.color, where: p.name, items: p.own[key] })), null) };
}).filter(k => k.items.length);

// ---- lines and drift dots ----
const segCount = nerves.reduce((n, v) => n + v.pts.length - 1, 0);
const nPos = new Float32Array(segCount * 6), nCol = new Float32Array(segCount * 6);
const nerveGeo = new THREE.BufferGeometry();
nerveGeo.setAttribute('position', new THREE.BufferAttribute(nPos, 3));
nerveGeo.setAttribute('color', new THREE.BufferAttribute(nCol, 3));
let o = 0;
for (const v of nerves) {
  v.seg = o;
  for (let i = 0; i < v.pts.length - 1; i++, o++) nPos.set([...v.pts[i].toArray(), ...v.pts[i + 1].toArray()], o * 6);
}
world.add(new THREE.LineSegments(nerveGeo, new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false })));
const dPos = new Float32Array(nerves.length * 3), dCol = new Float32Array(nerves.length * 3);
const dotGeo = new THREE.BufferGeometry();
dotGeo.setAttribute('position', new THREE.BufferAttribute(dPos, 3));
dotGeo.setAttribute('color', new THREE.BufferAttribute(dCol, 3));
const dots = new THREE.Points(dotGeo, new THREE.PointsMaterial({ size: 0.45, map: glowTexture(), vertexColors: true, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false }));
dots.frustumCulled = false;
dots.visible = MODE === 'dots';
world.add(dots);

// ---- selection: the hovered or clicked node lights its own path to the core ----
let selected = null, hovered = null;
const pathOf = n => !n ? [] : n.userData.hub ? [n.userData.nerve, n.userData.hub.userData.nerve] : [n.userData.nerve];
const ownSections = item => Object.entries(item.own).map(([key, list]) => ({ label: KIND_BY_KEY[key].label, kind: KIND_BY_KEY[key].one, color: KIND_BY_KEY[key].color, where: item.name, items: list }));

// ---- the view toggle ----
let view = 'global';
const fade = { global: 1, project: 0 };
const toggle = el('div', { class: 'viewtoggle', role: 'tablist', 'aria-label': 'View' },
  el('button', { role: 'tab', 'data-view': 'global', onclick: () => setView('global') }, 'Global'),
  el('button', { role: 'tab', 'data-view': 'project', onclick: () => setView('project') }, 'By project'));
document.querySelector('.hud').appendChild(toggle);
const homeDistance = () => (view === 'global' ? 108 : 205);
function setView(v, instant, stay) {
  view = v;
  toggle.querySelectorAll('button').forEach(b => b.setAttribute('aria-selected', String(b.dataset.view === v)));
  toggle.dataset.view = v;
  selected = hovered = null;
  ui.setView(v, v === 'global' ? globalKinds : projectKinds);
  if (instant) { fade.global = v === 'global' ? 1 : 0; fade.project = 1 - fade.global; }
  else if (!stay) flyTo(stage, new THREE.Vector3(), homeDistance(), 1300).then(() => { controls.autoRotate = true; });
  try { localStorage.setItem('setupMapView', v); } catch { /* storage blocked: the toggle still works */ }
}

picker(stage, () => pickables.filter(m => m.visible && m.userData.view === view), ui, {
  onHover: h => { hovered = h; },
  onClick: h => {
    selected = h;
    controls.autoRotate = false;
    if (h.userData.view === 'project') openProject(h.userData.projectItem || h.userData.item);
    flyTo(stage, h.getWorldPosition(new THREE.Vector3()), h.userData.isHub ? (view === 'global' ? 38 : 34) : 26, 1500);
  },
});
ui.onChip = k => {
  if (view !== 'global') return;
  selected = hubs.find(x => x.userData.kind === k && x.userData.view === 'global');
  flyTo(stage, selected.getWorldPosition(new THREE.Vector3()), 38, 1500);
};
ui.onClose = () => { selected = null; flyTo(stage, new THREE.Vector3(), homeDistance(), 1600).then(() => { controls.autoRotate = true; }); };

let start = 'global';
try { start = localStorage.getItem('setupMapView') === 'project' ? 'project' : 'global'; } catch { /* no storage */ }
setView(start, true);
if (start === 'project') camera.position.setLength(homeDistance());

// ---- search: type a name, pick a result, the map flies there and opens its panel ----
const norm = t => String(t).toLowerCase().replace(/[\s\-_.:/]+/g, '');
const index = [];
for (const m of pickables) {
  const u = m.userData;
  if (u.view === 'global') {
    index.push(u.item
      ? { name: u.item.name, color: u.kind.color, tag: u.kind.label, where: 'global', node: m, open: () => ui.openPanel(u.kind, u.item.name) }
      : { name: u.kind.label, color: u.kind.color, tag: 'kind', where: 'global', node: m, open: () => ui.openPanel(u.kind) });
  } else if (u.isHub) {
    index.push({ name: u.item.name, color: KIND_BY_KEY.projects.color, tag: 'project', where: 'by project', node: m, open: () => openProject(u.item), rank: -1 });
  } else if (u.ownKey) {
    for (const x of u.projectItem.own[u.ownKey]) {
      index.push({ name: x.name, color: KIND_BY_KEY[u.ownKey].color, tag: KIND_BY_KEY[u.ownKey].one, where: u.projectItem.name, node: m, open: () => openProject(u.projectItem, x.name) });
    }
  }
}
for (const e of index) e.key = norm(e.name);
const results = el('ul', { class: 'sresults', hidden: '' });
const input = el('input', { type: 'search', placeholder: 'Search projects, skills, agents, hooks…', 'aria-label': 'Search the setup map', autocomplete: 'off', spellcheck: 'false' });
const searchBox = el('div', { class: 'search' }, input, results);
document.querySelector('.hud').appendChild(searchBox);
let hits = [];
function find(q) {
  const k = norm(q);
  if (!k) return [];
  return index.map(e => ({ e, s: e.key === k ? 0 : e.key.startsWith(k) ? 1 : e.key.includes(k) ? 2 : 9 }))
    .filter(x => x.s < 9).sort((a, b) => a.s - b.s || (a.e.rank || 0) - (b.e.rank || 0) || a.e.name.length - b.e.name.length)
    .slice(0, 8).map(x => x.e);
}
function showHits() {
  hits = find(input.value);
  results.hidden = !hits.length;
  results.replaceChildren(...hits.map((h, i) => el('li', {},
    el('button', { type: 'button', class: i ? '' : 'top', onclick: () => go(h) },
      el('b', {}, h.name),
      el('span', { class: 'stag', style: { '--k': h.color } }, h.tag),
      el('span', { class: 'swhere' }, h.where)))));
}
function go(h) {
  const target = h.node.userData.view;
  if (target !== view) setView(target, false, true);
  results.hidden = true;
  input.blur();
  controls.autoRotate = false;
  selected = h.node;
  ui.hideTip();
  h.open();
  flyTo(stage, h.node.getWorldPosition(new THREE.Vector3()), h.node.userData.isHub ? (target === 'global' ? 38 : 34) : 26, 1500);
}
input.addEventListener('input', showHits);
input.addEventListener('focus', showHits);
input.addEventListener('keydown', e => {
  e.stopPropagation(); // typing must not trigger the map's own keys (H hides the HUD)
  if (e.key === 'Enter' && hits[0]) go(hits[0]);
  if (e.key === 'Escape') { input.value = ''; results.hidden = true; input.blur(); }
});

// handle for automated checks: lets a test find a node on screen without hunting for it
window.__setupMap = { pickables, camera, controls, setView };

// ---- loop ----
const clock = new THREE.Clock(), P = new THREE.Vector3(), D = new THREE.Vector3(), O = new THREE.Vector3();
renderer.setAnimationLoop(() => {
  const dt = Math.min(clock.getDelta(), 0.05), t = clock.elapsedTime;
  const ease = Math.min(1, dt * 3);
  for (const v of ['global', 'project']) fade[v] += ((view === v ? 1 : 0) - fade[v]) * Math.min(1, dt * 2.5);
  const lit = new Set([...pathOf(hovered), ...pathOf(selected)]);
  const focus = selected || hovered;
  const litKind = view === 'global' ? focus?.userData.kind : null;
  for (const v of nerves) v.glow += ((lit.has(v) ? 1 : 0) - v.glow) * ease;

  nucleus.scale.setScalar(1 + Math.sin(t * 0.8) * 0.03);
  coreGlow.material.opacity = 0.3 + Math.sin(t * 0.8) * 0.05;
  stars.rotation.y += dt * 0.0015;

  for (const m of pickables) {
    const u = m.userData, F = fade[u.view];
    const shown = F;
    m.visible = shown > 0.02;
    if (!m.visible) continue;
    const breath = MODE === 'breath' ? 0.82 + 0.18 * Math.sin(t * 0.9 + u.phase) : 1;
    const dim = (litKind && u.kind !== litKind ? 0.45 : 1) * (u.dimmed && m !== hovered ? 0.5 : 1);
    m.material.opacity = shown;
    m.material.color.copy(u.base).multiplyScalar(breath * dim * (m === hovered || m === selected ? 1.6 : 1));
    if (u.isHub) {
      // a view eases in from slightly smaller as it fades up
      m.scale.setScalar(u.size * (0.75 + 0.25 * F) * (MODE === 'breath' ? 1 + 0.04 * Math.sin(t * 0.9 + u.phase) : 1));
      u.shell.material.uniforms.s.value = 1.1 * F * (u.dimmed ? 0.4 : 1);
    }
  }
  const camZ = O.set(0, 0, 0).applyMatrix4(camera.matrixWorldInverse).z;
  // the project in focus: clicked or picked from search (until the panel closes), or under the pointer
  const projectOf = n => !n || n.userData.view !== 'project' ? null : n.userData.isHub ? n : n.userData.hub;
  const focusedProject = projectOf(selected) || projectOf(hovered);
  for (const l of labels3d) {
    const hub = l.lbl.parent, u = hub.userData;
    // project labels on the far side of the core fade back, so the near ones read first
    let depth = 1;
    if (l.view === 'project' && hub !== hovered && hub !== selected) {
      D.copy(hub.position).applyMatrix4(camera.matrixWorldInverse);
      depth = THREE.MathUtils.clamp(0.25 + 0.75 * (D.z - camZ + 30) / 45, 0.25, 1);
    }
    // count labels under the kind circles come in as the camera nears them, so the overview stays readable
    // count labels show on the near half of the sphere at full strength and fade out behind the core,
    // so the overview reads; they come forward as the map turns
    if (l.near) depth = THREE.MathUtils.clamp((depth - 0.5) / 0.2, 0, 1);
    // the focused project's own pills always show, on top of everything else
    const mine = l.near && focusedProject && hub.userData.hub === focusedProject;
    if (mine) depth = 1;
    if (l.near) l.lbl.element.classList.toggle('focus', !!mine);
    l.lbl.visible = fade[l.view] > 0.02 && depth > 0.02;
    l.lbl.element.style.opacity = (fade[l.view] * depth).toFixed(2);
  }

  nerves.forEach((v, idx) => {
    const n = v.pts.length - 1;
    const breath = MODE === 'breath' ? 0.6 + 0.4 * Math.sin(t * 0.9 + v.off * 6) : 1;
    const vis = fade[v.view];
    const base = (v.weight === 1 ? 0.085 : 0.045) * breath * vis;
    for (let i = 0; i < n; i++) {
      // a lit path brightens toward the core, so the eye follows it inward
      const k = base + v.glow * vis * (0.35 + 0.3 * i / n);
      nCol.set([v.color.r * k, v.color.g * k, v.color.b * k, v.color.r * k, v.color.g * k, v.color.b * k], (v.seg + i) * 6);
    }
    if (MODE === 'dots') {
      const f = (t * v.speed + v.off) % 1, u = f * n, i0 = Math.floor(u);
      P.lerpVectors(v.pts[i0], v.pts[Math.min(n, i0 + 1)], u - i0);
      dPos.set([P.x, P.y, P.z], idx * 3);
      const g = Math.sin(f * Math.PI) * (0.22 + v.glow * 0.9) * vis;
      dCol.set([v.color.r * g, v.color.g * g, v.color.b * g], idx * 3);
    }
  });
  nerveGeo.attributes.color.needsUpdate = true;
  if (MODE === 'dots') dotGeo.attributes.position.needsUpdate = dotGeo.attributes.color.needsUpdate = true;
  controls.update();
  composer.render();
  labels.render(scene, camera);
});
</script>
</body>
</html>
----- END FILE 2 -----
`````

## Option 2: use the scripts from this repo

A short prompt that downloads the skill's two files from this repo and runs them.
Claude says what it will download and asks first. To add projects Claude Code has never
been opened in, name their folder on the first line.

```text
Extra projects folder: none

Draw my Claude Code setup map with the setup-map tool from the public repo
github.com/ZazaGdev/AI-fun. Do not write the page or the script yourself: use the
repo's fixed files, so the result is exactly the same as the setup-map skill's.

1. Before downloading anything, tell me what you will fetch and from where, and ask me
   to confirm. The two files are:
   - https://raw.githubusercontent.com/ZazaGdev/AI-fun/main/setup-map/skill/scripts/setup_map.py
     (the Python script: reads my setup, writes one HTML file)
   - https://raw.githubusercontent.com/ZazaGdev/AI-fun/main/setup-map/skill/map.tpl.html
     (the page template the script fills in)
   Say that the script reads ~/.claude, ~/.claude.json and my projects' own .claude
   folders, takes names, short descriptions and counts only, reads only the working
   folder path and file dates from session files (never what was said), sends nothing
   anywhere, and writes ~/setup-map/setup-map.html. Offer to show me the script before
   running it.

2. Once I confirm, download both files with Python's standard library (urllib), not by
   retyping them, into `~/setup-map/tool/`, keeping this layout:
   - `~/setup-map/tool/scripts/setup_map.py`
   - `~/setup-map/tool/map.tpl.html`
   Save them byte for byte. Do not edit either file.

3. If either download fails, stop. Tell me which URL failed and the error, and that I
   can install the skill instead by copying the repo's `setup-map/skill` folder to
   `~/.claude/skills/setup-map`. Do not write your own version of the page or script.

4. Run it with Python 3:
   `python ~/setup-map/tool/scripts/setup_map.py --open`
   If an extra projects folder is named above, pass it first:
   `python ~/setup-map/tool/scripts/setup_map.py "<folder>" --open`
   On Windows use `%USERPROFILE%` in place of `~` if needed, and `python3` on macOS or
   Linux if `python` is not found.

5. Tell me the page path and the lines the script printed: the counts of each kind,
   how many projects have a setup of their own, and anything not shown.

The page shows my project, skill and memory folder names, so never publish or upload
it unless I ask.
```
