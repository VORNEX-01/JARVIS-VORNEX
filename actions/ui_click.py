"""JARVIS universal verified Windows UI action engine."""
from __future__ import annotations

import os
import time
import unicodedata

from core import window_agent as WA

TOOL = {
    "name": "ui_click",
    "description": (
        "Generic Windows UI perception and control. "
        "Find windows and controls by name, click, right-click, "
        "set text, type, send keys, and perform verified Save As."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "windows",
                    "list",
                    "focus",
                    "click",
                    "right_click",
                    "set_text",
                    "keys",
                    "type",
                    "save_as",
                ],
            },
            "window": {"type": "string"},
            "name": {"type": "string"},
            "control": {"type": "string"},
            "text": {"type": "string"},
            "keys": {"type": "string"},
            "path": {"type": "string"},
            "replace": {"type": "boolean"},
            "expect": {"type": "string"},
        },
    },
}

_MAX_CONTROLS = 500


def _norm(value):
    return " ".join(
        unicodedata.normalize("NFKC", str(value or "")).split()
    ).casefold()


def _hwnd(win):
    try:
        return int((win or {}).get("hwnd") or 0)
    except Exception:
        return 0


def _area(win):
    try:
        r = win.get("rect") or (0, 0, 0, 0)
        return max(0, r[2] - r[0]) * max(0, r[3] - r[1])
    except Exception:
        return 0


def _foreground():
    try:
        import ctypes
        hwnd = int(ctypes.windll.user32.GetForegroundWindow())
    except Exception:
        return None

    for win in WA.list_windows():
        if _hwnd(win) == hwnd:
            return win
    return None


def _find_window(title):
    return WA.find_window(title)


def _resolve_window(title=""):
    query = str(title or "").strip()

    if not query:
        return _foreground()

    win = WA.find_window(query)
    if win is not None:
        return win

    matches = []
    nq = _norm(query)

    for w in WA.list_windows():
        fields = (
            w.get("name"),
            w.get("title"),
            w.get("exe"),
            w.get("process"),
        )
        if any(nq == _norm(x) for x in fields if x):
            matches.append(w)

    return matches[0] if len(matches) == 1 else None


def _controls_of(win, limit=_MAX_CONTROLS):
    return WA.inventory(win, limit=limit)


def _named_controls(exclude_hwnd=0):
    out = []
    for win in WA.list_windows():
        if _hwnd(win) == int(exclude_hwnd or 0):
            continue
        try:
            out.extend(_controls_of(win))
        except Exception:
            continue
    return out


def _pick(controls, name):
    q = _norm(name)
    if not q:
        return None

    scored = []

    for c in controls:
        values = (
            c.get("name"),
            c.get("text"),
            c.get("value"),
            c.get("automation_id"),
            c.get("auto_id"),
            c.get("control_type"),
            c.get("type"),
        )

        best = 0.0

        for value in values:
            v = _norm(value)
            if not v:
                continue
            if q == v:
                best = max(best, 1.0)
            elif q in v:
                best = max(best, 0.86)
            elif v in q:
                best = max(best, 0.78)

        if best:
            scored.append((best, c))

    if not scored:
        return None

    scored.sort(key=lambda x: (-x[0], _area(x[1])))
    best_score, best = scored[0]

    if len(scored) > 1:
        second_score = scored[1][0]
        if best_score < 1.0 and best_score - second_score < 0.08:
            return None

    return best


def _uia_window(win):
    hwnd = _hwnd(win)
    if not hwnd:
        return None

    try:
        import pywinauto
        return pywinauto.Desktop(backend="uia").window(handle=hwnd)
    except Exception:
        return None


def _all_controls(win):
    root = _uia_window(win)
    if root is None:
        return []

    try:
        return list(root.descendants())
    except Exception:
        return []


def _control_matches(wrapper, item):
    try:
        wanted_name = _norm(
            item.get("name") or item.get("text") or item.get("value")
        )
        wanted_auto = _norm(
            item.get("automation_id") or item.get("auto_id")
        )
        wanted_type = _norm(
            item.get("control_type") or item.get("type")
        )

        if wanted_auto:
            try:
                if _norm(wrapper.element_info.automation_id) == wanted_auto:
                    return True
            except Exception:
                pass

        try:
            actual_type = _norm(wrapper.element_info.control_type)
        except Exception:
            actual_type = ""

        try:
            actual_name = _norm(wrapper.window_text())
        except Exception:
            actual_name = ""

        if wanted_type and actual_type != wanted_type:
            return False

        if wanted_name and actual_name == wanted_name:
            return True

        if wanted_name and wanted_name in actual_name:
            return True

    except Exception:
        pass

    return False


