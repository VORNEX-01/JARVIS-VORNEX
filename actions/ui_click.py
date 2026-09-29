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


# ── v2: aim at the right window, and PROVE the file exists ───────────────────
# MEASURED: `ui_click list` with no window listed the MINGW console's own
# ScrollBar / Close button, because the foreground window was the terminal the
# test ran in - not the "Save As" dialog. So: a console is NEVER a valid target,
# and a dialog-shaped window (small, carrying Save/OK/Cancel) is preferred over
# an arbitrary big window. #32770 alone is only a CLUE, never proof - an app's
# real main window can carry that class too.
# Second lesson, from the failed Notepad session: "I saved it" was said five
# times with no file on disk. So click takes expect_file and the answer is the
# TRUTH about the filesystem, not a claim.
import os as _os

_DIALOG_CLASSES = {"#32770"}
_CONSOLE_EXES = {
    "cmd.exe", "conhost.exe", "powershell.exe", "pwsh.exe",
    "windowsterminal.exe", "wt.exe", "mintty.exe", "bash.exe", "sh.exe",
    "python.exe", "pythonw.exe",
}
_DIALOG_HINTS = ("save", "ok", "cancel", "file name", "open", "yes", "no",
                 "saving", "ذخیره", "لغو", "باز", "بله", "خیر")


def _is_console(w):
    return str((w or {}).get("exe") or "").lower().rsplit("\\", 1)[-1] in _CONSOLE_EXES


def _is_dialog_class(w):
    return str((w or {}).get("cls") or "") in _DIALOG_CLASSES


def _screen_area():
    try:
        import ctypes
        u = ctypes.windll.user32
        return max(1, u.GetSystemMetrics(0)) * max(1, u.GetSystemMetrics(1))
    except Exception:
        return 1920 * 1080


def _looks_like_dialog(w):
    """Small window carrying a Save / OK / Cancel style control."""
    if _is_dialog_class(w):
        return True
    if _area(w) > 0.8 * _screen_area():
        return False
    names = [c["name"].casefold() for c in _controls_of(w, limit=200) if c["name"]]
    return any(any(h in n for h in _DIALOG_HINTS) for n in names)


def _window_choices():
    out = []
    for w in sorted(_windows(), key=_area, reverse=True):
        if _area(w) <= 0:
            continue
        out.append("%s [%s] %s%s" % (str(w.get("name") or "?")[:50],
                                     str(w.get("exe") or "?"),
                                     str(w.get("cls") or "?"),
                                     " <DIALOG>" if _is_dialog_class(w) else ""))
    return out


def _resolve_window(title):
    ws = [w for w in _windows() if _area(w) > 0]
    t = str(title or "").strip().lower()
    if t:
        hits = [w for w in ws
                if t in (str(w.get("name") or "") + " " + str(w.get("exe") or "")).lower()]
        if not hits:
            return None, ("No window matches '%s'. Open windows: %s"
                          % (title, " | ".join(_window_choices()[:15])))
        hits.sort(key=lambda w: -_area(w))
        return hits[0], ""

    fg = _foreground()
    if fg and not _is_console(fg) and _area(fg) > 0:
        return fg, ""

    # foreground is a terminal: look for a dialog-shaped window instead
    small = sorted([w for w in ws
                    if not _is_console(w) and _area(w) <= 0.8 * _screen_area()],
                   key=_area)
    for w in small[:5]:
        if _looks_like_dialog(w):
            return w, ""
    return None, ("I am running inside a terminal so I cannot infer the window - "
                  "name it, or open windows: " + " | ".join(_window_choices()[:15]))


def _file_exists(expect):
    """True/False, and also try the usual Desktop / Downloads spots when the
    caller passed a bare file name like 'testy.txt'."""
    exp = _os.path.expandvars(_os.path.expanduser(str(expect)))
    cands = [exp]
    if (_os.sep not in exp) and ("/" not in exp):
        home = _os.path.expanduser("~")
        cands += [_os.path.join(home, "Desktop", exp),
                  _os.path.join(home, "OneDrive", "Desktop", exp),
                  _os.path.join(home, "Downloads", exp)]
    for c in cands:
        if _os.path.exists(c):
            return True, c
    return False, exp


