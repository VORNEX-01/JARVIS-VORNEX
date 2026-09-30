"""
core/desktop_agent.py — universal app driver.

perceive → think → act → verify → learn

Rules:
- ONE run_task, ONE _recipient, ONE prompt
- هر اپی رو میتونه کنترل کنه
- اگه نشد صادقانه میگه چرا
- یاد میگیره و cache میکنه
- irreversible → confirm gate
"""
from __future__ import annotations

import ctypes
import re
import time
from typing import Optional

from core import window_agent as wa

try:
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    _sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ── constants ────────────────────────────────────────────────────────────────
MAX_STEPS = 12

_MESSENGERS = (
    "telegram", "whatsapp", "signal", "discord", "slack",
    "teams", "messenger", "instagram", "eitaa", "bale",
)

_SECRET_RE = re.compile(
    r"(password|passwd|رمز|پسورد|پین|pin|otp|"
    r"کد\s*یکبار|شماره\s*کارت|cvv|seed)",
    re.IGNORECASE,
)

_IRREVERSIBLE_RE = re.compile(
    r"(\bsend\b|\bsubmit\b|\bdelete\b|\bremove\b|\bbuy\b|\bpay\b"
    r"|\bpurchase\b|\bpost\b|\bpublish\b|\bcall\b"
    r"|ارسال|بفرست|حذف|پاک|خرید|بخر|ثبت|تماس)",
    re.IGNORECASE,
)

_BAD_RECIPIENTS = {
    "delete","del","remove","send","open","message","msg","reply",
    "forward","pin","edit","copy","select","chat","conversation",
    "both","sides","the","a","an","my","your","this","that",
    "last","first","all","it","me","new","autonomous",
    "حذف","پاک","بفرست","باز","پیام","چت","گفتگو","هر","دو","طرف",
    "را","در","و","این","آن","یک","همه","برای","با","به","کن",
}

_WHO_PAT = re.compile(
    r"(?:chat\s+with|message\s+to|send\s+to|talk\s+to|with|to|for|"
    r"چت\s+با|گفتگو\s+با|برای|به|با)\s+([^\s,،;؛]+)",
    re.IGNORECASE,
)

# ── single prompt ────────────────────────────────────────────────────────────
_PROMPT = """\
You are the control loop of a desktop agent. You see LIVE controls of ONE window.
Reach the task with minimum steps.

Reply ONLY with this JSON (no markdown, no explanation):
{
  "done": false,
  "say": "",
  "steps": [
    {"action": "", "index": -1, "text": "", "keys": "", "irreversible": false}
  ],
  "evidence": {"index": -1, "expect": ""},
  "why": ""
}

action = click | set_value | type | key | hotkey | wait | activate
- click / set_value  → need "index" = [N] of the control
- type               → need "text" (goes to whatever has focus — click first!)
- key / hotkey       → need "keys"  e.g. "enter", "ctrl+a"
- wait               → pauses 1 second

RULES:
1. Never invent an index not in the list.
2. Mark irreversible=true ONLY on the step that sends/posts/deletes/buys/calls.
3. Enter inside a messenger app = SEND. That step must have irreversible=true.
4. Always fill "evidence" with the control [N] and exact text that PROVES done.
5. If already done set done=true. If unsure keep done=false and explain in "why".
6. Follow EXACT numbers/words in the task - never substitute your own values.
7. A name can appear in another script: "ماهک" and "Mahak" are the same person.
8. Click the target field before typing. Never type blindly.
9. If the task says SEND, the plan MUST end with action=key, keys=enter.
"""


# ── helpers ──────────────────────────────────────────────────────────────────

def _log(player, msg: str) -> None:
    try:
        if player:
            player.write_log(str(msg)[:160])
    except Exception:
        pass


def _truthy(v) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("true", "yes", "1")


def _is_usable(win) -> bool:
    try:
        r = win.get("rect") or (0, 0, 0, 0)
        return (not win.get("minimized")) and r[0] > -30000 and r[1] > -30000
    except Exception:
        return False


def _is_messenger(win) -> bool:
    exe = str(win.get("exe") or "").lower()
    name = str(win.get("name") or "").lower()
    return any(m in exe or m in name for m in _MESSENGERS)


