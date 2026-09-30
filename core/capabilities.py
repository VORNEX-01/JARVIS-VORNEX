"""Trusted JARVIS capability registry.

This module reports capabilities that already exist in the trusted runtime.
It does not create, install, hot-load, or execute generated code.
Code changes are exclusively handled through core.self_patch.
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
    return (
        (ROOT / "core" / "memory.py").exists()
        or (ROOT / ".jarvis" / "memory.json").exists()
    )


def available(cid):
    entry = _REG.get(cid)
    if not entry:
        return False
    try:
        return bool(entry["probe"]())
    except Exception:
        return False


def list_all():
    return {cid: available(cid) for cid in sorted(_REG)}


def missing(needed):
    return [cid for cid in needed if not available(cid)]


def describe():
    lines = []
    for cid, entry in sorted(_REG.items()):
        lines.append(
            "%-20s %-8s %s"
            % (
                cid,
                "OK" if available(cid) else "MISSING",
                entry.get("purpose", ""),
            )
        )
    return "\n".join(lines)


register(
    "screen_vision",
    _has_vision,
    how="core/screen_eye.py",
    purpose="see the desktop when visual perception is available",
)

register(
    "keyboard_mouse",
    lambda: _importable("actions.ui_click"),
    how="actions/ui_click.py",
    purpose="interact with desktop controls by semantic UI information",
)

register(
    "app_driver",
    lambda: _importable("core.desktop_agent"),
    how="core/desktop_agent.py",
    purpose="drive desktop applications end to end with live UI verification",
)

register(
    "self_patch",
    lambda: _importable("core.self_patch"),
    how="core/self_patch.py",
    purpose="change trusted source through validation, compile/import checks, and rollback",
)

register(
    "persistent_memory",
    _has_memory,
    how="core/memory.py",
    purpose="remember durable facts across sessions",
)