def _wrap(win, item):
    controls = _all_controls(win)

    if not controls:
        return None

    for control in controls:
        if _control_matches(control, item):
            return control

    target_rect = item.get("rect")
    if target_rect:
        try:
            tx = (target_rect[0] + target_rect[2]) / 2
            ty = (target_rect[1] + target_rect[3]) / 2
        except Exception:
            target_rect = None

        if target_rect:
            best = None
            best_d = None

            for control in controls:
                try:
                    r = control.rectangle()
                    cx = (r.left + r.right) / 2
                    cy = (r.top + r.bottom) / 2
                    d = abs(cx - tx) + abs(cy - ty)

                    if best_d is None or d < best_d:
                        best = control
                        best_d = d
                except Exception:
                    continue

            if best is not None and best_d is not None and best_d < 80:
                return best

    return None


def _invoke(el):
    if el is None:
        return False

    try:
        pattern = el.iface_invoke
        pattern.Invoke()
        return True
    except Exception:
        pass

    try:
        el.invoke()
        return True
    except Exception:
        pass

    try:
        el.click_input()
        return True
    except Exception:
        return False


def _right_click(el):
    if el is None:
        return False

    try:
        el.right_click_input()
        return True
    except Exception:
        pass

    try:
        r = el.rectangle()
        import pyautogui
        pyautogui.rightClick(
            int((r.left + r.right) / 2),
            int((r.top + r.bottom) / 2),
        )
        return True
    except Exception:
        return False


def _fill(el, text):
    if el is None:
        return False

    text = str(text)

    try:
        el.set_edit_text(text)
        return True
    except Exception:
        pass

    try:
        el.click_input()
        import pywinauto.keyboard as keyboard
        keyboard.send_keys("^a")
        keyboard.send_keys(text, with_spaces=True)
        return True
    except Exception:
        return False


def _read_back(el):
    if el is None:
        return ""

    try:
        value = el.get_value()
        if value is not None:
            return str(value)
    except Exception:
        pass

    try:
        return str(el.window_text() or "")
    except Exception:
        return ""


def _still_there(el):
    try:
        return bool(el.exists())
    except Exception:
        return False


def _force_foreground(win):
    try:
        return bool(WA.activate(win))
    except Exception:
        return False


def _send_keys(keys):
    try:
        import pywinauto.keyboard as keyboard
        keyboard.send_keys(
            str(keys),
            with_spaces=True,
            with_tabs=True,
            with_newlines=True,
        )
        return True
    except Exception:
        return False


def _desktop_path(path):
    p = os.path.expandvars(os.path.expanduser(str(path or "")))

    if os.path.isabs(p):
        return os.path.normpath(p)

    candidates = [
        os.path.join(os.path.expanduser("~/Desktop"), p),
        os.path.join(os.path.expanduser("~/Downloads"), p),
        os.path.abspath(p),
    ]

    for candidate in candidates:
        parent = os.path.dirname(candidate)
        if os.path.isdir(parent):
            return os.path.normpath(candidate)

    return os.path.normpath(candidates[0])


def _find_save_dialog(before_hwnds, app_win, timeout=5.0):
    deadline = time.time() + timeout
    app_pid = int((app_win or {}).get("pid") or 0)

    while time.time() < deadline:
        for win in WA.list_windows():
            hwnd = _hwnd(win)
            pid = int(win.get("pid") or 0)

            if not hwnd or hwnd in before_hwnds:
                continue

            if app_pid and pid and pid != app_pid:
                continue

            title = _norm(win.get("name") or win.get("title"))

            if any(
                token in title
                for token in (
                    "save as",
                    "save",
                    "ذخیره",
                )
            ):
                return win

        time.sleep(0.15)

    return None


def _save_as(win, path, replace=False, expect=""):
    destination = _desktop_path(path)

    if not _force_foreground(win):
        return "Failed: could not activate target window."

    before = {_hwnd(w) for w in WA.list_windows() if _hwnd(w)}

    if not _send_keys("^s"):
        return "Failed: could not send Ctrl+S."

    dialog = _find_save_dialog(before, win)
    if dialog is None:
        return "Failed: Save dialog was not detected."

    if not _force_foreground(dialog):
        return "Failed: could not activate Save dialog."

    controls = _controls_of(dialog)
    filename = None

    preferred = (
        "1001",
        "FileNameControlHost",
        "File name",
        "Filename",
        "نام فایل",
    )

    for key in preferred:
        filename = _pick(controls, key)
        if filename:
            break

    if filename is None:
        for item in controls:
            typ = _norm(item.get("control_type") or item.get("type"))
            if typ in ("edit", "document"):
                filename = item
                break

    if filename is None:
        return "Failed: Save filename control was not found."

    element = _wrap(dialog, filename)
    if element is None:
        return "Failed: Save filename control could not be resolved."

    if not _fill(element, destination):
        return "Failed: could not enter destination filename."

    typed = _read_back(element)
    if destination.casefold() not in typed.casefold():
        return "Failed: filename field verification failed."

    controls = _controls_of(dialog)
    save_button = None

    for key in ("Save", "save", "ذخیره"):
        save_button = _pick(controls, key)
        if save_button:
            break

    if save_button is None:
        for item in controls:
            if _norm(item.get("control_type") or item.get("type")) == "button":
                if "save" in _norm(item.get("name") or item.get("text")):
                    save_button = item
                    break

    if save_button is None:
        return "Failed: Save button was not found."

    save_element = _wrap(dialog, save_button)
    if save_element is None or not _invoke(save_element):
        return "Failed: could not activate Save."

    deadline = time.time() + 5.0
    target_exists = False

    while time.time() < deadline:
        if os.path.isfile(destination):
            target_exists = True
            break
        time.sleep(0.15)

    if not target_exists and not replace:
        return "Failed: output file was not verified."

    if replace and not os.path.isfile(destination):
        return "Failed: replacement file was not verified."

    if expect:
        try:
            with open(destination, "r", encoding="utf-8", errors="replace") as f:
                data = f.read()
            if str(expect) not in data:
                return "Failed: expected text was not found in saved file."
        except Exception as exc:
            return f"Failed: could not verify saved file contents: {exc}"

    return f"Verified: saved file exists at {destination}"


