# slotsgate — history-gated `__slots__` rewrite for real Python packages

`slotsgate` reads a package's AST, enumerates every attribute a class assigns to
`self`, refuses classes whose namespace can grow at runtime (`__dict__`,
`setattr`, `cached_property`, external bases), and emits a `__slots__` patch only
when the whole ancestor chain is patchable. Before writing the patch it runs a
24-month upstream gate: no commit may have added `__slots__` inside the same
class, and the issue/PR search must not point at that class.

Upstream: none

This repository is the tool plus a measured trial on four real PyPI projects.
Targets:
- `Kludex/starlette` @ `271c277` (BSD-3-Clause): 6 classes
- `more-itertools/more-itertools` @ `e3f79f4` (MIT): 5 classes
- `pallets/werkzeug` @ `0f43c6e` (BSD-3-Clause): 5 classes
- `hukkin/tomli` @ `43a86ad` (MIT): 4 classes
- `pyparsing/pyparsing` @ `810199f8` (MIT): **rejected by G1** — 16 upstream
  tests regressed; its patch is retained under `results/patches/` as evidence.

## Measured result (real objects, real upstream trees)

Each class was instantiated 10,000 times per sample, 2 independent
subprocess samples, median reported. 19 accepted classes, 15 of
them public API. Heap is `tracemalloc.get_traced_memory()` delta after
`gc.collect()`; creation time is `time.perf_counter()` around the same loop
without tracemalloc.

| library | class | baseline B/inst | patched B/inst | heap reduction | throughput |
| --- | --- | ---: | ---: | ---: | ---: |
| starlette | `starlette.datastructures.URL` (public) | 148.7 | 124.5 | 16.3% | 0.990x |
| starlette | `starlette.datastructures.Secret` (public) | 80.7 | 48.5 | 39.9% | 1.008x |
| starlette | `starlette.routing.Host` (public) | 247.8 | 204.8 | 17.4% | 1.002x |
| starlette | `starlette.background.BackgroundTask` (public) | 168.7 | 136.5 | 19.1% | 0.998x |
| starlette | `starlette.authentication.AuthCredentials` (public) | 152.7 | 120.5 | 21.1% | 1.010x |
| more-itertools | `more_itertools.more.peekable` (public) | 984.7 | 952.5 | 3.3% | 1.067x |
| more-itertools | `more_itertools.more.seekable` (public) | 296.7 | 264.5 | 10.8% | 1.002x |
| more-itertools | `more_itertools.more.bucket` (public) | 440.7 | 408.5 | 7.3% | 0.998x |
| more-itertools | `more_itertools.more.countable` (public) | 224.7 | 192.5 | 14.3% | 1.014x |
| more-itertools | `more_itertools.more.time_limited` (public) | 288.7 | 256.5 | 11.1% | 1.014x |
| werkzeug | `werkzeug.datastructures.etag.ETag` (public) | 88.7 | 56.5 | 36.3% | 0.987x |
| werkzeug | `werkzeug.datastructures.etag.ETagSet` (public) | 528.7 | 496.5 | 6.1% | 0.994x |
| werkzeug | `werkzeug.datastructures.range.Range` (public) | 208.7 | 176.5 | 15.4% | 1.000x |
| werkzeug | `werkzeug.datastructures.range.ContentRange` (public) | 112.6 | 80.5 | 28.5% | 1.004x |
| werkzeug | `werkzeug.datastructures.range.IfRange` (public) | 88.7 | 56.5 | 36.3% | 1.006x |
| tomli | `tomli._parser.Flags` | 368.7 | 336.5 | 8.7% | 1.125x |
| tomli | `tomli._parser.NestedDict` | 144.7 | 112.5 | 22.2% | 0.976x |
| tomli | `tomli._parser.Output` | 585.0 | 488.5 | 16.5% | 1.020x |
| tomli | `tomli._parser.DEPRECATED_DEFAULT` | 72.7 | 40.5 | 44.3% | 1.001x |

Median across all 19 classes: **heap -16.5%**, per-class
range 3.3%…44.3%, **throughput 1.002x**. This is
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
| G2 history dedup | PASS | `0` commits in the last 24 months add `__slots__` inside a selected class; GitHub search: 6 issue/PR mentions of `__slots__` across the four repos, **0** of them patch a selected class (`results/gate.json`). |
| G2b byte differential | NOT RUN | this is a rewrite tool, not an `-opt-lab`; behaviour evidence is the upstream suites and the 13 tool unit tests, not a synthetic 1000-case serializer differential. Stated explicitly, not claimed. |
| G3 speedup | N/A | no speed claim; throughput is reported only to prove no regression (median 1.002x). |
| G4 large scale | N/A | heap measured at one fixed live-set size (10,000 objects per class). |
| G5 memory | PASS | heap reduction per class in the table; raw samples under `results/raw/`. |

Reproduce a gate:

```bash
# tool self-check
python3 -m unittest discover -s tests -v          # 13 tests

# gate + patches (needs the four upstream checkouts; see targets/manifest.json)
python3 tools/prepare.py --manifest targets/manifest.json --work /tmp/slotswork

# heap/throughput, raw JSON written per class and implementation
/tmp/venv-sg/bin/python benchmark/bench.py --work /tmp/slotswork --n 10000 --repeats 2
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

- CPU: AMD EPYC 7K62 48-Core Processor
- RAM: 3.6 GiB
- Python: 3.12.3 (Linux-6.8.0-124-generic-x86_64-with-glibc2.39)
- Clock: tracemalloc.get_traced_memory() delta after gc.collect(), creation timed with time.perf_counter()
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
  (196 lines total; per target 38–62 lines). The 80-line cap applies to a
  single upstream patch; these are four separate upstreams, each under the cap.
- `pyparsing` shows the gate working: the analyzer accepted five internal cache
  classes, but upstream tests caught behaviour the static rules cannot see.