# ── window management ────────────────────────────────────────────────────────

def _hwnd_of(win) -> int:
    for k in ("hwnd", "handle", "NativeWindowHandle", "hWnd"):
        try:
            v = win.get(k)
            if v:
                return int(v)
        except Exception:
            pass
    return 0


def _front_hwnd() -> int:
    try:
        return int(ctypes.windll.user32.GetForegroundWindow())
    except Exception:
        return 0


def _raise_window(win) -> bool:
    """Bring window to front using every available trick."""
    h = _hwnd_of(win)
    if h and _front_hwnd() == h:
        return True

    # try project's own activate first
    try:
        if wa.activate(win):
            time.sleep(0.1)
            if not h or _front_hwnd() == h:
                return True
    except Exception:
        pass

    if not h:
        return False

    u = ctypes.windll.user32
    k = ctypes.windll.kernel32

    # minimize + restore trick
    try:
        u.ShowWindow(h, 6)
        time.sleep(0.12)
        u.ShowWindow(h, 9)
    except Exception:
        pass

    # SetForegroundWindow with retries
    for _ in range(3):
        try:
            u.SetForegroundWindow(h)
        except Exception:
            pass
        time.sleep(0.1)
        if _front_hwnd() == h:
            return True

    # AttachThreadInput trick
    try:
        fg = _front_hwnd()
        t_fg = u.GetWindowThreadProcessId(fg, None)
        t_my = k.GetCurrentThreadId()
        u.AttachThreadInput(t_my, t_fg, True)
        try:
            u.BringWindowToTop(h)
            u.SetForegroundWindow(h)
        finally:
            u.AttachThreadInput(t_my, t_fg, False)
    except Exception:
        pass

    time.sleep(0.12)
    return _front_hwnd() == h


def _launch(app: str) -> None:
    try:
        import importlib
        m = importlib.import_module("actions.open_app")
        h = getattr(m, "open_app", None) or (m.TOOL or {}).get("handler")
        if h:
            h(parameters={"app_name": app})
            return
    except Exception as e:
        print("[desktop_agent] open_app failed:", repr(e))
    try:
        import subprocess
        subprocess.Popen([app], shell=True)
    except Exception:
        pass


def _pick_window(app: str, tries: int = 6, settle: float = 1.5) -> Optional[dict]:
    if not app:
        return None
    deadline = time.time() + tries * settle
    while time.time() < deadline:
        win = wa.find_window(app)
        if win and _is_usable(win):
            return win
        time.sleep(settle)
    return None


# ── recipient extraction (ONE definition) ───────────────────────────────────

def _recipient(task: str) -> str:
    """Extract the person's name from a task string.
    
    Only returns something if there's an EXPLICIT cue like
    'with X', 'to X', 'با X', etc. Never guesses from verbs.
    """
    text = str(task or "")
    for m in _WHO_PAT.finditer(text):
        cand = m.group(1).strip().strip("?.!،؛:\"'")
        if len(cand) >= 2 and cand.casefold() not in _BAD_RECIPIENTS:
            return cand
    return ""


def _chat_name(win) -> str:
    """Title of the currently open conversation."""
    try:
        import re
        name = str(win.get("name") or "")
        # strip invisible unicode chars (RTL mark etc)
        name = name.strip().lstrip("‎‏‪‫‬‭‮")
        # remove trailing message count like (156952)
        name = re.sub(r"\s*\(\d+\)\s*$", "", name).strip()
        # split on em-dash, en-dash, or regular dash
        for sep in (" — ", "—", " – ", "–", " - ", "-"):
            if sep in name:
                return name.split(sep, 1)[-1].strip()
        return name.strip()
    except Exception:
        return ""


# ── irreversibility check (ONE definition) ──────────────────────────────────

def _is_irreversible(step: dict, action: str, text: str,
                     win: dict, target_name: str = "") -> bool:
    """Returns True only on deterministic signals — not the model's flag alone."""
    if action not in ("click", "set_value", "type", "key", "hotkey"):
        return False

    keys = str(step.get("keys") or "")
    exe = str(win.get("exe") or "").lower()

    # Enter inside a messenger = send
    if action in ("key", "hotkey") and "enter" in keys.lower():
        if any(m in exe for m in _MESSENGERS):
            return True

    # Control label or typed text contains irreversible keyword
    if _IRREVERSIBLE_RE.search(target_name or ""):
        return True
    if _IRREVERSIBLE_RE.search(text or ""):
        return True

    # Model flagged it AND the control has no readable label
    model_flagged = _truthy(step.get("irreversible"))
    if model_flagged and action in ("click", "set_value") and not target_name:
        return True

    return False


