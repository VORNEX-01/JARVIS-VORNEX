"""actions/make_tool.py — JARVIS extends and repairs itself.

Called AFTER the user agrees. Writes a plugin, validates it (py_compile + PLUGIN
+ run), hot-loads it into core.plugin_runtime. On any failure the previous file
is restored, so a bad build can never break a working tool.
"""
from __future__ import annotations
import json
from core import plugin_runtime as RT

_TEMPLATE = '''"""VORNEX self-made plugin: {name} - {purpose}"""
PLUGIN = {{
    "name": {name!r},
    "description": {purpose!r},
    "parameters": {schema},
}}


def run(parameters: dict, player=None, session_memory=None) -> str:
{body}
'''


def _wrap(name, purpose, schema_json, body):
    try:
        schema = json.loads(schema_json) if schema_json else {"type": "OBJECT", "properties": {}}
    except Exception:
        schema = {"type": "OBJECT", "properties": {}}
    body = str(body or "return 'not implemented yet'")
    lines = ["    " + ln if ln.strip() else "" for ln in body.splitlines()]
    return _TEMPLATE.format(name=name, purpose=purpose, schema=repr(schema),
                            body="\n" + "\n".join(lines))


def make_tool(parameters, player=None, session_memory=None, **kwargs):
    p = parameters or {}
    name = str(p.get("name") or "").strip()
    purpose = str(p.get("purpose") or "").strip()
    source = str(p.get("source") or "").strip()
    if not source:
        if not name:
            return "I need the tool name and its source to build it."
        source = _wrap(name, purpose, p.get("parameters_json"), p.get("body"))
    ok, msg = RT.install(name or "self_made", source, purpose)
    if player:
        try: player.write_log("[VORNEX] make_tool: %s" % msg)
        except Exception: pass
    if ok:
        return ("Done - I added the tool '%s' and it is live now. "
                "Use call_tool to run it." % name)
    return ("I could not add '%s' - %s. Tell me what to fix and I will try again."
            % (name, msg))


TOOL = {
    "name": "make_tool",
    "description": (
        "Create or repair a VORNEX tool (a small Python plugin) when no existing "
        "tool can do what the user asked. Call this ONLY after the user has clearly "
        "agreed. Give a complete, safe plugin source with a PLUGIN dict and a "
        "run(parameters, player, session_memory) that returns a short string and "
        "never raises. It is validated and hot-loaded immediately; on failure the "
        "previous file is restored. After it succeeds, run it via call_tool."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "mode": {"type": "STRING", "enum": ["create", "repair"]},
            "name": {"type": "STRING", "description": "snake_case tool name"},
            "purpose": {"type": "STRING", "description": "one line: what it does"},
            "source": {"type": "STRING", "description": "the COMPLETE python source of the plugin file"},
            "parameters_json": {"type": "STRING", "description": "optional JSON schema when only a body is given"},
            "body": {"type": "STRING", "description": "optional: just the run() body"},
        },
        "required": ["mode", "name"],
    },
    "handler": make_tool,
}


# ── self-heal at the RIGHT seam: make_tool validates the plugin itself ────────
# MEASURED: appending the heal to core/plugin_runtime.py changed nothing - the
# ModuleNotFoundError is raised by make_tool's OWN validation (py_compile + import
# of the generated source) BEFORE plugin_runtime is called, and make_tool returns
# that failure as a STRING instead of raising it. So the wrapper lives here and
# handles BOTH shapes: a raised ModuleNotFoundError, and the standard
# "No module named 'X'" pattern inside make_tool's own error message. It installs
# X only when X is on the allowlist shared with core.plugin_runtime, re-runs the
# validation exactly ONCE, and otherwise returns an honest message with the exact
# pip command - it never pretends the tool was added.
import re as _re
import sys as _sys

_MAKE_TOOL_V1 = make_tool

_MISSING_RE = _re.compile(r"No module named '?([A-Za-z_][\w.]*)'?")


def _missing_from(text) -> str:
    m = _MISSING_RE.search(str(text or ""))
    return m.group(1).split(".")[0] if m else ""


def _heal(mod: str) -> bool:
    try:
        from core import plugin_runtime as _RT
        return bool(_RT._install_missing(mod))
    except Exception:
        return False


def make_tool(parameters, player=None, session_memory=None, **kwargs):
    try:
        out = _MAKE_TOOL_V1(parameters, player=player,
                            session_memory=session_memory, **kwargs)
    except ModuleNotFoundError as e:
        out = "%r" % e

    mod = _missing_from(out)
    if not mod:
        return out

    if _heal(mod):
        try:
            again = _MAKE_TOOL_V1(parameters, player=player,
                                  session_memory=session_memory, **kwargs)
        except ModuleNotFoundError as e2:
            again = "%r" % e2
        if not _missing_from(again):
            return again + (" (it works now: I installed the missing '%s' module "
                            "and the tool is live)" % mod)
        return again

    return (out + " | I could not install '%s' automatically. Install it with:  "
            "%s -m pip install %s" % (mod, _sys.executable, mod))


TOOL["handler"] = make_tool
