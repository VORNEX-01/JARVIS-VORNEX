"""JARVIS universal Windows window/UI perception and verified control engine."""
from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes

try:
    import psutil
except Exception:
    psutil = None

try:
    import uiautomation as auto
except Exception:
    auto = None

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.05
except Exception:
    pyautogui = None

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32
SW_RESTORE = 9
SW_SHOW = 5

_WNDENUMPROC = ctypes.WINFUNCTYPE(
    ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p
)

_SKIP_TITLES = {"taskbar", "program manager"}
_OWN_TITLES = ("jarvis", "vornex")


def _norm(value) -> str:
    return str(value or "").strip().casefold()


def _proc_name(pid: int) -> str:
    if psutil is None:
        return ""
    try:
        return psutil.Process(int(pid)).name() or ""
    except Exception:
        return ""


def _class_name(hwnd: int) -> str:
    try:
        buf = ctypes.create_unicode_buffer(256)
        _user32.GetClassNameW(int(hwnd), buf, 256)
        return buf.value or ""
    except Exception:
        return ""


def _win_text(hwnd: int) -> str:
    try:
        n = _user32.GetWindowTextLengthW(int(hwnd))
        if n <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(n + 1)
        _user32.GetWindowTextW(int(hwnd), buf, n + 1)
        return (buf.value or "").strip()
    except Exception:
        return ""


def _win_pid(hwnd: int) -> int:
    try:
        pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(int(hwnd), ctypes.byref(pid))
        return int(pid.value)
    except Exception:
        return 0


def _win_rect(hwnd: int) -> tuple:
    try:
        r = wintypes.RECT()
        _user32.GetWindowRect(int(hwnd), ctypes.byref(r))
        return int(r.left), int(r.top), int(r.right), int(r.bottom)
    except Exception:
        return 0, 0, 0, 0


def _is_cloaked(hwnd: int) -> bool:
    try:
        dwm = ctypes.windll.dwmapi
        value = ctypes.c_int(0)
        dwm.DwmGetWindowAttribute(
            ctypes.c_void_p(hwnd), 14,
            ctypes.byref(value), ctypes.sizeof(value)
        )
        return bool(value.value)
    except Exception:
        return False


def _is_iconic(hwnd: int) -> bool:
    try:
        return bool(_user32.IsIconic(int(hwnd)))
    except Exception:
        return False


def _uia_title(hwnd: int) -> str:
    if auto is None:
        return ""
    try:
        c = auto.ControlFromHandle(int(hwnd))
        return str(c.Name or "").strip() if c else ""
    except Exception:
        return ""


def own_pids():
    return {os.getpid()}


def _is_own_window(title: str) -> bool:
    n = _norm(title)
    return any(x in n for x in _OWN_TITLES)


def raw_windows():
    rows = []
    me = os.getpid()

    def callback(hwnd, _):
        try:
            h = int(hwnd)
            title = _win_text(h)
            pid = _win_pid(h)
            cls = _class_name(h)
            l, t, r, b = _win_rect(h)
            visible = bool(_user32.IsWindowVisible(h))
            cloak = _is_cloaked(h)

            reasons = []
            if not title:
                reasons.append("no-title")
            if not visible:
                reasons.append("invisible")
            if cloak:
                reasons.append("cloaked")
            if pid == me:
                reasons.append("self")
            if _is_own_window(title):
                reasons.append("own-hud")
            if (r - l) < 40 or (b - t) < 40:
                reasons.append("tiny")

            rows.append({
                "name": title,
                "pid": pid,
                "hwnd": h,
                "exe": _proc_name(pid),
                "cls": cls,
                "rect": (l, t, r, b),
                "visible": visible,
                "cloaked": cloak,
                "keep": not reasons,
                "reasons": reasons,
            })
        except Exception:
            pass
        return True

    try:
        _user32.EnumWindows(_WNDENUMPROC(callback), 0)
    except Exception:
        pass
    return rows


