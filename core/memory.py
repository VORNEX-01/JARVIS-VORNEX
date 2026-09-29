"""Persistent memory across restarts - the assistant's long-term store.

Facts and notes live in .jarvis/memory.json (atomic writes). recall() returns
only what is ACTUALLY on disk - so "I remember" can never be a bluff.
"""
from __future__ import annotations
import json, os, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / ".jarvis" / "memory.json"


def _load():
    try:
        data = json.loads(STORE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("facts", {}); data.setdefault("notes", [])
            return data
    except Exception:
        pass
    return {"facts": {}, "notes": []}


def _save(data):
    STORE.parent.mkdir(exist_ok=True)
    tmp = STORE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, STORE)


def remember(text="", key=None, value=None, tags=None):
    data = _load()
    if key:
        data["facts"][str(key)] = str(value if value is not None else text)
        _save(data)
        return "Remembered %s = %s" % (key, data["facts"][str(key)])
    note = {"text": str(text).strip(), "tags": [t for t in (tags or []) if t],
            "at": time.strftime("%Y-%m-%d %H:%M")}
    if not note["text"]:
        return "Nothing to remember."
    data["notes"].append(note); _save(data)
    return "Remembered: %s" % note["text"][:80]


def recall(query="", limit=5):
    data = _load()
    q = str(query or "").casefold().strip()
    hits = []
    for k, v in data["facts"].items():
        if not q or q in k.casefold() or q in str(v).casefold():
            hits.append("%s = %s" % (k, v))
    for n in data["notes"]:
        if not q or q in n["text"].casefold() or any(q in t.casefold() for t in n.get("tags", [])):
            hits.append(n["text"])
    return "\n".join(hits[:limit]) if hits else "I have nothing stored about that."


def all_():
    data = _load()
    out = ["Facts:"] + ["  %s = %s" % (k, v) for k, v in data["facts"].items()]
    out += ["Notes:"] + ["  - %s" % n["text"] for n in data["notes"]]
    return "\n".join(out)


def forget(key_or_text=""):
    data = _load(); k = str(key_or_text)
    if k in data["facts"]:
        del data["facts"][k]; _save(data)
        return "Forgotten fact: %s" % k
    before = len(data["notes"])
    data["notes"] = [n for n in data["notes"] if k.casefold() not in n["text"].casefold()]
    if len(data["notes"]) != before:
        _save(data); return "Forgotten %d note(s)." % (before - len(data["notes"]))
    return "Nothing matched %r." % k
