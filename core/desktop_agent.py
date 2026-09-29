"""
core/desktop_agent.py — ONE general loop that drives ANY app.

    perceive -> propose ONE step -> execute -> re-observe -> verify

The model never touches the machine. It only PICS the next step from the live
control list of one window; this code executes it, looks again, and compares.
Anything irreversible is parked behind core/confirm.py, so the loop cannot be
talked around, and a step that produces no visible change is reported as such.
"""
from __future__ import annotations

import ctypes
import re
import time

from core import window_agent as wa

try:
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    _sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

MAX_STEPS = 14

_SECRET_RE = re.compile(
    r"(password|passwd|رمز|پسورد|پین|pin|otp|کد\s*یکبار|شماره\s*کارت|cvv|seed)",
    re.IGNORECASE)
_IRREVERSIBLE_RE = re.compile(
    r"(\bsend\b|\bsubmit\b|\bdelete\b|\bremove\b|\bbuy\b|\bpay\b"
    r"|\bpurchase\b|\bpost\b|\bpublish\b|\bcall\b"
    r"|ارسال|بفرست|حذف|پاک|خرید|بخر|ثبت|تماس)", re.IGNORECASE)
_MESSENGERS = ("telegram", "whatsapp", "signal", "discord", "slack",
               "teams", "messenger", "instagram", "eitaa", "bale")

_LOOP = """You are the control loop of a desktop agent. Below is the LIVE list of
controls of ONE window. Choose the NEXT SINGLE step toward the task.

Reply with ONLY this JSON:
{"done": false, "say": "", "action": "", "index": -1, "text": "", "keys": "",
 "irreversible": false, "evidence": {"index": -1, "expect": ""}, "why": ""}

action is one of: click | set_value | type | key | hotkey | wait | activate
 - click / set_value need "index" = the [N] of the control to act on.
 - type needs "text" (types where the focus is right now).
 - key needs "keys" (e.g. "enter"); hotkey needs "keys" (e.g. "ctrl+c").
Set "irreversible": true ONLY on the step that actually sends / posts / buys /
deletes / calls / submits — something that cannot be undone.
When the task IS finished set "done": true and give "evidence" = the [N] of the
control that PROVES it plus "expect" = the exact text that must be readable
there (e.g. a calculator display reading 84). If you cannot point at proof, keep
"done": false and explain in "why".
"say" is one short sentence in the user's own language.
Never invent an index that is not in the list. Never claim something is done in
"say" while "done" is false.
"""


def _log(player, msg):
    try:
        if player:
            player.write_log(str(msg)[:160])
    except Exception:
        pass


def _truthy(v):
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("true", "yes", "1")


def _launch(app):
    try:
        import importlib
        m = importlib.import_module("actions.open_app")
        h = getattr(m, "open_app", None) or (m.TOOL or {}).get("handler")
        if h:
            h(parameters={"app_name": app})
            return
    except Exception as e:
        print("[desktop_agent] open_app handler failed:", repr(e))
    try:
        import subprocess
        subprocess.Popen([app], shell=True)
    except Exception:
        pass


def _is_usable(win):
    try:
        r = win.get("rect") or (0, 0, 0, 0)
        return (not win.get("minimized")) and r[0] > -30000 and r[1] > -30000
    except Exception:
        return False


def _pick_window(app, tries=6, settle=0.5):
    """The app's REAL main window, not a short-lived dialog with the same title.

    Telegram keeps invisible helper windows also titled "Telegram"; a dialog
    that closes two seconds later looks identical to the real window by name.
    So: use the FILTERED window list, keep the BIGGEST match, and trust a
    handle only if it is still there on the next tick.
    """
    if not app:
        return None
    q = str(app).strip().lower()

    def area(w):
        r = w.get("rect") or (0, 0, 0, 0)
        try:
            return max(0, r[2] - r[0]) * max(0, r[3] - r[1])
        except Exception:
            return 0

    last, last_hwnd = None, None
    for _ in range(max(1, tries)):
        try:
            ws = wa.list_windows()
        except Exception:
            ws = []
        _CONSOLE = ("ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS",
                    "PseudoConsoleWindow")
        hits = [w for w in ws if q in (str(w.get("name") or "") + " "
                                        + str(w.get("exe") or "")).lower()
                and str(w.get("cls") or "") not in _CONSOLE]
        if hits:
            def rank(w):
                r = w.get("rect") or (0, 0, 0, 0)
                try:
                    bad = bool(w.get("minimized")) or r[0] <= -30000 or r[1] <= -30000
                except Exception:
                    bad = True
                return (1 if bad else 0, -area(w))

            hits.sort(key=rank)
            best = hits[0]
            h = best.get("hwnd")
            if last_hwnd is not None and h == last_hwnd:
                return best
            last, last_hwnd = best, h
        time.sleep(settle)
    return last


def _irreversible(plan, action, text, win, target=""):
    """Only a DETERMINISTIC signal may open the confirm gate.

    The model's own "irreversible": true is NOT sufficient -- it parked an
    innocent Calculator click/type behind a confirm and dead-ended the run. It
    now counts only as a hint, and only for an unnamed button. Everything else
    must come from the ACTION, its TARGET label, or the app itself.
    """
    if action not in ("click", "set_value", "type", "key", "hotkey"):
        return False

    keys = str(plan.get("keys") or "")
    exe = (win.get("exe") or "").lower()

    # 1) Enter inside a messaging app IS a send.
    if action in ("key", "hotkey") and "enter" in keys.lower():
        if any(m in exe for m in _MESSENGERS):
            return True

    # 2) The label of the control we touch, or the text we type.
    name = (target or "").strip()
    if _IRREVERSIBLE_RE.search(name):
        return True
    if _IRREVERSIBLE_RE.search(text or ""):
        return True

    # 3) The model insisted AND the control has no readable label at all.
    flagged = str(plan.get("irreversible")).strip().lower() in ("true", "yes", "1")
    if flagged and action in ("click", "set_value") and not name:
        return True

    return False


def _check_evidence(items, ev):
    if not isinstance(ev, dict):
        return False, "no evidence was given"
    try:
        i = int(ev.get("index"))
    except Exception:
        return False, "evidence index was missing"
    if not (0 <= i < len(items)):
        return False, "evidence index %s is not in the window" % ev.get("index")
    expect = str(ev.get("expect") or "").strip()
    if not expect:
        return False, "evidence had nothing to check against"
    it = items[i]
    val = str(it.get("value") or "")
    nm = str(it.get("name") or "")
    if expect.casefold() in val.casefold():
        return True, "[%d] reads %r" % (i, val[:60])
    if expect.casefold() in nm.casefold():
        return True, "[%d] label matches %r (weaker proof)" % (i, nm[:60])
    return False, ("I expected %r there but [%d] reads %r (label %r)"
                   % (expect, i, val[:40], nm[:40]))


def _resolve_live(win, items, plan):
    """Re-find the control the model chose, in the CURRENT tree.

    The model answers from a snapshot that is now seconds old (a planning call
    takes 5-8s). In a live window the list shifts — a message arrives, a panel
    opens — and the same index points at a DIFFERENT control. So we match the
    chosen control by TYPE + NAME against a fresh inventory and keep the
    closest candidate geometrically. None means "it is gone; look again".
    """
    try:
        want = items[int(plan.get("index"))]
    except Exception:
        return None
    cands = [it for it in wa.inventory(win)
             if it["type"] == want["type"] and it["name"] == want["name"]]
    if not cands:
        return None
    if len(cands) > 1:
        l, t = want["rect"][0], want["rect"][1]
        cands.sort(key=lambda it: abs(it["rect"][0] - l) + abs(it["rect"][1] - t))
    return cands[0]["i"]