def list_windows():
    out = []
    me = os.getpid()

    def callback(hwnd, _):
        try:
            h = int(hwnd)

            if not _user32.IsWindowVisible(h):
                return True
            if _is_cloaked(h):
                return True

            pid = _win_pid(h)
            if pid == me:
                return True

            title = _win_text(h) or _uia_title(h)
            if not title or _is_own_window(title):
                return True

            if _norm(title) in _SKIP_TITLES:
                return True

            iconic = _is_iconic(h)
            rect = _win_rect(h)

            if not iconic:
                if rect[2] - rect[0] < 40 or rect[3] - rect[1] < 40:
                    return True

            out.append({
                "name": title,
                "pid": pid,
                "hwnd": h,
                "exe": _proc_name(pid),
                "cls": _class_name(h),
                "rect": rect,
                "minimized": iconic,
            })
        except Exception:
            pass
        return True

    try:
        _user32.EnumWindows(_WNDENUMPROC(callback), 0)
    except Exception:
        pass

    return out


def find_window(query):
    q = _norm(query)
    if not q:
        return None

    candidates = []

    for w in list_windows():
        title = _norm(w.get("name"))
        exe = _norm(w.get("exe"))
        cls = _norm(w.get("cls"))

        score = -1

        if title == q or exe == q or exe == q + ".exe" or cls == q:
            score = 100
        elif title.startswith(q):
            score = 90
        elif exe.startswith(q):
            score = 85
        elif q in title:
            score = 75
        elif q in exe or q in cls:
            score = 65

        if score >= 0:
            candidates.append((score, w))

    if not candidates:
        return None

    candidates.sort(key=lambda x: (-x[0], -(x[1]["rect"][2] - x[1]["rect"][0]) *
                                    (x[1]["rect"][3] - x[1]["rect"][1])))

    best = candidates[0][1]

    if len(candidates) > 1 and candidates[0][0] == candidates[1][0]:
        # Exact title/exe is allowed; otherwise ambiguity is unsafe.
        if candidates[0][0] < 100:
            return None

    return best


def find_processes(query):
    if psutil is None:
        return []

    q = _norm(query)
    if not q:
        return []

    out = []
    try:
        for p in psutil.process_iter(["pid", "name"]):
            name = _norm(p.info.get("name"))
            if name and (q in name or name.startswith(q) or name == q + ".exe"):
                out.append((p.info["pid"], p.info["name"]))
    except Exception:
        pass
    return out


def window_alive(win) -> bool:
    try:
        return bool(_user32.IsWindow(int(win["hwnd"])))
    except Exception:
        return False


def activate(win, timeout: float = 4.0) -> bool:
    if not win:
        return False

    hwnd = int(win.get("hwnd") or 0)
    if not hwnd:
        return False

    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        try:
            if _user32.IsIconic(hwnd):
                _user32.ShowWindow(hwnd, SW_RESTORE)

            if _user32.GetForegroundWindow() == hwnd:
                return True

            fg = int(_user32.GetForegroundWindow())
            fg_thread = int(_user32.GetWindowThreadProcessId(fg, None))
            target_thread = int(_user32.GetWindowThreadProcessId(hwnd, None))
            current_thread = int(_kernel32.GetCurrentThreadId())

            attached = []

            for thread in (fg_thread, target_thread):
                if thread and thread != current_thread and thread not in attached:
                    try:
                        if _user32.AttachThreadInput(current_thread, thread, True):
                            attached.append(thread)
                    except Exception:
                        pass

            try:
                _user32.BringWindowToTop(hwnd)
                _user32.SetActiveWindow(hwnd)
                _user32.SetForegroundWindow(hwnd)
            finally:
                for thread in attached:
                    try:
                        _user32.AttachThreadInput(current_thread, thread, False)
                    except Exception:
                        pass

            if _user32.GetForegroundWindow() == hwnd:
                return True

        except Exception:
            pass

        time.sleep(0.15)

    return bool(_user32.GetForegroundWindow() == hwnd)


def _control_for(win):
    if auto is None or not win:
        return None
    try:
        return auto.ControlFromHandle(int(win["hwnd"]))
    except Exception:
        return None


def _value_of(control) -> str:
    try:
        return str(control.GetValuePattern().Value or "")
    except Exception:
        return ""


def _text_of(control, cap=500) -> str:
    try:
        pattern = control.GetTextPattern()
        if pattern:
            return str(pattern.DocumentRange.GetText(cap) or "").strip()
    except Exception:
        pass
    return ""


def _readable(control, cap=500) -> str:
    try:
        text = _text_of(control, cap)
        if text:
            return text[:cap]
    except Exception:
        pass

    try:
        value = _value_of(control)
        if value:
            return value[:cap]
    except Exception:
        pass

    try:
        return str(control.Name or "").strip()[:cap]
    except Exception:
        return ""


