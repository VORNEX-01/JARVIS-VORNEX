"""core/chat.py - who is the open conversation, and how to open the right one.

A messenger puts the OPEN CHAT in its window title. That single fact answers the
only question that matters before a message can leave the machine: "is this the
person the task names?" - with no model call and no guessing.

Everything here is deliberately deterministic. Reaching a contact is a fixed
procedure (search, pick the ONE matching row, verify), not a judgement call, so
it lives in one place and every caller gets the same safe behaviour.
"""
from __future__ import annotations

import re
import time

from core import live
from core import names
from core import window_agent as wa

CONV_ROWS = ("ListItem", "DataItem", "TreeItem")
SEARCH_WORDS = ("search", "find", "جستجو", "جست‌وجو", "بحث")
STOP = set("""send message telegram whatsapp signal discord instagram messenger
this exact text the and please to on for by with via that say tell open chat
conversation contact person into document leave it there write type
پیام تلگرام واتساپ سیگنال دیسکورد اینستاگرام مسنجر دقیقا دقیقاً این متن که بگو
به برای توی در روی از با عزیزم جان لطفا بفرست ارسال""".split())


def _log(player, msg):
    try:
        if player:
            player.write_log(str(msg)[:160])
    except Exception:
        pass


def _raise(win):
    try:
        from core import desktop_agent as da
        return da._raise_window(win)
    except Exception:
        try:
            return bool(wa.activate(win))
        except Exception:
            return False


def _settle(win, before, rev):
    try:
        from core import desktop_agent as da
        return da._settle(win, before, rev)
    except Exception:
        time.sleep(0.3)
        return True


def name(win):
    """The OPEN conversation of a window, or '' - read live, never from a cache."""
    if not isinstance(win, dict):
        return ""
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


def conv_ok(win, task, clicked=""):
    """'' means the open conversation is acceptable; else the reason it is not.

    Acceptable = it is the row just clicked, OR it is the person the task names
    (across scripts - two spellings of one name are one person). Anything else is
    refused, so a click on the wrong chat can never be followed by typing."""
    if not isinstance(win, dict):
        return "no window to check"
    title = name(win)
    if not title:
        return "the open conversation has no name I can read"
    exe = (win.get("exe") or "").lower().replace(".exe", "")
    if exe and names.score(title, exe) > 0.9:
        return "no conversation is open (the window is just %r)" % title
    if clicked and names.score(clicked, title) >= 0.7:
        return ""
    nk, tk = names.skeleton(title), names.skeleton(task)
    if len(nk) >= 3 and nk in tk:
        return ""
    if names.score(title, task) >= 0.6:
        return ""
    return ("the open conversation is %r, which is neither the row I clicked nor "
            "the person in the task" % title)


def focus_is_search():
    """True when the keyboard sits in a search field - there, typing a NAME is
    expected and the open chat is irrelevant."""
    try:
        f = wa.focused() or {}
    except Exception:
        f = {}
    nm = str(f.get("name") or "").lower()
    return any(k in nm for k in SEARCH_WORDS)


def payloads(steps):
    return [str(s.get("text") or "") for s in steps[:5]
            if isinstance(s, dict)
            and str(s.get("action") or "").lower() == "type"
            and str(s.get("text") or "").strip()]


def recipient(task, payloads=(), preset=""):
    """Who the task is for: the exact name when the caller knows it, else the
    first substantial word of the task that is not part of the message itself."""
    who = str(preset or "").strip()
    if who:
        return who
    try:
        t = names.norm(task)
    except Exception:
        return ""
    used = set()
    for p in payloads or ():
        try:
            used.update(names.norm(p).split())
        except Exception:
            pass
    for w in t.split():
        if len(w) >= 3 and not w.isdigit() and w not in used and w not in STOP:
            return w
    return ""


def find_search(items):
    for it in items:
        if str(it.get("type") or "") in ("Edit", "ComboBox"):
            if any(k in str(it.get("name") or "").lower() for k in SEARCH_WORDS):
                return it
    for it in items:
        if str(it.get("type") or "") == "Button":
            if any(k in str(it.get("name") or "").lower() for k in SEARCH_WORDS):
                return it
    return None


