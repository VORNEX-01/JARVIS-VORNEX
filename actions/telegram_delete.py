"""Delete the last message in a Telegram chat, for both sides.

MEASURED (Telegram Desktop 7.2.9): the reading pane is canvas (anonymous
Group, no text) and the right-click context menu is custom-drawn and INVISIBLE
to UIA - after right-click, Desktop(backend='uia').windows() showed only the
Taskbar, the Telegram MainWindow and the terminal. So "click Delete by name" is
impossible; the menu can only be acted on from a screenshot (the existing
Gemini-vision planner in desktop_agent does that).

HONEST VERIFICATION: the LEFT chat-list row is readable and carries the
last-message preview (e.g. "Mahak, Pinned, چی, Received, at 3:44 PM"). A delete
MUST change that preview. If it does not change, we say so and claim nothing.
"""
from __future__ import annotations
import re
import time

from core import desktop_agent as da
from core import window_agent as wa
from actions import ui_click as U

_STATUS = ("Received", "Seen", "Sending", "Sent", "ویرایش", "ارسال")
_TIME = re.compile(r"\bat\s+\d{1,2}:\d{2}\s*(AM|PM)?", re.IGNORECASE)


def _row(win, chat):
    low = str(chat).casefold().strip()
    for it in wa.inventory(win):
        nm = str(it.get("name") or "")
        if nm and nm.split(",", 1)[0].strip().casefold() == low:
            return nm
    return ""


def _preview(row):
    # drop the clock and delivery status so a mere 'Seen'/'at 3:44' change is
    # not mistaken for a deletion; what remains is the message preview itself.
    s = _TIME.sub("", str(row))
    for tok in _STATUS:
        s = s.replace(tok, "")
    return " ".join(s.split())


def delete_last_message(chat="", player=None) -> str:
    chat = str(chat or "").strip()
    if not chat:
        return "Which chat? Tell me the name and I will delete its last message."

    win = da._pick_window("Telegram", tries=6)
    if not win:
        da._launch("Telegram"); time.sleep(8)
        win = da._pick_window("Telegram", tries=6)
    if not win:
        return "I could not find the Telegram window."
    U._force_foreground(win)

    row = _row(win, chat)
    if not row:
        return ("I could not see a chat row named %r, so I did nothing. Open it "
                "once and I will retry." % chat)
    before = _preview(row)
    if not before:
        return "I could not read that chat's preview, so I will not guess."

    # Vision does the clicking (the menu is invisible to UIA).
    da.run_task(
        "In the open Telegram chat with %s, right-click the LAST message, click "
        "the 'Delete' item, then in the confirmation tick 'Delete for both sides' "
        "and click Delete." % chat,
        app="Telegram", player=player)

    # The confirmed action runs on a worker thread, so wait for the preview to
    # ACTUALLY change instead of trusting the planner's own message.
    deadline = time.time() + 30
    while time.time() < deadline:
        time.sleep(0.6)
        after = _preview(_row(win, chat))
        if after and after != before:
            return ("Deleted the last message in %r: the chat preview changed "
                    "from %r to %r." % (chat, before[:60], after[:60]))
    return ("I could not confirm the deletion - the chat preview for %r did not "
            "change. I am not claiming it was deleted." % chat)


def telegram_delete(parameters, player=None, session_memory=None) -> str:
    p = parameters if isinstance(parameters, dict) else {}
    chat = p.get("chat") or p.get("name") or p.get("to") or p.get("recipient") or ""
    return delete_last_message(str(chat), player=player)
