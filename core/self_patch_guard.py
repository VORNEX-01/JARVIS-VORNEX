"""Refuse a candidate change before it can do harm.

Refuses: syntax errors, NEW duplicate top-level defs (relative to the old file -
pre-existing ones are allowed so a clean-up is not blocked), and any change to an
EXISTING function's signature/defaults (what broke us with _conv_ok)."""
from __future__ import annotations
import ast


class UnsafePatch(ValueError):
    pass


def _inspect(src, fn):
    try:
        compile(src, fn, "exec"); tree = ast.parse(src, filename=fn)
    except (SyntaxError, ValueError) as e:
        raise UnsafePatch("invalid Python: %s" % e) from e
    names = [n.name for n in tree.body
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
    dups = {n for n in names if names.count(n) > 1}
    sigs = {}

    def walk(node, scope):
        for n in node.body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                key = ".".join([*scope, n.name])
                sigs[key] = ast.dump(n.args) + "|" + (ast.dump(n.returns) if n.returns else "")
                walk(n, [*scope, n.name])
            elif isinstance(n, ast.ClassDef):
                walk(n, [*scope, n.name])

    walk(tree, [])
    return sigs, dups


def validate_candidate(old_src, new_src, filename):
    old_sigs, old_dup = _inspect(old_src, filename)
    new_sigs, new_dup = _inspect(new_src, filename)
    added = sorted(new_dup - old_dup)
    if added:
        raise UnsafePatch("NEW duplicate top-level definitions: %s" % added)
    changed = sorted(k for k in old_sigs.keys() & new_sigs.keys()
                     if old_sigs[k] != new_sigs[k])
    if changed:
        raise UnsafePatch("existing function signature/default changed: %s" % changed)
