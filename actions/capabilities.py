"""Tool: report what the assistant can and cannot do; make gaps visible so the
assistant can ASK the user and then build them with make_tool, then re-check."""
from __future__ import annotations


def capabilities(parameters, player=None, session_memory=None) -> str:
    from core import capabilities as C
    p = parameters if isinstance(parameters, dict) else {}
    action = str(p.get("action") or "list").lower()
    if action in ("list", "status"):
        return "Capabilities:\n" + C.describe()
    if action == "check":
        need = p.get("need") or p.get("capabilities") or ""
        ids = (need if isinstance(need, list)
               else [s.strip() for s in str(need).split(",") if s.strip()])
        miss = C.missing(ids)
        return "Available: %s | Missing: %s" % ([c for c in ids if c not in miss], miss)
    return "Use action='list', or action='check' with need=['a','b']."


def run(parameters, player=None, session_memory=None):
    return capabilities(parameters, player=player, session_memory=session_memory)