def ui_click(parameters, player=None, session_memory=None) -> str:
    p = parameters or {}
    action = str(p.get("action") or "list").strip().lower()
    name = p.get("name") or ""
    text = p.get("text") or ""
    title = p.get("window") or ""
    confirm = bool(p.get("confirm"))
    expect = p.get("expect_file") or ""

    if action == "windows":
        ch = _window_choices()
        return ("Open windows: " + " | ".join(ch[:25])) if ch else "No windows found."

    win, err = _resolve_window(title)
    if win is None:
        return err
    where = str(win.get("name") or "") or str(win.get("exe") or "") or "the window"

    if action == "list":
        controls = [c for c in _controls_of(win) if c["name"]]
        if not controls:
            controls = [c for c in _named_controls(exclude_hwnd=_hwnd(win)) if c["name"]]
        if not controls:
            return ("I could not read any NAMED control in %s - the app may have "
                    "accessibility switched off." % where)
        listing = "; ".join("%s [%s]" % (c["name"], c["type"]) for c in controls[:60])
        return "Controls in %s: %s%s" % (where, listing,
                                         "" if len(controls) <= 60 else "; ...")

    target = _pick(_controls_of(win), name)
    if target is None:
        target = _pick(_named_controls(exclude_hwnd=_hwnd(win)), name)
    if target is None:
        return ("No control matched '%s' in %s. Call ui_click with action='list' "
                "and window='%s' first, then use the exact name."
                % (name, where, where))

    if action in ("click", "right_click"):
        low = target["name"].casefold()
        if any(b in low for b in _IRREVERSIBLE) and not confirm:
            return ("'%s' is an irreversible control, so I did not touch it. "
                    "Confirm with the user first, then call again with confirm=true."
                    % target["name"])

    if action == "click":
        how = _invoke(target)
        if not how:
            return "I found '%s' in %s but could not activate it." % (target["name"], where)
        time.sleep(0.4)
        gone = not _still_there(target)
        if expect:
            ok, path = _file_exists(expect)
            if ok:
                return ("Clicked '%s' (%s) in %s and VERIFIED the file exists: %s"
                        % (target["name"], how, where, path))
            return ("Clicked '%s' (%s) in %s, but the file '%s' is NOT on disk - "
                    "the save did NOT happen. Look at the dialog again."
                    % (target["name"], how, where, expect))
        return ("Clicked '%s' (%s) in %s and the control is gone - the action went through."
                % (target["name"], how, where) if gone else
                "Clicked '%s' (%s) in %s - it is still on screen." % (target["name"], how, where))

    if action == "right_click":
        how = _right_click(target)
        if not how:
            return "I found '%s' but could not right-click it." % target["name"]
        return ("Right-clicked '%s' in %s - the menu should be open. Call "
                "action='list' to read its items." % (target["name"], where))

    if action == "set_text":
        how = _fill(target, text)
        if not how:
            return "I found '%s' in %s but could not write into it." % (target["name"], where)
        back = _read_back(target)
        if back and text and str(text).strip().casefold() not in back.casefold():
            return ("Wrote into '%s' (%s) but it now reads '%s' - not what you asked for."
                    % (target["name"], how, back))
        return "Wrote '%s' into '%s' in %s (%s)." % (text, target["name"], where, how)

    return "Unknown action '%s'. Use windows, list, click, right_click or set_text." % action


TOOL["parameters"]["properties"]["action"]["description"] = (
    "windows | list | click | right_click | set_text")
TOOL["parameters"]["properties"]["expect_file"] = {
    "type": "STRING",
    "description": ("For click: the file that MUST exist afterwards, e.g. "
                    "'testy.txt' or a full path. The result then reports the "
                    "real state of the disk instead of claiming success."),
}
TOOL["handler"] = ui_click


# ── v3: real keys into a NAMED window, and one-call save_as ──────────────────
# The Notepad session failed in five different ways for one reason: nothing could
# put keys into a CHOSEN window. `computer_settings save` pressed Ctrl+S at
# whatever happened to have focus, and the log shows the engine then losing the
# window ("could not bring 'File' to the front"). So v3 sends keys to a NAMED
# window only after proving that window is really in the foreground, and adds
# save_as which does the whole thing and then asks the FILESYSTEM whether it
# worked - never the click.
from pywinauto.keyboard import send_keys as _send_keys_raw

_SAVE_BUTTONS = ("Save", "ذخیره", "ذخیره کردن")
_REPLACE_YES = ("Replace", "Yes", "جایگزین", "بله")
_CANCEL_NO = ("No", "Cancel", "لغو", "خیر")


def _fg_hwnd():
    try:
        import ctypes
        return int(ctypes.windll.user32.GetForegroundWindow())
    except Exception:
        return 0


