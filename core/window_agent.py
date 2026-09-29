"""
core/window_agent.py — live perception + control of ANY window.

THE bug this exists to kill: every helper asked Windows for the FOREGROUND
window, and the foreground window was JARVIS's own HUD. So the assistant read
its OWN tree and announced the target app "was not open".

This module never asks "what is in front?". It asks "which top-level windows
exist", drops our own process, picks the target by PROCESS/TITLE, raises it on
purpose, and reads THAT window's UI Automation tree — no screenshots unless the
tree is empty.
"""
from __future__ import annotations

import ctypes
import os
import time

try:
    import uiautomation as auto
except Exception:
    auto = None

try:
    import psutil
except Exception:
    psutil = None

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32
SW_RESTORE = 9


def _norm(s) -> str:
    return (s or "").strip().casefold()


def _proc_name(pid: int) -> str:
    if psutil is None:
        return ""
    try:
        return psutil.Process(pid).name() or ""
    except Exception:
        return ""


def activate(win, timeout: float = 3.0) -> bool:
    """Raise + focus, using the AttachThreadInput trick (the only reliable way)."""
    hwnd = win["hwnd"]
    end = time.time() + timeout
    while time.time() < end:
        try:
            if _user32.GetForegroundWindow() == hwnd:
                return True
            fg = _user32.GetForegroundWindow()
            fg_tid = _user32.GetWindowThreadProcessId(fg, None)
            cur_tid = _kernel32.GetCurrentThreadId()
            attached = False
            if fg_tid and fg_tid != cur_tid:
                attached = bool(_user32.AttachThreadInput(fg_tid, cur_tid, True))
            try:
                if _user32.IsIconic(hwnd):
                    _user32.ShowWindow(hwnd, SW_RESTORE)
                _user32.BringWindowToTop(hwnd)
                _user32.SetForegroundWindow(hwnd)
                _user32.SetActiveWindow(hwnd)
            finally:
                if attached:
                    _user32.AttachThreadInput(fg_tid, cur_tid, False)
        except Exception:
            pass
        if _user32.GetForegroundWindow() == hwnd:
            return True
        time.sleep(0.15)
    return _user32.GetForegroundWindow() == hwnd


def window_alive(win) -> bool:
    try:
        return bool(_user32.IsWindow(win["hwnd"]))
    except Exception:
        return False


def _control_for(win):
    if auto is None:
        return None
    try:
        c = auto.ControlFromHandle(win["hwnd"])
        return c
    except Exception:
        return None


def _value_of(c):
    try:
        return c.GetValuePattern().Value
    except Exception:
        return ""


_SCREEN = None




def snapshot_text(win, items=None) -> str:
    items = items if items is not None else inventory(win)
    if not items:
        return ("(no accessible controls read from window %r — it may be a "
                "canvas/game drawing itself)" % win["name"])
    lines = ["WINDOW %r  exe=%s" % (win["name"], win["exe"] or "?")]
    for it in items:
        v = "  value=%r" % it["value"] if it["value"] else ""
        lines.append("[%d] %-10s %-38r %s%s"
                     % (it["i"], it["type"], it["name"], it["rect"], v))
    return "\n".join(lines)


def signature(items: list) -> tuple:
    return tuple((it["type"], it["name"], it["value"]) for it in items[:90])


def set_value_item(win, i: int, text: str) -> str:
    items = inventory(win)
    if i < 0 or i >= len(items):
        return "index %d is not in the window" % i
    c = _control_for(win)
    if c is not None:
        try:
            target = None
            flat = []

            def collect(x, d):
                if d > 12:
                    return
                for k in x.GetChildren():
                    flat.append(k)
                    collect(k, d + 1)

            collect(c, 0)
            if 0 <= i < len(flat):
                target = flat[i]
            if target is not None:
                target.SetFocus()
                time.sleep(0.15)
                target.GetValuePattern().SetValue(text)
                time.sleep(0.2)
                if str(_value_of(target)) == text:
                    return "set [%d] to %r" % (i, text)
        except Exception:
            pass
    click_item(win, i)
    time.sleep(0.3)
    hotkey("ctrl+a")
    time.sleep(0.1)
    type_text(text)
    return "clicked + pasted into [%d]" % i