def _execute(win, action, plan):
    # Never type or click unless the target window really owns the foreground.
    # This is the bug that once typed into whatever app happened to be on top.
    if action in ("click", "set_value", "type", "key", "hotkey"):
        h = _hwnd_of(win)
        if h and _front_hwnd() != h:
            if not _raise_window(win):
                return ("refused: %r is not the foreground window and I could not "
                        "bring it to the front, so I sent no input"
                        % (win.get("name") or "the target"))
    idx = plan.get("index")
    if action == "click":
        return wa.click_item(win, int(idx))
    if action == "set_value":
        return wa.set_value_item(win, int(idx), str(plan.get("text") or ""))
    if action == "type":
        txt = str(plan.get("text") or "")
        # A field that already holds text gets APPENDED to - and the doubled
        # message is what actually got SENT once ("test az vornextest az vornex").
        # Clear a non-empty edit box first.
        try:
            cur = wa.focused_value()
        except Exception:
            cur = ""
        if cur.strip():
            wa.hotkey("ctrl+a")
            time.sleep(0.08)
            wa.press("delete")
            time.sleep(0.12)
        return wa.type_text(txt)
    if action == "key":
        return wa.press(str(plan.get("keys") or ""))
    if action == "hotkey":
        return wa.hotkey(str(plan.get("keys") or ""))
    if action == "activate":
        return "raised" if wa.activate(win) else "could NOT raise"
    if action == "wait":
        time.sleep(1.0)
        return "waited"
    return "nothing"


_LOOP2 = """You are the control loop of a desktop agent. Below is the LIVE list of
controls of ONE window. Reach the task with the FEWEST model calls.

Reply with ONLY this JSON:
{"done": false, "say": "", "steps": [{"action": "", "index": -1, "text": "", "keys": "", "irreversible": false}], "evidence": {"index": -1, "expect": ""}, "why": ""}

"steps" is a SHORT plan of up to 5 steps to run IN ORDER right now (use several
steps when you are confident of the whole sequence, e.g. a calculator: click 1,
click 5, click "Multiply by", click "Equals"). If unsure of the sequence, return
just ONE step.
Each step: action = click | set_value | type | key | hotkey | wait | activate
 - click / set_value need "index" = the [N] of the control.
 - type needs "text"; key/hotkey need "keys" (e.g. "enter", "ctrl+c").
Set "irreversible": true on the ONE step that actually sends / posts / buys /
deletes / calls / submits.
ALWAYS fill "evidence" with the [N] and the exact text that will PROVE the task is
finished (e.g. the display control and "20") -- even while "done" is false -- so I
can confirm your plan worked without asking you again.
When the task is already finished set "done": true. If you cannot point at proof,
keep "done": false and explain in "why".
TIP: in a calculator, focus the display and TYPE the whole expression (e.g. "15*4") then press Enter/Equals instead of clicking each digit.\n"say" is one short sentence in the user's language. Never invent an index that is
not in the list, and never claim something is done while "done" is false. Follow the TASK's EXACT numbers and words; never substitute your own values.
"""


def run_task(task, app=None, details="", player=None, max_steps=MAX_STEPS):
    if wa.auto is None:
        return "UI Automation is unavailable, so I cannot read the screen safely."

    try:
        from core.confirm import pending_title
        waiting = pending_title()
    except Exception:
        waiting = ""
    if waiting:
        return ("There is already a confirmation on screen for %r - please answer "
                "that one first." % waiting)

    win = _pick_window(app, tries=2) if app else None
    if win is None and app:
        try:
            win = wa.unhide(app)
        except Exception:
            win = None
        if win:
            _log(player, "brought %s back from the tray" % app)
    if win is None and app:
        _log(player, "opening %s..." % app)
        _launch(app)
        deadline = time.time() + 15
        while time.time() < deadline:
            win = _pick_window(app, tries=3)
            if win:
                break
            time.sleep(0.4)

    if win is not None and not _is_usable(win):
        _log(player, "restoring %r..." % (win.get("name") or app))
        try:
            wa.activate(win)
        except Exception:
            pass
        time.sleep(0.5)
        win = _pick_window(app, tries=10) or win
    if win is not None and not _is_usable(win):
        return ("%r is minimised and I could NOT restore it, so I sent NO "
                "input - acting now would type into whatever is on top."
                % (win.get("name") or app))

    if win is None:
        procs = wa.find_processes(app or "")
        if procs:
            names = ", ".join("%s (pid %s)" % (n, p) for p, n in procs[:4])
            return ("%s is running (%s) but has no visible window - it is very "
                    "likely minimised to the tray. Please open its window and ask "
                    "me again; I did nothing." % (app, names))
        return ("I could not find %r among the open windows and it did not come "
                "up when I asked it to, so I did nothing."
                % (app or "the target window"))

    if not _raise_window(win):
        _log(player, "warning: could not bring %r to the front" % win["name"])
    time.sleep(0.2)

    from core import gemini

    history = []
    did_any = []
    no_progress = 0
    tier = gemini.SMART
    rounds = 0
    while rounds < max_steps:
        rounds += 1
        if not wa.window_alive(win):
            win = _pick_window(app, tries=4) or win
            if not wa.window_alive(win):
                return ("The window %r closed while I was working, so I stopped."
                        % win.get("name"))

        items = wa.inventory(win)
        seen = wa.snapshot_text(win, items)
        if len(seen) > 4000:
            seen = seen[:4000] + "\n...(list truncated)"
        parts = [_LOOP2, "TASK: " + str(task)]
        if app:
            parts.append("APP: " + str(app))
        if details:
            parts.append("DETAILS: " + str(details))
        if history:
            parts.append("ALREADY TRIED:\n" + "\n".join(history[-6:]))
        try:
            _f = wa.focused()
        except Exception:
            _f = None
        parts.append("KEYBOARD FOCUS: " + ("[%s] %r" % (_f["type"], _f["name"])
                     if _f else "nothing editable"))
        parts.append("RULE: `type` sends keys to WHATEVER has focus. Click the "
                     "target text field FIRST (an Edit control). Enter inside "
                     "a messenger SENDS.")
        parts.append("If you TYPE text into a field, your evidence must be "
                     "THAT edit box, and 'expect' must be the exact text "
                     "you typed.")
        parts.append("If the task says SEND, the plan MUST end with "
                     "{\"action\":\"key\",\"keys\":\"enter\"} - it is parked "
                     "behind the user's confirmation anyway.")
        parts.append("LIVE CONTROLS:\n" + seen)
        prompt = "\n".join(parts)

        plan = gemini.as_json(prompt, tier=tier, timeout_ms=15000, default=None)
        if not isinstance(plan, dict):
            if did_any:
                return ("I carried out %s, but then I could not work out the next "
                        "step, so I stopped - I did NOT finish and I am not claiming "
                        "it worked." % "; ".join(did_any[-3:]))
            return ("I could not work out the next step for %r, so I did nothing." % task)

        if _truthy(plan.get("done")):
            ok, why = _check_evidence(items, plan.get("evidence"))
            if ok:
                _log(player, "done - %s" % why)
                say = str(plan.get("say") or "").strip() or ("Done: " + str(task))
                return "%s (I verified it: %s)" % (say, why)
            history.append("You set done=true but the evidence did not hold: %s" % why)
            continue

        raw_steps = plan.get("steps")
        if not isinstance(raw_steps, list) or not raw_steps:
            raw_steps = [plan]

        gate = None
        for _st in raw_steps[:5]:
            if isinstance(_st, dict):
                _a = str(_st.get("action") or "").lower()
                _tn = ""
                if _a in ("click", "set_value"):
                    try:
                        _tn = items[int(_st.get("index"))]["name"]
                    except Exception:
                        _tn = ""
                if _irreversible(_st, _a, str(_st.get("text") or ""), win, _tn):
                    gate = _st
                    break
        if gate is not None:
            _log(player, "gated because of: %r" % (gate,))
            from core import confirm

            def _run_all(win=win, steps=raw_steps, items=items, plan=plan):
                for _s in steps[:5]:
                    if not isinstance(_s, dict):
                        continue
                    _aa = str(_s.get("action") or "").lower()
                    _raise_window(win)
                    time.sleep(0.2)
                    if _aa in ("click", "set_value"):
                        _lv = _resolve_live(win, items, _s)
                        if _lv is not None:
                            _s = dict(_s, index=_lv)
                    _execute(win, _aa, _s)
                    time.sleep(0.6)
                _end = wa.inventory(win)
                _want = [str(_s.get("text") or "") for _s in steps[:5]
                         if isinstance(_s, dict)
                         and str(_s.get("action") or "").lower() == "type"]
                _want = [x for x in _want if x.strip()]
                _blob = " ".join(str(_it.get("value") or "") for _it in _end)
                if _want and any(x.casefold() in _blob.casefold() for x in _want):
                    return ("Done, and I checked: the app now shows %r"
                            % _want[-1])
                _ok, _why = _check_evidence(_end, plan.get("evidence"))
                if _ok:
                    return "Done, and I checked: %s" % _why
                return ("I did it, but I could NOT confirm it worked (%s). "
                        "Please check it yourself." % _why)

            return confirm.request(
                key="desktop_agent",
                title=("Confirm: " + str(task))[:120],
                detail=(str(plan.get("say") or "") or str(plan.get("why") or "")
                        or task)[:280],
                run=_run_all)

        sig_before_plan = wa.signature(items)
        abort = None
        for step in raw_steps[:5]:
            if not isinstance(step, dict):
                continue
            if not wa.window_alive(win):
                return "The window closed while I was working, so I stopped."

            action = str(step.get("action") or "").strip().lower()
            text = str(step.get("text") or "")
            if action not in ("click", "set_value", "type", "key", "hotkey",
                              "wait", "activate"):
                abort = "unknown action %r" % action
                break
            if action == "type" and _SECRET_RE.search(text):
                return "That looks like a password/PIN/card, so I will not type it."

            tname = ""
            if action in ("click", "set_value"):
                try:
                    tname = items[int(step.get("index"))]["name"]
                except Exception:
                    abort = "a step needs an index that exists in the list"
                    break

            if action in ("click", "set_value", "type", "key", "hotkey"):
                if not _raise_window(win):
                    abort = "could not bring %r to the front" % win["name"]
                    break

            if _irreversible(step, action, text, win, tname):
                from core import confirm
                detail = (str(plan.get("say") or "") or str(plan.get("why") or "")
                          or task)[:280]

                def _run(win=win, action=action, step=step, items=items, plan=plan):
                    _raise_window(win)
                    time.sleep(0.2)
                    live = _resolve_live(win, items, step)
                    if live is not None:
                        step = dict(step, index=live)
                    _execute(win, action, step)
                    time.sleep(1.2)
                    ok, why = _check_evidence(wa.inventory(win), plan.get("evidence"))
                    if ok:
                        return "Done, and I checked: %s" % why
                    return ("I did it, but I could NOT confirm it worked (%s). "
                            "Please check it yourself." % why)

                return confirm.request(key="desktop_agent",
                                       title=("Confirm: " + str(task))[:120],
                                       detail=detail, run=_run)

            if action in ("click", "set_value"):
                live = _resolve_live(win, items, step)
                if live is None:
                    abort = ("[%s] %r is not on screen any more"
                             % (step.get("index"), tname))
                    break
                step = dict(step, index=live)

            before = wa.signature(wa.inventory(win))   # fresh, not the stale plan snapshot
            what = _execute(win, action, step)
            did_any.append(what)
            _log(player, what)
            # A REFUSED step must stop the plan. Otherwise the next step still
            # runs - and a `type` goes into whatever happens to have focus.
            if str(what).startswith(("refused", "could NOT", "unknown", "no such")):
                abort = "the last action was refused: %s" % what
                break
            deadline = time.time() + 0.9
            while True:
                time.sleep(0.2)
                if not wa.window_alive(win):
                    win = _pick_window(app, tries=4) or win
                    if not wa.window_alive(win):
                        return "The window closed right after I acted, so I stopped."
                if wa.signature(wa.inventory(win)) != before or time.time() >= deadline:
                    break

        if abort:
            history.append("Stopped the plan: %s" % abort)
            continue

        end = wa.inventory(win)
        ok, why = _check_evidence(end, plan.get("evidence"))
        if not ok:
            exp = str((plan.get("evidence") or {}).get("expect") or "").strip()
            if exp:
                for it in end:
                    # CONTENT only. "found X somewhere on screen" also matched the
                    # chat TITLE, so a type that never landed looked verified.
                    # A match inside a control's VALUE is the real proof.
                    if exp.casefold() in str(it.get("value") or "").casefold():
                        ok, why = True, "[%s] contains %r" % (it.get("i"), exp)
                        break
        typed = [str(_s.get("text") or "") for _s in raw_steps[:5]
                 if isinstance(_s, dict)
                 and str(_s.get("action") or "").lower() == "type"]
        typed = [x for x in typed if x.strip()]
        consumed = any(isinstance(_s, dict)
                       and str(_s.get("action") or "").lower() in ("key", "hotkey")
                       for _s in raw_steps[:5])
        if ok and typed and not consumed:
            _blob = " ".join(str(_it.get("value") or "") for _it in end)
            if not any(x.casefold() in _blob.casefold() for x in typed):
                ok = False
                why = ("I typed %r but no control content shows it" % typed[-1])
        if ok:
            say = str(plan.get("say") or "").strip() or ("Done: " + str(task))
            return "%s (I verified it: %s)" % (say, why)

        if wa.signature(end) == sig_before_plan:
            no_progress += 1
        else:
            no_progress = 0
        if no_progress >= 2:
            return ("I tried %s but nothing changed on screen, so I stopped instead "
                    "of repeating the same thing. I could not finish the task - "
                    "please check the app." % "; ".join(did_any[-4:]))
        history.append("Your last plan ran but the screen does not show the expected "
                       "result yet, so it is not done.")

    if did_any:
        return ("I carried out %s, but after %d steps I still could not reach a "
                "state I could verify, so I will not claim it worked. Please check "
                "the app." % ("; ".join(did_any[-4:]), max_steps))
    return ("I stopped after %d steps without reaching a state I could verify, "
            "so I will not claim it worked." % max_steps)