def click(win, item, player=None):
    """Click ONE live control, precisely, then wait for the UI to settle."""
    try:
        idx = int(item.get("i"))
    except Exception:
        return False
    _raise(win)
    try:
        before = wa.signature(wa.inventory(win))
    except Exception:
        before = None
    rev = live.revision(win)
    r = item.get("rect") or (0, 0, 0, 0)
    _log(player, "click %r centre (%d,%d) box %dx%d" % (
        str(item.get("name") or "")[:34],
        (r[0] + r[2]) // 2, (r[1] + r[3]) // 2,
        max(0, r[2] - r[0]), max(0, r[3] - r[1])))
    try:
        wa.click_item(win, idx)
    except Exception as e:
        _log(player, "click failed: %s" % e)
        return False
    _settle(win, before, rev)
    return True


def open_chat(win, who, player=None):
    """Open the conversation with `who` through the app's own Search.

    True when the chat that is OPEN now really is that person. If the result list
    is ambiguous we refuse rather than guess - a wrong recipient is worse than an
    unfinished task."""
    who = str(who or "").strip()
    if not who:
        return False
    if not conv_ok(win, who, ""):
        return True
    _log(player, "opening the chat with %r through the app's own Search" % who[:28])
    for _try in (1, 2):
        items = wa.inventory(win)
        box = find_search(items)
        if box is None:
            _log(player, "this app has no Search box I can use")
            return False
        if not click(win, box, player):
            return False
        items = wa.inventory(win)
        box = find_search(items) or box
        click(win, box, player)
        try:
            wa.hotkey("ctrl+a")
            time.sleep(0.05)
            wa.press("delete")
            time.sleep(0.05)
        except Exception:
            pass
        try:
            wa.type_text(who)
        except Exception:
            return False
        live.wait_change(win, timeout=1.2, since=live.revision(win))
        live.quiet(win, 0.25, timeout=0.8)
        items = wa.inventory(win)
        rows = [it for it in items
                if str(it.get("type") or "") in CONV_ROWS
                and str(it.get("name") or "").strip()]
        hit = names.best(who, rows, key="name", floor=0.85, margin=0.08)
        if hit is None:
            _log(player, "no row on screen is clearly %r - I will not guess" % who[:28])
            continue
        click(win, hit, player)
        if not conv_ok(win, who, str(hit.get("name") or "")):
            _log(player, "verified: the open chat is %r" % name(win)[:28])
            return True
    return not conv_ok(win, who, "")


# ── make sure the MESSAGE actually gets said ─────────────────────────────────
# The planner can aim at the right chat and still hand us a plan with no text in
# it (it typed the recipient into the search box and went straight to Enter).
# Sending an empty box is a silent no-op, so before any send we make sure the
# task's own words are sitting in the message box - typed by us if need be.

_COMPOSE_WORDS = ("message", "پیام", "متن", "type a", "write a")
_PAY_MARKS = (":", "،", " that says ", " saying ", " with the text ", " بگو ", " که ")


def task_payload(task, steps=(), who=""):
    """The words the task wants said: the task's own tail, else what the plan typed."""
    s = str(task or "").strip().strip('"\'«»“” ')
    for m in _PAY_MARKS:
        if m in s:
            tail = s.rsplit(m, 1)[1].strip().strip('"\'«»“” ').strip()
            if tail:
                return tail
    for t in payloads(steps):
        t = str(t or "").strip()
        if not t or (who and names.score(t, who) >= 0.6):
            continue
        return t
    return ""


def find_compose(items):
    cands = [it for it in items
             if str(it.get("type") or "") in ("Edit", "Document")
             and any(k in str(it.get("name") or "").lower() for k in _COMPOSE_WORDS)]
    if not cands:
        cands = [it for it in items if str(it.get("type") or "") in ("Edit", "Document")]
    if not cands:
        return None
    cands.sort(key=lambda it: (it.get("rect") or (0, 0, 0, 0))[1], reverse=True)
    return cands[0]


