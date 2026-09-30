"""Report trusted JARVIS capabilities.

This action is observational only. It never creates, installs, hot-loads,
or executes generated tools.
"""
from __future__ import annotations


def capabilities(parameters, player=None, session_memory=None) -> str:
    from core import capabilities as C

    p = parameters if isinstance(parameters, dict) else {}
    action = str(p.get("action") or "list").lower()

    if action in ("list", "status"):
        return "Capabilities:\n" + C.describe()

    if action == "check":
        need = p.get("need") or p.get("capabilities") or ""
        ids = (
            need
            if isinstance(need, list)
            else [s.strip() for s in str(need).split(",") if s.strip()]
        )
        missing = C.missing(ids)
        available = [cid for cid in ids if cid not in missing]
        return "Available: %s | Missing: %s" % (available, missing)

    return "Use action='list' or action='check' with need=['capability']."


def run(parameters, player=None, session_memory=None):
    return capabilities(
        parameters,
        player=player,
        session_memory=session_memory,
    )