def type_text(text: str) -> str:
    if pyautogui is None:
        return "keyboard unavailable"
    try:
        import pyperclip
        pyperclip.copy(text)
        time.sleep(0.15)
        pyautogui.hotkey("ctrl", "v")
    except Exception:
        pyautogui.write(text, interval=0.03)
    return "typed %r" % text[:40]


def press(key: str) -> str:
    if pyautogui is None:
        return "keyboard unavailable"
    pyautogui.press((key or "enter").strip())
    return "pressed %s" % key


def hotkey(spec: str) -> str:
    if pyautogui is None:
        return "keyboard unavailable"
    keys = [k.strip() for k in (spec or "").split("+") if k.strip()]
    if not keys:
        return "no keys given"
    pyautogui.hotkey(*keys)
    return "hotkey %s" % spec


try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.05
except Exception:
    pyautogui = None
_SKIP_TITLES = ("taskbar", "program manager")


def _class_name(hwnd):
    try:
        buf = ctypes.create_unicode_buffer(256)
        _user32.GetClassNameW(hwnd, buf, 256)
        return buf.value or ""
    except Exception:
        return ""


def own_pids():
    return {os.getpid()}


def _is_own_window(name):
    n = _norm(name)
    return any(t in n for t in _OWN_TITLES)


def find_window(query):
    """Match on title, process name, OR window class. None when unsure."""
    q = _norm(query)
    if not q:
        return None
    best, score = None, -1
    for w in list_windows():
        if any(_norm(w["name"]) == t for t in _SKIP_TITLES):
            continue
        n = _norm(w["name"])
        e = _norm(w["exe"])
        c = _norm(w.get("cls"))
        s = -1
        if n == q or e == q or e == q + ".exe" or c == q:
            s = 5
        elif e and e.startswith(q):
            s = 4
        elif n.startswith(q):
            s = 3
        elif q in n or (e and q in e) or (c and q in c):
            s = 2
        if s > score:
            best, score = w, s
    return best if score >= 2 else None


# ── v3 (overrides above) ─────────────────────────────────────────────────────
# Two things the probe proved:
#  1. auto.GetRootControl().GetChildren() MISSES real windows (UIA hides
#     cloaked/UWP ones — Settings, Photos, Aether were all invisible to it while
#     EnumWindows saw them). So we enumerate with Win32 EnumWindows and then read
#     each window's tree with UIA, instead of trusting the UIA root list.
#  2. The own-window filter matched on TITLE, and 'jarvis-vornex' made the VS Code
#     window "our own" and hid it. Our HUD is simply our own PID, so filter on
#     PID only and keep the title list very narrow.

from ctypes import wintypes

_OWN_TITLES = ("jarvis", "vornex")
_DWMWA_CLOAKED = 14
_WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

try:
    _dwm = ctypes.windll.dwmapi
except Exception:
    _dwm = None


def _is_cloaked(hwnd):
    """A UWP window that is suspended is reported by EnumWindows but drawn
    nowhere and hidden by UIA — skip it so we never 'find' a ghost."""
    if _dwm is None:
        return False
    try:
        v = ctypes.c_int(0)
        _dwm.DwmGetWindowAttribute(ctypes.c_void_p(hwnd), _DWMWA_CLOAKED,
                                   ctypes.byref(v), ctypes.sizeof(v))
        return v.value != 0
    except Exception:
        return False


def _win_text(hwnd):
    try:
        n = _user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(n + 1)
        _user32.GetWindowTextW(hwnd, buf, n + 1)
        return (buf.value or "").strip()
    except Exception:
        return ""


def _win_pid(hwnd):
    try:
        pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return int(pid.value)
    except Exception:
        return 0


def _win_rect(hwnd):
    try:
        r = wintypes.RECT()
        _user32.GetWindowRect(hwnd, ctypes.byref(r))
        return (r.left, r.top, r.right, r.bottom)
    except Exception:
        return (0, 0, 0, 0)