# ── execution ────────────────────────────────────────────────────────────────

def _execute(win: dict, action: str, step: dict) -> str:
    """Execute one step. Returns a short description of what happened."""
    # Safety: never act on a window that isn't foreground
    if action in ("click", "set_value", "type", "key", "hotkey"):
        h = _hwnd_of(win)
        if h and _front_hwnd() != h:
            if not _raise_window(win):
                return ("refused: %r is not foreground and I could not raise it"
                        % (win.get("name") or "target"))

    idx = step.get("index")
    action = action.lower().strip()

    if action == "click":
        return wa.click_item(win, int(idx))

    if action == "set_value":
        return wa.set_value_item(win, int(idx), str(step.get("text") or ""))

    if action == "type":
        txt = str(step.get("text") or "")
        # Clear existing content first to avoid doubling
        try:
            cur = wa.focused_value()
        except Exception:
            cur = ""
        if cur.strip():
            wa.hotkey("ctrl+a")
            time.sleep(0.08)
            wa.press("delete")
            time.sleep(0.1)
        return wa.type_text(txt)

    if action == "key":
        return wa.press(str(step.get("keys") or ""))

    if action == "hotkey":
        return wa.hotkey(str(step.get("keys") or ""))

    if action == "activate":
        return "raised" if wa.activate(win) else "could not raise"

    if action == "wait":
        time.sleep(1.0)
        return "waited 1s"

    return "unknown action %r" % action


def _resolve_live(win: dict, items: list, step: dict) -> Optional[int]:
    """Re-find a control by type+name in the current tree (items may have shifted)."""
    try:
        want = items[int(step.get("index"))]
    except Exception:
        return None

    cands = [it for it in wa.inventory(win)
             if it["type"] == want["type"] and it["name"] == want["name"]]
    if not cands:
        return None
    if len(cands) == 1:
        return cands[0]["i"]

    # multiple matches → pick geometrically closest
    lx, ly = want["rect"][0], want["rect"][1]
    cands.sort(key=lambda it: abs(it["rect"][0]-lx) + abs(it["rect"][1]-ly))
    return cands[0]["i"]


# ── evidence check ───────────────────────────────────────────────────────────

def _check_evidence(items: list, ev) -> tuple[bool, str]:
    if not isinstance(ev, dict):
        return False, "no evidence given"
    try:
        i = int(ev.get("index"))
    except Exception:
        return False, "evidence index missing"
    if not (0 <= i < len(items)):
        return False, "evidence index %s out of range" % ev.get("index")
    expect = str(ev.get("expect") or "").strip()
    if not expect:
        return False, "evidence has nothing to check"
    it = items[i]
    val = str(it.get("value") or "")
    nm  = str(it.get("name")  or "")
    if expect.casefold() in val.casefold():
        return True, "[%d] reads %r" % (i, val[:60])
    if expect.casefold() in nm.casefold():
        return True, "[%d] label matches %r" % (i, nm[:60])
    return False, "expected %r but [%d] reads %r" % (expect, i, val[:40])


# ── plan cache (recipes) ─────────────────────────────────────────────────────