def _focus(win):
    root = _wrap(win)
    if root is None:
        return False
    try:
        root.restore()
    except Exception:
        pass
    for how in ("set_focus", "set_keyboard_focus"):
        try:
            getattr(root, how)()
            return True
        except Exception:
            continue
    return False


def _send_keys(win, keys, focus=True):
    if focus:
        _focus(win)
        time.sleep(0.25)
    try:
        _send_keys_raw(str(keys), pause=0.05)
        return True
    except Exception:
        return False


def _names_of(w):
    return "; ".join(c["name"] for c in _controls_of(w) if c["name"])[:300]


def _desktop_path(name):
    s = str(name or "").strip().strip('"')
    if _os.sep in s or "/" in s:
        return _os.path.expandvars(_os.path.expanduser(s))
    home = _os.path.expanduser("~")
    for base in (("Desktop",), ("OneDrive", "Desktop"), ("Downloads",)):
        d = _os.path.join(home, *base)
        if _os.path.isdir(d):
            return _os.path.join(d, s)
    return _os.path.join(home, s)


def _stat_of(path):
    try:
        st = _os.stat(path)
        return (int(st.st_mtime), int(st.st_size))
    except Exception:
        return None


def _wait_for_dialog(before, timeout=6.0, pid=None):
    t0 = time.time()
    while time.time() - t0 < timeout:
        for w in [w for w in _windows() if _area(w) > 0]:
            if _hwnd(w) in before or not _looks_like_dialog(w):
                continue
            if pid is not None and w.get("pid") and w.get("pid") != pid:
                continue
            return w
        time.sleep(0.35)
    return None


def _save_as(app_title, target, replace=False):
    win, err = _resolve_window(app_title)
    if win is None:
        return err
    where = str(win.get("name") or "") or str(win.get("exe") or "") or "the app"
    pid = win.get("pid")
    full = _desktop_path(target)
    before_state = _stat_of(full)

    # 1) prove the window is in front BEFORE a single key is sent
    _focus(win)
    if _fg_hwnd() != _hwnd(win):
        _focus(win)
        time.sleep(0.4)
    if _fg_hwnd() != _hwnd(win):
        return ("I could not bring %s to the front, so I did NOT send Ctrl+S - "
                "another window would have received it instead." % where)

    before = {_hwnd(w) for w in _windows()}
    if not _send_keys(win, "^s", focus=False):
        return "Could not send Ctrl+S to %s." % where

    # 2) the Save dialog, belonging to THIS app
    dlg = _wait_for_dialog(before, timeout=7.0, pid=pid)
    if dlg is None:
        ok, path = _file_exists(full)
        if ok and before_state is None:
            return "No dialog appeared and the file is on disk: %s" % path
        if ok and _stat_of(full) == before_state:
            return ("No Save dialog appeared and %s already existed unchanged - "
                    "nothing was written." % path)
        return ("Ctrl+S opened no Save dialog in %s and %s is not on disk, so "
                "nothing was saved." % (where, full))

    # 3) the file-name field, scoped to this dialog, then READ BACK
    field = _pick(_controls_of(dlg), "File name") or _pick(_controls_of(dlg), "Name")
    if field is None:
        return ("The Save dialog has no readable file-name field, so I stopped. "
                "Its controls: %s" % _names_of(dlg))
    if not _fill(field, full):
        return "Could not write the path into the Save dialog's file-name field."
    time.sleep(0.25)
    read = _read_back(field).strip().strip('"')
    if read.casefold() != full.casefold():
        return ("The file-name field reads '%s', not '%s' - I stopped before "
                "saving anything wrong." % (read, full))

    # 4) a uniquely named Save button - never a blind Enter
    btn = None
    for want in _SAVE_BUTTONS:
        btn = _pick(_controls_of(dlg), want)
        if btn is not None:
            break
    if btn is None:
        return ("I filled the path but found no Save button, so I pressed "
                "nothing. Dialog controls: %s" % _names_of(dlg))
    if not _invoke(btn):
        return "The Save button could not be activated; nothing was saved."
    time.sleep(0.6)

    # 5) an overwrite prompt is its own dialog - never overwrite unasked
    follow = _wait_for_dialog(before | {_hwnd(dlg)}, timeout=2.5, pid=pid)
    if follow is not None:
        prompt = _names_of(follow)
        if not replace:
            for no in _CANCEL_NO:
                c = _pick(_controls_of(follow), no)
                if c is not None and _invoke(c):
                    break
            return ("%s already exists and Windows asked to replace it. I chose "
                    "NOT to overwrite and cancelled. Ask again with replace=true "
                    "and I will; the prompt offered: %s" % (full, prompt))
        for yes in _REPLACE_YES:
            c = _pick(_controls_of(follow), yes)
            if c is not None and _invoke(c):
                break
        time.sleep(0.6)

    # 6) the disk decides, not the click
    ok, path = _file_exists(full)
    if not ok:
        return ("I clicked Save in %s but %s is NOT on disk - the save did not "
                "happen." % (where, full))
    if before_state is not None and _stat_of(full) == before_state:
        return ("%s exists but its contents did not change, so treat this as NOT "
                "saved." % path)
    return "Saved and verified on disk: %s" % path


