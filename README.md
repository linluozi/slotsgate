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

**Correction in this revision.** The first published revision generated
`__slots__` without `__weakref__`, which made `weakref.ref()` fail on every
patched public class. The generator now adds `__weakref__` only to the root of
each patched chain (a subclass inherits the slot and must not redeclare it), and
every number below was re-measured with that slot present. The slot costs one
pointer (8 B) per instance, so these savings are 8 B lower per instance than the
earlier table: the previous percentages were overstated. `results/weakref.json`
records `weakref.ref()` working on 19/19 accepted classes.

| library | class | baseline B/inst | patched B/inst | heap reduction | throughput |
| --- | --- | ---: | ---: | ---: | ---: |
| starlette | `starlette.datastructures.URL` (public) | 148.7 | 140.5 | 5.5% | 1.046x |
| starlette | `starlette.datastructures.Secret` (public) | 80.7 | 64.5 | 20.0% | 1.019x |
| starlette | `starlette.routing.Host` (public) | 247.8 | 220.7 | 11.0% | 1.019x |
| starlette | `starlette.background.BackgroundTask` (public) | 168.7 | 152.5 | 9.6% | 1.006x |
| starlette | `starlette.authentication.AuthCredentials` (public) | 152.7 | 136.5 | 10.6% | 1.136x |
| more-itertools | `more_itertools.more.peekable` (public) | 984.7 | 968.5 | 1.6% | 0.941x |
| more-itertools | `more_itertools.more.seekable` (public) | 296.7 | 280.5 | 5.4% | 1.697x |
| more-itertools | `more_itertools.more.bucket` (public) | 440.7 | 424.5 | 3.7% | 0.986x |
| more-itertools | `more_itertools.more.countable` (public) | 224.7 | 208.5 | 7.2% | 0.986x |
| more-itertools | `more_itertools.more.time_limited` (public) | 288.7 | 272.5 | 5.6% | 1.003x |
| werkzeug | `werkzeug.datastructures.etag.ETag` (public) | 88.7 | 72.5 | 18.2% | 0.977x |
| werkzeug | `werkzeug.datastructures.etag.ETagSet` (public) | 528.7 | 512.5 | 3.1% | 1.017x |
| werkzeug | `werkzeug.datastructures.range.Range` (public) | 208.7 | 192.5 | 7.7% | 1.003x |
| werkzeug | `werkzeug.datastructures.range.ContentRange` (public) | 112.6 | 96.5 | 14.3% | 1.252x |
| werkzeug | `werkzeug.datastructures.range.IfRange` (public) | 88.7 | 72.5 | 18.2% | 1.074x |
| tomli | `tomli._parser.Flags` | 368.7 | 352.5 | 4.4% | 0.970x |
| tomli | `tomli._parser.NestedDict` | 144.7 | 128.5 | 11.2% | 0.999x |
| tomli | `tomli._parser.Output` | 585.0 | 536.5 | 8.3% | 1.000x |
| tomli | `tomli._parser.DEPRECATED_DEFAULT` | 72.7 | 56.5 | 22.3% | 1.033x |

Median across all 19 classes: **heap -8.3%**, per-class
range 1.6%…22.3%, **throughput 1.006x**. This is
below the 40% target set for the day: on CPython 3.12 an empty instance dict is
only 64 B and the `__weakref__` slot gives 8 B back, so the measured saving here
is 8–49 B per instance (median about 16 B); wrapper objects that also own
iterators, tuples or strings show a modest percentage. The tool reports that
instead of inflating it.

The closure rule is measurable: in the earlier revision, patching
`starlette.routing.Host` alone saved only 3.5% because its base `BaseRoute` kept
the dict; adding the base to the same patch raised the saving to the value in the
table. The corrected run keeps the same closure, one weakref slot later.

## Gates

| gate | verdict | evidence / command |
| --- | --- | --- |
| G1 upstream suites | PASS (0 new failures) | starlette `4 failed / 1419 passed` both pristine and patched (same httpx2 header assertions); more-itertools `772 passed` both; tomli `17 passed / 1 skipped` both; werkzeug focused `100 passed` both. pyparsing `16 failed` vs pristine `0` → target rejected. |
| G2 history dedup | PASS | `0` commits in the last 24 months add `__slots__` inside a selected class; GitHub search: 6 issue/PR mentions of `__slots__` across the four repos, **0** of them patch a selected class (`results/gate.json`). |
| G2c weakref semantics | PASS | `results/weakref.json`: **19/19** accepted classes answer `weakref.ref(obj)() is obj`; child classes inherit `__weakref__` instead of redeclaring it (`tests/test_slotsgate.py::test_patched_chain_keeps_weakref`). |
| G2b behaviour differential | PASS | `results/diffcheck.json`: **1,029 unique factory variants** (literal sweeps, not repeated calls) across the 19 classes, pristine vs patched, **0 mismatches**. Each transcript compares `repr`, every slot value, `pickle.loads(pickle.dumps(...))` state and `copy.copy` state; `time_limited._start_time` is masked because it is a `time.monotonic()` reading. |
| G3 speedup | N/A | no speed claim; throughput is reported only to prove no regression (median 1.006x). |
| G4 large scale | N/A | heap measured at one fixed live-set size (10,000 objects per class). |
| G5 memory | PASS | heap reduction per class in the table; raw samples under `benchmark/raw/`. |

Reproduce a gate:

```bash
# tool self-check
python3 -m unittest discover -s tests -v          # 14 tests

# gate + patches (needs the four upstream checkouts; see targets/manifest.json)
python3 tools/prepare.py --manifest targets/manifest.json --work /tmp/slotswork

# heap/throughput, raw JSON written per class and implementation
/tmp/venv-sg/bin/python benchmark/bench.py --work /tmp/slotswork --n 10000 --repeats 2

# weakref gate: 19/19 accepted classes must answer weakref.ref(obj)()
/tmp/venv-sg/bin/python tools/weakref_check.py
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

**2026-11-20 修订**：首版生成器漏了 `__weakref__`，19 个公开类全部失去 weakref
支持；本版只给补丁链的根类加该槽（子类继承、不得重复声明），并在带槽的版本上重测
全部 heap 数字。`results/weakref.json` 为 19/19 实测，测试里钉死"根类有、子类无"。

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
tests/test_slotsgate.py  14 unit tests (analyzer, patch, weakref, history)
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
- The differential covers 1,029 unique constructor variants; 15 classes have literal
  variants, the four no-argument tomli classes contribute one each. Raw
  transcripts are under `benchmark/raw/diff-*.json`.
- `pyparsing` shows the gate working: the analyzer accepted five internal cache
  classes, but upstream tests caught behaviour the static rules cannot see.
