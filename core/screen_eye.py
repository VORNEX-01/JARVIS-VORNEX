"""A live eye on the screen. Always-on LOCAL capture (mss), Gemini vision only
on demand. Keys come from the project's own config/api_keys.json (core.gemini),
so the assistant's rotation is used - not env vars."""
from __future__ import annotations
import io, os, re, threading, time
from typing import Optional

_MODEL = os.environ.get("VORNEX_VISION_MODEL", "gemini-3.5-flash")
_lock = threading.Lock()
_last = {"png": None, "w": 0, "h": 0, "t": 0.0}
_thread = None
_stop = threading.Event()


def snapshot(bbox=None):
    import mss
    from PIL import Image
    with mss.mss() as sct:
        mon = ({"left": bbox[0], "top": bbox[1], "width": bbox[2]-bbox[0],
                "height": bbox[3]-bbox[1]} if bbox else sct.monitors[1])
        shot = sct.grab(mon)
    img = Image.frombytes("RGB", shot.size, shot.rgb)
    buf = io.BytesIO(); img.save(buf, format="PNG")
    with _lock:
        _last.update(png=buf.getvalue(), w=img.size[0], h=img.size[1], t=time.time())
    return buf.getvalue(), img.size[0], img.size[1]


def latest():
    with _lock:
        return _last["png"], _last["w"], _last["h"]


def _loop(interval=1.0):
    while not _stop.is_set():
        try: snapshot()
        except Exception: pass
        _stop.wait(interval)


def start(interval=1.0):
    global _thread
    if _thread and _thread.is_alive(): return
    _stop.clear()
    _thread = threading.Thread(target=_loop, args=(interval,), daemon=True)
    _thread.start()


def stop():
    _stop.set()


def _first_key():
    """Same source the assistant itself uses: config/api_keys.json via core.gemini."""
    try:
        from core import gemini as G
        k = G.api_key()
        if k:
            return k
    except Exception:
        pass
    for k, v in os.environ.items():
        if ("GEMINI" in k.upper() or "GOOGLE" in k.upper()) and len(str(v)) > 20:
            return str(v)
    return ""


def ask_image(png: bytes, prompt: str) -> str:
    from google import genai
    from google.genai import types
    key = _first_key()
    if not key:
        raise RuntimeError("no Gemini API key found (config/api_keys.json)")
    client = genai.Client(api_key=key, http_options={"api_version": "v1beta"})
    part = types.Part.from_bytes(data=png, mime_type="image/png")
    cfg = types.GenerateContentConfig(response_mime_type="application/json")
    return client.models.generate_content(
        model=_MODEL, contents=[part, prompt], config=cfg).text or ""


def find_text(text: str, bbox=None, tries: int = 2) -> Optional[tuple]:
    import json
    png, w, h = snapshot(bbox)
    prompt = ('Find the visible UI control whose text is exactly "%s". Return JSON '
              '{"found": bool, "box_2d": [ymin,xmin,ymax,xmax]} normalised 0-1000; '
              "null box if not visible. Whole control, not just the glyphs." % text)
    for _ in range(max(1, tries)):
        try:
            data = json.loads(ask_image(png, prompt))
        except Exception:
            continue
        b = data.get("box_2d")
        if data.get("found") and isinstance(b, list) and len(b) == 4:
            ymin, xmin, ymax, xmax = b
            ox, oy = (bbox[0], bbox[1]) if bbox else (0, 0)
            return (ox + round((xmin+xmax)/2*w/1000), oy + round((ymin+ymax)/2*h/1000))
    return None