# ── robust bring-to-front (Win32 SetForegroundWindow is often denied) ────────
# A background process frequently cannot raise another app's window; Windows
# refuses SetForegroundWindow and the call silently does nothing. Then a click
# or a paste lands in the WRONG window. We retry, then use AttachThreadInput,
# and we only ever act once the target window is really the foreground one.


def _hwnd_of(win):
    for k in ("hwnd", "handle", "NativeWindowHandle", "hWnd", "handle_value"):
        try:
            v = win.get(k)
            if v:
                return int(v)
        except Exception:
            pass
    try:
        c = wa._control_for(win)
        if c is not None:
            return int(c.NativeWindowHandle or 0)
    except Exception:
        pass
    return 0


def _front_hwnd():
    try:
        return int(ctypes.windll.user32.GetForegroundWindow())
    except Exception:
        return 0


def _focus_control(win):
    try:
        c = wa._control_for(win)
        if c is not None:
            c.SetFocus()
            return True
    except Exception:
        pass
    return False


def _raise_window(win):
    """Bring `win` to the front using every trick Windows offers.

    SetForegroundWindow is refused unless the caller already owns the
    foreground, so a window that sits BEHIND another app stays behind. We try
    the project's own activate, then UIA SetFocus, then minimise+restore, then
    AttachThreadInput, then tap ALT to release the lock -- and we only act once
    the target really is the foreground window.
    """
    h = _hwnd_of(win)
    if h and _front_hwnd() == h:
        return True
    try:
        if wa.activate(win) and (not h or _front_hwnd() == h):
            return True
    except Exception:
        pass
    if h and _front_hwnd() == h:
        return True

    _focus_control(win)
    if h and _front_hwnd() == h:
        return True
    if not h:
        return False

    u = ctypes.windll.user32
    k = ctypes.windll.kernel32

    try:
        u.ShowWindow(h, 6)          # SW_MINIMIZE
        time.sleep(0.15)
        u.ShowWindow(h, 9)          # SW_RESTORE
    except Exception:
        pass
    for _ in range(4):
        try:
            u.SetForegroundWindow(h)
        except Exception:
            pass
        time.sleep(0.12)
        if _front_hwnd() == h:
            return True

    try:
        fg = _front_hwnd()
        t_fg = u.GetWindowThreadProcessId(fg, None)
        t_my = k.GetCurrentThreadId()
        u.AttachThreadInput(t_my, t_fg, True)
        try:
            u.BringWindowToTop(h)
            u.SetForegroundWindow(h)
            u.SetActiveWindow(h)
        finally:
            u.AttachThreadInput(t_my, t_fg, False)
    except Exception:
        pass
    time.sleep(0.15)
    if _front_hwnd() == h:
        return True

    try:
        VK_MENU = 0x12
        u.keybd_event(VK_MENU, 0, 0, 0)
        u.keybd_event(VK_MENU, 0, 2, 0)
        u.SetForegroundWindow(h)
    except Exception:
        pass
    time.sleep(0.15)
    return _front_hwnd() == h


