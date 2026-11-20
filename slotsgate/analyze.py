"""Static analysis for __slots__ safety.

The analyzer only accepts classes for which every attribute the class code
assigns to ``self`` is statically enumerable.  Anything that can create
attributes at runtime (``setattr``, ``__dict__``, ``vars()``, custom
``__getattr__``/``__setattr__``) disqualifies the class: a slot-only instance
would raise AttributeError at the first dynamic write instead of silently
growing a dict.
"""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass, field
from pathlib import Path

DYNAMIC_HOOKS = {
    "__getattr__",
    "__setattr__",
    "__delattr__",
    "__getstate__",
    "__setstate__",
    "__reduce__",
    "__reduce_ex__",
    "__copy__",
    "__deepcopy__",
}
# Classes whose instances must keep a mutable namespace.
DYNAMIC_BASES = {
    "Exception",
    "BaseException",
    "dict",
    "list",
    "set",
    "tuple",
    "type",
    "ABC",
    "ABCMeta",
    "Enum",
    "NamedTuple",
    "Generic",
    "Protocol",
    "object",
}


@dataclass
class ClassInfo:
    module: str
    qualname: str
    file: str
    lineno: int
    end_lineno: int
    bases: list[str]
    decorators: list[str]
    class_vars: set[str]
    attrs: set[str]
    methods: set[str]
    has_slots: bool = False
    dynamic_reason: str | None = None
    internal_bases: list["ClassInfo"] = field(default_factory=list)
    external_bases: list[str] = field(default_factory=list)
    slots: tuple[str, ...] = ()
    status: str = "candidate"  # candidate | rejected | already_slotted
    reason: str = ""


def _class_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ast.unparse(node)


def _is_self(node: ast.expr) -> bool:
    return isinstance(node, ast.Name) and node.id == "self"


def _walk_method_calls(func: ast.AST):
    for node in ast.walk(func):
        yield node


def _analyse_class(cls: ast.ClassDef, module: str, file: str) -> ClassInfo:
    decorators = [_class_name(d) for d in cls.decorator_list]
    bases = [_class_name(b) for b in cls.bases]
    class_vars: set[str] = set()
    attrs: set[str] = set()
    methods: set[str] = set()
    has_slots = False
    dynamic: str | None = None

    for stmt in cls.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            methods.add(stmt.name)
            if stmt.name in DYNAMIC_HOOKS:
                dynamic = f"defines {stmt.name}"
            for dec in stmt.decorator_list:
                if _class_name(dec) == "cached_property":
                    dynamic = "method uses cached_property (needs __dict__)"
            if any(_is_self(n.value) and n.attr == "__dict__" for n in ast.walk(stmt) if isinstance(n, ast.Attribute)):
                dynamic = "touches self.__dict__"
            for n in ast.walk(stmt):
                if isinstance(n, ast.Call):
                    f = n.func
                    fname = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else "")
                    if fname in {"setattr", "delattr", "vars"} and n.args and _is_self(n.args[0]):
                        dynamic = f"calls {fname}(self, ...)"
                if isinstance(n, ast.Attribute) and isinstance(n.ctx, (ast.Store, ast.Del)) and _is_self(n.value):
                    if n.attr == "__dict__":
                        dynamic = "assigns self.__dict__"
                    else:
                        attrs.add(n.attr)
        elif isinstance(stmt, (ast.Assign, ast.AnnAssign)):
            targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
            for t in targets:
                if isinstance(t, ast.Name):
                    if t.id == "__slots__":
                        has_slots = True
                    else:
                        class_vars.add(t.id)

    info = ClassInfo(
        module=module,
        qualname=f"{module}.{cls.name}",
        file=file,
        lineno=cls.lineno,
        end_lineno=cls.end_lineno or cls.lineno,
        bases=bases,
        decorators=decorators,
        class_vars=class_vars,
        attrs=attrs,
        methods=methods,
        has_slots=has_slots,
        dynamic_reason=dynamic,
    )
    if has_slots:
        info.status = "already_slotted"
        info.reason = "class already defines __slots__"
    elif decorators:
        info.status = "rejected"
        info.reason = "decorated class (metaclass/generator may own the layout)"
    elif dynamic:
        info.status = "rejected"
        info.reason = dynamic
    return info


def scan_package(package_dir: str, module_prefix: str) -> list[ClassInfo]:
    """Scan all module-level classes below ``package_dir``."""
    root = Path(package_dir)
    infos: list[ClassInfo] = []
    by_simple: dict[str, list[ClassInfo]] = {}
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root.parent)
        module = str(rel.with_suffix("")).replace(os.sep, ".")
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            info = _analyse_class(node, module, str(rel))
            infos.append(info)
            by_simple.setdefault(node.name, []).append(info)

    def resolve(base: str) -> ClassInfo | None:
        found = by_simple.get(base)
        if found and len(found) == 1:
            return found[0]
        return None

    # Link bases, decide inheritance safety bottom-up (iterative fixed point).
    for info in infos:
        for b in info.bases:
            target = resolve(b)
            if target is not None and not target.has_slots:
                info.internal_bases.append(target)
            else:
                info.external_bases.append(b)

    changed = True
    while changed:
        changed = False
        for info in infos:
            if info.status != "candidate":
                continue
            if any(b.status != "candidate" and b.status != "already_slotted" for b in info.internal_bases):
                info.status = "rejected"
                info.reason = "base class is not slot-safe"
                changed = True
            elif any(b != "object" for b in info.external_bases):
                fmt = ", ".join(info.external_bases)
                info.status = "rejected"
                info.reason = f"external base {fmt!r} may own a __dict__"
                changed = True
            elif info.class_vars & info.attrs:
                clash = ", ".join(sorted(info.class_vars & info.attrs))
                info.status = "rejected"
                info.reason = f"class variable conflicts with instance attribute: {clash}"
                changed = True

    # Compute slots: every statically assigned attribute not inherited.
    for info in infos:
        if info.status != "candidate":
            continue
        inherited: set[str] = set()
        for base in info.internal_bases:
            inherited |= set(base.slots)
        own = tuple(sorted(info.attrs - inherited))
        info.slots = own
        # A slot named like a class variable is a hard ValueError at import.
        if set(own) & info.class_vars:
            info.status = "rejected"
            info.reason = "slot name conflicts with class variable"
    return infos


def summarize(infos: list[ClassInfo]) -> dict:
    counts: dict[str, int] = {}
    for info in infos:
        counts[info.status] = counts.get(info.status, 0) + 1
    return {
        "total_classes": len(infos),
        "counts": counts,
        "candidates": [
            {
                "qualname": i.qualname,
                "file": i.file,
                "lineno": i.lineno,
                "slots": list(i.slots),
                "bases": i.bases,
            }
            for i in infos
            if i.status == "candidate"
        ],
    }