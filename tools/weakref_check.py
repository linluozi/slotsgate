import importlib, json, subprocess, sys, weakref
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
gate = json.loads((ROOT / "results/gate.json").read_text())
work = Path("/tmp/slotswork")
code = r'''
import importlib, json, sys, weakref
spec = json.loads(sys.argv[1])
mod = importlib.import_module(spec["module"])
cls = getattr(mod, spec["attr"].split(".")[-1])
ns = {"cls": cls}
if spec.get("setup"):
    exec(spec["setup"], ns)
obj = eval(spec["factory"], ns)
try:
    r = weakref.ref(obj)
    ok = r() is obj
    err = None
except Exception as e:
    ok, err = False, f"{type(e).__name__}: {e}"
print(json.dumps({"module": spec["module"], "attr": spec["attr"], "weakref_ok": ok, "error": err}))
'''
out = {"classes": [], "total": 0, "ok": 0}
for lib in gate["libraries"]:
    repo = work / f"{lib['name']}-opt"
    env = {"PYTHONPATH": str(repo / lib["pkg_parent"] if lib["pkg_parent"] != "." else repo), "PATH": "/usr/bin:/bin"}
    for cls in lib["classes"]:
        if not cls.get("factory"):
            continue
        spec = {"module": cls["qualname"].rsplit(".", 1)[0], "attr": cls["attr"],
                "factory": cls["factory"], "setup": lib.get("setup")}
        p = subprocess.run([sys.executable, "-c", code, json.dumps(spec)], capture_output=True, text=True, env=env)
        row = json.loads(p.stdout) if p.returncode == 0 else {"error": p.stderr[-300:], "weakref_ok": False}
        row["lib"] = lib["name"]
        out["classes"].append(row)
        out["total"] += 1
        out["ok"] += 1 if row.get("weakref_ok") else 0
Path("/tmp/sg/results/weakref.json").write_text(json.dumps(out, indent=2) + "\n")
print(f"{out['ok']}/{out['total']} weakref-able")
for r in out["classes"]:
    if not r.get("weakref_ok"):
        print("FAIL", r)
