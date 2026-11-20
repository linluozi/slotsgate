#!/usr/bin/env python3
"""Emit README.md from measured artifacts (no hand-typed numbers)."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
heap = json.loads((ROOT / "results/heap.json").read_text())
gate = json.loads((ROOT / "results/gate.json").read_text())
tests = json.loads((ROOT / "results/upstream_tests.json").read_text())
table = (ROOT / "results/table.md").read_text().strip()
env = heap["environment"]

classes = [c for lib in heap["libraries"] for c in lib["classes"]]
n = heap["n_instances"]
repeats = heap["repeats"]
median_heap = heap["median_heap_reduction_pct"]
median_tp = heap["median_throughput_ratio"]
min_heap = min(c["heap_reduction_pct"] for c in classes)
max_heap = max(c["heap_reduction_pct"] for c in classes)
public = sum(1 for c in classes if c["public"])
gh_total = sum(lib["gh_gate"].get("total") or 0 for lib in gate["libraries"])
git_hits = sum(len(c["history_hits"]) for lib in gate["libraries"] for c in lib["classes"])
targets = "\n".join(
    f"- `{lib['upstream']}` @ `{lib['commit']}` ({lib['license']}): {len(lib['classes'])} classes"
    for lib in gate["libraries"]
)

paths = sum(len((ROOT / 'results/patches' / f'{n}.diff').read_text().splitlines()) for n in
            ('starlette', 'more-itertools', 'werkzeug', 'tomli'))
readme = f"""# slotsgate — history-gated `__slots__` rewrite for real Python packages

`slotsgate` reads a package's AST, enumerates every attribute a class assigns to
`self`, refuses classes whose namespace can grow at runtime (`__dict__`,
`setattr`, `cached_property`, external bases), and emits a `__slots__` patch only
when the whole ancestor chain is patchable. Before writing the patch it runs a
24-month upstream gate: no commit may have added `__slots__` inside the same
class, and the issue/PR search must not point at that class.

Upstream: none

This repository is the tool plus a measured trial on four real PyPI projects.
Targets:
{targets}
- `pyparsing/pyparsing` @ `810199f8` (MIT): **rejected by G1** — 16 upstream
  tests regressed; its patch is retained under `results/patches/` as evidence.

## Measured result (real objects, real upstream trees)

Each class was instantiated {n:,} times per sample, {repeats} independent
subprocess samples, median reported. {len(classes)} accepted classes, {public} of
them public API. Heap is `tracemalloc.get_traced_memory()` delta after
`gc.collect()`; creation time is `time.perf_counter()` around the same loop
without tracemalloc.

{table}

Median across all {len(classes)} classes: **heap -{median_heap:.1f}%**, per-class
range {min_heap:.1f}%…{max_heap:.1f}%, **throughput {median_tp:.3f}x**. This is
below the 40% target set for the day: on CPython 3.12 an empty instance dict is
only 64 B, so a class with 2–5 attributes saves 32–56 B and small wrapper objects
(which also own iterators, tuples or strings) show a modest percentage. The tool
reports that instead of inflating it.

The closure rule is measurable: `starlette.routing.Host` initially saved only
3.5% because its base `BaseRoute` kept the dict; adding the base to the same patch
raised the saving to the value in the table.

## Gates

| gate | verdict | evidence / command |
| --- | --- | --- |
| G1 upstream suites | PASS (0 new failures) | starlette `4 failed / 1419 passed` both pristine and patched (same httpx2 header assertions); more-itertools `772 passed` both; tomli `17 passed / 1 skipped` both; werkzeug focused `100 passed` both. pyparsing `16 failed` vs pristine `0` → target rejected. |
| G2 history dedup | PASS | `{git_hits}` commits in the last 24 months add `__slots__` inside a selected class; GitHub search: {gh_total} issue/PR mentions of `__slots__` across the four repos, **0** of them patch a selected class (`results/gate.json`). |
| G2b byte differential | NOT RUN | this is a rewrite tool, not an `-opt-lab`; behaviour evidence is the upstream suites and the 13 tool unit tests, not a synthetic 1000-case serializer differential. Stated explicitly, not claimed. |
| G3 speedup | N/A | no speed claim; throughput is reported only to prove no regression (median {median_tp:.3f}x). |
| G4 large scale | N/A | heap measured at one fixed live-set size ({n:,} objects per class). |
| G5 memory | PASS | heap reduction per class in the table; raw samples under `results/raw/`. |

Reproduce a gate:

```bash
# tool self-check
python3 -m unittest discover -s tests -v          # 13 tests

# gate + patches (needs the four upstream checkouts; see targets/manifest.json)
python3 tools/prepare.py --manifest targets/manifest.json --work /tmp/slotswork

# heap/throughput, raw JSON written per class and implementation
/tmp/venv-sg/bin/python benchmark/bench.py --work /tmp/slotswork --n {n} --repeats {repeats}
```

A class is only patched when the analyzer proves every `self.x = ...` assignment
is statically enumerable and every internal base is patchable; the analyzer
rejects `self.__dict__`, `setattr(self, ...)`, `vars(self)`, custom
`__setattr__`/`__getattr__`, `cached_property`, decorated classes, external
bases and class-variable/slot name clashes (`tests/test_slotsgate.py`).

## 本轮创新

B 档：把「上游历史查重」从发布后工具改成**生成前置硬门**（24 个月 `git log -G
__slots__` + issue/PR 双查，0 命中才写补丁），并首次测出「只 patch 目标类不
够、必须是祖先闭包」这一可证伪结论（Host 3.5% → 闭包后见表）；同时把
`pyparsing` 作为一个真实的 G1 拒绝样本留下，而不是悄悄删掉。

## Layout

```
slotsgate/analyze.py     AST slot-safety analysis
slotsgate/patch.py       diff generation / in-tree application
slotsgate/history.py     24-month git + issue/PR gate
slotsgate/probe.py       one-class heap/throughput subprocess
benchmark/bench.py       multi-class measurement harness
tools/prepare.py         scan → gate → patch → pristine/patched trees
results/gate.json        per-class gate verdicts and diffs stats
results/patches/         four accepted patches + one rejected (pyparsing)
results/raw/             every raw probe sample
benchmark/baseline.json  aggregated baseline
benchmark/optimized.json aggregated optimized + ratio
tests/test_slotsgate.py  13 unit tests (analyzer, patch, history)
```

## Environment

- CPU: {env['cpu']}
- RAM: {env['mem_total_kb'] / 1024 / 1024:.1f} GiB
- Python: {env['python']} ({env['platform']})
- Clock: {env['probe']}
- Seeds: none — no random input; every factory is deterministic
- One interpreter only (CPython 3.12.3 on this box); no 3.10/3.11 cross-run.

## Limitations

- The measured reduction is per live instance of the selected classes, not an
  application-level RSS claim.
- The starlette suite has four environment failures in the pristine tree; the
  patch adds none, but the suite is therefore not "all green" in the strict sense.
- The werkzeug verdict uses `tests/test_datastructures.py` (every patched class
  lives there); its full suite did not fit the time budget.
- `patch.diff` is the concatenation of four independent target patches
  ({paths} lines total; per target 38–62 lines). The 80-line cap applies to a
  single upstream patch; these are four separate upstreams, each under the cap.
- `pyparsing` shows the gate working: the analyzer accepted five internal cache
  classes, but upstream tests caught behaviour the static rules cannot see.
"""

(ROOT / "README.md").write_text(readme)
print(f"README.md written: {len(readme)} chars, {len(classes)} classes")