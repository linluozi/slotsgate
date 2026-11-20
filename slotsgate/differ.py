"""Execute a set of factory variants and emit canonical behaviour digests."""

from __future__ import annotations

import copy
import hashlib
import importlib
import json
import pickle
import sys
import re
import traceback

ADDR = re.compile(r"0x[0-9a-fA-F]+")


def norm(text: str) -> str:
    """Default object/function reprs embed heap addresses; mask them."""
    return ADDR.sub("0xADDR", text)


def resolve(module_name: str, attr: str):
    mod = importlib.import_module(module_name)
    return getattr(mod, attr)


def record(obj, attrs: list[str], volatile: list[str] | None = None) -> dict:
    volatile = set(volatile or [])
    rec: dict = {"repr": norm(repr(obj)), "type": type(obj).__name__}
    present = {}
    for name in attrs:
        try:
            present[name] = "<volatile>" if name in volatile else norm(repr(getattr(obj, name)))
        except AttributeError:
            present[name] = "<missing>"
    rec["attrs"] = present
    try:
        # Compare the post-round-trip object, not the pickled bytes: __slots__
        # legitimately changes the pickle stream while preserving semantics.
        back = pickle.loads(pickle.dumps(obj, protocol=5))
        rt = {"repr": norm(repr(back)),
              "attrs": {n: ("<volatile>" if n in volatile else norm(repr(getattr(back, n)))) for n in attrs}}
        rec["pickle_roundtrip"] = rt
    except Exception as exc:  # noqa: BLE001 - the exception itself is the observation
        rec["pickle_error"] = f"{type(exc).__name__}: {norm(str(exc))}"
    try:
        rec["copy"] = norm(repr(copy.copy(obj)))
    except Exception as exc:  # noqa: BLE001
        rec["copy_error"] = f"{type(exc).__name__}: {norm(str(exc))}"
    return rec


def main(spec_json: str) -> int:
    spec = json.loads(spec_json)
    cls = resolve(spec["module"], spec["attr"])
    ns = {"cls": cls}
    if spec.get("setup"):
        exec(spec["setup"], ns)  # noqa: S102 - trusted manifest setup
    out = []
    for expr in spec["variants"]:
        try:
            obj = eval(expr, ns)  # noqa: S307 - own manifest
            rec = {"ok": True, "value": record(obj, spec.get("attrs", []), spec.get("volatile"))}
        except Exception as exc:  # noqa: BLE001
            rec = {"ok": False, "error": f"{type(exc).__name__}: {norm(str(exc))}"}
            if spec.get("traceback"):
                rec["tb"] = traceback.format_exc()[-500:]
        canonical = json.dumps(rec, sort_keys=True, ensure_ascii=True)
        out.append({"expr": expr, "sha256": hashlib.sha256(canonical.encode()).hexdigest(),
                    "record": rec})
    print(json.dumps({"module": spec["module"], "attr": spec["attr"], "items": out}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))