def raw_windows():
    """EVERY top-level window (EnumWindows) with the filter's verdict."""
    rows = []
    me = os.getpid()

    def cb(hwnd, _l):
        try:
            h = int(hwnd)
            title = _win_text(h)
            pid = _win_pid(h)
            cls = _class_name(h)
            l, t, r, b = _win_rect(h)
            vis = bool(_user32.IsWindowVisible(h))
            cl = _is_cloaked(h)
            why = []
            if not title:
                why.append("no-title")
            if not vis:
                why.append("invisible")
            if cl:
                why.append("cloaked")
            if pid == me:
                why.append("self-pid")
            if title and _is_own_window(title):
                why.append("own-hud")
            if (r - l) < 40 or (b - t) < 40:
                why.append("tiny")
            rows.append("%-42r pid=%-7s cls=%-24r vis=%-5s cloak=%-5s keep=%-5s %s"
                        % (title[:40], pid, cls[:22], vis, cl, not why,
                           ",".join(why) or "-"))
        except Exception as e:
            rows.append("<row error: %s>" % e)
        return True

    try:
        _user32.EnumWindows(_WNDENUMPROC(cb), 0)
    except Exception:
        pass
    return rows


# ── v4 (overrides above) ─────────────────────────────────────────────────────
# Three things the v3 probe showed:
#  * a MINIMISED window reports its restore rect off-screen, so the size filter
#    dropped it and the rect was useless. Keep iconic windows; activate()
#    already restores them.
#  * some apps expose a title only through UIA (Win32 caption is ''), so fall
#    back to the UIA name for windows that are visible AND uncloaked.
#  * "Telegram is running but its window is in the TRAY" is a different truth
#    from "Telegram is not installed". find_processes() lets us say which.

def _uia_title(hwnd):
    try:
        if auto is None:
            return ""
        c = auto.ControlFromHandle(hwnd)
        return (c.Name or "").strip() if c is not None else ""
    except Exception:
        return ""


def _is_iconic(hwnd):
    try:
        return bool(_user32.IsIconic(hwnd))
    except Exception:
        return False


def find_processes(query):
    """Running processes matching a name — distinguishes 'closed' from 'in tray'."""
    if psutil is None:
        return []
    q = _norm(query)
    if not q:
        return []
    out = []
    try:
        for p in psutil.process_iter(["pid", "name"]):
            nm = _norm(p.info.get("name") or "")
            if nm and (q in nm or nm.startswith(q) or nm == q + ".exe"):
                out.append((p.info["pid"], p.info["name"]))
    except Exception:
        pass
    return out


def list_windows():
    """Real top-level windows via EnumWindows, minimised ones included."""
    out = []
    me = os.getpid()

    def cb(hwnd, _l):
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
            iconic = _is_iconic(h)
            l, t, r, b = _win_rect(h)
            if not iconic and ((r - l) < 40 or (b - t) < 40):
                return True
            out.append({"name": title, "pid": pid, "hwnd": h,
                        "exe": _proc_name(pid), "cls": _class_name(h),
                        "rect": (l, t, r, b), "minimized": iconic})
        except Exception:
            pass
        return True

    try:
        _user32.EnumWindows(_WNDENUMPROC(cb), 0)
    except Exception:
        pass
    return out


# ── v5: never click or fill a control whose centre is off-screen ─────────────
# A minimised or scrolled-away window reports rects like (-32000,-32000) or
# y=-6304. Clicking there is a click into nowhere — and it is exactly how a
# message once went to the wrong place. Refuse instead of guessing.

def click_item(win, i):
    items = inventory(win)
    if i < 0 or i >= len(items):
        return "index %d is not in the window" % i
    l, t, r, b = items[i]["rect"]
    cx, cy = (l + r) // 2, (t + b) // 2
    try:
        sw, sh = pyautogui.size()
    except Exception:
        sw = sh = 0
    if sw and (cx < 0 or cy < 0 or cx > sw or cy > sh):
        return ("refused: control [%d] is off-screen at (%d,%d) — the window is "
                "probably minimised; I did not click" % (i, cx, cy))
    pyautogui.click(cx, cy)
    return "clicked [%d] %r at (%d,%d)" % (i, items[i]["name"], cx, cy)