# ── dispatch the new actions, keep v2 for everything else ───────────────────
_ui_click_v2 = ui_click


def ui_click(parameters, player=None, session_memory=None) -> str:
    p = parameters or {}
    a = str(p.get("action") or "").strip().lower()

    if a == "save_as":
        return _save_as(p.get("window") or "", p.get("text") or p.get("path") or "",
                        bool(p.get("replace")))

    if a in ("keys", "type"):
        win, err = _resolve_window(p.get("window") or "")
        if win is None:
            return err
        where = str(win.get("name") or "") or str(win.get("exe") or "") or "the window"
        _focus(win)
        if _fg_hwnd() != _hwnd(win):
            return ("I could not bring %s to the front, so I did NOT send keys - "
                    "they would have gone to another window." % where)
        payload = p.get("keys") if a == "keys" else p.get("text")
        payload = str(payload or "")
        if not payload:
            return "Nothing to send - give me 'keys' (e.g. '^s') or 'text'."
        try:
            if a == "keys":
                _send_keys_raw(payload, pause=0.05)
            else:
                _send_keys_raw(payload, with_spaces=True, pause=0.03)
        except Exception as e:
            return "Could not send it to %s: %r" % (where, e)
        return "Sent %s to %s." % ("keys '%s'" % payload if a == "keys" else "text", where)

    return _ui_click_v2(parameters, player, session_memory)


TOOL["parameters"]["properties"]["keys"] = {
    "type": "STRING",
    "description": "For action='keys': the combination, e.g. '^s' = Ctrl+S, '{ENTER}'.",
}
TOOL["parameters"]["properties"]["replace"] = {
    "type": "BOOLEAN",
    "description": "For save_as: true only if the user agreed to overwrite an existing file.",
}
TOOL["parameters"]["properties"]["action"]["description"] = (
    "windows | list | click | right_click | set_text | keys | type | save_as")
TOOL["description"] += (
    " action='save_as' with window=<app> and text=<name or full path> does the "
    "entire save in ONE call: brings the app to the front, Ctrl+S, fills the "
    "dialog's file-name field, clicks Save by name, answers an overwrite prompt, "
    "and then reports the REAL state of the disk - it never claims a save it "
    "cannot prove. 'testy.txt' alone means the Desktop."
)
TOOL["handler"] = ui_click


# ── v4: put the keys in the RIGHT window, or the save never happens ──────────
# MEASURED: save_as on Notepad said "Ctrl+S opened no Save dialog ... so nothing
# was saved" while the window itself resolved perfectly. The test ran from MINGW,
# so the FOREGROUND window was the terminal. _focus() only REQUESTS focus and
# pywinauto.keyboard.send_keys() types into the ACTIVE window - so Ctrl+S went to
# the console and Notepad never saw it. Windows refuses SetForegroundWindow to a
# background process on purpose; the documented way through is AttachThreadInput
# to the current + target threads, then BringWindowToTop + SetForegroundWindow,
# and - critically - to VERIFY GetForegroundWindow()==hwnd before typing. This
# layer does exactly that; _send_keys now refuses to type unless the target is
# provably in front. A File->Save As menu fallback covers Ctrl+S doing nothing.
import ctypes as _ct

_u32 = _ct.windll.user32
_kt32 = _ct.windll.kernel32


def _is_fg(hwnd) -> bool:
    try:
        return int(_u32.GetForegroundWindow()) == int(hwnd or 0)
    except Exception:
        return False