def _screen_size():
    try:
        return (
            int(_user32.GetSystemMetrics(0) or 1920),
            int(_user32.GetSystemMetrics(1) or 1080),
        )
    except Exception:
        return 1920, 1080


def _safe_rect(control):
    try:
        r = control.BoundingRectangle
        rect = (int(r.left), int(r.top), int(r.right), int(r.bottom))
        if rect[2] <= rect[0] or rect[3] <= rect[1]:
            return None
        return rect
    except Exception:
        return None


def inventory(win, limit: int = 300, max_depth: int = 14) -> list:
    """Return real accessible controls and their REAL screen rectangles."""
    root = _control_for(win)
    if root is None:
        return []

    sw, sh = _screen_size()
    items = []

    def walk(control, depth):
        if len(items) >= limit or depth > max_depth:
            return

        try:
            children = control.GetChildren()
        except Exception:
            children = []

        for child in children:
            if len(items) >= limit:
                return

            try:
                rect = _safe_rect(child)

                if rect:
                    l, t, r, b = rect
                    cx = (l + r) // 2
                    cy = (t + b) // 2

                    onscreen = (
                        -2 <= cx <= sw + 2 and
                        -2 <= cy <= sh + 2
                    )

                    if onscreen:
                        ctype = str(
                            getattr(child, "ControlTypeName", "") or ""
                        ).replace("Control", "")

                        items.append({
                            "i": len(items),
                            "type": ctype,
                            "name": str(getattr(child, "Name", "") or "")[:120],
                            "cls": str(getattr(child, "ClassName", "") or "")[:80],
                            "auto_id": str(
                                getattr(child, "AutomationId", "") or ""
                            )[:100],
                            "rect": rect,
                            "value": _readable(child),
                            "en": bool(getattr(child, "IsEnabled", True)),
                            "offscreen": bool(getattr(child, "IsOffscreen", False)),
                            "_control": child,
                        })
            except Exception:
                pass

            walk(child, depth + 1)

    walk(root, 0)
    return items


def snapshot_text(win, items=None) -> str:
    items = items if items is not None else inventory(win)

    lines = [
        "WINDOW %r exe=%s hwnd=%s" % (
            win.get("name", ""),
            win.get("exe", ""),
            win.get("hwnd", ""),
        )
    ]

    if not items:
        lines.append("(no accessible controls)")
        return "\n".join(lines)

    for item in items:
        lines.append(
            "[%d] %-14s %-60r rect=%r value=%r enabled=%s"
            % (
                item["i"],
                item["type"],
                item["name"],
                item["rect"],
                item["value"][:100],
                item["en"],
            )
        )

    return "\n".join(lines)


def signature(items: list) -> tuple:
    return tuple(
        (
            item.get("type"),
            item.get("name"),
            item.get("value"),
            item.get("rect"),
        )
        for item in items[:120]
    )


def focused():
    if auto is None:
        return None

    try:
        control = auto.GetFocusedControl()
        if control is None:
            return None

        top = control.GetTopLevelControl()

        return {
            "type": str(
                getattr(control, "ControlTypeName", "") or ""
            ).replace("Control", ""),
            "name": str(getattr(control, "Name", "") or "")[:120],
            "value": _readable(control),
            "hwnd": int(getattr(top, "NativeWindowHandle", 0) or 0),
        }
    except Exception:
        return None


def focused_value(cap: int = 500) -> str:
    f = focused()
    return str((f or {}).get("value") or "")[:cap]


def _control_at_index(win, index):
    items = inventory(win)
    if index < 0 or index >= len(items):
        return None, items
    return items[index], items