def ensure_payload(win, task, steps=(), player=None):
    """'' when the message is in the box (or there is nothing to say)."""
    who = recipient(task, payloads(steps))
    text = task_payload(task, steps, who)
    if not text:
        return ""
    box = find_compose(wa.inventory(win))
    if box is None:
        return "I cannot find the message box"
    cur = str(box.get("value") or "")
    if text.casefold() in cur.casefold():
        return ""
    _log(player, "putting the message into the box: %r" % text[:30])
    click(win, box, player)
    try:
        wa.hotkey("ctrl+a")
        time.sleep(0.05)
        wa.press("delete")
        time.sleep(0.05)
    except Exception:
        pass
    try:
        wa.type_text(text)
    except Exception as e:
        return "I could not type the message (%s)" % e
    live.wait_change(win, timeout=1.0, since=live.revision(win))
    live.quiet(win, 0.2, timeout=0.6)
    after = find_compose(wa.inventory(win)) or box
    if text.casefold() in str(after.get("value") or "").casefold():
        return ""
    return "the message did not land in the box"


# ── faster, calmer search dance (appended last: these win) ───────────────────
# The first version clicked the search field twice and waited the full settle on
# every click, so reaching a contact could take 20s. The field needs ONE click,
# and the result list renders within a second - so we type once and then poll,
# bounded, for a row that IS the person.

def _settle(win, before, rev, hard_limit=2.5):
    try:
        from core import desktop_agent as da
        return da._settle(win, before, rev, hard_limit)
    except Exception:
        time.sleep(min(0.3, hard_limit))
        return True


def click(win, item, player=None, settle=2.5):
    """Click ONE live control, precisely, then wait for the UI to settle."""
    try:
        idx = int(item.get("i"))
    except Exception:
        return False
    _raise(win)
    try:
        before = wa.signature(wa.inventory(win))
    except Exception:
        before = None
    rev = live.revision(win)
    r = item.get("rect") or (0, 0, 0, 0)
    _log(player, "click %r centre (%d,%d) box %dx%d" % (
        str(item.get("name") or "")[:34],
        (r[0] + r[2]) // 2, (r[1] + r[3]) // 2,
        max(0, r[2] - r[0]), max(0, r[3] - r[1])))
    try:
        wa.click_item(win, idx)
    except Exception as e:
        _log(player, "click failed: %s" % e)
        return False
    _settle(win, before, rev, settle)
    return True


def open_chat(win, who, player=None):
    """Open the conversation with `who` through the app's own Search.

    True when the chat that is OPEN now really is that person. If the result list
    stays ambiguous we refuse - a wrong recipient is worse than an unfinished
    task."""
    who = str(who or "").strip()
    if not who:
        return False
    if not conv_ok(win, who, ""):
        return True
    _log(player, "opening the chat with %r through the app's own Search" % who[:28])
    for _try in (1, 2):
        items = wa.inventory(win)
        box = find_search(items)
        if box is None:
            _log(player, "this app has no Search box I can use")
            return False
        if not click(win, box, player, settle=0.7):
            return False
        try:
            wa.hotkey("ctrl+a")
            time.sleep(0.04)
            wa.press("delete")
        except Exception:
            pass
        try:
            wa.type_text(who)
        except Exception:
            return False
        hit = None
        deadline = time.time() + 2.5
        while time.time() < deadline:
            live.wait_change(win, timeout=0.5, since=live.revision(win))
            live.quiet(win, 0.15, timeout=0.4)
            rows = [it for it in wa.inventory(win)
                    if str(it.get("type") or "") in CONV_ROWS
                    and str(it.get("name") or "").strip()]
            hit = names.best(who, rows, key="name", floor=0.85, margin=0.08)
            if hit is not None:
                break
        if hit is None:
            _log(player, "no row on screen is clearly %r - I will not guess" % who[:28])
            continue
        click(win, hit, player, settle=1.5)
        if not conv_ok(win, who, str(hit.get("name") or "")):
            _log(player, "verified: the open chat is %r" % name(win)[:28])
            return True
        _log(player, "the open chat is still %r" % name(win)[:28])
    return not conv_ok(win, who, "")


