"""Never let generated code replace something real.

make_tool MUST call validate_new_plugin() BEFORE writing or hot-loading. It
refuses a reserved/already-live name, refuses to overwrite an existing plugin
file, and rejects placeholder/simulated code - exactly what put a fake stub
named 'desktop_agent' on the machine.
"""
from __future__ import annotations
import ast, re
from pathlib import Path

PLACEHOLDERS = (
    "placeholder", "simulated", "simulate", "in a real scenario",
    "actual logic not shown", "not implemented", "todo", "fixme",
    "assume we", "confirmation_pending", "for demo", "for this example",
)
FORBIDDEN_CALLS = {"eval", "exec", "compile", "__import__"}
FORBIDDEN_ATTRS = {("pyautogui", "press"), ("pyautogui", "hotkey"), ("os", "system"),
                   ("subprocess", "popen"), ("subprocess", "run"), ("subprocess", "call")}
ROOT = Path(__file__).resolve().parent.parent


def _stems(folder):
    try:
        return {p.stem for p in Path(folder).glob("*.py") if p.stem != "__init__"}
    except Exception:
        return set()


def default_reserved():
    return _stems(ROOT / "actions") | _stems(ROOT / "core") | {"make_tool", "call_tool"}


def default_plugin_dir():
    try:
        from core import plugin_runtime as RT
        for a in ("PLUGIN_DIR", "_PLUGIN_DIR", "DIR", "PLUGINS_DIR", "BASE"):
            v = getattr(RT, a, None)
            if v:
                return str(v)
    except Exception:
        pass
    return str(ROOT / "plugins")


def validate_new_plugin(name, source, *, reserved=None, plugin_dir=None, live_names=()):
    name = str(name or "")
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,40}", name):
        raise ValueError("invalid plugin name: %r" % name)
    reserved = default_reserved() if reserved is None else set(reserved)
    if name in reserved or name in set(live_names):
        raise ValueError("refusing to replace a live/reserved tool: %r" % name)
    p = Path(plugin_dir or default_plugin_dir()) / (name + ".py")
    if p.exists():
        raise ValueError("refusing to overwrite an existing plugin: %s" % p.name)

    low = str(source).casefold()
    hits = [m for m in PLACEHOLDERS if m in low]
    if hits:
        raise ValueError("placeholder/simulated code rejected: %s" % hits)

    tree = ast.parse(str(source))
    if not any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "run"
               for n in tree.body):
        raise ValueError("plugin has no run(parameters, player, session_memory)")
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Name) and f.id in FORBIDDEN_CALLS:
                raise ValueError("forbidden call: %s" % f.id)
            if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
                if (f.value.id, f.attr) in FORBIDDEN_ATTRS:
                    raise ValueError("forbidden call: %s.%s" % (f.value.id, f.attr))
    return True