def _replay(win: dict, task: str, app: str, player) -> Optional[str]:
    """Try to re-run a cached successful plan without calling the model."""
    try:
        from core import recipes as _recipes
        rec = _recipes.load(app, task)
    except Exception:
        return None
    if not rec:
        return None
    if _is_messenger(win):
        return None  # never replay messenger plans — chat state changes
    steps = rec.get("steps") or []
    if not steps:
        return None
    if any(s.get("irr") for s in steps):
        return None  # irreversible → always go through normal path + confirm

    _log(player, "replaying cached plan (%d steps)" % len(steps))
    did = []
    for st in steps:
        if not wa.window_alive(win):
            return None
        op = str(st.get("op") or "")
        live_step: dict = {}

        if op == "type":
            live_step = {"action": "type", "text": str(st.get("text") or "")}
        elif op in ("click", "set_value"):
            # find control by semantic match
            items_now = wa.inventory(win)
            hit = next(
                (it for it in items_now
                 if it["type"] == st.get("type") and it["name"] == st.get("name")),
                None,
            )
            if hit is None:
                _log(player, "cached control gone, planning fresh")
                return None
            live_step = {"action": op, "index": hit["i"]}
        elif op in ("key", "hotkey"):
            live_step = {"action": op, "keys": str(st.get("keys") or "")}
        else:
            continue

        _raise_window(win)
        what = _execute(win, live_step["action"], live_step)
        did.append(what)
        time.sleep(0.4)

    # verify
    end_items = wa.inventory(win)
    blob = " ".join(str(it.get("value") or "") for it in end_items)
    expects = [str(x) for x in (rec.get("expect") or []) if x]
    if expects and all(x.casefold() in blob.casefold() for x in expects):
        return "Done (replayed cached plan, verified): %s" % "; ".join(did[-3:])
    # cache miss — drop it and plan fresh
    try:
        from core import recipes as _recipes
        _recipes.drop(app, task)
    except Exception:
        pass
    return None


def _save_plan(app: str, task: str, raw_steps: list, items: list) -> None:
    try:
        from core import recipes as _recipes
        record = []
        for st in raw_steps:
            op = str(st.get("action") or "")
            entry: dict = {"op": op}
            if op in ("click", "set_value"):
                try:
                    it = items[int(st.get("index"))]
                    entry.update(type=it["type"], name=it["name"])
                except Exception:
                    continue
            elif op == "type":
                entry["text"] = str(st.get("text") or "")
                entry["irr"] = _truthy(st.get("irreversible"))
            elif op in ("key", "hotkey"):
                entry["keys"] = str(st.get("keys") or "")
            record.append(entry)
        _recipes.save(app, task, {"steps": record})
    except Exception:
        pass


# ── main loop ────────────────────────────────────────────────────────────────

