"""Upstream history gate: has this class already been slotted or proposed?"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

CLASS_RE = re.compile(r"^[ +\-]class\s+([A-Za-z_]\w*)")


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=60
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"git {' '.join(args)} failed")
    return proc.stdout


def slot_history_hits(repo: Path, relfile: str, class_name: str, months: int = 24) -> list[dict]:
    """Commits in the window that add a __slots__ line inside this class body."""
    since = f"{months} months ago"
    log = _git(
        repo,
        "log",
        f"--since={since}",
        "--format=%H%x09%cs%x09%s",
        "-G",
        "__slots__",
        "--",
        relfile,
    )
    hits = []
    for line in log.splitlines():
        if not line.strip():
            continue
        sha, date, subject = (line.split("\t", 2) + ["", ""])[:3]
        patch = _git(repo, "show", "--format=", "--unified=3", sha, "--", relfile)
        current = None
        for pline in patch.splitlines():
            m = CLASS_RE.match(pline)
            if m and pline[:1] in (" ", "+"):
                current = m.group(1)
            elif pline.startswith("+") and "__slots__" in pline and current == class_name:
                hits.append({"sha": sha[:10], "date": date, "subject": subject})
                break
    return hits


def issue_hits(repo_slug: str, class_name: str, token: str | None = None) -> dict:
    """Issues/PRs in the last 24 months that mention __slots__ for this class.

    Returns the raw count plus the matching numbers, or an explicit error.  The
    gate never treats an API failure as 'no hits'.
    """
    import urllib.parse

    query = urllib.parse.quote(f"repo:{repo_slug} __slots__")
    cmd = [
        "gh",
        "api",
        f"search/issues?q={query}&per_page=20",
        "--jq",
        ".total_count, (.items[] | {number, title, state, createdAt, html_url})",
    ]
    env = None
    if token:
        import os

        env = dict(os.environ, GH_TOKEN=token)
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=45, env=env)
    if proc.returncode != 0:
        return {"ok": False, "error": (proc.stderr or proc.stdout).strip()[:300], "hits": []}
    lines = [ln for ln in (proc.stdout or "").splitlines() if ln.strip()]
    if not lines:
        return {"ok": True, "total": 0, "recent": 0, "hits": []}
    try:
        total = int(lines[0])
        items = [json.loads(ln) for ln in lines[1:]]
    except (ValueError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": f"bad output: {exc}", "hits": []}
    cutoff = "2024-11"
    recent = [i for i in items if str(i.get("createdAt", ""))[:7] >= cutoff]
    return {"ok": True, "total": total, "recent": len(recent), "hits": recent}