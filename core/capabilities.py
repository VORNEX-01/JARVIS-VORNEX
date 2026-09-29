"""Self-extension: know what the assistant CAN do, and provision what it cannot.

A capability is a named, LIVE-probed ability (never a claim). available() runs
the probe now. missing() tells what a task needs but the assistant lacks - so it
can ASK the user, build it (actions/make_tool.py), then RE-CHECK, and only claim
success if the probe passes afterwards.
"""
from __future__ import annotations
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_REG = {}


def register(cid, probe, *, how="", purpose=""):
    _REG[cid] = {"probe": probe, "how": how, "purpose": purpose}


def _importable(mod):
    try:
        return importlib.util.find_spec(mod) is not None
    except Exception:
        return False


def _has_vision():
    try:
        from core import screen_eye as E
        return bool(E._first_key()) and E.snapshot()[1] > 0
    except Exception:
        return False


def _has_memory():
    return (ROOT / "core" / "memory.py").exists() or (ROOT / ".jarvis" / "memory.json").exists()


def available(cid):
    e = _REG.get(cid)
    if not e:
        return False
    try:
        return bool(e["probe"]())
    except Exception:
        return False


def list_all():
    return {c: available(c) for c in sorted(_REG)}


def missing(needed):
    return [c for c in needed if not available(c)]


def describe():
    lines = []
    for c, e in sorted(_REG.items()):
        lines.append("%-20s %-8s %s" % (c, "OK" if available(c) else "MISSING",
                                        e.get("purpose", "")))
    return "\n".join(lines)


def ensure(cid, ask, build=None):
    """ask(title, detail)->bool ; build(cid, how)->(ok, msg). Re-verifies after."""
    e = _REG.get(cid)
    if not e:
        return False, "unknown capability '%s'" % cid
    if available(cid):
        return True, "'%s' is already available" % cid
    if not ask(title="Add the '%s' capability?" % cid, detail=(e["how"] or "")[:280]):
        return False, "you declined - I will not add '%s'" % cid
    if build is None:
        return False, "approved, but no builder is wired for '%s'" % cid
    try:
        ok, msg = build(cid, e["how"])
    except Exception as ex:
        return False, "build of '%s' raised: %s" % (cid, ex)
    if available(cid):
        return True, "'%s' added and VERIFIED" % cid
    return False, "'%s' still not available after building (%s)" % (cid, msg)


register("screen_vision", _has_vision,
         how="core/screen_eye.py (mss + Gemini vision, keys from config/api_keys.json)",
         purpose="see/click custom-drawn UI that UIA cannot see")
register("keyboard_mouse", lambda: _importable("actions.ui_click"),
         how="actions/ui_click.py", purpose="type keys / act on a control by name")
register("app_driver", lambda: _importable("core.desktop_agent"),
         how="core/desktop_agent.py", purpose="drive an app end to end")
register("self_patch", lambda: _importable("core.self_patch"),
         how="core/self_patch.py", purpose="change own code safely (validate+rollback)")
register("persistent_memory", _has_memory,
         how="add core/memory.py to store facts across sessions",
         purpose="remember the user across restarts")
