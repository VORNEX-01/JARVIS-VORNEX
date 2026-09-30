"""
actions/desktop_agent.py — discoverable wrapper for core/desktop_agent.py
"""
from core.desktop_agent import run_task, _recipient, _chat_name

def desktop_agent(parameters, player=None, session_memory=None) -> str:
    p = parameters if isinstance(parameters, dict) else {}
    task    = str(p.get("task")    or p.get("action") or "")
    app     = str(p.get("app")     or p.get("application") or "")
    details = str(p.get("details") or "")
    if not task:
        return "No task was given."
    return run_task(task, app=app, details=details, player=player)

def run(parameters, player=None, session_memory=None) -> str:
    return desktop_agent(parameters, player=player, session_memory=session_memory)

TOOL = {
    "name": "desktop_agent",
    "description": (
        "Control ANY desktop application to complete a task. "
        "Reads live UI controls, acts step by step, verifies the result. "
        "Use this for anything that needs clicking, typing, or navigating "
        "inside an app — even apps with no API."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "app":     {"type": "STRING", "description": "App name e.g. 'Telegram', 'Chrome'"},
            "task":    {"type": "STRING", "description": "What to do in plain language"},
            "details": {"type": "STRING", "description": "Extra context if needed"},
        },
        "required": ["task"],
    },
    "handler": desktop_agent,
    "scheduling": "INTERRUPT",
}