# ══════════════════════════════════════════════════════════════════════════════
#  desktop_agent v2 - appended last, so THIS run_task is the one that runs.
#  Adds the two missing pillars: event-driven perception (core.live) and a
#  learned plan cache (core.recipes), plus script-aware name matching
#  (core.names). Every uncertainty falls back to the model or to the user.
# ══════════════════════════════════════════════════════════════════════════════
from core import live as _live
from core import names as _names
from core import recipes as _recipes

_LOOP3 = """You are the control loop of a desktop agent. Below is the LIVE list of
controls of ONE window. Reach the task with the FEWEST model calls.

Reply with ONLY this JSON:
{"done": false, "say": "", "steps": [{"action": "", "index": -1, "text": "", "keys": "", "irreversible": false}], "evidence": {"index": -1, "expect": ""}, "why": ""}

"steps" is a SHORT plan of up to 5 steps to run IN ORDER right now.
Each step: action = click | set_value | type | key | hotkey | wait | activate
 - click / set_value need "index" = the [N] of the control.
 - type needs "text"; key/hotkey need "keys" (e.g. "enter", "ctrl+c").
Set "irreversible": true on the ONE step that actually sends / posts / buys /
deletes / calls / submits.
ALWAYS fill "evidence" with the [N] and the exact text that will PROVE the task
is finished (e.g. the display control and "20") - even while "done" is false.
When the task is already finished set "done": true. If you cannot point at proof,
keep "done": false and explain in "why".
"say" is one short sentence in the user's language. Never invent an index that is
not in the list, and never claim something is done while "done" is false.
Follow the TASK's EXACT numbers and words; never substitute your own values.
"""


def _settle(win, before_sig, rev, hard_limit=2.5):
    """Woken by a real event, then paused for the UI to go quiet.

    Windows tells us the instant the window changed; the event is the signal and
    the quiet period is the settling. If an app raises no events at all we still
    re-check the signature once, so a silent but real change is never missed."""
    end = time.time() + hard_limit
    try:
        _live.wait_change(win, timeout=min(1.5, max(0.25, end - time.time())), since=rev)
        _live.quiet(win, 0.22, timeout=0.6)
    except Exception:
        time.sleep(0.3)
    if before_sig is None:
        return True
    try:
        if wa.signature(wa.inventory(win)) != before_sig:
            return True
        time.sleep(0.2)
        return wa.signature(wa.inventory(win)) != before_sig
    except Exception:
        return True


def _live_index(win, items, plan):
    """The control the model chose, re-found in a FRESH tree.

    Exact type+name first, then nearest by position, then a script-aware name
    match - because the model answers from a snapshot that is seconds old and a
    Persian name on screen and a Latin name in the task are the same person."""
    try:
        want = items[int(plan.get("index"))]
    except Exception:
        return None
    try:
        fresh = wa.inventory(win)
    except Exception:
        return None
    same = [it for it in fresh
            if it.get("type") == want.get("type") and it.get("name") == want.get("name")]
    if same:
        if len(same) == 1:
            return same[0]
        wl, wt = (want.get("rect") or (0, 0, 0, 0))[0], (want.get("rect") or (0, 0, 0, 0))[1]
        same.sort(key=lambda it: abs((it.get("rect") or (0, 0, 0, 0))[0] - wl)
                  + abs((it.get("rect") or (0, 0, 0, 0))[1] - wt))
        return same[0]
    nm = str(want.get("name") or "").strip()
    if nm:
        pool = [it for it in fresh
                if it.get("type") == want.get("type") and str(it.get("name") or "").strip()]
        hit = _names.best(nm, pool, key="name", floor=0.75, margin=0.0)
        if hit is not None:
            return hit
    return None


def _find_semantic(win, ctype, cname):
    """A stored recipe locator -> the live control, or None."""
    if not cname:
        return None
    try:
        fresh = wa.inventory(win)
    except Exception:
        return None
    same = [it for it in fresh if ctype and it.get("type") == ctype
            and str(it.get("name") or "").strip()]
    hit = _names.best(cname, same, key="name", floor=0.6, margin=0.0)
    if hit is None:
        pool = [it for it in fresh if str(it.get("name") or "").strip()]
        hit = _names.best(cname, pool, key="name", floor=0.6, margin=0.0)
    return hit


def _run_plan(win, steps, items, record=None, player=None):
    """Run a plan in order. Returns (what was done, stop-message or None)."""
    did = []
    for st in steps[:5]:
        if not isinstance(st, dict):
            continue
        if not wa.window_alive(win):
            return did, "The window closed while I was working, so I stopped."
        action = str(st.get("action") or "").strip().lower()
        text = str(st.get("text") or "")
        if action not in ("click", "set_value", "type", "key", "hotkey", "wait", "activate"):
            continue
        if action == "type" and _SECRET_RE.search(text):
            return did, "That looks like a password/PIN/card, so I will not type it."
        if action in ("click", "set_value", "type", "key", "hotkey"):
            if not _raise_window(win):
                _log(player, "warning: could not bring the window to the front")
        if action in ("click", "set_value"):
            hit = _live_index(win, items, st)
            if hit is None:
                return did, "[%s] %r is not on screen any more" % (
                    st.get("index"), str(st.get("name") or text)[:40])
            st = dict(st, index=hit.get("i"))
            if record is not None:
                record.append({"op": action, "type": hit.get("type"), "name": hit.get("name")})
        elif action == "type":
            if record is not None:
                record.append({"op": "type", "text": text})
        elif action in ("key", "hotkey"):
            if record is not None:
                record.append({"op": action, "keys": str(st.get("keys") or "")})
        try:
            before = wa.signature(wa.inventory(win))
        except Exception:
            before = None
        rev = _live.revision(win)
        what = _execute(win, action, st)
        did.append(what)
        _log(player, what)
        _settle(win, before, rev)
    return did, None


def _verify(win, steps, plan):
    """True only if the APP itself shows the result - never just our own hope."""
    end = wa.inventory(win)
    want = [str(s.get("text") or "") for s in steps
            if isinstance(s, dict) and str(s.get("action") or "").lower() == "type"]
    want = [x for x in want if x.strip()]
    consumed = any(isinstance(s, dict)
                   and str(s.get("action") or "").lower() in ("key", "hotkey")
                   for s in steps)
    if want:
        if consumed:
            # the text must now live somewhere OTHER than the box it was typed in
            vals = " ".join(str(it.get("value") or "") for it in end
                            if str(it.get("type") or "") != "Edit")
            if any(x.casefold() in vals.casefold() for x in want):
                return True, "the app now shows %r" % want[-1]
        else:
            blob = " ".join(str(it.get("value") or "") for it in end)
            if any(x.casefold() in blob.casefold() for x in want):
                return True, "the app now shows %r" % want[-1]
    ok, why = _check_evidence(end, plan.get("evidence"))
    if ok:
        return True, why
    exp = str((plan.get("evidence") or {}).get("expect") or "").strip()
    if len(exp) >= 2:
        for it in end:
            b = str(it.get("value") or "") + " " + str(it.get("name") or "")
            if exp.casefold() in b.casefold():
                return True, "found %r on screen" % exp
    return False, why


def _forget(app, task, player, why):
    try:
        _recipes.drop(app, task)
    except Exception:
        pass
    _log(player, "forgetting that plan (%s) - planning fresh" % why)
    return None