def _force_foreground(win, tries=10):
    hwnd = _hwnd(win)
    if not hwnd:
        return False
    try:
        if not _u32.IsWindow(hwnd):
            return False
        if _u32.IsIconic(hwnd):
            _u32.ShowWindow(hwnd, 9)      # SW_RESTORE
    except Exception:
        pass
    cur = int(_kt32.GetCurrentThreadId())
    for _ in range(max(1, tries)):
        if _is_fg(hwnd):
            return True
        fg = int(_u32.GetForegroundWindow())
        fg_th = int(_u32.GetWindowThreadProcessId(fg, None))
        tg_th = int(_u32.GetWindowThreadProcessId(hwnd, None))
        attached = []
        try:
            for th in (fg_th, tg_th):
                if th and th != cur and th not in attached:
                    _u32.AttachThreadInput(cur, th, True)
                    attached.append(th)
            _u32.BringWindowToTop(hwnd)
            _u32.SetForegroundWindow(hwnd)
        except Exception:
            pass
        finally:
            for th in attached:
                try:
                    _u32.AttachThreadInput(cur, th, False)
                except Exception:
                    pass
        if _is_fg(hwnd):
            return True
        time.sleep(0.2)
    return _is_fg(hwnd)


def _focus(win):                         # redefined: real, verified foreground
    return _force_foreground(win)


def _send_keys(win, keys, focus=True):   # redefined: never type into the wrong window
    if focus and not _force_foreground(win):
        return False
    if not _is_fg(_hwnd(win)):           # proven in front, or we do not type
        return False
    try:
        _send_keys_raw(str(keys), pause=0.05)
        return True
    except Exception:
        return False


def _menu_save_as(win):
    """Fallback with no keystrokes: File -> Save As through UIA by name."""
    title = str((win or {}).get("name") or "")
    if not title:
        return False
    try:
        ui_click({"action": "click", "window": title, "name": "File"})
        time.sleep(0.4)
        ui_click({"action": "click", "window": title, "name": "Save as"})
        return True
    except Exception:
        return False


# ── v5: the real Save-As path, matched by IDENTITY not by UIA Name ───────────
# MEASURED: with the foreground fix, Ctrl+S DID open the dialog (focus=True,
# fg==win=True) but the reader reported "no readable file-name field" - because
# it looked for a control NAME and the modern Windows 11 save dialog's file-name
# field has an EMPTY Name (class 'Edit' under 'FileNameControlHost', auto_id
# '1001'); it may also not expose a Value pattern. So this path matches by
# auto_id / class_name, writes with the CLIPBOARD (not ValuePattern), clicks a
# UNIQUELY identified Save (auto_id '1', class 'Button') - never a blind Enter -
# handles an overwrite prompt by ID, and then asks the FILESYSTEM whether it
# really happened. No file on disk => it says so, always.
def _fg_win():
    try:
        import ctypes
        h = int(ctypes.windll.user32.GetForegroundWindow())
    except Exception:
        return None
    for w in _windows():
        if _hwnd(w) == h:
            return w
    return None


def _uia_dialog(dlg):
    from pywinauto import Application
    h = _hwnd(dlg)
    app = Application(backend="uia").connect(handle=h)
    d = app.window(handle=h)
    try:
        d.wait("visible enabled", timeout=6)
    except Exception:
        pass
    return d


def _first(d, probes):
    for p in probes:
        try:
            c = p()
            if c is not None and c.exists(timeout=0.6):
                return c
        except Exception:
            continue
    return None


def _click_replace_if_prompted(before):
    import time as _t
    for _ in range(8):
        w = _wait_for_dialog(before, timeout=0.7)
        if w is None:
            return ""
        try:
            d = _uia_dialog(w)
            btn = _first(d, [
                lambda: d.child_window(title_re="(?i)^&?(replace|yes|جایگزین|بله)$",
                                       class_name="Button"),
                lambda: d.child_window(auto_id="6", class_name="Button"),   # Yes
            ])
            if btn is not None:
                try:
                    btn.click_input()
                except Exception:
                    btn.invoke()
                return " (I confirmed the overwrite)"
        except Exception:
            pass
        _t.sleep(0.25)
    return ""


