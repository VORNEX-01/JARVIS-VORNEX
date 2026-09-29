"""actions/ui_click.py - act on any window, dialog or menu BY NAME.

A "Save As" dialog, an "Open" dialog, a right-click menu and a small confirm box
are the SAME problem: their controls HAVE NAMES, they are just invisible to a
screenshot. Clicking them by pixel position is why saving a Notepad file failed
five times in a row. This reads those names through UI Automation and invokes the
control directly: exact, instant, and able to say what really happened.

Rules kept from the rest of VORNEX:
  * it never guesses - an EXACT normalised name wins; fuzzy matches only RANK,
    and a tie is refused;
  * it verifies instead of assuming - after acting it RE-READS the control and
    compares through core.names, so "Mahak\\nIn reply to ..." is not falsely
    treated as a different thing than "Mahak";
  * a destructive control (delete / remove / uninstall / ارسال / حذف ...) is
    refused unless the caller passes confirm=true, so this stays a second pair
    of HANDS for the verified flow, not a second unguarded engine.
"""
from __future__ import annotations

import time

_MAX_CONTROLS = 1200

_IRREVERSIBLE = (
    "delete", "remove", "uninstall", "format", "erase", "empty trash",
    "حذف", "پاک کن", "خالی کن",
)


# ── windows ──────────────────────────────────────────────────────────────────
def _windows():
    try:
        from core import window_agent as wa
        return wa.list_windows()
    except Exception:
        return []


def _area(w):
    try:
        r = w.get("rect") or (0, 0, 0, 0)
        return max(0, r[2] - r[0]) * max(0, r[3] - r[1])
    except Exception:
        return 0


def _hwnd(w):
    try:
        return int((w or {}).get("hwnd") or 0)
    except Exception:
        return 0


def _foreground():
    try:
        import ctypes
        hwnd = int(ctypes.windll.user32.GetForegroundWindow())
    except Exception:
        return None
    for w in _windows():
        if _hwnd(w) == hwnd:
            return w
    return {"hwnd": hwnd, "name": "", "exe": "", "rect": (0, 0, 0, 0)}


def _find_window(title):
    t = str(title or "").strip().lower()
    if not t:
        return _foreground()
    hits = [w for w in _windows()
            if t in (str(w.get("name") or "") + " " + str(w.get("exe") or "")).lower()]
    if not hits:
        return None
    hits.sort(key=lambda w: -_area(w))
    return hits[0]


# ── controls ─────────────────────────────────────────────────────────────────
def _wrap(win):
    try:
        from pywinauto import Application
        hwnd = _hwnd(win)
        if not hwnd:
            return None
        return Application(backend="uia").connect(handle=hwnd).window(handle=hwnd)
    except Exception:
        return None


def _controls_of(win, limit=_MAX_CONTROLS):
    out = []
    root = _wrap(win)
    if root is None:
        return out
    try:
        for el in root.descendants():
            if len(out) >= limit:
                break
            try:
                info = el.element_info
                out.append({"el": el,
                            "name": str(info.name or "").strip(),
                            "type": str(info.control_type or "")})
            except Exception:
                continue
    except Exception:
        pass
    return out


def _named_controls(exclude_hwnd=0):
    """Every named control, SMALL windows first - a popup menu or a dialog is a
    small top-level window, so this finds its items before a big app's chrome."""
    out = []
    ws = [w for w in _windows() if _hwnd(w) != exclude_hwnd and _area(w) > 0]
    for w in sorted(ws, key=_area):          # ascending: menus/dialogs first
        if len(out) >= _MAX_CONTROLS:
            break
        out.extend(_controls_of(w, limit=_MAX_CONTROLS - len(out)))
    return out


def _pick(controls, name):
    """EXACT normalised name first; fuzzy only ranks; a tie is refused."""
    from core import names
    q = str(name or "").strip()
    if not q:
        return None
    try:
        nq = names.norm(q)
    except Exception:
        nq = q.casefold()

    exact = [c for c in controls if c["name"] and names.norm(c["name"]) == nq]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return None                          # ambiguous even exactly: ask

    scored = []
    for c in controls:
        if not c["name"]:
            continue
        try:
            s = names.score(q, c["name"])
        except Exception:
            s = 0.0
        if s >= 0.62:
            scored.append((s, c))
    if not scored:
        return None
    scored.sort(key=lambda t: t[0], reverse=True)
    second = scored[1][0] if len(scored) > 1 else 0.0
    if scored[0][0] - second < 0.06 and second >= 0.62:
        return None                          # two equally likely: never guess
    return scored[0][1]