def _replay(win, task, app, player):
    """Re-run a plan we already verified, with no model call.

    Only reversible plans are replayed; anything irreversible still goes through
    the normal path so the user confirms it fresh."""
    try:
        rec = _recipes.load(app, task)
    except Exception:
        rec = None
    if not rec:
        return None
    if _is_messenger(win):
        return None
    steps = rec.get("steps") or []
    if not steps:
        return None
    if any(s.get("irr") for s in steps):
        _log(player, "a plan for this task exists but it is irreversible - using the normal path")
        return None

    payload = rec.get("payload")
    if rec.get("has_tail"):
        t = re.sub(r"\s+", " ", str(task or "")).strip()
        pref = str(rec.get("prefix") or "")
        if not t.lower().startswith(pref.lower()):
            return _forget(app, task, player, "the task shape changed")
        payload = t[len(pref):].lstrip(" :،,.-—").strip()
        if not payload:
            return _forget(app, task, player, "the task carries no text")

    _log(player, "replaying a plan that worked before (%d steps)" % len(steps))
    did = []
    for st in steps:
        if not wa.window_alive(win):
            return _forget(app, task, player, "the window closed")
        op = str(st.get("op") or "")
        if op == "type":
            text = payload if st.get("uses_payload") else str(st.get("text") or "")
            live_step = {"action": "type", "text": text}
        elif op in ("click", "set_value"):
            hit = _find_semantic(win, st.get("type"), st.get("name"))
            if hit is None:
                return _forget(app, task, player,
                               "%r is not on screen any more" % str(st.get("name"))[:40])
            live_step = {"action": op, "index": hit.get("i")}
        elif op in ("key", "hotkey"):
            live_step = {"action": op, "keys": str(st.get("keys") or "")}
        else:
            continue
        _raise_window(win)
        try:
            before = wa.signature(wa.inventory(win))
        except Exception:
            before = None
        rev = _live.revision(win)
        did.append(_execute(win, live_step.get("action"), live_step))
        _settle(win, before, rev)

    blob = " ".join(str(it.get("value") or "") for it in wa.inventory(win))
    exp = [str(x).replace("${payload}", str(payload or "")) for x in (rec.get("expect") or [])]
    if exp and all(x and x.casefold() in blob.casefold() for x in exp):
        _log(player, "replay verified")
        try:
            _recipes.bump(rec.get("key"))
        except Exception:
            pass
        return ("Done - I repeated a plan that worked before and verified it (%s)."
                % "; ".join(did[-3:]))
    return _forget(app, task, player, "the result did not show on screen")


def run_task(task, app=None, details="", player=None, max_steps=MAX_STEPS):
    if wa.auto is None:
        return "UI Automation is unavailable, so I cannot read the screen safely."

    try:
        from core.confirm import pending_title
        waiting = pending_title()
    except Exception:
        waiting = ""
    if waiting:
        return ("There is already a confirmation on screen for %r - please answer "
                "that one first." % waiting)

    _live.start()

    win = wa.find_window(app) if app else None
    if win is None and app:
        try:
            win = wa.unhide(app)
        except Exception:
            win = None
        if win:
            _log(player, "brought %s back from the tray" % app)
    if win is None and app:
        _log(player, "opening %s..." % app)
        _launch(app)
        win = _pick_window(app, tries=6, settle=0.5)

    if win is None:
        procs = wa.find_processes(app or "")
        if procs:
            tag = ", ".join("%s (pid %s)" % (n, p) for p, n in procs[:4])
            return ("%s is running (%s) but has no visible window - it is very "
                    "likely minimised to the tray. Please open its window and ask "
                    "me again; I did nothing." % (app, tag))
        return ("I could not find %r among the open windows and it did not come "
                "up when I asked it to, so I did nothing."
                % (app or "the target window"))

    if not _raise_window(win):
        _log(player, "warning: could not bring %r to the front" % win.get("name"))
    time.sleep(0.15)

    try:
        fast = _replay(win, task, app, player)
    except Exception:
        fast = None
    if fast:
        return fast

    from core import gemini

    try:
        hint = _recipes.hint(app, task)
    except Exception:
        hint = ""

    history, record, did_any = [], [], []
    no_progress, rounds = 0, 0
    tier = gemini.SMART

    while rounds < max_steps:
        rounds += 1
        if not wa.window_alive(win):
            return "The window %r closed while I was working, so I stopped." % win.get("name")

        items = wa.inventory(win)
        seen = wa.snapshot_text(win, items)
        if len(seen) > 4000:
            seen = seen[:4000] + "\n...(list truncated)"

        parts = [_LOOP3, "TASK: " + str(task)]
        if app:
            parts.append("APP: " + str(app))
        if details:
            parts.append("DETAILS: " + str(details))
        try:
            _f = wa.focused()
        except Exception:
            _f = None
        parts.append("KEYBOARD FOCUS: " + (
            "[%s] %r" % (_f.get("type"), _f.get("name")) if _f else "nothing editable"))
        parts.append('RULE: `type` sends keys to WHATEVER has focus, so click the target text field first.')
        parts.append('RULE: a name can be written in another script on screen - "ماهک" and "Mahak" '
                     'are the same person. Match by sound, not exact letters. If a search finds '
                     'nothing, try the other spelling and look again; if two names are equally '
                     'close, ask the user instead of guessing.')
        parts.append("If you TYPE text into a field, the evidence must be THAT edit box and "
                     "'expect' must be the exact text you typed.")
        parts.append('If the task says SEND, the plan MUST end with {"action":"key","keys":"enter"}.')
        parts.append('The message TEXT must be its own `type` step aimed at the message box; '
                     'the recipient name goes ONLY in the search field.')
        if hint:
            parts.append("THIS PLAN WORKED BEFORE FOR THIS APP - reuse it unless the screen "
                         "now says otherwise:\n" + hint)
        if history:
            parts.append("ALREADY TRIED:\n" + "\n".join(history[-6:]))
        parts.append("LIVE CONTROLS:\n" + seen)
        prompt = "\n".join(parts)

        plan = gemini.as_json(prompt, tier=tier, timeout_ms=15000, default=None)
        if not isinstance(plan, dict):
            if did_any:
                return ("I carried out %s, but then I could not work out the next "
                        "step, so I stopped - I did NOT finish and I am not claiming "
                        "it worked." % "; ".join(did_any[-3:]))
            return "I could not work out the next step for %r, so I did nothing." % task

        if _truthy(plan.get("done")):
            ok, why = _evidence(win, items, plan.get("evidence"))
            if ok:
                if record and app:
                    try:
                        _recipes.save(app, task, record)
                    except Exception:
                        pass
                _log(player, "done - %s" % why)
                say = str(plan.get("say") or "").strip() or ("Done: " + str(task))
                return "%s (I verified it: %s)" % (say, why)
            history.append("You set done=true but the evidence did not hold: %s" % why)
            continue

        raw_steps = plan.get("steps")
        if not isinstance(raw_steps, list) or not raw_steps:
            raw_steps = [plan]
        raw_steps = [s for s in raw_steps[:5] if isinstance(s, dict)]
        if not raw_steps:
            history.append("Your plan had no usable steps; give at least one step.")
            continue

        # ── atomic gate: if ANY step is irreversible, park the WHOLE plan ────
        gate = None
        for st in raw_steps:
            a = str(st.get("action") or "").lower()
            tn = ""
            if a in ("click", "set_value"):
                try:
                    tn = str(items[int(st.get("index"))].get("name") or "")
                except Exception:
                    gate = st
                    break
            if _irreversible(st, a, str(st.get("text") or ""), win, tn):
                gate = st
                break
        if gate is not None:
            _log(player, "gated because of: %r" % (gate,))
            from core import confirm
            detail = (str(plan.get("say") or "") or str(plan.get("why") or "") or task)[:280]

            def _run(win=win, raw=list(raw_steps), items=items, plan=plan):
                did, stop = _run_plan(win, raw, items)
                if stop:
                    return stop
                time.sleep(0.3)
                ok, why = _verify(win, raw, plan)
                if ok:
                    return "Done, and I checked: %s" % why
                return ("I did it, but I could NOT confirm it worked (%s). "
                        "Please check it yourself." % why)

            return confirm.request(key="desktop_agent",
                                   title=("Confirm: " + str(task))[:120],
                                   detail=detail, run=_run)

        try:
            sig_before = wa.signature(items)
        except Exception:
            sig_before = None
        did, stop = _run_plan(win, raw_steps, items, record=record, player=player)
        did_any.extend(did)
        if stop:
            if stop.startswith("That looks like"):
                return stop
            history.append(stop)
            continue

        ok, why = _verify(win, raw_steps, plan)
        if ok:
            if record and app:
                try:
                    _recipes.save(app, task, record)
                except Exception:
                    pass
            say = str(plan.get("say") or "").strip() or ("Done: " + str(task))
            return "%s (I verified it: %s)" % (say, why)

        try:
            if wa.signature(wa.inventory(win)) == sig_before:
                no_progress += 1
            else:
                no_progress = 0
        except Exception:
            no_progress = 0
        if no_progress >= 2:
            return ("I tried %s but nothing changed on screen, so I stopped instead "
                    "of repeating the same thing. I could not finish the task - "
                    "please check the app." % "; ".join(did_any[-4:]))
        history.append("Your last plan ran but the screen does not show the expected "
                       "result yet. Reason: %s" % why)

    if did_any:
        return ("I carried out %s, but after %d steps I still could not reach a "
                "state I could verify, so I will not claim it worked. Please check "
                "the app." % ("; ".join(did_any[-4:]), max_steps))
    return ("I stopped after %d steps without reaching a state I could verify, "
            "so I will not claim it worked." % max_steps)


