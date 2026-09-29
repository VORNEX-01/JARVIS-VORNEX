"""core/plugin_runtime.py — the LIVE plugin registry.

plugin_loader discovers plugins/ only at startup, and Gemini Live freezes its tool
list at connect. So a plugin created DURING a session could never be called. This
registry is what make_tool adds to and call_tool dispatches to, so a tool built
mid-session works immediately, with no restart.
"""
from __future__ import annotations
import importlib.util, json, py_compile, time
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent
_PLUGINS = _BASE / "plugins"
_LEARN = _BASE / "memory" / "learned_tools.json"
_REGISTRY: dict = {}


def _learn(name, purpose, ok, err=""):
    try:
        _LEARN.parent.mkdir(parents=True, exist_ok=True)
        data = []
        if _LEARN.exists():
            try: data = json.loads(_LEARN.read_text(encoding="utf-8"))
            except Exception: data = []
        data.append({"name": name, "purpose": purpose, "ok": bool(ok),
                     "error": str(err)[:200], "at": time.strftime("%Y-%m-%d %H:%M")})
        _LEARN.write_text(json.dumps(data[-300:], ensure_ascii=False, indent=2),
                          encoding="utf-8")
    except Exception:
        pass


def _import(path: Path, name: str):
    mod_name = "vornex_dyn_%s_%d" % (name, int(time.time() * 1000) % 1000000)
    spec = importlib.util.spec_from_file_location(mod_name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def install(name: str, source: str, purpose: str = ""):
    name = str(name or "").strip()
    if not name or not name.replace("_", "a").isalnum() or name[0].isdigit():
        return False, "bad tool name %r (use snake_case)" % name
    _PLUGINS.mkdir(parents=True, exist_ok=True)
    path = _PLUGINS / (name + ".py")
    backup = path.read_text(encoding="utf-8") if path.exists() else None
    try:
        path.write_text(source, encoding="utf-8")
        py_compile.compile(str(path), doraise=True)
        mod = _import(path, name)
        meta, run = getattr(mod, "PLUGIN", None), getattr(mod, "run", None)
        if not isinstance(meta, dict) or not callable(run):
            raise ValueError("plugin must define PLUGIN (dict) and run()")
        pname = str(meta.get("name") or name)
        _REGISTRY[pname] = {"run": run, "schema": meta.get("parameters") or {},
                            "file": str(path),
                            "description": str(meta.get("description") or purpose)}
        _learn(name, purpose or meta.get("description", ""), True)
        return True, "live: %s" % pname
    except Exception as e:
        if backup is not None:
            try: path.write_text(backup, encoding="utf-8")
            except Exception: pass
        else:
            try: path.unlink()
            except Exception: pass
        _learn(name, purpose, False, repr(e))
        return False, repr(e)


def invoke(name: str, args: dict, player=None, memory=None):
    rec = _REGISTRY.get(str(name or "").strip())
    if rec is None:
        return None, ("No live tool named %r. Live tools: %s"
                      % (name, ", ".join(sorted(_REGISTRY)) or "(none)"))
    try:
        return True, str(rec["run"](args or {}, player=player, session_memory=memory))
    except Exception as e:
        return False, "Tool %r crashed: %r" % (name, e)


def names():
    return sorted(_REGISTRY)


def schema(name: str):
    rec = _REGISTRY.get(str(name or "").strip())
    return rec["schema"] if rec else None
