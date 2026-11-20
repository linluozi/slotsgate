#!/usr/bin/env python3
"""Assemble baseline.json / optimized.json / table.md from heap.json."""
from __future__ import annotations

import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
heap = json.loads((ROOT / "results/heap.json").read_text())
tests_path = ROOT / "results/upstream_tests.json"
tests = json.loads(tests_path.read_text()) if tests_path.exists() else {}


def class_row(lib: dict, c: dict) -> dict:
    b, o = c["baseline"], c["optimized"]
    return {
        "class": c["qualname"],
        "public": c["public"],
        "slots": c["slots"],
        "baseline_bytes": round(b["per_instance_bytes"], 1),
        "optimized_bytes": round(o["per_instance_bytes"], 1),
        "heap_reduction_pct": round(c["heap_reduction_pct"], 1),
        "baseline_ns": round(b["ns_per_instance"], 1),
        "optimized_ns": round(o["ns_per_instance"], 1),
        "throughput_ratio": round(c["throughput_ratio"], 3),
        "raw_baseline": b["raw"],
        "raw_optimized": o["raw"],
    }


baseline = {"environment": heap["environment"], "n_instances_per_class": heap["n_instances"],
            "repeats": heap["repeats"], "upstream_tests": tests, "libraries": []}
optimized = {"environment": heap["environment"], "n_instances_per_class": heap["n_instances"],
             "repeats": heap["repeats"], "upstream_tests": tests, "libraries": []}
rows = []
for lib in heap["libraries"]:
    b_classes, o_classes = [], []
    for c in lib["classes"]:
        row = class_row(lib, c)
        rows.append((lib["name"], lib["upstream"], row))
        b_classes.append({k: row[k] for k in ("class", "public", "slots", "baseline_bytes", "baseline_ns")})
        o_classes.append({k: row[k] for k in ("class", "public", "optimized_bytes", "optimized_ns", "heap_reduction_pct", "throughput_ratio")})
    baseline["libraries"].append({"name": lib["name"], "upstream": lib["upstream"], "classes": b_classes})
    optimized["libraries"].append({"name": lib["name"], "upstream": lib["upstream"], "classes": o_classes})

baseline["median_throughput_ratio"] = heap["median_throughput_ratio"]
optimized["median_heap_reduction_pct"] = heap["median_heap_reduction_pct"]
optimized["median_throughput_ratio"] = heap["median_throughput_ratio"]
optimized["class_count"] = heap["all_classes"]
(ROOT / "benchmark/baseline.json").write_text(json.dumps(baseline, indent=2) + "\n")
(ROOT / "benchmark/optimized.json").write_text(json.dumps(optimized, indent=2) + "\n")

lines = ["| library | class | baseline B/inst | patched B/inst | heap reduction | throughput |",
         "| --- | --- | ---: | ---: | ---: | ---: |"]
for lib_name, _, row in rows:
    lines.append(
        f"| {lib_name} | `{row['class']}`{' (public)' if row['public'] else ''} | "
        f"{row['baseline_bytes']:.1f} | {row['optimized_bytes']:.1f} | "
        f"{row['heap_reduction_pct']:.1f}% | {row['throughput_ratio']:.3f}x |"
    )
(ROOT / "results/table.md").write_text("\n".join(lines) + "\n")
print(f"{len(rows)} classes; median heap -{heap['median_heap_reduction_pct']:.1f}%; "
      f"median throughput {heap['median_throughput_ratio']:.3f}x")