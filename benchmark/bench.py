#!/usr/bin/env python3
"""Heap/throughput measurement for the slot rewrite.

For every selected class, measures live heap and instance-creation time in a
fresh subprocess against the pristine and the patched upstream checkout.  Raw
subprocess output is kept under benchmark/raw/.

Usage:
  python benchmark/bench.py --gate results/gate.json --work /tmp/slotswork \
      --out results/heap.json
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def environment() -> dict:
    cpu = ""
    try:
        for line in subprocess.run(["lscpu"], capture_output=True, text=True).stdout.splitlines():
            if line.startswith("Model name:"):
                cpu = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    mem_kb = 0
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                mem_kb = int(line.split()[1])
                break
    except OSError:
        pass
    return {
        "cpu": cpu,
        "mem_total_kb": mem_kb,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "probe": "tracemalloc.get_traced_memory() delta after gc.collect(), creation timed with time.perf_counter()",
    }


def run_probe(repo: Path, pkg_parent: str, pkg: str, cls: dict, n: int, repeats: int, setup: str | None) -> dict:
    spec = {
        "module": None,
        "attr": cls["attr"].split(".")[-1],
        "factory": cls["factory"],
        "touch": cls["touch"],
        "n": n,
        "repeats": repeats,
    }
    # The manifest stores the import module separately from the attribute path.
    spec["module"] = cls["module"]
    if setup:
        spec["setup"] = setup
    env = dict(os.environ, PYTHONPATH=str(repo / pkg_parent if pkg_parent != "." else repo))
    proc = subprocess.run(
        [sys.executable, str(ROOT / "slotsgate/probe.py"), json.dumps(spec)],
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr[-800:])
    return json.loads(proc.stdout)


def median_sample(samples: list[dict], key: str) -> float:
    return statistics.median(s[key] for s in samples)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gate", default=str(ROOT / "results/gate.json"))
    ap.add_argument("--work", default="/tmp/slotswork")
    ap.add_argument("--out", default=str(ROOT / "results/heap.json"))
    ap.add_argument("--n", type=int, default=100000)
    ap.add_argument("--repeats", type=int, default=3)
    args = ap.parse_args()

    gate = json.loads(Path(args.gate).read_text())
    work = Path(args.work)
    raw_dir = ROOT / "benchmark/raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    out = {"environment": environment(), "n_instances": args.n, "repeats": args.repeats, "libraries": []}

    for lib in gate["libraries"]:
        entry = {"name": lib["name"], "upstream": lib["upstream"], "commit": lib["commit"],
                 "license": lib["license"], "classes": []}
        for cls in lib["classes"]:
            if not cls.get("factory"):
                continue
            module = cls["qualname"].rsplit(".", 1)[0]
            cls = dict(cls, module=module)
            rows = {}
            for impl in ("baseline", "optimized"):
                repo = work / f"{lib['name']}-{'orig' if impl == 'baseline' else 'opt'}"
                t0 = time.time()
                res = run_probe(repo, lib["pkg_parent"], lib["pkg"], cls, args.n, args.repeats, lib.get("setup"))
                raw_name = f"{lib['name']}-{cls['attr'].split('.')[-1]}-{impl}.json"
                (raw_dir / raw_name).write_text(json.dumps(res, indent=2) + "\n")
                rows[impl] = {
                    "per_instance_bytes": median_sample(res["samples"], "per_instance_bytes"),
                    "ns_per_instance": median_sample(res["samples"], "ns_per_instance"),
                    "rss_kb": median_sample(res["samples"], "rss_kb"),
                    "heap_bytes": median_sample(res["samples"], "heap_bytes"),
                    "samples": res["samples"],
                    "raw": f"benchmark/raw/{raw_name}",
                    "seconds": round(time.time() - t0, 2),
                }
            b, o = rows["baseline"], rows["optimized"]
            entry["classes"].append(
                {
                    "qualname": cls["qualname"],
                    "public": cls["public"],
                    "slots": cls["slots"],
                    "baseline": b,
                    "optimized": o,
                    "heap_reduction_pct": (1 - o["per_instance_bytes"] / b["per_instance_bytes"]) * 100,
                    "throughput_ratio": b["ns_per_instance"] / o["ns_per_instance"],
                }
            )
            print(f"{lib['name']:16s} {cls['qualname']:42s} "
                  f"{b['per_instance_bytes']:7.1f} -> {o['per_instance_bytes']:7.1f} B "
                  f"({(1 - o['per_instance_bytes']/b['per_instance_bytes'])*100:5.1f}%) "
                  f"tp {b['ns_per_instance']/o['ns_per_instance']:.3f}x")
        entry["median_heap_reduction_pct"] = statistics.median(
            c["heap_reduction_pct"] for c in entry["classes"]
        )
        entry["median_throughput_ratio"] = statistics.median(
            c["throughput_ratio"] for c in entry["classes"]
        )
        out["libraries"].append(entry)

    out["all_classes"] = sum(len(l["classes"]) for l in out["libraries"])
    out["median_heap_reduction_pct"] = statistics.median(
        c["heap_reduction_pct"] for l in out["libraries"] for c in l["classes"]
    )
    out["median_throughput_ratio"] = statistics.median(
        c["throughput_ratio"] for l in out["libraries"] for c in l["classes"]
    )
    (Path(args.out)).write_text(json.dumps(out, indent=2) + "\n")
    print(f"\nclasses={out['all_classes']} median heap -{out['median_heap_reduction_pct']:.1f}% "
          f"median throughput {out['median_throughput_ratio']:.3f}x")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())