# ── stricter click matching (appended last: these win) ───────────────────────
# A recipe replays a click on a saved NAME, and a chat row carries a changing
# tail ("... Reactions: ❤, yesterday at 1"). A loose floor could land on a
# DIFFERENT, similar chat - the one mistake we must never make. Matching is now
# strict and must be unique; anything less bails and the model re-plans.

def _find_semantic(win, ctype, cname):
    if not cname:
        return None
    try:
        fresh = wa.inventory(win)
    except Exception:
        return None
    same = [it for it in fresh if ctype and it.get("type") == ctype
            and str(it.get("name") or "").strip()]
    hit = _names.best(cname, same, key="name", floor=0.85, margin=0.08)
    if hit is None:
        pool = [it for it in fresh if str(it.get("name") or "").strip()]
        hit = _names.best(cname, pool, key="name", floor=0.85, margin=0.08)
    return hit


def _live_index(win, items, plan):
    """Re-find the model's chosen control in a FRESH tree - exact, then strictly."""
    try:
        want = items[int(plan.get("index"))]
    except Exception:
        return None
    try:
        fresh = wa.inventory(win)
    except Exception:
        return None
    same = [it for it in fresh
            if it.get("type") == want.get("type") and it.get("name") == want.get("name")]
    if same:
        if len(same) == 1:
            return same[0]
        r = want.get("rect") or (0, 0, 0, 0)
        same.sort(key=lambda it: abs((it.get("rect") or (0, 0, 0, 0))[0] - r[0])
                  + abs((it.get("rect") or (0, 0, 0, 0))[1] - r[1]))
        return same[0]
    nm = str(want.get("name") or "").strip()
    if nm:
        pool = [it for it in fresh
                if it.get("type") == want.get("type") and str(it.get("name") or "").strip()]
        hit = _names.best(nm, pool, key="name", floor=0.85, margin=0.06)
        if hit is not None:
            return hit
    return None


# ── SEND GUARD + full step logging (appended last: these win) ────────────────
# A message once went to the WRONG chat. A draft in the wrong box is harmless;
# pressing Enter is not. So before the ONE irreversible step of a messenger we
# check, with no model call, that the OPEN conversation is the one the task
# names. Telegram/WhatsApp put the open chat in the window title, so the check
# is exact and cheap - and it reads the title LIVE, not the cached one.

_CURRENT = ["", None]


def _chat_name(win):
    n = ""
    try:
        n = str(wa._win_text(int(win.get("hwnd") or 0)) or "")
    except Exception:
        n = ""
    if not n.strip():
        n = str(win.get("name") or "")
    for ch in ("\u200e", "\u200f", "\u202a", "\u202b", "\u202c", "\u2066", "\u2069"):
        n = n.replace(ch, "")
    n = n.strip()
    for sep in (" – ", " — ", " - ", " | ", " · ", " :: "):
        if sep in n:
            n = n.split(sep)[0].strip()
            break
    n = re.sub(r"\s*[\(\[]?\d+[\)\]]?\s*$", "", n).strip()
    return n


def _chat_ok(win, task):
    """'' means the open chat IS the recipient. Otherwise a reason to refuse."""
    name = _chat_name(win)
    if not name:
        return "the open conversation has no name I can read"
    exe = (win.get("exe") or "").lower().replace(".exe", "")
    if exe and _names.score(name, exe) > 0.9:
        return "no conversation is open (the window is just %r)" % name
    nk, tk = _names.skeleton(name), _names.skeleton(task)
    if len(nk) >= 3 and nk in tk:
        return ""
    if _names.score(name, task) >= 0.6:
        return ""
    return "the open conversation is %r, which the task does not name" % name


def _run_plan(win, steps, items, record=None, player=None):
    """Run a plan in order - with the recipient guard on any messenger send.

    Every executed step is logged with the control it resolved to and the exact
    click point, so a wrong click is visible in the log instead of being
    discovered in the wrong chat."""
    if player is None:
        player = _CONTEXT["player"] or _CURRENT[1]
    task = _CONTEXT["task"] or (_CURRENT[0] or "")
    exe = (win.get("exe") or "").lower()
    messenger = any(m in exe for m in _MESSENGERS)
    sending = any(str(_s.get("action") or "").lower() in ("key", "hotkey")
                  and "enter" in str(_s.get("keys") or "").lower()
                  for _s in steps[:5] if isinstance(_s, dict))
    did = []

    # -- route FIRST, then run the plan: if the task names a recipient and that
    #    person is not the open chat, open them now. Everything the plan then
    #    does happens in the right conversation, so a stray click on a chat row
    #    no longer has to be refused.
    if messenger and sending and _conv_ok(win, task):
        _who = _recipient(task, _payloads(steps))
        if _who:
            _open_chat(win, _who, player)

    for st in steps[:5]:
        if not isinstance(st, dict):
            continue
        if not wa.window_alive(win):
            return did, "The window closed while I was working, so I stopped."
        action = str(st.get("action") or "").strip().lower()
        text = str(st.get("text") or "")
        keys = str(st.get("keys") or "")
        if action not in ("click", "set_value", "type", "key", "hotkey", "wait", "activate"):
            continue
        _row = None
        if action == "type" and _SECRET_RE.search(text):
            return did, "That looks like a password/PIN/card, so I will not type it."
        if messenger and action == "type" and not _focus_is_search():
            _why = _conv_ok(win, task)
            if _why and _open_chat(win, _recipient(task, _payloads(steps)), player):
                _why = _conv_ok(win, task)
            if _why:
                _log(player, "TYPE BLOCKED: %s" % _why)
                return did, ("I did NOT type: %s. Nothing was typed there and "
                             "nothing was sent." % _why)

        # ── the recipient guard: only on the irreversible messenger send ─────
        if messenger and action in ("key", "hotkey") and "enter" in keys.lower():
            why = _conv_ok(win, task)
            if why and _open_chat(win, _recipient(task, _payloads(steps)), player):
                why = _conv_ok(win, task)
            if not why:
                why = _chat.ensure_payload(win, task, steps, player)
            if why:
                _log(player, "SEND BLOCKED: %s" % why)
                return did, ("I did NOT send: %s. The text stayed a draft, so "
                             "nothing left the machine." % why)

        if action in ("click", "set_value", "type", "key", "hotkey"):
            if not _raise_window(win):
                _log(player, "warning: could not bring the window to the front")

        if action in ("click", "set_value"):
            hit = _live_index(win, items, st)
            if hit is None:
                return did, "[%s] %r is not on screen any more" % (
                    st.get("index"), str(st.get("name") or text)[:40])
            r = hit.get("rect") or (0, 0, 0, 0)
            _log(player, "click %r centre (%d,%d) box %dx%d" % (
                str(hit.get("name") or "")[:34],
                (r[0] + r[2]) // 2, (r[1] + r[3]) // 2,
                max(0, r[2] - r[0]), max(0, r[3] - r[1])))
            if (messenger and sending
                    and str(hit.get("type") or "") in _CONV_ROWS):
                _rn0 = str(hit.get("name") or "")
                _who0 = _recipient(task, _payloads(steps))
                if (_conv_ok(win, task) and _who0 and _rn0
                        and _names.score(_who0, _names.lead(_rn0)) < 0.85):
                    _log(player, "CLICK BLOCKED: not opening %r" % _rn0[:40])
                    return did, ("I did NOT open %r: it is not the person the "
                                 "task names. To reach a contact: click the "
                                 "Search box, type the name there, then click "
                                 "the result row whose name is that person. "
                                 "I touched nothing." % _rn0[:50])
            _row = (hit if (messenger and action == "click"
                            and str(hit.get("type") or "") in _CONV_ROWS)
                    else None)
            st = dict(st, index=hit.get("i"))
            if record is not None:
                record.append({"op": action, "type": hit.get("type"), "name": hit.get("name")})
        elif action == "type":
            if record is not None:
                record.append({"op": "type", "text": text})
        elif action in ("key", "hotkey"):
            if record is not None:
                record.append({"op": action, "keys": keys})

        try:
            before = wa.signature(wa.inventory(win))
        except Exception:
            before = None
        rev = _live.revision(win)
        what = _execute(win, action, st)
        did.append(what)
        _log(player, what)
        _settle(win, before, rev)

        # -- live re-check: ONLY for a row the task itself names (a person),
        #    confirm the app switched to exactly that row. A folder, a tab or
        #    "Saved Messages" is not a recipient, so it is not identity-checked.
        if _row is not None:
            _rn = str(_row.get("name") or "")
            _now = _chat_name(win)
            if _conv_ok(win, task, _rn):
                    _log(player, "click landed on %r, not %r - stopping"
                         % (_now[:30], _rn[:30]))
                    return did, ("I clicked %r but the app now shows %r, so the "
                                 "click did not land on the right one. I stopped "
                                 "and did nothing else."
                                 % (_rn[:40], _now[:40]))
    return did, None