def _save_as_v2(p):
    import os as _o
    import time as _t
    title = str((p or {}).get("window") or "").strip()
    name = str((p or {}).get("text") or (p or {}).get("name") or "").strip()
    if not name:
        return "Give me a file name: {'action':'save_as','window':'Notepad','text':'testy.txt'}"
    dest = _desktop_path(name)

    tgt = _resolve_window(title) if title else _fg_win()
    if tgt is None:
        return "I cannot see a window matching %r - open the app first." % title
    before = {_hwnd(w) for w in _windows()}
    st_before = _stat_of(dest)
    if not _force_foreground(tgt):
        return "I could not bring %r to the front, so I did not type blind." % title
    if not _send_keys(tgt, "^s"):
        return "I could not send Ctrl+S to %r." % title

    dlg = _wait_for_dialog(before, timeout=6.0, pid=tgt.get("pid"))
    if dlg is None:
        st = _stat_of(dest)
        if st and st != st_before:
            return "Saved (no dialog needed - the file was already named). %s is on disk." % dest
        return ("Ctrl+S opened no Save dialog in %r and %s is not on disk, "
                "so nothing was saved." % (title, dest))

    try:
        d = _uia_dialog(dlg)
    except Exception as e:
        return "I opened the Save dialog but could not attach to it: %s" % e

    field = _first(d, [
        lambda: d.child_window(auto_id="FileNameControlHost", class_name="Edit"),
        lambda: d.child_window(auto_id="1001", class_name="Edit"),
        lambda: d.child_window(auto_id="1001"),
        lambda: d.child_window(class_name="Edit"),
    ])
    if field is None:
        return ("The Save dialog opened but exposes no file-name field. "
                "Its controls: %s" % _names_of(dlg))

    from pywinauto.keyboard import send_keys as _sk
    try:
        field.click_input()
        _sk("^a")
    except Exception:
        pass
    wrote = False
    try:
        import pyperclip
        pyperclip.copy(dest)
        _t.sleep(0.15)
        _sk("^v")
        wrote = True
    except Exception:
        pass
    if not wrote:
        try:
            _sk(dest, with_spaces=True, pause=0.01)
            wrote = True
        except Exception as e:
            return "I could not type into the file-name field: %s" % e
    _t.sleep(0.3)

    try:
        shown = str(field.get_value() or field.window_text() or "")
    except Exception:
        shown = ""
    if shown and _o.path.basename(dest).casefold() not in shown.casefold():
        return ("I typed %r but the field reads %r - stopping before Save."
                % (dest, shown[:80]))

    save = _first(d, [
        lambda: d.child_window(auto_id="1", class_name="Button"),
        lambda: d.child_window(title_re="(?i)^&?(save|ذخیره( کردن)?)$",
                               class_name="Button"),
    ])
    if save is None:
        return ("I filled the file name but found no uniquely identified Save "
                "button, so I did not press Enter blind. Controls: %s" % _names_of(dlg))
    try:
        save.click_input()
    except Exception:
        try:
            save.invoke()
        except Exception as e:
            return "I could not press Save: %s" % e

    extra = _click_replace_if_prompted(before | {_hwnd(dlg)})

    t0 = _t.time()
    while _t.time() - t0 < 8.0:
        st = _stat_of(dest)
        if st and st != st_before:
            return "Saved%s. I checked the disk: %s now exists (%d bytes)." % (
                extra, dest, st[1])
        _t.sleep(0.25)
    return ("I pressed Save but %s is not on disk (or did not change), so I will "
            "not claim it was saved." % dest)


_ui_click_v5 = ui_click


def ui_click(parameters, player=None, session_memory=None) -> str:
    act = str((parameters or {}).get("action") or "").lower()
    if act in ("save_as", "saveas", "save_as_file"):
        return _save_as_v2(parameters)
    return _ui_click_v5(parameters, player=player, session_memory=session_memory)


# ── v5: the real Save-As path, matched by IDENTITY not by UIA Name ───────────
# MEASURED: with the foreground fix, Ctrl+S DID open the dialog (focus=True,
# fg==win=True) but the reader reported "no readable file-name field" - because
# it looked for a control NAME and the modern Windows 11 save dialog's file-name
# field has an EMPTY Name (class 'Edit' under 'FileNameControlHost', auto_id
# '1001'); it may also not expose a Value pattern. So this path matches by
# auto_id / class_name, writes with the CLIPBOARD (not ValuePattern), clicks a
# UNIQUELY identified Save (auto_id '1', class 'Button') - never a blind Enter -
# handles an overwrite prompt by ID, and then asks the FILESYSTEM whether it
# really happened. No file on disk => it says so, always.
def _fg_win():
    try:
        import ctypes
        h = int(ctypes.windll.user32.GetForegroundWindow())
    except Exception:
        return None
    for w in _windows():
        if _hwnd(w) == h:
            return w
    return None


def _uia_dialog(dlg):
    from pywinauto import Application
    h = _hwnd(dlg)
    app = Application(backend="uia").connect(handle=h)
    d = app.window(handle=h)
    try:
        d.wait("visible enabled", timeout=6)
    except Exception:
        pass
    return d


def _first(d, probes):
    for p in probes:
        try:
            c = p()
            if c is not None and c.exists(timeout=0.6):
                return c
        except Exception:
            continue
    return None