# ── put text INTO a field, provably (appended last: this wins) ───────────────
# Typing into the search field only works if that field happens to hold the
# focus, so the chat was sometimes never found. The UIA value pattern needs no
# focus at all, so we try that first and then CHECK that the field really shows
# the text - and only fall back to a real keystroke when it does not.

def _type_into(win, box, text, player=None):
    try:
        wa.set_value_item(win, int(box.get("i")), text)
    except Exception:
        pass
    live.wait_change(win, timeout=0.6, since=live.revision(win))
    live.quiet(win, 0.12, timeout=0.4)
    for it in wa.inventory(win):
        if str(it.get("type") or "") in ("Edit", "ComboBox") and \
                text.casefold() in str(it.get("value") or "").casefold():
            _log(player, "search box holds %r" % text[:24])
            return True
    click(win, box, player, settle=0.5)
    if not focus_is_search():
        _log(player, "the search field did not take the focus")
    try:
        wa.hotkey("ctrl+a")
        time.sleep(0.04)
        wa.press("delete")
        time.sleep(0.04)
        wa.type_text(text)
    except Exception:
        return False
    live.wait_change(win, timeout=0.8, since=live.revision(win))
    live.quiet(win, 0.15, timeout=0.5)
    for it in wa.inventory(win):
        if str(it.get("type") or "") in ("Edit", "ComboBox") and \
                text.casefold() in str(it.get("value") or "").casefold():
            _log(player, "search box holds %r" % text[:24])
            return True
    _log(player, "I could not put %r into the search box" % text[:24])
    return False


def open_chat(win, who, player=None):
    """Open the conversation with `who` through the app's own Search."""
    who = str(who or "").strip()
    if not who:
        return False
    if not conv_ok(win, who, ""):
        return True
    _log(player, "opening the chat with %r through the app's own Search" % who[:28])
    for _try in (1, 2):
        items = wa.inventory(win)
        box = find_search(items)
        if box is None:
            _log(player, "this app has no Search box I can use")
            return False
        if not _type_into(win, box, who, player):
            click(win, box, player, settle=0.5)
            if not _type_into(win, box, who, player):
                continue
        hit = None
        deadline = time.time() + 3.0
        while time.time() < deadline:
            live.wait_change(win, timeout=0.5, since=live.revision(win))
            live.quiet(win, 0.15, timeout=0.4)
            rows = [it for it in wa.inventory(win)
                    if str(it.get("type") or "") in CONV_ROWS
                    and str(it.get("name") or "").strip()]
            hit = names.best(who, rows, key="name", floor=0.85, margin=0.08)
            if hit is not None:
                break
        if hit is None:
            _log(player, "no row on screen is clearly %r - I will not guess" % who[:28])
            continue
        click(win, hit, player, settle=1.5)
        if not conv_ok(win, who, str(hit.get("name") or "")):
            _log(player, "verified: the open chat is %r" % name(win)[:28])
            return True
        _log(player, "the open chat is still %r" % name(win)[:28])
    return not conv_ok(win, who, "")


# ── real typing with a guaranteed focus (appended last: this wins) ───────────
# Filling a field through the UIA value pattern does NOT fire the app's own
# filtering (Telegram showed the text but never narrowed the list). So we type
# for real, we make sure the search field actually has the focus first, and we
# CHECK the field afterwards. When nothing matches we log the closest rows and
# their scores, so the next decision is based on what is really on screen.

def _field_holds(win, text):
    try:
        for it in wa.inventory(win):
            if str(it.get("type") or "") in ("Edit", "ComboBox") and \
                    str(text).casefold() in str(it.get("value") or "").casefold():
                return True
    except Exception:
        pass
    return False


