"""core/apps.py - the small per-app knowledge the engine needs, as DATA.

The send engine is ONE engine. An app is only a handful of facts: where its search
box lives, where the message box lives, how its window names the open
conversation, and which control types its result rows use. Everything else -
reading the UI, matching the name across scripts, refusing the wrong chat, the
confirmation, the proof - is generic and lives in the engine.

Add a new app by adding ONE entry below. An app with NO entry still works: the
generic defaults are the UNION of every hint here, and if the recipient or the
open conversation cannot be PROVEN the engine fails closed.
"""
from __future__ import annotations

DEFAULT_PROFILE = {
    "exe": (),
    "title_separators": (" – ", " — ", " - ", " | ", " · ", " :: "),
    "search_hints": ("search", "find", "جستجو", "جست‌وجو", "بحث", "recipient"),
    "compose_hints": ("write a message", "type a message", "message #", "message",
                      "پیام", "متن"),
    "row_types": ("ListItem", "DataItem", "TreeItem"),
    "is_messenger": True,
}

# one line per app; anything not listed inherits the defaults above
PROFILES = {
    "telegram":  {"exe": ("telegram.exe",)},
    "whatsapp":  {"exe": ("whatsapp.exe",),
                  "compose_hints": ("type a message", "message", "پیام")},
    "signal":    {"exe": ("signal.exe",)},
    "discord":   {"exe": ("discord.exe",),
                  "compose_hints": ("message #", "message")},
    "slack":     {"exe": ("slack.exe",)},
    "messenger": {"exe": ("messenger.exe", "messengerdesktop.exe")},
    "instagram": {"exe": ("instagram.exe",)},
    "skype":     {"exe": ("skype.exe",)},
    "viber":     {"exe": ("viber.exe",)},
    "teams":     {"exe": ("ms-teams.exe", "teams.exe", "msteams.exe",
                          "teamsupdate.exe")},
    "wechat":    {"exe": ("wechat.exe",)},
    "line":      {"exe": ("line.exe",)},
    "element":   {"exe": ("element.exe",)},
    "telegram-tray": {"exe": ("telegramdesktop.exe",)},
}


def _merge(name):
    p = dict(DEFAULT_PROFILE)
    p.update(PROFILES.get(name, {}))
    return p


def profile(win):
    """The profile for a window: matched on the exe basename, else the defaults."""
    try:
        exe = str((win or {}).get("exe") or "").lower().rsplit("\\", 1)[-1]
    except Exception:
        exe = ""
    if exe:
        for k in PROFILES:
            if exe in _merge(k)["exe"]:
                return _merge(k)
    return dict(DEFAULT_PROFILE)


def _union(field):
    out = list(DEFAULT_PROFILE[field])
    for k in PROFILES:
        for v in PROFILES[k].get(field, ()):
            if v not in out:
                out.append(v)
    return tuple(out)


SEARCH_HINTS = _union("search_hints")
COMPOSE_HINTS = _union("compose_hints")
TITLE_SEPARATORS = _union("title_separators")
ROW_TYPES = _union("row_types")

MESSENGER_KEYS = tuple(sorted(set(PROFILES) | {"telegramdesktop",
                                               "messengerdesktop"}))


def is_messenger(win):
    """True only for a KNOWN messenger - never assumed for an unknown app."""
    exe = ""
    try:
        exe = str((win or {}).get("exe") or "").lower()
    except Exception:
        exe = ""
    return any(k in exe for k in MESSENGER_KEYS)


_BAD = ("search", "menu", "minimiz", "maximiz", "close", "back", "more",
        "settings", "attach", "emoji", "gif", "sticker", "record", "voice",
        "call", "video", "info", "pinned", "add", "edit", "filter", "folders",
        "new chat", "جستجو", "منو", "بستن")


def header_names(win, band=0.18, right=0.5):
    """Candidate names for the OPEN conversation, read from the TOP-RIGHT of the
    window (the conversation header) - for apps whose window TITLE is just the app
    name (WhatsApp, Discord) and so cannot confirm the recipient on its own. Only
    the right half is scanned so the LEFT chat list can never be mistaken for the
    open chat."""
    out = []
    try:
        from core import window_agent as wa
        r = win.get("rect") or (0, 0, 0, 0)
        left, top, rgt, bot = r[0], r[1], r[2], r[3]
        w = max(1, rgt - left)
        h = max(1, bot - top)
        ymax = top + band * h
        xmin = left + right * w
        for it in wa.inventory(win):
            nm = str(it.get("name") or "").strip()
            if not nm or len(nm) > 40:
                continue
            rr = it.get("rect") or (0, 0, 0, 0)
            cx, cy = (rr[0] + rr[2]) // 2, (rr[1] + rr[3]) // 2
            if cy > ymax or cx < xmin:
                continue
            low = nm.casefold()
            if any(b in low for b in _BAD):
                continue
            out.append(nm)
    except Exception:
        pass
    return out

# Extend the reject set: never let a control label pass as a conversation name.
_BAD = tuple(_BAD) + (
    "message", "messages", "search messages", "write a message", "type a message",
    "پیام", "پیام‌ها", "جستجوی پیام", "پیام بنویس",
)