def click_item(win, i):
    item, items = _control_at_index(win, int(i))

    if item is None:
        return "FAILED: index %s is not in the current UI tree." % i

    control = item.get("_control")
    rect = item.get("rect")

    if not rect:
        return "FAILED: control has no real screen rectangle."

    try:
        if control is not None:
            try:
                control.GetInvokePattern().Invoke()
                return "VERIFIED_ACTION: invoked [%d] %r" % (
                    item["i"], item["name"]
                )
            except Exception:
                pass

            try:
                control.Click()
                return "VERIFIED_ACTION: UIA clicked [%d] %r" % (
                    item["i"], item["name"]
                )
            except Exception:
                pass

        if pyautogui is None:
            return "FAILED: pixel fallback unavailable."

        sw, sh = _screen_size()
        l, t, r, b = rect
        cx = max(0, min(sw - 1, (l + r) // 2))
        cy = max(0, min(sh - 1, (t + b) // 2))

        if not (0 <= cx < sw and 0 <= cy < sh):
            return "FAILED: real control center is outside the screen."

        pyautogui.click(cx, cy)

        return "ACTION_SENT: pixel click on real control center (%d,%d) for [%d] %r" % (
            cx, cy, item["i"], item["name"]
        )

    except Exception as exc:
        return "FAILED: click [%d] %r: %s" % (
            item["i"], item["name"], exc
        )


def set_value_item(win, i: int, text: str) -> str:
    item, _ = _control_at_index(win, int(i))

    if item is None:
        return "FAILED: index %s is not in the current UI tree." % i

    control = item.get("_control")
    desired = str(text)

    if control is not None:
        try:
            control.GetValuePattern().SetValue(desired)
            time.sleep(0.15)

            if _readable(control, 1000) == desired:
                return "VERIFIED_ACTION: value set on [%d] %r" % (
                    item["i"], item["name"]
                )
        except Exception:
            pass

    if pyautogui is None:
        return "FAILED: no keyboard fallback."

    rect = item.get("rect")
    if not rect:
        return "FAILED: field has no real screen rectangle."

    l, t, r, b = rect
    cx, cy = (l + r) // 2, (t + b) // 2

    try:
        pyautogui.click(cx, cy)
        pyautogui.hotkey("ctrl", "a")

        try:
            import pyperclip
            pyperclip.copy(desired)
            pyautogui.hotkey("ctrl", "v")
        except Exception:
            pyautogui.write(desired, interval=0.01)

        time.sleep(0.2)

        value = focused_value(1000)
        if desired and desired in value:
            return "VERIFIED_ACTION: typed into [%d] %r" % (
                item["i"], item["name"]
            )

        return "UNVERIFIED: text was sent but read-back did not confirm it."

    except Exception as exc:
        return "FAILED: set value: %s" % exc


def type_text(text: str) -> str:
    if pyautogui is None:
        return "FAILED: keyboard unavailable."

    try:
        import pyperclip
        pyperclip.copy(str(text))
        pyautogui.hotkey("ctrl", "v")
        return "ACTION_SENT: pasted text."
    except Exception:
        try:
            pyautogui.write(str(text), interval=0.01)
            return "ACTION_SENT: typed text."
        except Exception as exc:
            return "FAILED: %s" % exc


def press(key: str) -> str:
    if pyautogui is None:
        return "FAILED: keyboard unavailable."
    try:
        pyautogui.press(str(key))
        return "ACTION_SENT: pressed %s" % key
    except Exception as exc:
        return "FAILED: %s" % exc


def hotkey(spec: str) -> str:
    if pyautogui is None:
        return "FAILED: keyboard unavailable."

    keys = [x.strip() for x in str(spec or "").split("+") if x.strip()]
    if not keys:
        return "FAILED: no keys supplied."

    try:
        pyautogui.hotkey(*keys)
        return "ACTION_SENT: hotkey %s" % spec
    except Exception as exc:
        return "FAILED: %s" % exc


def unhide(app):
    processes = find_processes(app)
    pids = {int(pid) for pid, _ in processes}

    if not pids:
        return None

    candidates = []

    def callback(hwnd, _):
        try:
            h = int(hwnd)
            pid = _win_pid(h)
            if pid not in pids:
                return True

            rect = _win_rect(h)
            area = max(0, rect[2] - rect[0]) * max(0, rect[3] - rect[1])

            if area:
                candidates.append((area, h))
        except Exception:
            pass
        return True

    try:
        _user32.EnumWindows(_WNDENUMPROC(callback), 0)
    except Exception:
        pass

    if not candidates:
        return None

    _, hwnd = max(candidates)

    try:
        _user32.ShowWindow(hwnd, SW_RESTORE)
        _user32.ShowWindow(hwnd, SW_SHOW)
    except Exception:
        pass

    w = find_window(app)
    if w:
        activate(w)

    return w


def list_processes(query):
    return find_processes(query)