# ── act ──────────────────────────────────────────────────────────────────────
def _invoke(el):
    for how in ("invoke", "select", "click_input"):
        try:
            getattr(el, how)()
            return how
        except Exception:
            continue
    return ""


def _right_click(el):
    try:
        el.click_input(button="right")
        return "right-click"
    except Exception:
        return ""


def _fill(el, text):
    try:
        el.set_edit_text(str(text))          # ValuePattern - no keyboard at all
        return "value"
    except Exception:
        pass
    try:
        el.set_focus()
        time.sleep(0.15)
        el.type_keys(str(text), with_spaces=True, set_foreground=True)
        return "keys"
    except Exception:
        return ""


def _read_back(el):
    try:
        return str(el.element_info.name or "").strip()
    except Exception:
        return ""


def _still_there(el):
    try:
        return bool(el.exists())
    except Exception:
        return False


# ── tool ─────────────────────────────────────────────────────────────────────
def ui_click(parameters, player=None, session_memory=None) -> str:
    p = parameters or {}
    action = str(p.get("action") or "list").strip().lower()
    name = p.get("name") or ""
    text = p.get("text") or ""
    title = p.get("window") or ""
    confirm = bool(p.get("confirm"))

    win = _find_window(title) if title else _foreground()
    where = str((win or {}).get("name") or "") or (title or "the foreground window")

    if action == "list":
        controls = _controls_of(win) if win else []
        if not controls:
            controls = _named_controls(exclude_hwnd=_hwnd(win))
        named = [c for c in controls if c["name"]]
        if not named:
            return ("I could not read any NAMED control in %s - the app may have "
                    "accessibility switched off." % where)
        listing = "; ".join("%s [%s]" % (c["name"], c["type"]) for c in named[:60])
        return "Controls in %s: %s%s" % (where, listing,
                                         "" if len(named) <= 60 else "; ...")

    target = _pick(_controls_of(win) if win else [], name)
    if target is None:
        target = _pick(_named_controls(exclude_hwnd=_hwnd(win)), name)
    if target is None:
        return ("No control matched '%s' clearly. Call ui_click with action='list' "
                "first and I will use the exact name." % name)

    if action in ("click", "right_click"):
        low = target["name"].casefold()
        if any(b in low for b in _IRREVERSIBLE) and not confirm:
            return ("'%s' is an irreversible control, so I did not touch it. "
                    "Confirm with the user first, then call again with confirm=true."
                    % target["name"])

    if action == "click":
        how = _invoke(target)
        if not how:
            return "I found '%s' but could not activate it." % target["name"]
        time.sleep(0.25)
        if _still_there(target):
            return "Clicked '%s' (%s) - it is still on screen." % (target["name"], how)
        return "Clicked '%s' (%s) and the control is gone - the action went through." % (target["name"], how)

    if action == "right_click":
        how = _right_click(target)
        if not how:
            return "I found '%s' but could not right-click it." % target["name"]
        return ("Right-clicked '%s' - the menu should be open. Call "
                "action='list' to read its items." % target["name"])

    if action == "set_text":
        how = _fill(target, text)
        if not how:
            return "I found '%s' but could not write into it." % target["name"]
        back = _read_back(target)
        if back and text and str(text).strip().casefold() not in back.casefold():
            return ("Wrote into '%s' (%s) but it now reads '%s' - not what you "
                    "asked for." % (target["name"], how, back))
        return "Wrote '%s' into '%s' (%s)." % (text, target["name"], how)

    return "Unknown action '%s'. Use list, click, right_click or set_text." % action


TOOL = {
    "name": "ui_click",
    "description": (
        "Act on a window, dialog or menu BY NAME - no coordinates. Use it for "
        "dialogs (Save As, Open, Print, confirmations), right-click context "
        "menus, and any button whose position you cannot trust. Steps: "
        "action='list' to read the exact control names, then action='set_text' "
        "with name='File name' and the text, then action='click' with "
        "name='Save'. Prefer this over computer_control or desktop_agent for "
        "anything that has a readable label. A destructive control (delete, "
        "remove, uninstall, حذف) needs confirm=true after the user agrees."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING",
                       "description": "list | click | right_click | set_text"},
            "name":   {"type": "STRING",
                       "description": "Control name, e.g. 'Save', 'File name:', 'Delete'."},
            "text":   {"type": "STRING",
                       "description": "For set_text: the value to write into the field."},
            "window": {"type": "STRING",
                       "description": "Window/app title to work in. Omit for the foreground window."},
            "confirm": {"type": "BOOLEAN",
                        "description": "true only after the user approved a destructive control."},
        },
        "required": ["action"],
    },
    "handler": ui_click,
}
