"""
actions/desktop_agent.py — the discoverable face of core/desktop_agent.py.

WHY THIS FILE EXISTS
    The loop was written into core/desktop_agent.py, which is never scanned:
    action_loader only loads actions/*.py that expose a module-level TOOL. So the
    model never saw `desktop_agent` and reached for app_explorer instead. This is
    the two-line adapter that puts it in front of the model.
"""
from core import desktop_agent as _agent


def desktop_agent(parameters: dict, player=None, **kwargs) -> str:
    p = parameters or {}
    task = str(p.get("task") or "").strip()
    app = str(p.get("app") or "").strip()
    details = str(p.get("details") or "").strip()
    if not task:
        return "Please tell me what task to perform."
    return _agent.run_task(task, app=(app or None), details=details, player=player)


TOOL = {
    "name": "desktop_agent",
    "description": (
        "Operates ANY desktop app by itself, step by step, by looking at the app's "
        "real controls and confirming each step worked. Use this for any task inside "
        "an app that has no dedicated tool: filling a form, clicking through a wizard, "
        "using the calculator, sending a message in an app without one, etc. It only "
        "acts on VERIFIED controls, parks anything irreversible (send/delete/buy) "
        "behind the user's on-screen confirmation, and reports honestly whether the "
        "task actually completed."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "task":    {"type": "STRING", "description": "The concrete goal, e.g. 'calculate 12*7' or 'send the message سلام to Mahak'"},
            "app":     {"type": "STRING", "description": "The app/window to work in, e.g. 'Calculator', 'Telegram'"},
            "details": {"type": "STRING", "description": "Extra specifics: recipient, text, values to enter"},
        },
        "required": ["task"],
    },
    "handler": desktop_agent,
}
