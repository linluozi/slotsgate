#!/usr/bin/env python3
"""Independent behaviour differential: pristine vs patched, N unique variants.

Each class factory is parsed and its literal constants are mutated one at a time
(and in pairs), so every sample is a genuinely different input rather than the
same call repeated.  The transcript for a sample includes repr, every slot
value, pickle bytes (sha256) and copy.copy repr; the two implementations must
produce byte-identical canonical JSON, including identical exception types.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

STR_POOL = ["{0}0", "{0}x", "{0} y", "{0}é", "{0}?k=1", "{0}#f", "{0}/p", "{0}{0}"]
INT_POOL = ["{0} + 1", "{0} - 1", "{0} * 2", "0", "1", "2", "7", "-1"]


def collect_constants(tree: ast.AST) -> list[ast.Constant]:
    return [n for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, (str, int)) and not isinstance(n.value, bool)]


def mutated_sources(factory: str, limit: int = 130) -> list[str]:
    """One or two literal mutations per sample, each built on a fresh AST."""
    origin = ast.parse(factory, mode="eval")
    consts = collect_constants(origin)
    kinds = [(isinstance(c.value, str), c.value) for c in consts]
    out: list[str] = [factory]
    seen = {factory}

    def emit(src: str) -> bool:
        if src not in seen:
            seen.add(src)
            out.append(src)
        return len(out) >= limit

    # Dense numeric sweep first: 40 genuinely different values per literal.
    for idx, (is_str, value) in enumerate(kinds):
        for k in range(1, 41):
            tree = ast.parse(factory, mode="eval")
            const = collect_constants(tree)[idx]
            const.value = value + str(k) if is_str else value + k
            if emit(ast.unparse(tree)):
                return out
    for idx, (is_str, value) in enumerate(kinds):
        pool = STR_POOL if is_str else INT_POOL
        for tpl in pool:
            tree = ast.parse(factory, mode="eval")
            const = collect_constants(tree)[idx]
            const.value = tpl.format(value) if is_str else eval(tpl.format(value))  # noqa: S307
            if emit(ast.unparse(tree)):
                return out
    str_idx = [i for i, (is_str, _) in enumerate(kinds) if is_str]
    int_idx = [i for i, (is_str, _) in enumerate(kinds) if not is_str]
    for si in str_idx:
        for ii in int_idx:
            for sp in (0, 1, 4):
                for ip in (0, 1, 3):
                    tree = ast.parse(factory, mode="eval")
                    cs = collect_constants(tree)
                    cs[si].value = STR_POOL[sp].format(kinds[si][1])
                    cs[ii].value = eval(INT_POOL[ip].format(kinds[ii][1]))  # noqa: S307
                    if emit(ast.unparse(tree)):
                        return out
    return out


def run(repo: Path, pkg_parent: str, lib: dict, cls: dict, variants: list[str]) -> dict:
    spec = {"module": cls["module"], "attr": cls["attr"].split(".")[-1], "variants": variants,
            "attrs": cls.get("slots", []), "setup": lib.get("setup"),
            "volatile": cls.get("volatile", [])}
    env = dict(os.environ, PYTHONPATH=str(repo / pkg_parent if pkg_parent != "." else repo))
    proc = subprocess.run(
        [sys.executable, str(ROOT / "slotsgate/differ.py"), json.dumps(spec)],
        capture_output=True, text=True, env=env, timeout=180,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr[-1200:])
    return json.loads(proc.stdout)


def main() -> int:
    manifest = json.loads((ROOT / "targets/manifest.json").read_text())
    gate = json.loads((ROOT / "results/gate.json").read_text())
    gate_lib = {l["name"]: l for l in gate["libraries"]}
    work = Path("/tmp/slotswork")
    out = {"libraries": [], "total_samples": 0, "total_comparisons": 0, "mismatches": 0}
    raw_dir = ROOT / "benchmark/raw"
    for lib in manifest["libraries"]:
        g = gate_lib[lib["name"]]
        slots_by_attr = {c["attr"]: c["slots"] for c in g["classes"]}
        module_by_attr = {c["attr"]: c["module"] for c in g["classes"]}
        entry = {"name": lib["name"], "classes": []}
        for cls in lib["classes"]:
            variants = mutated_sources(cls["factory"])
            cls = dict(cls, slots=slots_by_attr.get(cls["attr"], []),
                       module=module_by_attr[cls["attr"]])
            base = run(work / f"{lib['name']}-orig", lib["pkg_parent"], lib, cls, variants)
            opt = run(work / f"{lib['name']}-opt", lib["pkg_parent"], lib, cls, variants)
            base_by = {i["expr"]: i for i in base["items"]}
            opt_by = {i["expr"]: i for i in opt["items"]}
            assert list(base_by) == list(opt_by)
            mism = [e for e in base_by if base_by[e]["sha256"] != opt_by[e]["sha256"]]
            entry["classes"].append({
                "class": cls["attr"], "variants": len(base_by), "mismatches": len(mism),
                "examples": [{"expr": e, "baseline": base_by[e]["record"], "optimized": opt_by[e]["record"]} for e in mism[:3]],
            })
            out["total_samples"] += len(base_by)
            out["total_comparisons"] += len(base_by)
            out["mismatches"] += len(mism)
            (raw_dir / f"diff-{lib['name']}-{cls['attr'].split('.')[-1]}.json").write_text(
                json.dumps({"variants": variants, "baseline": base["items"], "optimized": opt["items"]}, indent=1) + "\n")
            print(f"{lib['name']:15s} {cls['attr']:45s} variants={len(base_by):3d} mismatch={len(mism)}")
        out["libraries"].append(entry)
    (ROOT / "results/diffcheck.json").write_text(json.dumps(out, indent=2) + "\n")
    print(f"\nunique samples={out['total_samples']} comparisons={out['total_comparisons']} mismatches={out['mismatches']}")
    return 0 if out["mismatches"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())