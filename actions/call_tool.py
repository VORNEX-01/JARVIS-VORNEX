"""actions/call_tool.py — run any VORNEX plugin by name, including one just made.

Gemini Live freezes its tool list at connect, so a plugin created mid-session is
not a declared tool. call_tool is declared once and dispatches to the live
plugin_runtime registry, so a fresh tool is usable in the SAME session.
"""
from __future__ import annotations
import json
from core import plugin_runtime as RT


def call_tool(parameters, player=None, session_memory=None, **kwargs):
    p = parameters or {}
    name = str(p.get("plugin_name") or "").strip()
    raw = p.get("arguments_json")
    if isinstance(raw, dict):
        args = raw
    else:
        try: args = json.loads(raw) if raw else {}
        except Exception: args = {}
    _ok, out = RT.invoke(name, args, player=player, memory=session_memory)
    return out


TOOL = {
    "name": "call_tool",
    "description": (
        "Run an installed VORNEX tool/plugin by name (including one you just made "
        "with make_tool). Arguments go in arguments_json (a JSON object string)."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "plugin_name": {"type": "STRING", "description": "the tool name, e.g. clip_clear"},
            "arguments_json": {"type": "STRING", "description": "JSON object string, e.g. {\"text\":\"hi\"}"},
        },
        "required": ["plugin_name"],
    },
    "handler": call_tool,
}
