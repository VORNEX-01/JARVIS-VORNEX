"""Delete the last message in the open Telegram chat, for both sides.

Telegram's message pane is canvas and its right-click menu is invisible to UIA
(measured), so the menu is found with the EYE (core.screen_eye.find_text) and the
delete is verified by the readable chat-list preview - never by an opened chat or
a dismissed dialog.
"""
from __future__ import annotations
import ctypes, re, time
from core import desktop_agent as da, window_agent as wa, screen_eye as E
from actions import ui_click as U

_TIME = re.compile(r"\bat\s+\d{1,2}:\d{2}\s*(AM|PM)?", re.IGNORECASE)
_STATUS = ("Received", "Seen", "Sending", "Sent", "Not seen", "Downloaded", "Not downloaded")


def _click(x, y, right=False):
    u = ctypes.windll.user32
    u.SetCursorPos(int(x), int(y)); time.sleep(0.2)
    if right:
        u.mouse_event(0x0008, 0, 0, 0, 0); u.mouse_event(0x0010, 0, 0, 0, 0)
    else:
        u.mouse_event(0x0002, 0, 0, 0, 0); u.mouse_event(0x0004, 0, 0, 0, 0)


def _row(win, name):
    low = str(name).casefold().strip()
    for it in wa.inventory(win):
        nm = str(it.get("name") or "")
        if nm and nm.split(",", 1)[0].strip().casefold() == low:
            return nm
    return ""


def _preview(row):
    s = _TIME.sub("", str(row))
    for t in _STATUS:
        s = s.replace(t, "")
    return " ".join(s.split())


def _anchor(win):
    r = win["rect"]; mid = (r[0] + r[2]) // 2
    edits = [it for it in wa.inventory(win)
             if it.get("rect") and str(it.get("type")) == "Edit" and it["rect"][0] > mid]
    if edits:
        cr = max(edits, key=lambda i: i["rect"][1])["rect"]
        return mid + (r[2] - mid) // 2, cr[1] - 55
    return mid + (r[2] - mid) // 2, r[3] - 170


def _find(labels):
    for lb in labels:
        pos = E.find_text(lb)
        if pos:
            return pos
    return None


def delete_last_message(chat="", player=None) -> str:
    win = da._pick_window("Telegram", tries=6)
    if not win:
        da._launch("Telegram"); time.sleep(8); win = da._pick_window("Telegram", tries=6)
    if not win:
        return "I could not find the Telegram window."
    U._force_foreground(win); E.start_auto()

    who = str(chat or da._chat_name(win) or "").strip()
    if not who:
        return "I cannot read which chat is open, so I stopped."
    before = _preview(_row(win, who))

    x, y = _anchor(win)
    _click(x, y, right=True); time.sleep(1.3)

    pos = _find(("Delete", "حذف"))
    if not pos:
        return "The menu opened but my eye did not find 'Delete' on it; I stopped."
    _click(*pos); time.sleep(1.0)

    chk = _find(("Delete for both sides", "Delete for everyone", "حذف برای هر دو طرف"))
    if chk:
        _click(*chk); time.sleep(0.4)

    pos = _find(("Delete", "حذف"))
    if not pos:
        return "I could not find the confirm button; nothing was deleted."
    _click(*pos)

    deadline = time.time() + 25
    while time.time() < deadline:
        time.sleep(0.6)
        after = _preview(_row(win, who))
        if after and after != before:
            return ("Deleted the last message in %r: preview %r -> %r."
                    % (who, before[:50], after[:50]))
    return "I could not confirm the deletion (preview unchanged); I am not claiming it."


def telegram_delete(parameters, player=None, session_memory=None) -> str:
    p = parameters if isinstance(parameters, dict) else {}
    return delete_last_message(str(p.get("chat") or p.get("name") or ""), player=player)


def run(parameters, player=None, session_memory=None):
    return telegram_delete(parameters, player=player, session_memory=session_memory)
