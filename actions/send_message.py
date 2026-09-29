"""
send_message — messaging that asks first, and then actually checks.

WHY THIS FILE LOOKS LIKE THIS
    The old version pressed Ctrl+F, typed the contact name, pressed Enter,
    pasted the message, pressed Enter and returned "Message sent to X." Three
    separate faults in that: Ctrl+F is the search INSIDE the open chat (Telegram
    has no contact-search shortcut), so the name went into the wrong field; the
    success string was hard-coded, so the function said "sent" whatever had
    happened; and nothing verified anything, so the assistant confidently told
    the user a message had gone that never went.

    This version: finds the search box by LOOKING at the screen, checks the name
    actually landed in it, verifies the contact really exists before typing
    anything, verifies the right chat is open, holds the message as a draft,
    asks the person to confirm on the HUD, and only then presses send — after
    which it looks again and says what it can actually see.

VERDICTS
    SENT      recipient verified, outgoing message visible, compose box empty
    NOT_SENT  the draft is still there, or the send was refused
    UNCLEAR   the screen could not be read — it says so instead of guessing

    A screenshot is in PHYSICAL pixels and the mouse is in LOGICAL pixels. On a
    scaled Windows display those differ, and mixing them is how a click aimed at
    the search box landed on the profile picture.
"""
import io
import json
import os
import re
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE    = 0.06
    _PYAUTOGUI = True
except Exception:
    _PYAUTOGUI = False

try:
    import pyperclip
    _PYPERCLIP = True
except Exception:
    _PYPERCLIP = False


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _get_os() -> str:
    try:
        cfg = json.loads(
            (_base_dir() / "config" / "api_keys.json").read_text(encoding="utf-8"))
        return str(cfg.get("os_system") or "windows").lower()
    except Exception:
        return "windows"


def _require_pyautogui():
    if not _PYAUTOGUI:
        raise RuntimeError("PyAutoGUI not installed. Run: pip install pyautogui")


def _log(player, msg: str) -> None:
    print(f"[SendMessage] {msg}")
    try:
        if player is not None:
            player.write_log(f"[msg] {msg}")
    except Exception:
        pass


# ── debug trail: SM_DEBUG=1 saves every screenshot it looked at ──────────────
_DEBUG     = os.environ.get("SM_DEBUG", "").strip() not in ("", "0", "false", "False")
_DEBUG_DIR = _base_dir() / "tools" / "_shots"
_LAST_SHOT = (0, 0)


# ── keyboard / clipboard ────────────────────────────────────────────────────
def _paste_text(text: str) -> None:
    """Clipboard paste, not typewrite: typewrite cannot produce Persian."""
    _require_pyautogui()
    if _PYPERCLIP:
        pyperclip.copy(text)
        time.sleep(0.15)
        pyautogui.hotkey(*("command", "v") if _get_os() == "mac" else ("ctrl", "v"))
        time.sleep(0.10)
    else:
        pyautogui.write(text, interval=0.03)


def _clear_here() -> None:
    _require_pyautogui()
    pyautogui.hotkey(*("command", "a") if _get_os() == "mac" else ("ctrl", "a"))
    time.sleep(0.10)
    pyautogui.press("delete")
    time.sleep(0.10)


def _foreground_title() -> str:
    if sys.platform != "win32":
        return ""
    try:
        import ctypes
        u = ctypes.windll.user32
        h = u.GetForegroundWindow()
        n = u.GetWindowTextLengthW(h)
        b = ctypes.create_unicode_buffer(n + 1)
        u.GetWindowTextW(h, b, n + 1)
        return b.value
    except Exception:
        return ""