def _type_into(win, box, text, player=None):
    cands = [box]
    try:
        for it in wa.inventory(win):
            if it is not box and str(it.get("type") or "") in ("Edit", "ComboBox") \
                    and any(k in str(it.get("name") or "").lower() for k in SEARCH_WORDS):
                cands.append(it)
    except Exception:
        pass
    for c in cands[:3]:
        click(win, c, player, settle=0.4)
        if not focus_is_search():
            try:
                wa.set_value_item(win, int(c.get("i")), "")
            except Exception:
                pass
            continue
        try:
            wa.hotkey("ctrl+a")
            time.sleep(0.03)
            wa.press("delete")
            time.sleep(0.03)
            wa.type_text(text)
        except Exception:
            continue
        live.wait_change(win, timeout=0.8, since=live.revision(win))
        live.quiet(win, 0.15, timeout=0.4)
        if _field_holds(win, text):
            _log(player, "search box holds %r" % text[:24])
            return True
    try:
        wa.set_value_item(win, int(box.get("i")), text)
        live.wait_change(win, timeout=0.6, since=live.revision(win))
        live.quiet(win, 0.12, timeout=0.4)
        if _field_holds(win, text):
            _log(player, "search box holds %r (value pattern)" % text[:24])
            return True
    except Exception:
        pass
    _log(player, "I could not put %r into the search box" % text[:24])
    return False


def open_chat(win, who, player=None):
    """Open the conversation with `who` through the app's own Search."""
    who = str(who or "").strip()
    if not who:
        return False
    if not conv_ok(win, who, ""):
        return True
    _log(player, "opening the chat with %r through the app's own Search" % who[:28])
    for _try in (1, 2):
        items = wa.inventory(win)
        box = find_search(items)
        if box is None:
            _log(player, "this app has no Search box I can use")
            return False
        _type_into(win, box, who, player)
        hit = None
        deadline = time.time() + 4.0
        while time.time() < deadline:
            live.wait_change(win, timeout=0.5, since=live.revision(win))
            live.quiet(win, 0.15, timeout=0.4)
            rows = [it for it in wa.inventory(win)
                    if str(it.get("type") or "") in CONV_ROWS
                    and str(it.get("name") or "").strip()]
            hit = names.best(who, rows, key="name", floor=0.85, margin=0.08)
            if hit is not None:
                break
        if hit is None:
            try:
                rows = [it for it in wa.inventory(win)
                        if str(it.get("type") or "") in CONV_ROWS
                        and str(it.get("name") or "").strip()]
                scored = sorted(((names.score(who, str(it.get("name") or "")), it)
                                 for it in rows), key=lambda t: t[0], reverse=True)[:3]
                _log(player, "closest rows: " + " | ".join(
                    "%.2f %s" % (sc, str(it.get("name") or "")[:24]) for sc, it in scored))
            except Exception:
                pass
            _log(player, "no row on screen is clearly %r - I will not guess" % who[:28])
            continue
        click(win, hit, player, settle=1.5)
        if not conv_ok(win, who, str(hit.get("name") or "")):
            _log(player, "verified: the open chat is %r" % name(win)[:28])
            return True
        _log(player, "the open chat is still %r" % name(win)[:28])
    return not conv_ok(win, who, "")


# ── pick the row that IS the person (appended last: this wins) ───────────────

def _pick_row(who, rows, floor=0.9, margin=0.05):
    """The one row that is `who`, judged on the leading NAME of each row, or None
    when it is not unique - so a channel that merely mentions the name never
    competes with the person."""
    scored = []
    for it in rows:
        nm = str(it.get("name") or "")
        scored.append((names.score(who, names.lead(nm)), it))
    scored.sort(key=lambda t: t[0], reverse=True)
    if not scored or scored[0][0] < floor:
        return None, scored[:3]
    if len(scored) > 1 and scored[1][0] >= floor and \
            scored[0][0] - scored[1][0] < margin:
        return None, scored[:3]
    return scored[0][1], scored[:3]


