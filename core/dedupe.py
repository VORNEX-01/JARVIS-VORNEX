"""Remove duplicate top-level defs SAFELY. Keeps the LAST (Python's rule) and
drops an earlier def ONLY when no top-level statement after it loads that name -
e.g. the '_SAVE_AS_BASE = ... or _save_as_v2' capture keeps the previous def."""
from __future__ import annotations
import ast
from pathlib import Path


def _defs(tree):
    out = {}
    for i, n in enumerate(tree.body):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.setdefault(n.name, []).append((i, n))
    return out


def _loaded_after(tree, start, name):
    for n in tree.body[start + 1:]:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for d in getattr(n, "decorator_list", []):
                if any(isinstance(x, ast.Name) and x.id == name for x in ast.walk(d)):
                    return True
            continue
        for x in ast.walk(n):
            if isinstance(x, ast.Name) and x.id == name and isinstance(x.ctx, ast.Load):
                return True
    return False


def plan(path):
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    rep = {}
    for name, defs in _defs(tree).items():
        if len(defs) < 2:
            continue
        removable, kept = [], []
        for i, n in defs[:-1]:
            (kept if _loaded_after(tree, i, name) else removable).append(n.lineno)
        rep[name] = {"keep_line": defs[-1][1].lineno,
                     "removable_lines": removable, "must_keep_earlier": kept}
    return rep


def apply_file(path, message="dedupe: drop dead earlier top-level defs"):
    from core.self_patch import apply_edit
    p = Path(path)
    src = p.read_text(encoding="utf-8")
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)
    kill = set()
    for name, defs in _defs(tree).items():
        for i, n in defs[:-1]:
            if _loaded_after(tree, i, name):
                continue
            first = min([n.lineno] + [d.lineno for d in getattr(n, "decorator_list", [])])
            kill.update(range(first - 1, n.end_lineno))
    if not kill:
        return False, "nothing safely removable in %s" % p.name
    return apply_edit(p, "".join(l for i, l in enumerate(lines) if i not in kill), message)