def _click_replace_if_prompted(before):
    import time as _t
    for _ in range(8):
        w = _wait_for_dialog(before, timeout=0.7)
        if w is None:
            return ""
        try:
            d = _uia_dialog(w)
            btn = _first(d, [
                lambda: d.child_window(title_re="(?i)^&?(replace|yes|جایگزین|بله)$",
                                       class_name="Button"),
                lambda: d.child_window(auto_id="6", class_name="Button"),   # Yes
            ])
            if btn is not None:
                try:
                    btn.click_input()
                except Exception:
                    btn.invoke()
                return " (I confirmed the overwrite)"
        except Exception:
            pass
        _t.sleep(0.25)
    return ""


def _save_as_v2(p):
    import os as _o
    import time as _t
    title = str((p or {}).get("window") or "").strip()
    name = str((p or {}).get("text") or (p or {}).get("name") or "").strip()
    if not name:
        return "Give me a file name: {'action':'save_as','window':'Notepad','text':'testy.txt'}"
    dest = _desktop_path(name)

    tgt = _resolve_window(title) if title else _fg_win()
    if tgt is None:
        return "I cannot see a window matching %r - open the app first." % title
    before = {_hwnd(w) for w in _windows()}
    st_before = _stat_of(dest)
    if not _force_foreground(tgt):
        return "I could not bring %r to the front, so I did not type blind." % title
    if not _send_keys(tgt, "^s"):
        return "I could not send Ctrl+S to %r." % title

    dlg = _wait_for_dialog(before, timeout=6.0, pid=tgt.get("pid"))
    if dlg is None:
        st = _stat_of(dest)
        if st and st != st_before:
            return "Saved (no dialog needed - the file was already named). %s is on disk." % dest
        return ("Ctrl+S opened no Save dialog in %r and %s is not on disk, "
                "so nothing was saved." % (title, dest))

    try:
        d = _uia_dialog(dlg)
    except Exception as e:
        return "I opened the Save dialog but could not attach to it: %s" % e

    field = _first(d, [
        lambda: d.child_window(auto_id="FileNameControlHost", class_name="Edit"),
        lambda: d.child_window(auto_id="1001", class_name="Edit"),
        lambda: d.child_window(auto_id="1001"),
        lambda: d.child_window(class_name="Edit"),
    ])
    if field is None:
        return ("The Save dialog opened but exposes no file-name field. "
                "Its controls: %s" % _names_of(dlg))

    from pywinauto.keyboard import send_keys as _sk
    try:
        field.click_input()
        _sk("^a")
    except Exception:
        pass
    wrote = False
    try:
        import pyperclip
        pyperclip.copy(dest)
        _t.sleep(0.15)
        _sk("^v")
        wrote = True
    except Exception:
        pass
    if not wrote:
        try:
            _sk(dest, with_spaces=True, pause=0.01)
            wrote = True
        except Exception as e:
            return "I could not type into the file-name field: %s" % e
    _t.sleep(0.3)

    try:
        shown = str(field.get_value() or field.window_text() or "")
    except Exception:
        shown = ""
    if shown and _o.path.basename(dest).casefold() not in shown.casefold():
        return ("I typed %r but the field reads %r - stopping before Save."
                % (dest, shown[:80]))

    save = _first(d, [
        lambda: d.child_window(auto_id="1", class_name="Button"),
        lambda: d.child_window(title_re="(?i)^&?(save|ذخیره( کردن)?)$",
                               class_name="Button"),
    ])
    if save is None:
        return ("I filled the file name but found no uniquely identified Save "
                "button, so I did not press Enter blind. Controls: %s" % _names_of(dlg))
    try:
        save.click_input()
    except Exception:
        try:
            save.invoke()
        except Exception as e:
            return "I could not press Save: %s" % e

    extra = _click_replace_if_prompted(before | {_hwnd(dlg)})

    t0 = _t.time()
    while _t.time() - t0 < 8.0:
        st = _stat_of(dest)
        if st and st != st_before:
            return "Saved%s. I checked the disk: %s now exists (%d bytes)." % (
                extra, dest, st[1])
        _t.sleep(0.25)
    return ("I pressed Save but %s is not on disk (or did not change), so I will "
            "not claim it was saved." % dest)


_ui_click_v5 = ui_click


def ui_click(parameters, player=None, session_memory=None) -> str:
    act = str((parameters or {}).get("action") or "").lower()
    if act in ("save_as", "saveas", "save_as_file"):
        return _save_as_v2(parameters)
    return _ui_click_v5(parameters, player=player, session_memory=session_memory)


