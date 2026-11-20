"""Turn a slot-safe class into a unified diff, and verify it applies."""

from __future__ import annotations

import ast
import difflib
from pathlib import Path

from .analyze import ClassInfo


class PatchError(RuntimeError):
    pass


def _insertion_point(source: str, info: ClassInfo) -> tuple[int, str]:
    """Return (0-based line index to insert at, indent string)."""
    tree = ast.parse(source)
    cls = None
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == info.qualname.rsplit(".", 1)[-1]:
            if node.lineno == info.lineno:
                cls = node
                break
    if cls is None:
        raise PatchError(f"class not found at {info.file}:{info.lineno}")
    first = cls.body[0]
    if first.lineno == cls.lineno:
        raise PatchError("single-line class body is not patchable")
    indent = " " * first.col_offset
    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
        return first.end_lineno, indent  # type: ignore[return-value]
    return first.lineno - 1, indent  # type: ignore[return-value]


def needs_weakref(info: ClassInfo, chosen: set[str]) -> bool:
    """A class must keep weakref support unless its patched base already has it.

    ``__weakref__`` is inherited from the nearest ancestor that declares it, and
    CPython raises ``TypeError`` when a subclass declares it twice.  So only the
    root of a patched chain gets it: a class whose internal bases are all in the
    same patch inherits the slot from that base.
    """
    return not any(base.qualname in chosen for base in info.internal_bases)


def slots_line(info: ClassInfo, include_weakref: bool = False) -> str:
    slots = info.slots + (("__weakref__",) if include_weakref else ())
    body = ", ".join(repr(s) for s in slots)
    if len(slots) == 1:
        body += ","
    return f"__slots__ = ({body})"


def render_patch(root: Path, infos: list[ClassInfo]) -> str:
    """Return a unified diff adding __slots__ to every info, in file order."""
    chosen = {i.qualname for i in infos}
    by_file: dict[str, list[ClassInfo]] = {}
    for info in infos:
        by_file.setdefault(info.file, []).append(info)

    chunks: list[str] = []
    for rel, group in sorted(by_file.items()):
        path = root / rel
        source = path.read_text(encoding="utf-8")
        lines = source.splitlines(keepends=True)
        inserts = []
        for info in group:
            idx, indent = _insertion_point(source, info)
            inserts.append((idx, indent, info))
        # Apply from the bottom so earlier line numbers stay valid.
        for idx, indent, info in sorted(inserts, key=lambda t: t[0], reverse=True):
            line = f"{indent}{slots_line(info, needs_weakref(info, chosen))}\n"
            if idx >= len(lines):
                lines.append(line)
            elif lines[idx - 1].strip() == "":
                lines.insert(idx, line + "\n")
            else:
                lines.insert(idx, "\n" + line)
        patched = "".join(lines)
        diff = difflib.unified_diff(
            source.splitlines(keepends=True),
            patched.splitlines(keepends=True),
            fromfile=f"a/{rel}",
            tofile=f"b/{rel}",
            n=3,
        )
        chunks.append("".join(diff))
    return "".join(chunks)


def apply_to_tree(root: Path, infos: list[ClassInfo]) -> None:
    """In-place edit used for the optimized variant (diff is generated first)."""
    chosen = {i.qualname for i in infos}
    by_file: dict[str, list[ClassInfo]] = {}
    for info in infos:
        by_file.setdefault(info.file, []).append(info)
    for rel, group in by_file.items():
        path = root / rel
        source = path.read_text(encoding="utf-8")
        lines = source.splitlines(keepends=True)
        inserts = [(i, ind) for i, ind in (_insertion_point(source, info) for info in group)]
        for (idx, indent), info in sorted(zip(inserts, group), key=lambda t: t[0][0], reverse=True):
            line = f"{indent}{slots_line(info, needs_weakref(info, chosen))}\n"
            if idx >= len(lines):
                lines.append(line)
            elif lines[idx - 1].strip() == "":
                lines.insert(idx, line + "\n")
            else:
                lines.insert(idx, "\n" + line)
        path.write_text("".join(lines), encoding="utf-8")