def run_task(task: str, app: str = "", details: str = "",
             player=None, max_steps: int = MAX_STEPS) -> str:
    """Drive ANY app to complete `task`. Returns a plain-English result."""

    if wa.auto is None:
        return "UI Automation is unavailable — I cannot read the screen safely."

    # block if another confirmation is already waiting
    try:
        from core.confirm import pending_title
        waiting = pending_title()
    except Exception:
        waiting = ""
    if waiting:
        return ("There is already a confirmation waiting for %r — "
                "please answer that one first." % waiting)

    # ── find or open the window ──────────────────────────────────────────────
    win: Optional[dict] = None
    if app:
        win = wa.find_window(app)
        if win is None:
            try:
                win = wa.unhide(app)
                if win:
                    _log(player, "brought %s out of tray" % app)
            except Exception:
                pass
        if win is None:
            _log(player, "launching %s..." % app)
            _launch(app)
            win = _pick_window(app, tries=6, settle=1.5)

    if win is not None and not _is_usable(win):
        try:
            wa.activate(win)
            time.sleep(0.5)
            win = _pick_window(app, tries=4) or win
        except Exception:
            pass

    if win is None:
        procs = wa.find_processes(app or "")
        if procs:
            names = ", ".join("%s(pid %s)" % (n, p) for p, n in procs[:3])
            return ("%s is running (%s) but has no visible window. "
                    "Open its window and ask me again." % (app, names))
        return ("I could not find %r and it did not open, so I did nothing."
                % (app or "the target window"))

    if not _raise_window(win):
        _log(player, "warning: could not bring %r to front" % win.get("name"))
    time.sleep(0.15)

    # ── try cached plan first ────────────────────────────────────────────────
    cached = _replay(win, task, app, player)
    if cached:
        return cached

    # ── live planning loop ───────────────────────────────────────────────────
    from core import gemini

    history: list[str] = []
    did_any: list[str] = []
    no_progress = 0
    rounds = 0

    while rounds < max_steps:
        rounds += 1

        # window still alive?
        if not wa.window_alive(win):
            win = _pick_window(app, tries=3) or win
            if not wa.window_alive(win):
                return ("The window closed while I was working — I stopped. "
                        "Did: %s" % "; ".join(did_any[-3:]))

        # build prompt
        items = wa.inventory(win)
        seen  = wa.snapshot_text(win, items)
        if len(seen) > 4000:
            seen = seen[:3900] + "\n...(truncated)"

        try:
            focused = wa.focused()
        except Exception:
            focused = None

        parts = [
            _PROMPT,
            "TASK: " + str(task),
        ]
        if app:
            parts.append("APP: " + str(app))
        if details:
            parts.append("DETAILS: " + str(details))
        parts.append("KEYBOARD FOCUS: " + (
            "[%s] %r" % (focused["type"], focused["name"])
            if focused else "nothing editable"
        ))
        if history:
            parts.append("ALREADY TRIED:\n" + "\n".join(history[-5:]))
        parts.append("LIVE CONTROLS:\n" + seen)

        prompt = "\n\n".join(parts)

        # ask the model
        plan = gemini.as_json(prompt, tier=gemini.SMART,
                              timeout_ms=15000, default=None)
        if not isinstance(plan, dict):
            if did_any:
                return ("I did %s but then lost track of the next step — "
                        "I stopped and I am NOT claiming it finished."
                        % "; ".join(did_any[-3:]))
            return ("I could not work out how to do %r — I did nothing." % task)

        # ── done? ────────────────────────────────────────────────────────────
        if _truthy(plan.get("done")):
            ok, why = _check_evidence(items, plan.get("evidence"))
            if ok:
                _log(player, "done — %s" % why)
                say = str(plan.get("say") or "").strip() or ("Done: " + task)
                return "%s (verified: %s)" % (say, why)
            history.append("done=true but evidence failed: %s" % why)
            continue

        # ── get steps ────────────────────────────────────────────────────────
        raw = plan.get("steps")
        if not isinstance(raw, list) or not raw:
            raw = [plan]
        raw = [s for s in raw[:5] if isinstance(s, dict)]
        if not raw:
            history.append("Plan had no usable steps.")
            continue

        # ── irreversibility gate ─────────────────────────────────────────────
        gate_step = None
        for st in raw:
            a = str(st.get("action") or "").lower()
            tname = ""
            if a in ("click", "set_value"):
                try:
                    tname = str(items[int(st.get("index"))].get("name") or "")
                except Exception:
                    pass
            if _is_irreversible(st, a, str(st.get("text") or ""), win, tname):
                gate_step = st
                break

        if gate_step is not None:
            _log(player, "confirm gate: %r" % gate_step)
            from core import confirm
            detail = (str(plan.get("say") or plan.get("why") or task))[:280]

            def _confirmed(win=win, steps=list(raw), items=items, plan=plan):
                for st in steps:
                    if not isinstance(st, dict):
                        continue
                    a = str(st.get("action") or "").lower()
                    _raise_window(win)
                    time.sleep(0.15)
                    if a in ("click", "set_value"):
                        lv = _resolve_live(win, items, st)
                        if lv is not None:
                            st = dict(st, index=lv)
                    _execute(win, a, st)
                    time.sleep(0.5)
                end = wa.inventory(win)
                ok, why = _check_evidence(end, plan.get("evidence"))
                if ok:
                    return "Done, verified: %s" % why
                return ("Done, but I could not verify it (%s). "
                        "Please check the app." % why)

            return confirm.request(
                key="desktop_agent",
                title=("Confirm: " + str(task))[:120],
                detail=detail,
                run=_confirmed,
            )

        # ── execute steps ────────────────────────────────────────────────────
        sig_before = wa.signature(items)
        abort_reason: Optional[str] = None

        for step in raw:
            if not isinstance(step, dict):
                continue
            if not wa.window_alive(win):
                return ("Window closed mid-task — stopped. Did: %s"
                        % "; ".join(did_any[-3:]))

            action = str(step.get("action") or "").strip().lower()
            text   = str(step.get("text")   or "")

            if action not in ("click","set_value","type","key",
                              "hotkey","wait","activate"):
                abort_reason = "unknown action %r" % action
                break

            if action == "type" and _SECRET_RE.search(text):
                return "That looks like a secret (password/PIN/card) — I will not type it."

            tname = ""
            if action in ("click", "set_value"):
                try:
                    tname = str(items[int(step.get("index"))].get("name") or "")
                except Exception:
                    abort_reason = "index %r is not in the control list" % step.get("index")
                    break

            if action in ("click","set_value","type","key","hotkey"):
                if not _raise_window(win):
                    abort_reason = "could not bring window to front"
                    break

            # live re-resolve before click
            if action in ("click", "set_value"):
                lv = _resolve_live(win, items, step)
                if lv is None:
                    abort_reason = "[%s] %r is gone from screen" % (
                        step.get("index"), tname)
                    break
                step = dict(step, index=lv)

            what = _execute(win, action, step)
            did_any.append(what)
            _log(player, what)

            if str(what).startswith(("refused","could not","unknown","no such")):
                abort_reason = "step refused: %s" % what
                break

            # wait for UI to settle
            deadline = time.time() + 1.0
            while time.time() < deadline:
                time.sleep(0.2)
                if not wa.window_alive(win):
                    break
                if wa.signature(wa.inventory(win)) != sig_before:
                    break

        if abort_reason:
            history.append("Stopped: %s" % abort_reason)
            continue

        # ── verify after plan ────────────────────────────────────────────────
        end_items = wa.inventory(win)
        ok, why = _check_evidence(end_items, plan.get("evidence"))

        # secondary: check typed text actually appeared
        if not ok:
            typed = [str(s.get("text") or "") for s in raw
                     if str(s.get("action","")).lower() == "type"
                     and str(s.get("text") or "").strip()]
            if typed:
                blob = " ".join(str(it.get("value") or "") for it in end_items)
                if any(t.casefold() in blob.casefold() for t in typed):
                    ok, why = True, "typed text found in controls"

        if ok:
            # save to cache (reversible only)
            has_irr = any(_truthy(s.get("irreversible")) for s in raw)
            if not has_irr and app:
                _save_plan(app, task, raw, items)
            say = str(plan.get("say") or "").strip() or ("Done: " + task)
            return "%s (verified: %s)" % (say, why)

        # no progress?
        if wa.signature(end_items) == sig_before:
            no_progress += 1
        else:
            no_progress = 0

        if no_progress >= 2:
            return (
                "I tried %s but nothing changed on screen. "
                "I stopped rather than looping. Please check the app."
                % "; ".join(did_any[-4:])
            )

        history.append("Steps ran but screen does not show expected result yet.")

    # max steps reached
    if did_any:
        return ("After %d steps I could not reach a verified result. "
                "I stopped. Did: %s. Please check the app."
                % (max_steps, "; ".join(did_any[-4:])))
    return ("I stopped after %d steps without completing %r."
            % (max_steps, task))


