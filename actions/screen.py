"""Tool: the assistant's live eye. Usable any time, no permission needed."""
from __future__ import annotations

# The eye is ALWAYS on: actions are loaded at boot, so this starts the live
# capture thread immediately (cheap, local, daemon). Idempotent.
try:
    from core import screen_eye as _E
    _E.start()
except Exception:
    pass


def screen(parameters, player=None, session_memory=None) -> str:
    from core import screen_eye as E
    p = parameters if isinstance(parameters, dict) else {}
    action = str(p.get("action") or "look").lower()
    E.start()
    if action in ("look", "describe", "what"):
        return E.describe(str(p.get("question") or
                              "In one or two lines, what is on the screen right now?"))
    if action in ("find", "locate", "where"):
        t = str(p.get("text") or p.get("target") or "").strip()
        if not t:
            return "Which text should I look for?"
        box = E.find_text(t)
        return ("I do not see %r on screen right now." % t if not box
                else "%r is at (%d, %d) on screen." % (t, box[0], box[1]))
    if action in ("state", "status"):
        s = E.state()
        return "Eye: %d frames, %d changes, front window %r." % (
            s["frames"], s["changes"], s["fg"][:60])
    if action == "start":
        E.start(); return "Eye started."
    if action == "pause":
        E.pause(); return "Eye paused."
    if action == "resume":
        E.resume(); return "Eye resumed."
    return "Use action=look|find|state|pause|resume."


def run(parameters, player=None, session_memory=None):
    return screen(parameters, player=player, session_memory=session_memory)