def open_chat(win, who, player=None):
    """Open the conversation with `who` through the app's own Search."""
    who = str(who or "").strip()
    if not who:
        return False
    if not conv_ok(win, who, ""):
        return True
    _log(player, "opening the chat with %r through the app's own Search" % who[:28])
    for _try in (1, 2):
        items = wa.inventory(win)
        box = find_search(items)
        if box is None:
            _log(player, "this app has no Search box I can use")
            return False
        _type_into(win, box, who, player)
        hit, near = None, []
        deadline = time.time() + 4.0
        while time.time() < deadline:
            live.wait_change(win, timeout=0.5, since=live.revision(win))
            live.quiet(win, 0.15, timeout=0.4)
            rows = [it for it in wa.inventory(win)
                    if str(it.get("type") or "") in CONV_ROWS
                    and str(it.get("name") or "").strip()]
            hit, near = _pick_row(who, rows)
            if hit is not None:
                break
        if hit is None:
            _log(player, "closest: " + " | ".join(
                "%.2f %s" % (sc, str(it.get("name") or "")[:24]) for sc, it in near))
            _log(player, "no row on screen is clearly %r - I will not guess" % who[:28])
            continue
        click(win, hit, player, settle=1.5)
        if not conv_ok(win, who, str(hit.get("name") or "")):
            _log(player, "verified: the open chat is %r" % name(win)[:28])
            return True
        _log(player, "the open chat is still %r" % name(win)[:28])
    return not conv_ok(win, who, "")


# ── type into the search field for real, and prove it by the VALUE ───────────
# The old routine only typed when `focus_is_search()` said the field held the
# focus - and Telegram is a Qt app whose UIA focus report is unreliable, so the
# field was clicked and left untouched: the list never filtered and open_chat
# gave up (slowly). We now click the INNER search field (the smallest
# Search-named Edit, not its container), clear it with the KEYBOARD (Qt ignores
# the UIA value pattern), type for real, and accept success ONLY when a
# search-named field itself shows the text - never the compose box.

def _rect_area(it):
    r = it.get("rect") or (0, 0, 1, 1)
    try:
        return max(0, r[2] - r[0]) * max(0, r[3] - r[1])
    except Exception:
        return 1 << 30


def _search_holds(win, text):
    try:
        for it in wa.inventory(win):
            if str(it.get("type") or "") not in ("Edit", "ComboBox"):
                continue
            nm = str(it.get("name") or "").lower()
            if any(k in nm for k in SEARCH_WORDS) and \
                    str(text).casefold() in str(it.get("value") or "").casefold():
                return True
    except Exception:
        pass
    return False


def _search_fields(win, box=None):
    try:
        fields = [it for it in wa.inventory(win)
                  if str(it.get("type") or "") in ("Edit", "ComboBox")
                  and any(k in str(it.get("name") or "").lower()
                          for k in SEARCH_WORDS)]
    except Exception:
        fields = []
    if not fields and box is not None:
        fields = [box]
    fields.sort(key=_rect_area)      # smallest = the real field, not its container
    return fields[:2]


def _type_into(win, box, text, player=None):
    text = str(text or "")
    for c in _search_fields(win, box):
        for _attempt in (1, 2):
            click(win, c, player, settle=0.3)
            try:
                wa.hotkey("ctrl+a")
                time.sleep(0.03)
                wa.press("delete")
                time.sleep(0.03)
                wa.type_text(text)
            except Exception:
                continue
            live.wait_change(win, timeout=0.7, since=live.revision(win))
            live.quiet(win, 0.10, timeout=0.35)
            if _search_holds(win, text):
                _log(player, "search box holds %r" % text[:24])
                return True
    _log(player, "I could not put %r into the search box" % text[:24])
    return False


# ── SPEED: short pauses, and sample the revision BEFORE acting ───────────────
# Two pure-latency bugs: (1) chat clicks waited up to 2.5s for the whole window
# to "go quiet" even though every step re-reads the tree and verifies itself;
# (2) _type_into sampled live.revision AFTER typing, so the change had already
# happened and wait_change always ran to its full timeout. We cap the settle and
# take the revision before the action.

_settle_old = _settle
_click_old = click

_FAST = 0.35


def _settle(win, before, rev, hard_limit=2.5):
    return _settle_old(win, before, rev, min(hard_limit, _FAST))


def click(win, item, player=None, settle=_FAST):
    return _click_old(win, item, player, settle=min(settle, _FAST))