# ── v6: resolve the target with the SAME picker the engine trusts ────────────
# MEASURED contradiction: the test foregrounded da._pick_window('Notepad') and got
# focus=True, but save_as then re-resolved with ui_click._resolve_window() and
# reported "I could not bring 'Notepad' to the front" - i.e. the two resolvers
# returned DIFFERENT windows (the second hidden/minimized/wrong), because
# _force_foreground refused to type into anything it could not prove was in front.
# Fix: resolve once, THROUGH desktop_agent._pick_window (the hardened picker),
# validate the HWND, treat an already-foreground window as instant success, and
# retry politely instead of giving up. Re-resolving was the only reason the test
# and save_as disagreed.
def _resolve_window(title):
    if not title:
        return _fg_win()
    try:
        from core import desktop_agent as da
        w = da._pick_window(title, tries=3, settle=0.2)
    except Exception:
        w = None
    h = _hwnd(w)
    try:
        if h and _u32.IsWindow(h):
            return w
    except Exception:
        pass
    return None


def _force_foreground(win, tries=12):
    import time as _t
    hwnd = _hwnd(win)
    if not hwnd:
        return False
    try:
        if not _u32.IsWindow(hwnd):
            return False
        if _is_fg(hwnd):
            return True
        if _u32.IsIconic(hwnd):
            _u32.ShowWindow(hwnd, 9)          # SW_RESTORE
    except Exception:
        pass
    cur = int(_kt32.GetCurrentThreadId())
    for _ in range(max(1, tries)):
        if _is_fg(hwnd):
            return True
        fg = int(_u32.GetForegroundWindow())
        fg_th = int(_u32.GetWindowThreadProcessId(fg, None))
        tg_th = int(_u32.GetWindowThreadProcessId(hwnd, None))
        attached = []
        try:
            for th in (fg_th, tg_th):
                if th and th != cur and th not in attached:
                    _u32.AttachThreadInput(cur, th, True)
                    attached.append(th)
            _u32.BringWindowToTop(hwnd)
            _u32.SetForegroundWindow(hwnd)
            _u32.SetActiveWindow(hwnd)
        except Exception:
            pass
        finally:
            for th in attached:
                try:
                    _u32.AttachThreadInput(cur, th, False)
                except Exception:
                    pass
        if _is_fg(hwnd):
            return True
        _t.sleep(0.15)
    return _is_fg(hwnd)


# ── keys must KEEP their spaces ──────────────────────────────────────────────
# MEASURED: _send_keys(w, "Hello VORNEX 123") wrote "HelloVORNEX123" into the file
# - pywinauto's send_keys drops spaces unless with_spaces=True, and tabs/newlines
# unless with_tabs/with_newlines are given. Any sentence typed through this path
# (a file name with spaces, a search phrase, a message) was silently mangled.
def _send_keys(win, keys, focus=True):
    if focus:
        _focus(win)
        time.sleep(0.25)
    try:
        _send_keys_raw(str(keys), pause=0.05,
                       with_spaces=True, with_tabs=True, with_newlines=True)
        return True
    except Exception:
        return False


# ── v7: a save must contain what was asked - never trust size alone ─────────
# An empty document legitimately saves as 0 bytes, but the same "exists+changed"
# check would pass a 0-byte file when the user DID write text. So save_as accepts
# `expect`; the file is read back and must contain it (Unicode-NFKC, whitespace
# collapsed). The base handler is captured ONCE via globals() so appending this
# block a second time can never make the wrapper call itself.
_SAVE_AS_BASE = globals().get("_SAVE_AS_BASE") or _save_as_v2


def _save_as_v2(p):
    out = _SAVE_AS_BASE(p)
    want = str((p or {}).get("expect") or (p or {}).get("expect_text") or "").strip()
    if not want or "now exists" not in out:
        return out
    dest = _desktop_path(str((p or {}).get("text") or (p or {}).get("name") or ""))
    try:
        with open(dest, "r", encoding="utf-8", errors="ignore") as f:
            body = f.read()
    except Exception:
        return out + " (I could not read it back to confirm its contents.)"

    def _norm(s):
        import unicodedata as _ud
        return " ".join(_ud.normalize("NFKC", str(s)).split()).casefold()

    if _norm(want) in _norm(body):
        return out + " Its contents match what you asked to write."
    return ("I saved %s but its contents do not contain %r, so I will NOT claim the "
            "text was saved correctly." % (dest, want[:60]))
