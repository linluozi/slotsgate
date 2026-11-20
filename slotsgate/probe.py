"""Subprocess heap/throughput probe for one class and one implementation."""

from __future__ import annotations

import gc
import importlib
import json
import resource
import sys
import time
import tracemalloc


def _resolve(module_name: str, dotted: str):
    obj = importlib.import_module(module_name)
    for part in dotted.split("."):
        obj = getattr(obj, part)
    return obj


def main(spec_json: str) -> int:
    spec = json.loads(spec_json)
    cls = _resolve(spec["module"], spec["attr"])
    expr = spec["factory"]  # trusted manifest expression, e.g. "cls([1, 2, 3])"
    ns = {"cls": cls}
    if spec.get("setup"):
        exec(spec["setup"], ns)  # noqa: S102 - trusted manifest setup
    n = int(spec["n"])
    repeats = int(spec.get("repeats", 3))
    out: dict = {"spec": spec, "samples": []}

    for _ in range(repeats):
        gc.collect()
        tracemalloc.start()
        base = tracemalloc.get_traced_memory()[0]
        objs = [eval(expr, ns) for _ in range(n)]  # noqa: S307 - own manifest
        gc.collect()
        cur, peak = tracemalloc.get_traced_memory()
        heap_delta = cur - base
        # Touch every attribute recorded in the slot list so both variants
        # actually materialise their storage.
        for attr in spec.get("touch", []):
            for o in objs:
                getattr(o, attr, None)
        tracemalloc.stop()
        del objs
        gc.collect()

        # Throughput without tracemalloc's allocation hooks.
        t0 = time.perf_counter()
        objs = [eval(expr, ns) for _ in range(n)]  # noqa: S307
        elapsed = time.perf_counter() - t0
        del objs
        gc.collect()

        rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        out["samples"].append(
            {
                "heap_bytes": heap_delta,
                "per_instance_bytes": heap_delta / n,
                "peak_bytes": peak,
                "rss_kb": rss_kb,
                "create_seconds": elapsed,
                "ns_per_instance": elapsed / n * 1e9,
            }
        )
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))