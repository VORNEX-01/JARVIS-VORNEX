"""Delete the last message in a Telegram chat, for both sides.

Measured on Telegram Desktop 7.2.9 (English UI):
  right-click menu:  Reply / Pin / View Sticker Set / ... / Delete / Select
  dialog:            "Do you want to delete this message?"
                     "Also delete for <Name>"     <- the 'both sides' option
                     [Cancel] [Delete]
The label this file used to look for ("Delete for both sides") does not exist in
this version, so the option was never ticked - the delete would have been 'for
me' only. The dialog is now read as it really is, the right chat is opened first,
every step is logged, and nothing is claimed unless the chat-list preview really
changes afterwards.
"""
from __future__ import annotations
import ctypes, re, time
from core import desktop_agent as da, window_agent as wa, screen_eye as E
from actions import ui_click as U

_TIME = re.compile(r"\bat\s+\d{1,2}:\d{2}\s*(AM|PM)?", re.IGNORECASE)
_STATUS = ("Received", "Seen", "Sending", "Sent", "Not seen", "Downloaded", "Not downloaded")

_BOTH_LABELS = ("Also delete for %s", "Also delete for", "Delete for both sides",
                "Delete for everyone", "حذف برای هر دو طرف", "برای %s هم حذف شود",
                "برای همه حذف شود")
_DIALOG_LABELS = ("Do you want to delete this message?", "حذف پیام؟")
_CONFIRM_LABELS = ("Delete", "Delete for everyone", "Delete for both sides",
                   "حذف", "حذف برای همه")


def _click(x, y, right=False):
    u = ctypes.windll.user32
    u.SetCursorPos(int(x), int(y)); time.sleep(0.2)
    if right:
        u.mouse_event(0x0008, 0, 0, 0, 0); u.mouse_event(0x0010, 0, 0, 0, 0)
    else:
        u.mouse_event(0x0002, 0, 0, 0, 0); u.mouse_event(0x0004, 0, 0, 0, 0)


def _row_item(win, name):
    """The chat-list row for `name`: exact first field, else a close name."""
    low = str(name).casefold().strip()
    fuzzy = None
    for it in wa.inventory(win):
        nm = str(it.get("name") or "")
        if not nm or not it.get("rect"):
            continue
        first = nm.split(",", 1)[0].strip()
        if first.casefold() == low:
            return it
        if fuzzy is None:
            try:
                if da._names.score(first, name) >= 0.75:
                    fuzzy = it
            except Exception:
                pass
    return fuzzy


def _row(win, name):
    return str((_row_item(win, name) or {}).get("name") or "")


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
            return pos, lb
    return None, ""


def _both_ticked(pos):
    """Is the 'also delete' checkbox already ticked?

    MEASURED 7.2.9: the box opens TICKED. Clicking it blind UNTICKS it and the
    delete becomes 'for me' only - so read the state, never assume it. A zoomed
    crop around the label goes to the eye; unreadable means 'do not confirm'.
    """
    import json
    x, y = int(pos[0]), int(pos[1])
    bbox = (max(0, x - 320), max(0, y - 45), x + 320, y + 45)
    img = E._grab(bbox)
    data, mime = E._vision_bytes(img, maxw=900)
    q = ('This is a zoomed crop of one checkbox row from a dialog. It is the '
         '"also delete for the other person" option. Is its checkbox ticked? '
         'Reply ONLY JSON {"ticked": true|false}.')
    for _ in range(2):
        try:
            return bool(json.loads(E.ask_image(data, mime, q)).get("ticked"))
        except Exception:
            pass
    return None


