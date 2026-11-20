#!/usr/bin/env python3
"""Prepare pristine/optimized trees, generate patches, run the history gate.

Usage: python tools/prepare.py --manifest targets/manifest.json --work /tmp/slotswork
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from slotsgate.analyze import scan_package  # noqa: E402
from slotsgate.history import issue_hits, slot_history_hits  # noqa: E402
from slotsgate.patch import render_patch  # noqa: E402


def sh(cmd: str, cwd: Path) -> str:
    p = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=120)
    return p.stdout + p.stderr


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default=str(ROOT / "targets/manifest.json"))
    ap.add_argument("--work", default="/tmp/slotswork")
    ap.add_argument("--skip-gh", action="store_true")
    args = ap.parse_args()
    manifest = json.loads(Path(args.manifest).read_text())
    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)
    (ROOT / "results/patches").mkdir(parents=True, exist_ok=True)

    token = os.environ.get("GH_TOKEN")
    if not token:
        token = subprocess.run(["gh", "auth", "token", "-u", "linluozi"], capture_output=True, text=True).stdout.strip()
    report = {"libraries": []}

    for lib in manifest["libraries"]:
        repo = Path(lib["repo"])
        pkg_dir = repo / lib["pkg_parent"] / lib["pkg"]
        infos = scan_package(str(pkg_dir), lib["pkg"])
        for info in infos:  # store paths relative to the repository root
            info.file = str((Path(lib["pkg_parent"]) / info.file))
        by_attr = {i.qualname.rsplit(".", 1)[-1]: i for i in infos}
        chosen = []
        for sel in lib["classes"]:
            simple = sel["attr"].split(".")[-1]
            info = by_attr.get(simple)
            if info is None:
                raise SystemExit(f"{lib['name']}: class not found: {sel['attr']}")
            if info.status != "candidate":
                raise SystemExit(f"{lib['name']}.{simple}: not a candidate ({info.status}: {info.reason})")
            sel = dict(sel, info=info)
            chosen.append(sel)

        # A class only loses its instance dict when every ancestor that owns a
        # dict is patched as well: include the transitive candidate bases.
        expanded = {s["info"].qualname: s["info"] for s in chosen}
        frontier = [s["info"] for s in chosen]
        while frontier:
            info = frontier.pop()
            for base in info.internal_bases:
                if base.qualname not in expanded and base.status == "candidate":
                    expanded[base.qualname] = base
                    frontier.append(base)
        chosen = chosen + [
            {"attr": i.qualname.rsplit(".", 1)[-1], "factory": "", "touch": [], "public": False, "info": i}
            for i in expanded.values() if i.qualname not in {c["info"].qualname for c in chosen}
        ]

        gate = {"gh": {"skipped": True}, "git": {}}
        if not args.skip_gh:
            gate["gh"] = issue_hits(lib["upstream"], "__slots__", token)
        blocked = []
        for sel in chosen:
            hits = slot_history_hits(repo, sel["info"].file, sel["info"].qualname.rsplit(".", 1)[-1])
            gate["git"][sel["info"].qualname] = hits
            if hits:
                blocked.append(sel["info"].qualname)
        if blocked:
            raise SystemExit(f"{lib['name']}: history gate blocked {blocked}")

        patch = render_patch(repo, [s["info"] for s in chosen])
        patch_path = ROOT / "results/patches" / f"{lib['name']}.diff"
        patch_path.write_text(patch)

        orig = work / f"{lib['name']}-orig"
        opt = work / f"{lib['name']}-opt"
        for dest in (orig, opt):
            if dest.exists():
                shutil.rmtree(dest)
            subprocess.run(["git", "clone", "-q", str(repo), str(dest)], check=True)
        check = subprocess.run(
            ["git", "apply", "--check", str(patch_path)], cwd=opt, capture_output=True, text=True
        )
        if check.returncode != 0:
            raise SystemExit(f"{lib['name']}: git apply --check failed: {check.stderr}")
        subprocess.run(["git", "apply", str(patch_path)], cwd=opt, check=True)
        stat = sh(f"git diff --stat", opt)
        files = sh(f"git diff --numstat", opt)

        report["libraries"].append(
            {
                "name": lib["name"],
                "upstream": lib["upstream"],
                "commit": sh("git rev-parse HEAD", repo).strip()[:7],
                "license": lib["license"],
                "pkg_parent": lib["pkg_parent"],
                "pkg": lib["pkg"],
                "setup": lib.get("setup"),
                "classes": [
                    {
                        "qualname": s["info"].qualname,
                        "attr": s["attr"],
                        "module": s.get("module", s["info"].qualname.rsplit(".", 1)[0]),
                        "file": s["info"].file,
                        "slots": list(s["info"].slots),
                        "public": s["public"],
                        "factory": s["factory"],
                        "touch": s["touch"],
                        "history_hits": gate["git"].get(s["info"].qualname, []),
                    }
                    for s in chosen
                ],
                "gh_gate": gate["gh"],
                "diff_stat": stat.strip(),
                "diff_numstat": files.strip(),
                "patch": str(patch_path.relative_to(ROOT)),
            }
        )
        print(f"{lib['name']}: {len(chosen)} classes, {len(patch.splitlines())} patch lines")

    (ROOT / "results/gate.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"wrote {ROOT/'results/gate.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())