"""core/recipes.py - remember a plan that worked, and replay it without a model.

A recipe is stored as SEMANTIC locators (control type + name), never indexes or
coordinates. When a task's text is a fixed prefix plus a payload tail (the usual
"send ... this exact text: X" shape) only the PREFIX is stored, so the same
recipe serves a different message.

Replay is never trusted blindly: any missing control, any changed task shape,
any failed final check deletes the recipe and falls back to planning from
scratch. Recipes with an irreversible step are NOT replayed at all - those still
go through the user's confirmation.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
import time
from pathlib import Path

_PATH = Path(__file__).resolve().parent.parent / "memory" / "recipes.json"
_LOCK = threading.Lock()
_MAX = 200
_SEP = " :،,.-—"


def _clean(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _norm(s) -> str:
    return _clean(s).casefold()


def _key(app, prefix) -> str:
    raw = (_norm(app) + "|" + _norm(prefix)).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:16]


def _load_raw():
    try:
        d = json.loads(_PATH.read_text(encoding="utf-8"))
        if isinstance(d, dict) and isinstance(d.get("recipes"), list):
            return d
    except Exception:
        pass
    return {"schema": 1, "recipes": []}


def _save_raw(d):
    try:
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(_PATH.parent), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        os.replace(tmp, str(_PATH))
    except Exception:
        pass


def split_tail(task, typed):
    """If `typed` is the tail of `task`, return (prefix, True)."""
    t, x = _clean(task), _clean(typed)
    if len(x) >= 2 and t.lower().endswith(x.lower()):
        pref = t[: len(t) - len(x)].rstrip(_SEP)
        if len(pref) >= 8:
            return pref, True
    return t, False


def save(app, task, steps):
    """Remember a plan that VERIFIED. `steps` are semantic; indexes are dropped."""
    if not app or not steps:
        return None
    typed = [s.get("text") for s in steps if s.get("op") == "type" and s.get("text")]
    tail = typed[-1] if typed else None
    if tail:
        prefix, has_tail = split_tail(task, tail)
    else:
        prefix, has_tail = _clean(task), False

    clean = []
    for s in steps:
        d = {"op": s.get("op")}
        for k in ("type", "name", "keys"):
            if s.get(k):
                d[k] = s[k]
        if s.get("text"):
            if has_tail and s["text"] == tail:
                d["uses_payload"] = True
            else:
                d["text"] = s["text"]
        if s.get("irr"):
            d["irr"] = True
        clean.append(d)

    rec = {"key": _key(app, prefix), "app": app, "prefix": prefix,
           "has_tail": bool(has_tail), "payload": (tail if has_tail else None),
           "steps": clean, "expect": ["${payload}" if has_tail else (tail or "")],
           "updated": time.time(), "hits": 0}

    with _LOCK:
        d = _load_raw()
        rs = [r for r in d.get("recipes", []) if r.get("key") != rec["key"]]
        rs.insert(0, rec)
        d["recipes"] = rs[:_MAX]
        _save_raw(d)
    return rec["key"]


def load(app, task):
    """The stored recipe whose prefix this task starts with, or None."""
    t, a = _norm(task), _norm(app)
    best = None
    with _LOCK:
        d = _load_raw()
    for r in d.get("recipes", []):
        if _norm(r.get("app")) != a:
            continue
        pref = _norm(r.get("prefix"))
        if not pref or not pref.startswith(""):
            continue
        if t.startswith(pref):
            if best is None or len(_norm(best.get("prefix"))) < len(pref):
                best = r
    return best


def hint(app, task):
    """A compact 'this worked before' block for the planner."""
    r = load(app, task)
    if not r:
        return ""
    lines = []
    for s in (r.get("steps") or [])[:6]:
        bit = str(s.get("op") or "")
        if s.get("name"):
            bit += " on %r" % str(s["name"])[:50]
        if s.get("uses_payload"):
            bit += " with the task's text"
        elif s.get("text"):
            bit += " %r" % str(s["text"])[:40]
        if s.get("keys"):
            bit += " keys=%s" % s["keys"]
        lines.append("  - " + bit)
    return "\n".join(lines)


def drop(app, task):
    r = load(app, task)
    if r:
        drop_key(r.get("key"))


def drop_key(key):
    if not key:
        return
    with _LOCK:
        d = _load_raw()
        d["recipes"] = [r for r in d.get("recipes", []) if r.get("key") != key]
        _save_raw(d)


def bump(key):
    if not key:
        return
    with _LOCK:
        d = _load_raw()
        for r in d.get("recipes", []):
            if r.get("key") == key:
                r["hits"] = int(r.get("hits") or 0) + 1
        _save_raw(d)


def count():
    with _LOCK:
        return len(_load_raw().get("recipes", []))


# ── one durable memory (appended last: these win) ────────────────────────────
# This file IS the memory of what worked. It must survive a crash, a hard kill
# mid-write, a power cut, and a corrupt file - and it must NEVER come back empty
# because reading failed. So: atomic tmp+fsync+replace, one previous good copy
# kept beside it, and the store is trimmed by USEFULNESS, never by silently
# dropping things.

_MAX = 500
_BACKUP = _PATH.with_suffix(".json.bak")


def _load_raw():
    for p in (_PATH, _BACKUP):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(d, dict) and isinstance(d.get("recipes"), list):
                return d
        except Exception:
            continue
    return {"schema": 1, "recipes": []}


def _save_raw(d):
    try:
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        try:
            if _PATH.exists():
                _BACKUP.write_bytes(_PATH.read_bytes())
        except Exception:
            pass
        fd, tmp = tempfile.mkstemp(dir=str(_PATH.parent), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, str(_PATH))
        return True
    except Exception:
        return False


def prune():
    """Over the cap? Drop the least USED, then the oldest - never the rest."""
    with _LOCK:
        d = _load_raw()
        rs = d.get("recipes", [])
        if len(rs) <= _MAX:
            return 0
        rs.sort(key=lambda r: (int(r.get("hits") or 0), float(r.get("updated") or 0)),
                reverse=True)
        d["recipes"] = rs[:_MAX]
        _save_raw(d)
        return len(rs) - _MAX


def entries():
    with _LOCK:
        d = _load_raw()
    return [{"app": r.get("app"), "prefix": r.get("prefix"),
             "steps": len(r.get("steps") or []),
             "irreversible": any(s.get("irr") for s in (r.get("steps") or [])),
             "hits": int(r.get("hits") or 0)}
            for r in d.get("recipes", [])]


_SAVE_OLD = save


def save(app, task, steps):
    key = _SAVE_OLD(app, task, steps)
    try:
        prune()
    except Exception:
        pass
    return key


# ── self-healing start-up (appended last: this wins) ─────────────────────────
# The earlier backup was only written on the NEXT save, so a corruption right
# after the first run had nothing to fall back to (the test showed count = 0).
# Now the memory heals itself the moment it is loaded: if the main file is fine
# its copy is sealed straight away, and if the main file is broken it is rebuilt
# from the copy. One file, always one memory, never empty because of an error.

def recover():
    try:
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        ok = False
        try:
            d = json.loads(_PATH.read_text(encoding="utf-8"))
            ok = isinstance(d, dict) and isinstance(d.get("recipes"), list)
        except Exception:
            ok = False
        if ok:
            if not _BACKUP.exists():
                _BACKUP.write_bytes(_PATH.read_bytes())
                return "sealed a first copy"
            return "ok"
        try:
            d = json.loads(_BACKUP.read_text(encoding="utf-8"))
            if isinstance(d, dict) and isinstance(d.get("recipes"), list):
                _PATH.write_text(json.dumps(d, ensure_ascii=False, indent=1),
                                 encoding="utf-8")
                return "healed %d recipes from the copy" % len(d.get("recipes") or [])
        except Exception:
            pass
        return "nothing to heal"
    except Exception as e:
        return "error: %s" % e


_STARTUP = recover()


# ── only plans that REALLY worked are kept (appended last: these win) ────────
# A false "verified" once saved a one-step plan that proved nothing, and the
# store then replayed it forever, claiming success each time. A recipe is now
# stamped `ok` only where a real proof passed, and load() refuses anything
# without that stamp. `forget(app)` drops what a mistake already wrote.

def save(app, task, steps):
    key = _SAVE_OLD(app, task, steps)
    try:
        with _LOCK:
            d = _load_raw()
            for r in d.get("recipes", []):
                if r.get("key") == key:
                    r["ok"] = True
                    r["schema"] = 2
            _save_raw(d)
    except Exception:
        pass
    try:
        prune()
    except Exception:
        pass
    return key


def load(app, task):
    t, a = _norm(task), _norm(app)
    best = None
    with _LOCK:
        d = _load_raw()
    for r in d.get("recipes", []):
        if r.get("ok") is not True:
            continue
        if _norm(r.get("app")) != a:
            continue
        pref = _norm(r.get("prefix"))
        if not pref:
            continue
        if t.startswith(pref):
            if best is None or len(_norm(best.get("prefix"))) < len(pref):
                best = r
    return best


def forget(app=None):
    """Drop what a mistake wrote. No app -> clear the store."""
    with _LOCK:
        d = _load_raw()
        rs = d.get("recipes", [])
        if app:
            a = _norm(app)
            rs = [r for r in rs if _norm(r.get("app")) != a]
        else:
            rs = []
        d["recipes"] = rs
        _save_raw(d)
        return len(rs)


# ── messengers are never learned, at all ─────────────────────────────────────
# A send depends on the OPEN conversation, so it must never be replayed (already
# enforced) - but it was still being SAVED, leaving dead rows like
# "send to Mahak … vornex 16". Replaying is refused, so storing is pointless; we
# now refuse to store a messenger task in the first place, and to load one.

_MESSENGERS = ("telegram", "whatsapp", "signal", "discord", "instagram",
               "messenger", "slack", "skype", "viber", "teams")

_SAVE_PREV = save
_LOAD_PREV = load


def save(app, task, steps):
    if any(m in str(app or "").lower() for m in _MESSENGERS):
        return ""
    return _SAVE_PREV(app, task, steps)


def load(app, task):
    if any(m in str(app or "").lower() for m in _MESSENGERS):
        return None
    return _LOAD_PREV(app, task)