_V2_RUN_TASK = run_task
_CURRENT = ["", None, ""]


def run_task(task, app=None, details="", player=None, max_steps=MAX_STEPS,
             recipient=""):
    """Publishes the task, the log sink, and the recipient (when known)."""
    _CURRENT[0], _CURRENT[1], _CURRENT[2] = str(task), player, str(recipient or "")
    try:
        return _V2_RUN_TASK(task, app=app, details=details,
                            player=player, max_steps=max_steps)
    finally:
        _CURRENT[0], _CURRENT[1], _CURRENT[2] = "", None, ""



# ── never crash on a missing window (appended last: these win) ───────────────
_CHAT_NAME_OLD = _chat_name
_CHAT_OK_OLD = _chat_ok


def _chat_name(win):
    if not isinstance(win, dict):
        return ""
    return _CHAT_NAME_OLD(win)


def _chat_ok(win, task):
    if not isinstance(win, dict):
        return "no window to check"
    return _CHAT_OK_OLD(win, task)



# ── the conversation rule, in ONE place (appended last: these win) ───────────
_CONV_ROWS = ("ListItem", "DataItem", "TreeItem")


def _conv_ok(win, task, clicked_name=""):
    """"" means the OPEN conversation is acceptable. Otherwise, why it is not.

    Acceptable = it is the row we just clicked, OR it is the person the task
    names (across scripts: something like a Persian name and its Latin spelling
    are the same). Everything else is refused, so a click that lands on the
    wrong chat can never be followed by typing or sending."""
    if not isinstance(win, dict):
        return "no window to check"
    title = _chat_name(win)
    if not title:
        return "the open conversation has no name I can read"
    exe = (win.get("exe") or "").lower().replace(".exe", "")
    if exe and _names.score(title, exe) > 0.9:
        return "no conversation is open (the window is just %r)" % title
    if clicked_name and _names.score(clicked_name, title) >= 0.7:
        return ""
    nk, tk = _names.skeleton(title), _names.skeleton(task)
    if len(nk) >= 3 and nk in tk:
        return ""
    if _names.score(title, task) >= 0.6:
        return ""
    return ("the open conversation is %r, which is neither the row I clicked "
            "nor the person in the task" % title)


def _focus_is_search():
    """True when the keyboard sits in a search field - there, typing a NAME is
    expected and the open chat is irrelevant."""
    try:
        f = wa.focused() or {}
    except Exception:
        f = {}
    nm = str(f.get("name") or "").lower()
    return any(k in nm for k in ("search", "find", "\u062c\u0633\u062a\u062c\u0648", "\u0628\u062d\u062b"))


_chat_ok = _conv_ok



# ══


# ── wire the conversation rules in (appended last: these win) ────────────────
from core import chat as _chat

_conv_ok = _chat.conv_ok
_open_chat = _chat.open_chat
_payloads = _chat.payloads
_focus_is_search = _chat.focus_is_search
_chat_name = _chat.name


def _recipient(task, payloads=()):
    preset = _CURRENT[2] if len(_CURRENT) > 2 else ""
    return _chat.recipient(task, payloads, preset=preset)



# ── the task must outlive the confirmation (appended last: this wins) ────────
# The confirmed action runs on a WORKER THREAD after run_task has already
# returned, and run_task's own cleanup had zeroed the task/player by then. So the
# guard was judging against an EMPTY task (and therefore blocking everything) and
# its log lines went nowhere. The context now lives in its own holder that is
# never cleared, so the async step sees the same task, player and recipient.

_CONTEXT = {"task": "", "player": None, "who": ""}
_V3_RUN_TASK = run_task


def run_task(task, app=None, details="", player=None, max_steps=MAX_STEPS,
             recipient=""):
    _CONTEXT["task"] = str(task)
    _CONTEXT["player"] = player
    _CONTEXT["who"] = str(recipient or "")
    return _V3_RUN_TASK(task, app=app, details=details,
                        player=player, max_steps=max_steps)


def _recipient(task, payloads=()):
    return _chat.recipient(task, payloads, preset=_CONTEXT["who"])



# ── proof must mean something (appended last: these win) ─────────────────────
# A run claimed "Done, and I checked: the app now shows 'Zzzz Qqqq Nobody'" while
# nothing had been sent: the text was sitting in the SEARCH BOX, where this very
# loop had just typed it. Evidence that we ourselves created proves nothing. For
# a messenger the proof has to be readable in a rendered control (a message
# row), never in an input field - while an editor stays exactly as before,
# because there the text in the document IS the result.

_INPUT_TYPES = ("Edit", "Document", "ComboBox")


def _is_messenger(win):
    exe = str((win or {}).get("exe") or "").lower()
    return any(m in exe for m in _MESSENGERS)


def _evidence(win, items, ev):
    ok, why = _check_evidence(items, ev)
    if not ok or not _is_messenger(win):
        return ok, why
    try:
        it = items[int((ev or {}).get("index"))]
    except Exception:
        it = None
    if it is not None and str(it.get("type") or "") in _INPUT_TYPES:
        return False, ("the only place it appears is an input field - that is where "
                       "I typed it, so it is not proof that anything was sent")
    return ok, why


def _verify(win, steps, plan):
    """True only when the app shows the result somewhere that MEANS something."""
    end = wa.inventory(win)
    messenger = _is_messenger(win)
    want = [str(s.get("text") or "") for s in steps
            if isinstance(s, dict) and str(s.get("action") or "").lower() == "type"]
    want = [x for x in want if x.strip()]
    consumed = any(isinstance(s, dict)
                   and str(s.get("action") or "").lower() in ("key", "hotkey")
                   for s in steps)

    def _blob(skip_inputs):
        vals = []
        for it in end:
            if skip_inputs and str(it.get("type") or "") in _INPUT_TYPES:
                continue
            vals.append(str(it.get("value") or ""))
        return " ".join(vals)

    if want:
        blob = _blob(bool(consumed and messenger))
        if any(x.casefold() in blob.casefold() for x in want):
            return True, "the app now shows %r" % want[-1]

    ok, why = _evidence(win, end, plan.get("evidence"))
    if ok:
        return True, why

    exp = str((plan.get("evidence") or {}).get("expect") or "").strip()
    if len(exp) >= 2:
        for it in end:
            if messenger and str(it.get("type") or "") in _INPUT_TYPES:
                continue
            b = str(it.get("value") or "") + " " + str(it.get("name") or "")
            if exp.casefold() in b.casefold():
                return True, "found %r on screen" % exp
    return False, why