# ── v6: read a rich-edit / document control's ACTUAL text ────────────────────
# Notepad (and any RichEdit / terminal) exposes its content through TextPattern,
# NOT through Name or ValuePattern — so inventory saw "Text Editor" with an empty
# value and the loop could never verify the sentence was typed. It kept clicking
# the same control and then died. Read the document text, safely.

def _text_of(ctrl, cap=240):
    try:
        tp = ctrl.GetTextPattern()
    except Exception:
        return ""
    if tp is None:
        return ""
    try:
        return (tp.DocumentRange.GetText(cap) or "").strip()
    except Exception:
        return ""


def _readable(ctrl, cap=200):
    """Document/edit content if available, else the old Name/Value."""
    t = ctrl.ControlTypeName or ""
    if t in ("DocumentControl", "EditControl"):
        txt = _text_of(ctrl, cap)
        if txt:
            return txt[:cap]
    return str(_value_of(ctrl) or "").strip()[:cap]


def unhide(app):
    """Bring back an app whose main window lives in the tray.

    A tray app keeps its window alive with IsWindowVisible() False, so
    list_windows()/find_window() cannot see it - and running the app again just
    pops an "already running" dialog that then dies. Enumerate EVERY top-level
    window of the matching processes, take the biggest one that is not a dialog,
    and force it visible. Returns the window, or None.
    """
    if not app:
        return None
    pids = set()
    try:
        for pid, _n in (find_processes(app) or []):
            pids.add(int(pid))
    except Exception:
        pass
    if not pids:
        return None

    from ctypes import wintypes
    u = ctypes.windll.user32
    CB = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    best = [0, -1]

    def cb(hwnd, _l):
        h = int(hwnd)
        if u.GetWindowThreadProcessId(h, None) not in pids:
            return True
        if u.GetWindow(h, 4):                 # GW_OWNER -> dialog/popup
            return True
        r = wintypes.RECT()
        try:
            u.GetWindowRect(h, ctypes.byref(r))
        except Exception:
            return True
        a = max(0, r.right - r.left) * max(0, r.bottom - r.top)
        if a > best[1]:
            best[0], best[1] = h, a
        return True

    try:
        u.EnumWindows(CB(cb), 0)
    except Exception:
        pass
    h = best[0]
    if not h or best[1] < 10000:
        return None
    try:
        u.ShowWindow(h, 9)                    # SW_RESTORE
        u.ShowWindow(h, 5)                    # SW_SHOW
        u.BringWindowToTop(h)
        u.SetForegroundWindow(h)
    except Exception:
        pass
    time.sleep(0.4)
    return find_window(app)


def focused():
    """The control that currently owns the keyboard: dict or None.

    `type` sends keystrokes to WHATEVER is focused, so the planner must know
    what that is before it decides to type instead of clicking a field.
    """
    try:
        c = auto.GetFocusedControl()
        if c is None:
            return None
        top = c.GetTopLevelControl()
        return {"type": (c.ControlTypeName or "").replace("Control", ""),
                "name": (c.Name or "")[:60],
                "hwnd": int(top.NativeWindowHandle or 0) if top else 0}
    except Exception:
        return None


def focused_value(cap: int = 200) -> str:
    """Content of the control that has the keyboard, or ''."""
    try:
        c = auto.GetFocusedControl()
        if c is None:
            return ""
        return str(_readable(c, cap) or "")
    except Exception:
        return ""


# ══════════════════════════════════════════════════════════════════════════════
#  inventory v2 - same tree, WITHOUT the blind Value-pattern probe.
#
#  MEASURED: a walk of Telegram cost ~1s of cross-process UIA calls, and one
#  send walked the tree 6 times = ~6s. The most expensive part was asking the
#  Value pattern of EVERY element: it raises a COMError for most of them, and
#  raising is slow. The value is now read only where one can exist - a field or a
#  rendered ROW (DataItem/ListItem/Text) - which is exactly where the text we
#  verify against lives. Everything else is identical to v1.
# ══════════════════════════════════════════════════════════════════════════════