def _type_into(win, box, text, player=None):
    text = str(text or "")
    for c in _search_fields(win, box):
        for _attempt in (1, 2):
            rev = live.revision(win)          # BEFORE the action
            click(win, c, player, settle=0.25)
            try:
                wa.hotkey("ctrl+a")
                time.sleep(0.03)
                wa.press("delete")
                time.sleep(0.03)
                wa.type_text(text)
            except Exception:
                continue
            live.wait_change(win, timeout=0.5, since=rev)
            if _search_holds(win, text):
                _log(player, "search box holds %r" % text[:24])
                return True
    _log(player, "I could not put %r into the search box" % text[:24])
    return False


# ── SPEED: never walk the same UI tree twice ─────────────────────────────────
# MEASURED: one full UIA walk of Telegram costs ~1s, and a single send walked the
# tree 16 times = 15.3s of ~20s (78%). Most of those walks happen back-to-back
# with nothing changed. So the tree is memoized keyed by the window's change
# counter, and EVERY ACTION DROPS THE CACHE - a read after an action is always
# fresh; only repeated reads are served from memory.

_inv_orig = wa.inventory
_inv_cache = {"key": None, "tree": None, "t": 0.0}
_inv_stats = {"calls": 0, "walks": 0}


def _inv_drop():
    _inv_cache["key"] = _inv_cache["tree"] = None


def _wrap_action(name):
    fn = getattr(wa, name, None)
    if fn is None or getattr(fn, "_inv_wrapped", False):
        return
    def _g(*a, **k):
        _inv_drop()
        return fn(*a, **k)
    _g._inv_wrapped = True
    setattr(wa, name, _g)


def inventory(win, limit=130, max_depth=12, _ttl=0.6):
    _inv_stats["calls"] += 1
    try:
        rev = live.revision(win)
    except Exception:
        rev = None
    key = (win.get("hwnd"), rev, limit, max_depth)
    c = _inv_cache
    now = time.time()
    if c["key"] == key and c["tree"] is not None and (now - c["t"]) <= _ttl:
        return c["tree"]
    tree = _inv_orig(win, limit, max_depth)
    _inv_stats["walks"] += 1
    c["key"], c["tree"], c["t"] = key, tree, now
    return tree


for _n in ("click_item", "type_text", "hotkey", "press", "set_value_item",
           "activate", "scroll"):
    _wrap_action(_n)


# ── the memoized reader must actually be the one callers use ─────────────────
# It was defined in this module but never BOUND onto window_agent, so every
# caller kept hitting the original walk (the stats stayed at walks=0). Bind it.
wa.inventory = inventory


# ── SPEED v2: no tree walks for settle / click ───────────────────────────────
# MEASURED: of 17 reads, 11 came from settling (5) and clicking (3 + 3) - none of
# which needs the tree. A settle now waits on the window's change EVENT (free),
# and a click goes straight to the centre of the rect we ALREADY read instead of
# looking the control up by index (which walked again). Correctness is untouched:
# every caller still VERIFIES afterwards (chat identity, message in the
# conversation), so a missed click can only fail - it can never send wrong.

def _settle(win, before=None, rev=None, hard_limit=2.5):
    try:
        if rev is not None:
            live.wait_change(win, timeout=min(hard_limit, 0.6), since=rev)
    except Exception:
        pass
    time.sleep(min(0.10, hard_limit))
    return True


wa._settle = _settle
try:
    from core import desktop_agent as _da
    _da._settle = _settle
except Exception:
    pass


def click(win, item, player=None, settle=_FAST):
    try:
        idx = int(item.get("i"))
    except Exception:
        return False
    r = item.get("rect") or (0, 0, 0, 0)
    x, y = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
    _raise(win)
    time.sleep(0.03)
    rev = live.revision(win)
    _log(player, "click %r centre (%d,%d) box %dx%d" % (
        str(item.get("name") or "")[:34], x, y,
        max(0, r[2] - r[0]), max(0, r[3] - r[1])))
    try:
        import pyautogui
        pyautogui.PAUSE = 0.02
        pyautogui.click(x, y)
    except Exception as e:
        _log(player, "click failed: %s" % e)
        return False
    _settle(win, None, rev, settle)
    return True