# ── public surface used by other modules ────────────────────────────────────

def _pick_window_public(app: str, tries: int = 6) -> Optional[dict]:
    return _pick_window(app, tries=tries)


# keep old name working for anything that imports it
_pick_window_public.__name__ = "_pick_window"


def desktop_agent(parameters, player=None, session_memory=None) -> str:
    p = parameters if isinstance(parameters, dict) else {}
    task    = str(p.get("task")    or p.get("action") or "")
    app     = str(p.get("app")     or p.get("application") or "")
    details = str(p.get("details") or "")
    if not task:
        return "No task was given."
    return run_task(task, app=app, details=details, player=player)


def run(parameters, player=None, session_memory=None) -> str:
    return desktop_agent(parameters, player=player,
                         session_memory=session_memory)


TOOL = {
    "name": "desktop_agent",
    "description": (
        "Control ANY desktop application to complete a task. "
        "Reads live UI controls, acts step by step, verifies the result. "
        "Use this for anything that needs clicking, typing, or navigating "
        "inside an app — even apps with no API."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "app":  {"type": "STRING",
                     "description": "App name, e.g. 'Notepad', 'Telegram', 'Chrome'"},
            "task": {"type": "STRING",
                     "description": "What to do, in plain language"},
            "details": {"type": "STRING",
                        "description": "Extra context if needed"},
        },
        "required": ["task"],
    },
    "handler": desktop_agent,
    "scheduling": "INTERRUPT",
}