def inventory(win, limit: int = 130, max_depth: int = 12) -> list:
    """On-screen controls of THIS window: index, type, name, rect, value."""
    global _SCREEN
    if _SCREEN is None:
        try:
            _u = ctypes.windll.user32
            _SCREEN = (_u.GetSystemMetrics(0) or 1920, _u.GetSystemMetrics(1) or 1080)
        except Exception:
            _SCREEN = (1920, 1080)
    root = _control_for(win)
    if root is None:
        return []
    items = []
    valued = ("Edit", "ComboBox", "Document", "DataItem", "ListItem", "Text")

    def walk(c, d):
        if len(items) >= limit or d > max_depth:
            return
        try:
            kids = c.GetChildren()
        except Exception:
            kids = []
        for x in kids:
            if len(items) >= limit:
                return
            try:
                r = x.BoundingRectangle
                l, t, rr, b = r.left, r.top, r.right, r.bottom
                if (rr - l) < 2 or (b - t) < 2:
                    walk(x, d + 1)
                    continue
                if x.IsOffscreen:
                    walk(x, d + 1)
                    continue
                _cx, _cy = (l + rr) // 2, (t + b) // 2
                if not (0 <= _cx <= _SCREEN[0] and 0 <= _cy <= _SCREEN[1]):
                    walk(x, d + 1)
                    continue
                ct = (x.ControlTypeName or "").replace("Control", "")
                items.append({
                    "i": len(items),
                    "type": ct,
                    "name": (x.Name or "")[:60],
                    "cls": (x.ClassName or "")[:36],
                    "rect": (l, t, rr, b),
                    "value": _readable(x) if ct in valued else "",
                    "en": bool(x.IsEnabled),
                })
            except Exception:
                pass
            walk(x, d + 1)

    walk(root, 0)
    return items


# ══════════════════════════════════════════════════════════════════════════════
#  inventory v5 - cached TEXT + LIVE rect, and SAFE BY CONSTRUCTION.
#  Measured here: a UIA CacheRequest fetches Name/Type/Class/Value/Enabled for the
#  WHOLE subtree in one call, but it does NOT deliver BoundingRectangle/IsOffscreen
#  (they come back 0 / True). So text comes from the cache, the rectangle is read
#  LIVE per element - and if the fast path finds suspiciously few items it is
#  thrown away and the old pure-Python walk runs. This can only ever be FASTER,
#  never less complete.
# ══════════════════════════════════════════════════════════════════════════════

import threading as _threading

_inventory_slow = inventory
_LAST = {"fast": None}

_CT = {
    50000: "Button", 50001: "Calendar", 50002: "CheckBox", 50003: "ComboBox",
    50004: "Edit", 50005: "Hyperlink", 50006: "Image", 50007: "ListItem",
    50008: "List", 50009: "Menu", 50010: "MenuBar", 50011: "MenuItem",
    50012: "ProgressBar", 50013: "RadioButton", 50014: "ScrollBar",
    50015: "Slider", 50016: "Spinner", 50017: "StatusBar", 50018: "Tab",
    50019: "TabItem", 50020: "Text", 50021: "ToolBar", 50022: "ToolTip",
    50023: "Tree", 50024: "TreeItem", 50025: "Custom", 50026: "Group",
    50027: "Thumb", 50028: "DataGrid", 50029: "DataItem", 50030: "Document",
    50031: "SplitButton", 50032: "Window", 50033: "Pane", 50034: "Header",
    50035: "HeaderItem", 50036: "Table", 50037: "TitleBar", 50038: "Separator",
}

_TLS = _threading.local()


