"""Tool: the assistant's live eye."""
from __future__ import annotations

try:
    from core import screen_eye as _E
    _E.start_auto()
except Exception:
    pass


def screen(parameters, player=None, session_memory=None) -> str:
    from core import screen_eye as E
    p = parameters if isinstance(parameters, dict) else {}
    a = str(p.get("action") or "look").lower()
    E.start_auto()
    if a in ("look", "describe", "what"):
        return E.describe(str(p.get("question") or "In one or two lines, what is on the screen right now?"))
    if a in ("find", "locate", "where"):
        t = str(p.get("text") or p.get("target") or "").strip()
        if not t:
            return "Which text should I look for?"
        box = E.find_text(t)
        return ("I do not see %r on screen right now." % t if not box
                else "%r is at (%d, %d) on screen." % (t, box[0], box[1]))
    if a in ("state", "status", "awareness"):
        s = E.state()
        line = ("Eye: %d frames, %d changes, front window %r."
                % (s["frames"], s["changes"], s["fg"][:60]))
        if s.get("scene"):
            line += " Latest scene: %s" % s["scene"]
        return line
    if a == "start":
        E.start_auto(); return "Eye started."
    if a == "pause":
        E.pause(); return "Eye paused."
    if a == "resume":
        E.resume(); return "Eye resumed."
    return "Use action=look|find|state|pause|resume."


def run(parameters, player=None, session_memory=None):
    return screen(parameters, player=player, session_memory=session_memory)