# ── opening the app ─────────────────────────────────────────────────────────
def _open_app(app_name: str) -> bool:
    _require_pyautogui()
    os_name = _get_os()
    try:
        if os_name == "windows":
            pyautogui.press("win")
            time.sleep(0.5)
            _paste_text(app_name)
            time.sleep(0.7)
            pyautogui.press("enter")
            time.sleep(2.5)
            return True
        if os_name == "mac":
            r = subprocess.run(["open", "-a", app_name], capture_output=True, text=True, timeout=10)
            if r.returncode != 0:
                r = subprocess.run(["open", "-a", f"{app_name}.app"], capture_output=True,
                                   text=True, timeout=10)
            time.sleep(2.5)
            return r.returncode == 0
        try:
            subprocess.Popen([app_name.lower()], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
            time.sleep(2.5)
            return True
        except FileNotFoundError:
            return False
    except Exception as e:
        print(f"[SendMessage] could not open {app_name}: {e}")
        return False


def _open_browser_url(url: str) -> bool:
    try:
        webbrowser.open(url)
        time.sleep(4.0)
        return True
    except Exception as e:
        print(f"[SendMessage] could not open browser: {e}")
        return False


# ── looking at the screen ───────────────────────────────────────────────────
_JSON_ONLY = ('\nReply with ONLY a JSON object, no prose and no markdown. '
              'Use exactly the keys asked for; when you cannot tell, use the '
              'string "unclear" rather than guessing.')


def _png() -> bytes:
    global _LAST_SHOT
    img = pyautogui.screenshot()
    _LAST_SHOT = img.size
    if _DEBUG:
        try:
            _DEBUG_DIR.mkdir(parents=True, exist_ok=True)
            name = time.strftime("%H%M%S") + f"_{int(time.time() * 1000) % 1000:03d}.png"
            img.save(str(_DEBUG_DIR / name))
            print(f"[SendMessage][dbg] shot {img.size} -> {name}")
        except Exception:
            pass
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _to_logical(x, y, pw, ph):
    """Screenshot pixels are PHYSICAL; the mouse uses LOGICAL. On a scaled
    Windows display these differ, and mixing them is exactly how a click aimed
    at the search box landed on the profile picture."""
    try:
        lw, lh = pyautogui.size()
        if pw and ph:
            return int(round(x * lw / pw)), int(round(y * lh / ph))
    except Exception:
        pass
    return x, y


def _contents(prompt: str, png):
    if png is None:
        return prompt
    from google.genai import types as gtypes
    return [gtypes.Part.from_bytes(data=png, mime_type="image/png"), prompt]


def _look(prompt: str, png=None, tier=None) -> str:
    try:
        from core import gemini
        out = gemini.text(_contents(prompt, png),
                          tier=tier or gemini.SMART, timeout_ms=25_000) or ""
        if _DEBUG:
            print(f"[SendMessage][dbg] look -> {out[:200]!r}")
        return out
    except Exception as e:
        print(f"[SendMessage] vision failed: {e}")
        return ""


def _ask(prompt: str, png=None, tier=None) -> dict:
    try:
        from core import gemini
        data = gemini.as_json(_contents(prompt + _JSON_ONLY, png),
                              tier=tier or gemini.SMART, timeout_ms=25_000, default=None)
        if _DEBUG:
            print(f"[SendMessage][dbg] ask  -> {data!r}")
        return data if isinstance(data, dict) else {}
    except Exception as e:
        print(f"[SendMessage] vision/json failed: {e}")
        return {}


def _find(desc: str):
    """Where is this on screen right now? Returns LOGICAL (x, y) or None.
    None means 'I cannot see it' — and we never guess a coordinate."""
    try:
        data = _png()
        pw, ph = _LAST_SHOT
        txt = _look(
            f"This is a screenshot of the whole screen, {pw} pixels wide and {ph} "
            f"pixels tall. Find the UI element described as: '{desc}'. "
            f"Reply with ONLY its centre coordinates as: x,y  "
            f"If it is not visible, reply: NOT_FOUND", data)
        if not txt or "NOT_FOUND" in txt.upper():
            return None
        m = re.search(r"(\d+)\s*,\s*(\d+)", txt)
        if m:
            lx, ly = _to_logical(int(m.group(1)), int(m.group(2)), pw, ph)
            lw, lh = pyautogui.size()
            if _DEBUG:
                print(f"[SendMessage][dbg] find({desc[:38]!r}) "
                      f"raw=({m.group(1)},{m.group(2)}) shot={pw}x{ph} "
                      f"-> logical=({lx},{ly}) screen={lw}x{lh}")
            if 0 <= lx <= lw and 0 <= ly <= lh:
                return lx, ly
    except Exception as e:
        print(f"[SendMessage] element lookup failed: {e}")
    return None


def _truthy(value):
    """True / False / None(=unclear). Reads a JSON bool, or the words a model
    may use instead."""
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    s = str(value).strip().lower()
    if s in ("true", "yes", "y", "1"):
        return True
    if s in ("false", "no", "n", "0", "none", "no_match", "not_found"):
        return False
    return None


# ── platforms ───────────────────────────────────────────────────────────────
_DESKTOP_SEARCH_HINTS = (
    "the search field for chats and contacts at the very top of the left-hand "
    "column (this is NOT the search inside an open conversation)",
    "the search box at the top of the chat list",
)
_WEB_SEARCH_HINTS = (
    "the search input used for choosing a message recipient",
    "the search box on this page",
)

_PLATFORMS = {
    "telegram":  {"app": "Telegram",  "kind": "desktop"},
    "whatsapp":  {"app": "WhatsApp",  "kind": "desktop"},
    "signal":    {"app": "Signal",    "kind": "desktop"},
    "discord":   {"app": "Discord",   "kind": "desktop"},
    "instagram": {"app": "Instagram", "kind": "web",
                  "url": "https://www.instagram.com/direct/new/"},
    "messenger": {"app": "Messenger", "kind": "web",
                  "url": "https://www.messenger.com/"},
}


def _platform_for(name: str) -> dict:
    key = (name or "").lower().strip()
    for k, spec in _PLATFORMS.items():
        if k in key:
            return dict(spec)
    if any(a in key for a in ("ig", "insta")):
        return dict(_PLATFORMS["instagram"])
    if any(a in key for a in ("fb", "facebook")):
        return dict(_PLATFORMS["messenger"])
    return {"app": (name or "App").strip().title(), "kind": "desktop"}


# ── the search field: click it, fill it, and CHECK that it landed ────────────
def _type_in_search(app: str, hints, receiver: str, player):
    """Returns (True, "") or (False, reason).

    Deliberately does NOT clear the field on the first attempt — if the click
    missed and landed somewhere else, Ctrl+A + Delete there could do damage. It
    pastes, then asks the screen whether the name is in the box; only if that
    fails does it press Escape and clear before the second try."""
    last = "the search box could not be found"
    for attempt in (1, 2):
        box = None
        for hint in hints:
            box = _find(hint)
            if box:
                break
        if not box:
            last = f"I could not find {app}'s search box on screen"
            continue

        if _DEBUG:
            print(f"[SendMessage][dbg] attempt {attempt}: clicking {box}")
        pyautogui.click(*box)
        time.sleep(0.5)

        if attempt > 1:
            _clear_here()

        _paste_text(receiver)
        time.sleep(1.7)

        chk = _ask(
            f"Look at the search box / search field in this screenshot of {app}. "
            f"Does it contain exactly the text \"{receiver}\" typed into it "
            f"(and nothing else)? "
            f'Return {{"text_in_search": true|false|"unclear", '
            f'"search_text": "the text you can actually read in it", '
            f'"on_right_screen": true|false|"unclear"}}.')
        if _truthy(chk.get("text_in_search")) is True:
            _log(player, f"'{receiver}' is now in {app}'s search box")
            return True, ""

        last = (f"the name did not end up in {app}'s search box "
                f"(I could read: {chk.get('search_text') or 'nothing'})")
        if _DEBUG:
            print(f"[SendMessage][dbg] attempt {attempt} failed: {last}")
        pyautogui.press("escape")
        time.sleep(0.4)

    return False, (f"I tried twice to put '{receiver}' into {app}'s search box, but "
                   f"{last} — so I typed nothing else and sent nothing.")


# ── phase 1: get to a verified, unsent draft ────────────────────────────────
def _prepare(spec: dict, receiver: str, message: str, player) -> dict:
    app  = spec["app"]
    kind = spec["kind"]

    def fail(reason: str) -> dict:
        return {"ok": False, "reason": reason}

    if kind == "desktop":
        if not _open_app(app):
            return fail(f"I couldn't open {app}, so nothing was typed and nothing was sent.")
    else:
        if not _open_browser_url(spec.get("url", "about:blank")):
            return fail(f"I couldn't open {app} in the browser, so nothing was sent.")

    hints = _DESKTOP_SEARCH_HINTS if kind == "desktop" else _WEB_SEARCH_HINTS
    typed, why = _type_in_search(app, hints, receiver, player)
    if not typed:
        return fail(why)

    found = _ask(
        f"This is a screenshot of {app}. Someone typed '{receiver}' into the search "
        f"box to find a chat or contact. Is there a search result, list entry or "
        f"contact whose name matches '{receiver}'? "
        f'Return {{"match": true|false|"unclear", "what_i_saw": "one short line"}}.')
    match = _truthy(found.get("match"))
    if match is None:
        pyautogui.press("escape")
        return fail(f"I could not read {app}'s search results clearly, so I stopped "
                    f"without typing the message and without sending anything.")
    if match is False:
        pyautogui.press("escape")
        _clear_here()
        return fail(f"I searched {app} for '{receiver}' and no matching contact came up. "
                    f"I typed nothing else and sent nothing.")

    hit = _find(f"the search result for the contact named '{receiver}' in the results list")
    if hit:
        pyautogui.click(*hit)
    else:
        pyautogui.press("enter")
    time.sleep(1.4)

    hdr = _ask(
        f"Look at the conversation header at the top of the chat pane. Is the open "
        f"conversation with '{receiver}'? "
        f'Return {{"recipient_match": true|false|"unclear", '
        f'"header_text": "the text you can read"}}.')
    if _truthy(hdr.get("recipient_match")) is not True:
        return fail(f"I could not confirm that the chat in front is really {receiver} "
                    f"(header reads: {hdr.get('header_text') or 'unreadable'}), "
                    f"so I sent nothing.")

    cbox = _find("the message input box at the bottom of the conversation, "
                 "where you type a reply")
    if not cbox:
        return fail("I opened the chat but could not find the message box, so nothing was sent.")
    pyautogui.click(*cbox)
    time.sleep(0.4)
    _paste_text(message)
    time.sleep(0.5)

    draft = _ask(
        f"Is the exact text \"{message}\" sitting in the message input box as an "
        f"UNSENT draft (not yet sent, no bubble in the conversation yet)? "
        f'Return {{"draft_match": true|false|"unclear", '
        f'"composer_empty": true|false|"unclear"}}.')
    if _truthy(draft.get("draft_match")) is not True:
        return fail("I typed the message but could not confirm it landed in the message "
                    "box, so I did not send it.")

    _log(player, f"draft ready for {receiver} — waiting for your confirmation")
    return {"ok": True, "app": app, "receiver": receiver, "message": message}


# ── phase 2: the confirmed send, then the check ─────────────────────────────
def _send_and_verify(state: dict) -> str:
    app      = state["app"]
    receiver = state["receiver"]
    message  = state["message"]

    before = _ask(
        f"Is the exact text \"{message}\" still in the message input box, unsent, and "
        f"is the open chat still the one with '{receiver}'? "
        f'Return {{"draft_match": true|false|"unclear"}}.', _png())
    if _truthy(before.get("draft_match")) is False:
        return (f"I did not send: the message box no longer holds the draft — the screen "
                f"changed since I set it up. Nothing was sent.")

    pyautogui.press("enter")
    time.sleep(1.7)

    after = _ask(
        f"Look at this {app} screenshot. Was the message \"{message}\" just sent to "
        f"'{receiver}'? An outgoing message bubble containing that text should now be "
        f"visible in the conversation, and the message input box should be EMPTY. "
        f'Return {{"outgoing_message_match": true|false|"unclear", '
        f'"composer_empty": true|false|"unclear", "what_i_saw": "one short line"}}.', _png())

    visible = _truthy(after.get("outgoing_message_match"))
    empty   = _truthy(after.get("composer_empty"))

    if visible is True and empty is True:
        return (f"Sent — I checked the screen: “{message[:60]}” is now in the conversation "
                f"with {receiver} and the message box is empty.")
    if visible is False or empty is False:
        return (f"I pressed send but the message is still sitting in the box — it did not go. "
                f"Nothing was sent to {receiver}.")
    return (f"I pressed send but I could not tell from the screen whether it went through. "
            f"Please check the chat with {receiver} yourself.")


def _confirm_and_send(state: dict) -> str:
    try:
        from core import confirm as confirm_gate
    except Exception:
        confirm_gate = None

    if confirm_gate is None:
        return ("I need your confirmation before sending, but the confirmation box is not "
                "available — so I have not sent anything.")

    if confirm_gate.pending_title():
        return ("There is already a confirmation on screen — please answer that one first, "
                "then ask me again.")

    return confirm_gate.request(
        key=f"send_message:{state['app']}",
        title=f"Send to {state['receiver']}?",
        detail=f"{state['app']}: “{state['message'][:140]}”"[:300],
        run=lambda: _send_and_verify(state),
    )


# ── the action ──────────────────────────────────────────────────────────────
# ── ONE PATH (appended last: this TOOL and handler win) ──────────────────────
# This file carried its own search/verify logic, which diverged from
# core/desktop_agent and kept producing NEW bugs ("no matching contact", "the
# message box no longer holds the draft"). UI work must have exactly ONE
# executor, so sending now goes through desktop_agent - the path that
# re-observes after every step and verifies from the app's own content.

from core import desktop_agent as _da


def send_message(parameters: dict, response=None, player=None, **kwargs) -> str:
    p = parameters or {}
    receiver = str(p.get("receiver") or "").strip()
    message = str(p.get("message_text") or p.get("message") or "").strip()
    platform = str(p.get("platform") or "Telegram").strip()
    if not receiver:
        return "Please specify a recipient."
    if not message:
        return "Please specify the message content."
    return _da.run_task("send this exact text to %s: %s" % (receiver, message),
                        app=platform, player=player)


TOOL = {
    "name": "send_message",
    "description": (
        "Sends a text message in WhatsApp, Telegram, Signal, Discord, Instagram or "
        "Messenger. It looks at the app's real controls, opens the right chat, types "
        "the message, asks the user to confirm on the HUD before pressing send, and "
        "verifies from the app itself whether it really went. Its return text is the "
        "truth."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "receiver":     {"type": "STRING", "description": "Recipient name"},
            "message_text": {"type": "STRING", "description": "The message to send"},
            "platform":     {"type": "STRING", "description": "Telegram / WhatsApp / Signal / Discord / Instagram / Messenger"},
        },
        "required": ["receiver", "message_text", "platform"],
    },
    "handler": send_message,
}