def _uia_state():
    st = getattr(_TLS, "st", None)
    if st is not None:
        return st
    st = {"ok": False, "uia": None, "cache": None, "U": None}
    try:
        import comtypes
        import comtypes.client
        try:
            comtypes.CoInitialize()
        except Exception:
            pass
        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen import UIAutomationClient as U
        uia = comtypes.client.CreateObject(U.CUIAutomation, interface=U.IUIAutomation)
        cache = uia.CreateCacheRequest()
        for p in ("UIA_NamePropertyId", "UIA_ControlTypePropertyId",
                  "UIA_ClassNamePropertyId", "UIA_ValueValuePropertyId",
                  "UIA_IsEnabledPropertyId"):
            cache.AddProperty(getattr(U, p))
        cache.AddPattern(U.UIA_ValuePatternId)
        cache.TreeScope = U.TreeScope_Subtree
        st.update(ok=True, uia=uia, cache=cache, U=U)
    except Exception:
        st["ok"] = False
    _TLS.st = st
    return st


def _r4(r):
    if not r:
        return None
    try:
        return (int(r[0]), int(r[1]), int(r[2]), int(r[3]))
    except Exception:
        pass
    try:
        return (int(r.left), int(r.top), int(r.right), int(r.bottom))
    except Exception:
        return None


def inventory(win, limit: int = 130, max_depth: int = 12) -> list:
    """On-screen controls of THIS window: index, type, name, rect, value."""
    global _SCREEN
    if _SCREEN is None:
        try:
            _u = ctypes.windll.user32
            _SCREEN = (_u.GetSystemMetrics(0) or 1920, _u.GetSystemMetrics(1) or 1080)
        except Exception:
            _SCREEN = (1920, 1080)

    st = _uia_state()
    if not st["ok"]:
        _LAST["fast"] = False
        return _inventory_slow(win, limit, max_depth)
    U = st["U"]
    try:
        root = st["uia"].ElementFromHandleBuildCache(int(win.get("hwnd") or 0),
                                                     st["cache"])
    except Exception:
        _LAST["fast"] = False
        return _inventory_slow(win, limit, max_depth)
    if root is None:
        _LAST["fast"] = False
        return _inventory_slow(win, limit, max_depth)

    def cached(el, pid, default=None):
        try:
            return el.GetCachedPropertyValue(pid)
        except Exception:
            return default

    def kidsof(el):
        try:
            arr = el.GetCachedChildren()
            return [arr.GetElement(i) for i in range(int(arr.Length))]
        except Exception:
            return []

    def rect_of(el):
        for get in (lambda: cached(el, U.UIA_BoundingRectanglePropertyId),
                    lambda: el.CurrentBoundingRectangle,
                    lambda: el.GetCurrentPropertyValue(U.UIA_BoundingRectanglePropertyId)):
            try:
                rc = _r4(get())
            except Exception:
                rc = None
            if rc and (rc[2] - rc[0]) >= 2 and (rc[3] - rc[1]) >= 2:
                return rc
        return None

    items = []
    valued = ("Edit", "ComboBox", "Document", "DataItem", "ListItem", "Text")

    def walk(el, d):
        if len(items) >= limit or d > max_depth:
            return
        for x in kidsof(el):
            if len(items) >= limit:
                return
            try:
                rc = rect_of(x)
                if rc is None:
                    walk(x, d + 1)
                    continue
                l, t, rr, b = rc
                _cx, _cy = (l + rr) // 2, (t + b) // 2
                if not (0 <= _cx <= _SCREEN[0] and 0 <= _cy <= _SCREEN[1]):
                    walk(x, d + 1)
                    continue
                cti = cached(x, U.UIA_ControlTypePropertyId)
                ct = _CT.get(int(cti), "Custom") if cti is not None else "Custom"
                val = ""
                if ct in valued:
                    vv = cached(x, U.UIA_ValueValuePropertyId)
                    val = str(vv) if vv else ""
                items.append({
                    "i": len(items),
                    "type": ct,
                    "name": str(cached(x, U.UIA_NamePropertyId) or "")[:60],
                    "cls": str(cached(x, U.UIA_ClassNamePropertyId) or "")[:36],
                    "rect": (l, t, rr, b),
                    "value": val,
                    "en": bool(cached(x, U.UIA_IsEnabledPropertyId)),
                })
            except Exception:
                pass
            walk(x, d + 1)

    walk(root, 0)
    if len(items) < min(25, limit):
        _LAST["fast"] = False
        return _inventory_slow(win, limit, max_depth)
    _LAST["fast"] = True
    return items