def _format_windows():
    windows = WA.list_windows()

    if not windows:
        return "Verified: no visible windows found."

    lines = ["Verified: visible windows:"]
    for w in windows:
        lines.append(
            f"- {w.get('name') or '<untitled>'} "
            f"[hwnd={w.get('hwnd')}, pid={w.get('pid')}, "
            f"exe={w.get('exe') or ''}]"
        )

    return "\n".join(lines)


def _format_inventory(win):
    controls = _controls_of(win)

    if not controls:
        return "Verified: no readable UI controls found."

    lines = [f"Verified: {len(controls)} UI controls detected."]

    for item in controls:
        name = (
            item.get("name")
            or item.get("text")
            or item.get("value")
            or "<unnamed>"
        )
        typ = item.get("control_type") or item.get("type") or ""
        auto_id = item.get("automation_id") or item.get("auto_id") or ""

        lines.append(
            f"- {name} | type={typ} | auto_id={auto_id}"
        )

    return "\n".join(lines)


def ui_click(parameters, player=None, session_memory=None) -> str:
    p = parameters or {}

    action = _norm(p.get("action") or p.get("op") or "")
    window_name = (
        p.get("window")
        or p.get("title")
        or p.get("app")
        or ""
    )

    if action in ("windows", "list_windows"):
        return _format_windows()

    if action in ("list", "inventory"):
        win = _resolve_window(window_name)
        if win is None:
            return "Failed: target window was not found."
        return _format_inventory(win)

    if action in ("focus", "activate"):
        win = _resolve_window(window_name)
        if win is None:
            return "Failed: target window was not found."
        if not _force_foreground(win):
            return "Failed: target window could not be activated."
        return f"Verified: activated {win.get('name') or window_name}"

    win = _resolve_window(window_name)
    if win is None:
        return "Failed: target window was not found."

    if not _force_foreground(win):
        return "Failed: target window could not be activated."

    if action in ("keys", "send_keys"):
        keys = p.get("keys") or p.get("text") or ""
        if not keys:
            return "Failed: no key sequence supplied."

        if not _send_keys(keys):
            return "Failed: key sequence could not be sent."

        return "Verified: key sequence sent to active window."

    if action in ("type", "type_text"):
        text = str(p.get("text") or "")

        if not _send_keys(text):
            return "Failed: text could not be typed."

        return "Verified: text sent to active window."

    controls = _controls_of(win)

    target_name = (
        p.get("name")
        or p.get("control")
        or p.get("target")
        or ""
    )

    if action in ("click", "right_click", "set_text", "fill"):
        if not target_name:
            return "Failed: control name was not supplied."

        item = _pick(controls, target_name)

        if item is None:
            return f"Failed: control '{target_name}' was not uniquely found."

        element = _wrap(win, item)

        if element is None:
            return f"Failed: control '{target_name}' could not be resolved."

        if action == "click":
            if not _invoke(element):
                return f"Failed: could not click '{target_name}'."

            return f"Verified: activated control '{target_name}'."

        if action == "right_click":
            if not _right_click(element):
                return f"Failed: could not right-click '{target_name}'."

            return f"Verified: right-clicked control '{target_name}'."

        text = str(p.get("text") or "")

        if not _fill(element, text):
            return f"Failed: could not set text in '{target_name}'."

        readback = _read_back(element)

        if _norm(readback) != _norm(text):
            return (
                f"Failed: text verification failed for '{target_name}'. "
                f"readback={readback!r}"
            )

        return f"Verified: set text in '{target_name}'."

    if action == "save_as":
        path = p.get("path") or p.get("text") or ""
        if not path:
            return "Failed: save_as requires path."

        return _save_as(
            win,
            path,
            replace=bool(p.get("replace", False)),
            expect=str(p.get("expect") or ""),
        )

    return (
        "Failed: unsupported ui_click action. "
        "Supported: windows, list, focus, click, right_click, "
        "set_text, keys, type, save_as."
    )

# ActionLoader runtime binding: handler must be the actual callable.
TOOL["handler"] = ui_click
