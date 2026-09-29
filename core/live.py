"""core/live.py - event-driven perception.

Windows already knows the moment the screen changes: a window opens, focus
moves, a value or a name changes, a menu pops. We used to learn this by sleeping
and re-reading the whole control tree - that is exactly why the agent felt "not
alive". Here one background thread owns a WinEvent hook and its own message
pump; every event bumps a revision counter for the affected top-level window.
The agent arms the counter before it acts and waits on it afterwards, so it
wakes the instant the app reacts instead of on a timer.

Where the platform gives us nothing (non-Windows, or a surface that raises no
events) these calls degrade honestly: wait_change just times out and the caller
falls back to a bounded re-check. Nothing here is required for correctness -
only for speed.
"""
from __future__ import annotations

import ctypes
import threading
import time

try:
    from ctypes import wintypes
    IS_WINDOWS = True
except Exception:
    wintypes = None
    IS_WINDOWS = False

_OBJECT_LO, _OBJECT_HI = 0x8000, 0x800F
_SYSTEM_LO, _SYSTEM_HI = 0x0003, 0x0010
_OUTOFCONTEXT = 0x0000
_SKIPOWNPROCESS = 0x0002
_WM_QUIT = 0x0012
_GA_ROOTOWNER = 3
_GA_ROOT = 2

if IS_WINDOWS:
    _WINEVENTPROC = ctypes.WINFUNCTYPE(
        None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND,
        wintypes.LONG, wintypes.LONG, wintypes.DWORD, wintypes.DWORD)
else:
    _WINEVENTPROC = None

_lock = threading.Lock()
_cond = threading.Condition(_lock)
_rev = {}
_last = {}
_total = [0]
_thread = None
_tid = [0]
_cb_ref = None
_hooks = []
_started = False
_own = {}


def _u32():
    if not IS_WINDOWS:
        return None
    u = _own.get("u32")
    if u is None:
        u = ctypes.WinDLL("user32", use_last_error=True)
        u.GetAncestor.restype = ctypes.c_void_p
        u.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        _own["u32"] = u
    return u


def _root(h):
    if not h:
        return 0
    try:
        u = _u32()
        r = int(u.GetAncestor(h, _GA_ROOTOWNER) or 0) or int(u.GetAncestor(h, _GA_ROOT) or 0)
        return r or int(h)
    except Exception:
        return int(h)


def root_of(win):
    if isinstance(win, dict):
        try:
            return _root(int(win.get("hwnd") or 0))
        except Exception:
            return 0
    try:
        return _root(int(win or 0))
    except Exception:
        return 0


def _bump(h):
    with _cond:
        _rev[h] = _rev.get(h, 0) + 1
        _last[h] = time.monotonic()
        _total[0] += 1
        _cond.notify_all()


def start():
    """Install the hook once, on its own thread. Safe to call repeatedly."""
    global _thread, _started
    if not IS_WINDOWS or _started:
        return
    _started = True
    _thread = threading.Thread(target=_pump, name="live-events", daemon=True)
    _thread.start()


def running():
    return bool(_started and _thread and _thread.is_alive())


def stop(timeout=2.0):
    global _started
    if not IS_WINDOWS or not _started:
        return
    _started = False
    try:
        u = _u32()
        u.PostThreadMessageW.restype = ctypes.c_int
        u.PostThreadMessageW.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
        if _tid[0]:
            u.PostThreadMessageW(_tid[0], _WM_QUIT, None, None)
    except Exception:
        pass
    try:
        if _thread:
            _thread.join(timeout)
    except Exception:
        pass


def _pump():
    u = _u32()
    u.SetWinEventHook.restype = ctypes.c_void_p
    u.SetWinEventHook.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p,
                                  _WINEVENTPROC, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint]
    u.UnhookWinEvent.argtypes = [ctypes.c_void_p]
    u.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint]
    u.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint]
    u.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
    u.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]

    global _cb_ref
    if _cb_ref is None:
        def _cb(_h, _event, hwnd, _obj, _child, _thr, _t):
            try:
                h = _root(int(hwnd or 0))
                if h:
                    _bump(h)
            except Exception:
                pass
        _cb_ref = _WINEVENTPROC(_cb)

    flags = _OUTOFCONTEXT | _SKIPOWNPROCESS
    for lo, hi in ((_OBJECT_LO, _OBJECT_HI), (_SYSTEM_LO, _SYSTEM_HI)):
        try:
            hk = u.SetWinEventHook(lo, hi, None, _cb_ref, 0, 0, flags)
            if hk:
                _hooks.append(hk)
        except Exception:
            pass

    msg = wintypes.MSG()
    try:
        u.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)   # create the queue first
        _tid[0] = int(ctypes.windll.kernel32.GetCurrentThreadId())
    except Exception:
        _tid[0] = 0

    while True:
        try:
            r = u.GetMessageW(ctypes.byref(msg), None, 0, 0)
        except Exception:
            break
        if r in (0, -1):
            break
        u.TranslateMessage(ctypes.byref(msg))
        u.DispatchMessageW(ctypes.byref(msg))

    for hk in _hooks:
        try:
            u.UnhookWinEvent(hk)
        except Exception:
            pass


def revision(win):
    h = root_of(win)
    with _lock:
        return _rev.get(h, 0)


def wait_change(win, timeout=2.0, since=None):
    """True if `win` changed after `since` (or at all), else False on timeout."""
    if not IS_WINDOWS:
        return False
    h = root_of(win)
    if not h:
        return False
    end = time.monotonic() + max(0.05, float(timeout))
    with _cond:
        base = since if since is not None else _rev.get(h, 0)
        while _rev.get(h, 0) == base:
            left = end - time.monotonic()
            if left <= 0:
                return False
            _cond.wait(left)
    return True


def quiet(win, seconds=0.22, timeout=1.0):
    """True once no event has arrived for `seconds` (or `timeout` passed)."""
    if not IS_WINDOWS:
        return True
    h = root_of(win)
    if not h:
        return True
    end = time.monotonic() + max(0.05, float(timeout))
    while True:
        with _lock:
            t = _last.get(h)
        now = time.monotonic()
        gap = seconds if t is None else (now - t)
        if gap >= seconds or now >= end:
            return True
        time.sleep(min(0.04, max(0.01, seconds)))


def total():
    return _total[0]
