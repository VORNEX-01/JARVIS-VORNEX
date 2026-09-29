"""Tool: the assistant's long-term memory (persisted in .jarvis/memory.json)."""
from __future__ import annotations


def memory(parameters, player=None, session_memory=None) -> str:
    from core import memory as M
    p = parameters if isinstance(parameters, dict) else {}
    action = str(p.get("action") or "recall").lower()
    if action in ("remember", "store", "save"):
        return M.remember(str(p.get("text") or p.get("value") or ""),
                          key=p.get("key"), value=p.get("value"), tags=p.get("tags"))
    if action in ("recall", "search", "get"):
        return M.recall(str(p.get("query") or p.get("text") or ""))
    if action in ("list", "all"):
        return M.all_()
    if action in ("forget", "delete"):
        return M.forget(str(p.get("key") or p.get("text") or ""))
    return "Use action=remember|recall|list|forget."


def run(parameters, player=None, session_memory=None):
    return memory(parameters, player=player, session_memory=session_memory)