def delete_last_message(chat="", player=None) -> str:
    log = []
    win = da._pick_window("Telegram", tries=6)
    if not win:
        da._launch("Telegram"); time.sleep(8); win = da._pick_window("Telegram", tries=6)
    if not win:
        return "I could not find the Telegram window."
    U._force_foreground(win); E.start_auto()

    who = str(chat or da._chat_name(win) or "").strip()
    item = _row_item(win, who) if who else None
    if not item:
        return "I cannot see a chat named %r in the list, so I stopped." % who
    disp = str(item.get("name") or "").split(",", 1)[0].strip() or who

    # the right-click must land in the RIGHT conversation
    if str(da._chat_name(win) or "").casefold().strip() != disp.casefold():
        rr = item["rect"]
        _click((rr[0] + rr[2]) // 2, (rr[1] + rr[3]) // 2)
        time.sleep(1.6)
        now = str(da._chat_name(win) or "")
        log.append("opened %r (title now %r)" % (disp, now))
        if now.casefold().strip() != disp.casefold():
            return ("I could not open the chat with %r (the open chat is %r), so I "
                    "touched nothing." % (disp, now))
    else:
        log.append("chat %r already open" % disp)

    before = _preview(_row(win, who))
    log.append("before %r" % before[:40])

    x, y = _anchor(win)
    _click(x, y, right=True); time.sleep(1.4)
    log.append("right-clicked (%d,%d)" % (x, y))

    menu_pos, menu_lb = _find(("Delete", "حذف"))
    if not menu_pos:
        return ("The menu opened but my eye did not find 'Delete' on it; I stopped. "
                "[%s]" % "; ".join(log))
    _click(*menu_pos); time.sleep(1.3)
    log.append("menu item %r at %s" % (menu_lb, menu_pos))

    # a missed menu click used to surface only at the very end as 'preview
    # unchanged'; prove the dialog is up and re-click the item once if it is not
    both = tuple((t % disp) if "%s" in t else t for t in _BOTH_LABELS)
    gate = (both[0],) + _DIALOG_LABELS
    gate_pos, gate_lb = _find(gate)
    if not gate_pos:
        _click(*menu_pos); time.sleep(1.4)
        log.append("re-clicked the menu item")
        gate_pos, gate_lb = _find(gate)
        if not gate_pos:
            return ("The delete dialog did not open, so I touched nothing. [%s]"
                    % "; ".join(log))

    if gate_lb.startswith("Also delete for"):
        chk_pos, chk_lb = gate_pos, gate_lb          # position already in hand
    else:
        chk_pos, chk_lb = _find(both)
    if chk_pos:
        ticked = _both_ticked(chk_pos)
        if ticked is True:
            log.append("%r is already ticked - not touching it" % chk_lb)
        elif ticked is False:
            _click(*chk_pos); time.sleep(0.5)
            log.append("was unticked; clicked %r at %s" % (chk_lb, chk_pos))
            if _both_ticked(chk_pos) is not True:
                return ("I clicked the 'also delete' box but could not prove it is "
                        "ticked now, so I did not delete anything. [%s]"
                        % "; ".join(log))
        else:
            return ("I could not read whether the 'also delete for the other side' "
                    "box is ticked, so I did not delete anything. [%s]"
                    % "; ".join(log))
    else:
        log.append("no 'also delete' option found (dialog may be a different version)")

    ok_pos, ok_lb = _find(_CONFIRM_LABELS)
    if not ok_pos:
        return ("I could not find the confirm button; nothing was deleted. [%s]"
                % "; ".join(log))
    _click(*ok_pos); time.sleep(0.9)
    log.append("confirm %r at %s" % (ok_lb, ok_pos))

    deadline = time.time() + 25
    while time.time() < deadline:
        time.sleep(0.7)
        after = _preview(_row(win, who))
        if after and after != before:
            return ("Deleted the last message in %r for both sides: preview %r -> %r. "
                    "[%s]" % (disp, before[:50], after[:50], "; ".join(log)))
    return ("I could not confirm the deletion (preview unchanged); I am not claiming "
            "it. [%s]" % "; ".join(log))


def telegram_delete(parameters, player=None, session_memory=None) -> str:
    p = parameters if isinstance(parameters, dict) else {}
    who = p.get("chat") or p.get("receiver") or p.get("name") or ""
    return delete_last_message(str(who), player=player)


def run(parameters, player=None, session_memory=None):
    return telegram_delete(parameters, player=player, session_memory=session_memory)