# ── the proof must be the MESSAGE (appended last: this wins) ─────────────────
# The last run reported "the app now shows 'Mahak'" - the recipient's name, not
# the message. It was true and useless: it proved the chat, not that anything was
# said. For a messenger send the proof is now the TASK's own words appearing in
# the conversation (never an input field, never the recipient's name), so a send
# is only called done when the words really are there.

def _verify(win, steps, plan):
    end = wa.inventory(win)
    messenger = _is_messenger(win)
    steps = [s for s in steps if isinstance(s, dict)]
    consumed = any(str(s.get("action") or "").lower() in ("key", "hotkey")
                   for s in steps)

    def _blob(skip_inputs):
        vals = []
        for it in end:
            if skip_inputs and str(it.get("type") or "") in _INPUT_TYPES:
                continue
            vals.append(str(it.get("value") or ""))
        return " ".join(vals)

    if messenger and consumed:
        task = _CONTEXT["task"] or (_CURRENT[0] or "")
        pay = _chat.task_payload(task, steps, _recipient(task, _payloads(steps)))
        if pay:
            if pay.casefold() in _blob(True).casefold():
                return True, "the message %r is in the conversation" % pay
            return False, ("I cannot see %r in the conversation, so I will not "
                           "claim it was sent" % pay)

    want = [str(s.get("text") or "") for s in steps
            if str(s.get("action") or "").lower() == "type"]
    want = [x for x in want if x.strip()]
    if want:
        blob = _blob(bool(consumed and messenger))
        if any(x.casefold() in blob.casefold() for x in want):
            return True, "the app now shows %r" % want[-1]

    ok, why = _evidence(win, end, plan.get("evidence"))
    if ok:
        return True, why

    exp = str((plan.get("evidence") or {}).get("expect") or "").strip()
    if len(exp) >= 2:
        for it in end:
            if messenger and str(it.get("type") or "") in _INPUT_TYPES:
                continue
            b = str(it.get("value") or "") + " " + str(it.get("name") or "")
            if exp.casefold() in b.casefold():
                return True, "found %r on screen" % exp
    return False, why


# ── a messenger is never "done" from an input field (appended last) ──────────
# A plan with no Enter slipped past the strict rule and a partial string in the
# SEARCH BOX was reported as "the app now shows 'mah'". For a messenger the proof
# is now always the TASK's own words seen in the CONVERSATION - no exceptions,
# whatever the plan happens to contain.

def _verify(win, steps, plan):
    end = wa.inventory(win)
    messenger = _is_messenger(win)
    steps = [s for s in steps if isinstance(s, dict)]

    def _blob(skip_inputs):
        vals = []
        for it in end:
            if skip_inputs and str(it.get("type") or "") in _INPUT_TYPES:
                continue
            vals.append(str(it.get("value") or ""))
        return " ".join(vals)

    if messenger:
        task = _CONTEXT["task"] or (_CURRENT[0] or "")
        pay = _chat.task_payload(task, steps, _recipient(task, _payloads(steps)))
        if pay:
            if pay.casefold() in _blob(True).casefold():
                return True, "the message %r is in the conversation" % pay
            return False, ("I cannot see %r in the conversation, so I will not call "
                           "this done" % pay)

    want = [str(s.get("text") or "") for s in steps
            if str(s.get("action") or "").lower() == "type"]
    want = [x for x in want if x.strip()]
    if want:
        blob = _blob(messenger)
        if any(x.casefold() in blob.casefold() for x in want):
            return True, "the app now shows %r" % want[-1]

    ok, why = _evidence(win, end, plan.get("evidence"))
    if ok:
        return True, why

    exp = str((plan.get("evidence") or {}).get("expect") or "").strip()
    if len(exp) >= 2:
        for it in end:
            if messenger and str(it.get("type") or "") in _INPUT_TYPES:
                continue
            b = str(it.get("value") or "") + " " + str(it.get("name") or "")
            if exp.casefold() in b.casefold():
                return True, "found %r on screen" % exp
    return False, why



# ── a plain send needs no model call at all (appended last: this wins) ───────
# If the task names a recipient and the words to say, there is nothing to decide.
# So: resolve the window, open that exact chat, prove it IS that person, put the
# words in the box, and park ONLY the Enter behind the user's confirmation. Any
# step that cannot be proven returns None and the normal (model) path takes over
# - this can only ever make things faster, never less safe.

def _get_window(app, player=None):
    w = wa.find_window(app) if app else None
    if w is None and app:
        try:
            w = wa.unhide(app)
        except Exception:
            w = None
        if w:
            _log(player, "brought %s back from the tray" % app)
    if w is None and app:
        _launch(app)
        w = _pick_window(app, tries=6, settle=0.5)
    return w


def _direct_send(win, task, app, player, recipient=""):
    if not win or not _is_messenger(win):
        return None
    who = _chat.recipient(task, (), preset=(recipient or _CONTEXT["who"]))
    pay = _chat.task_payload(task, (), who)
    if not who or not pay or len(pay) > 400:
        return None
    _log(player, "this is a plain send - doing it directly, no model needed")
    if not _chat.open_chat(win, who, player):
        _log(player, "could not prove the chat is %r - asking the planner instead"
             % who[:24])
        return None
    if _chat.ensure_payload(win, task, (), player):
        _log(player, "could not put the message in the box - asking the planner instead")
        return None

    from core import confirm

    def _run(win=win, who=who, pay=pay):
        time.sleep(0.4)
        rev = _live.revision(win)
        _execute(win, "key", {"keys": "enter"})
        _live.wait_change(win, timeout=1.5, since=rev)
        _live.quiet(win, 0.25, timeout=1.0)
        blob = " ".join(str(it.get("value") or "") for it in wa.inventory(win)
                        if str(it.get("type") or "") not in _INPUT_TYPES)
        if pay.casefold() in blob.casefold():
            return "Done, and I checked: the message %r is in the conversation" % pay
        return ("I pressed Enter but I cannot see %r in the conversation, so I will "
                "not claim it was sent." % pay)

    return confirm.request(key="desktop_agent",
                           title=("Send to %s?" % who)[:120],
                           detail=pay[:280], run=_run)


_V4_RUN_TASK = run_task


def run_task(task, app=None, details="", player=None, max_steps=MAX_STEPS,
             recipient=""):
    _CONTEXT["task"], _CONTEXT["player"], _CONTEXT["who"] = (
        str(task), player, str(recipient or ""))
    _CURRENT[0], _CURRENT[1], _CURRENT[2] = str(task), player, str(recipient or "")
    _live.start()
    try:
        direct = _direct_send(_get_window(app, player), task, app, player, recipient)
    except Exception as e:
        _log(player, "direct path unavailable (%s)" % e)
        direct = None
    if direct:
        return direct
    return _V4_RUN_TASK(task, app=app, details=details, player=player,
                        max_steps=max_steps, recipient=recipient)


# ── the event detector must be running, or every wait times out ──────────────
# MEASURED: with the WinEvent hook not running, live.revision() stays 0, so
# live.wait_change() can never observe a change and every settle waits its full
# timeout - and the inventory cache key never moves. Starting it is idempotent,
# so we make sure of it at the top of every task.

_PREV_RUN_TASK = run_task
try:
    import inspect as _inspect
    _HAS_RECIPIENT = "recipient" in _inspect.signature(_PREV_RUN_TASK).parameters
except Exception:
    _HAS_RECIPIENT = False


def run_task(task, app=None, details="", player=None, max_steps=MAX_STEPS,
             recipient=""):
    try:
        from core import live as _live
        if not _live.running():
            _live.start()
    except Exception:
        pass
    if _HAS_RECIPIENT:
        return _PREV_RUN_TASK(task, app=app, details=details, player=player,
                              max_steps=max_steps, recipient=recipient)
    return _PREV_RUN_TASK(task, app=app, details=details, player=player,
                          max_steps=max_steps)


# ── the messenger list comes from the same registry (one source of truth) ────
from core import apps as _apps
try:
    _MESSENGERS = tuple(sorted(set(_MESSENGERS) | set(_apps.MESSENGER_KEYS)))
except Exception:
    pass


# ── the messenger list comes from the same registry (one source of truth) ────
from core import apps as _apps
try:
    _MESSENGERS = tuple(sorted(set(_MESSENGERS) | set(_apps.MESSENGER_KEYS)))
except Exception:
    pass