# ── the engine reads its per-app knowledge from the registry, as data ─────────
from core import apps as _apps

SEARCH_WORDS = tuple(dict.fromkeys(tuple(SEARCH_WORDS) + tuple(_apps.SEARCH_HINTS)))
_COMPOSE_WORDS = tuple(dict.fromkeys(tuple(_COMPOSE_WORDS) + tuple(_apps.COMPOSE_HINTS)))
CONV_ROWS = tuple(dict.fromkeys(tuple(CONV_ROWS) + tuple(_apps.ROW_TYPES)))


def conv_ok(win, who, task=""):
    """'' if the OPEN conversation IS `who`, else a reason to refuse.

    Generic across apps: first the window title (Telegram names the chat there),
    and if the title is only the app name (WhatsApp, Discord) then the conversation
    HEADER at the top-right. If neither can prove the recipient we refuse - never
    guess, never send to the wrong chat.
    """
    who = str(who or "").strip()
    if not who:
        return ""
    cur = name(win)
    if cur and names.score(who, cur) >= 0.85:
        return ""
    for cand in _apps.header_names(win):
        if names.score(who, cand) >= 0.85:
            return ""
    if not cur:
        return "no conversation is open (the window is just %r)" % (win.get("name") or "")
    return "the open conversation is %r, not %r" % (cur, who)


# ── the engine reads its per-app knowledge from the registry, as data ─────────
from core import apps as _apps

SEARCH_WORDS = tuple(dict.fromkeys(tuple(SEARCH_WORDS) + tuple(_apps.SEARCH_HINTS)))
_COMPOSE_WORDS = tuple(dict.fromkeys(tuple(_COMPOSE_WORDS) + tuple(_apps.COMPOSE_HINTS)))
CONV_ROWS = tuple(dict.fromkeys(tuple(CONV_ROWS) + tuple(_apps.ROW_TYPES)))


def conv_ok(win, who, task=""):
    """'' if the OPEN conversation IS `who`, else a reason to refuse.

    Generic across apps: first the window title (Telegram names the chat there),
    and if the title is only the app name (WhatsApp, Discord) then the conversation
    HEADER at the top-right. If neither can prove the recipient we refuse - never
    guess, never send to the wrong chat.
    """
    who = str(who or "").strip()
    if not who:
        return ""
    cur = name(win)
    if cur and names.score(who, cur) >= 0.85:
        return ""
    for cand in _apps.header_names(win):
        if names.score(who, cand) >= 0.85:
            return ""
    if not cur:
        return "no conversation is open (the window is just %r)" % (win.get("name") or "")
    return "the open conversation is %r, not %r" % (cur, who)


# ── decorative rows must NEVER be a recipient (appended last: this wins) ─────
# MEASURED: a row literally named "Message" reached the model and was about to be
# treated as a person ("click landed on 'Mahak', not 'Message'"). A control LABEL
# is not a name. Known UI labels are rejected BEFORE returning a recipient, and if
# nothing survives the filter the answer is empty (fail closed) - never a guess.
import re as _re
import unicodedata as _ud

_DECORATIVE_LABELS = {
    "message", "message #", "messages", "search messages", "search message",
    "write a message", "type a message", "new message", "search",
    "پیام", "پیام‌ها", "پیام بنویس", "پیام بنویسید", "جستجوی پیام‌ها", "جستجو",
}


def _clean_label(s) -> str:
    s = str(s or "").split("\n", 1)[0]          # first line only
    s = _ud.normalize("NFKC", s)
    return " ".join(s.split()).strip()          # keeps ZWNJ inside tokens


def _is_decorative(s) -> bool:
    low = _clean_label(s).casefold().replace("…", "...")
    if not low:
        return True
    if low in _DECORATIVE_LABELS:
        return True
    return bool(_re.match(r"^message\s*(#|\d|\.\.\.)?$", low))


_chat_recipient_v1 = recipient


def recipient(task, payloads=(), preset=""):
    who = _chat_recipient_v1(task, payloads, preset=preset)
    if who and _is_decorative(who):
        return ""
    return who
