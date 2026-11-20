"""Unit tests for the analyzer, patcher and history gate (stdlib only)."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from slotsgate.analyze import scan_package  # noqa: E402
from slotsgate.history import slot_history_hits  # noqa: E402
from slotsgate.patch import PatchError, apply_to_tree, render_patch  # noqa: E402

SRC = '''
class Plain:
    def __init__(self, a, b):
        self.a = a
        self.b = b


class Child(Plain):
    def __init__(self, a, b, c):
        super().__init__(a, b)
        self.c = c


class Dynamic:
    def __init__(self):
        self.__dict__["x"] = 1


class Setattr:
    def __init__(self, k):
        setattr(self, k, 1)


class Cached:
    @cached_property
    def value(self):
        return 1


class WithDefault:
    kind = "x"

    def __init__(self):
        self.kind = "y"


class External(Exception):
    def __init__(self, msg):
        self.msg = msg


@dataclass
class Decorated:
    x: int


class AlreadySlotted:
    __slots__ = ("a",)


class Single: pass
'''


class AnalyzerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name) / "pkg"
        root.mkdir()
        (root / "__init__.py").write_text("")
        (root / "mod.py").write_text(SRC)
        (root / "single.py").write_text("class Single: pass\n")
        self.root = root
        self.infos = {i.qualname.rsplit(".", 1)[-1]: i for i in scan_package(str(root), "pkg")}

    def tearDown(self):
        self.tmp.cleanup()

    def test_plain_slots(self):
        info = self.infos["Plain"]
        self.assertEqual(info.status, "candidate")
        self.assertEqual(info.slots, ("a", "b"))

    def test_child_subtracts_inherited_slots(self):
        info = self.infos["Child"]
        self.assertEqual(info.status, "candidate")
        self.assertEqual(info.slots, ("c",))

    def test_dict_access_rejected(self):
        self.assertEqual(self.infos["Dynamic"].status, "rejected")

    def test_setattr_rejected(self):
        self.assertEqual(self.infos["Setattr"].status, "rejected")

    def test_cached_property_rejected(self):
        self.assertEqual(self.infos["Cached"].status, "rejected")

    def test_class_var_conflict_rejected(self):
        self.assertEqual(self.infos["WithDefault"].status, "rejected")

    def test_external_base_rejected(self):
        self.assertEqual(self.infos["External"].status, "rejected")

    def test_decorated_rejected(self):
        self.assertEqual(self.infos["Decorated"].status, "rejected")

    def test_already_slotted(self):
        self.assertEqual(self.infos["AlreadySlotted"].status, "already_slotted")

    def test_single_line_rejected_on_patch(self):
        info = self.infos["Single"]
        with self.assertRaises(PatchError):
            render_patch(self.root.parent, [info])

    def test_patch_applies_and_keeps_behavior(self):
        chosen = [self.infos["Plain"], self.infos["Child"]]
        patch = render_patch(self.root.parent, chosen)
        self.assertIn("__slots__ = ('a', 'b')", patch)
        self.assertIn("__slots__ = ('c',)", patch)
        target = Path(self.tmp.name) / "apply"
        (target / "pkg").mkdir(parents=True)
        (target / "pkg" / "mod.py").write_text(SRC)
        proc = subprocess.run(["git", "apply", "--check", "-"], input=patch, cwd=target,
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_apply_to_tree(self):
        apply_to_tree(self.root.parent, [self.infos["Plain"]])
        text = (self.root / "mod.py").read_text()
        self.assertIn("__slots__ = ('a', 'b')", text)
        compile(text, "mod.py", "exec")


class HistoryTest(unittest.TestCase):
    def test_detects_recent_slot_addition(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "pkg").mkdir()
            f = repo / "pkg" / "m.py"
            f.write_text("class A:\n    def __init__(self):\n        self.x = 1\n")
            run = lambda *a: subprocess.run(["git", *a], cwd=repo, capture_output=True, text=True)
            run("init", "-q")
            run("config", "user.email", "t@example.com")
            run("config", "user.name", "t")
            run("add", ".")
            run("commit", "-qm", "base")
            f.write_text("class A:\n    __slots__ = ('x',)\n\n    def __init__(self):\n        self.x = 1\n")
            run("add", ".")
            run("commit", "-qm", "slot A")
            hits = slot_history_hits(repo, "pkg/m.py", "A")
            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0]["subject"], "slot A")
            self.assertEqual(slot_history_hits(repo, "pkg/m.py", "B"), [])


if __name__ == "__main__":
    unittest.main()