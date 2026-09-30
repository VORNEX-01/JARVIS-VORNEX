"""A LIVE eye: capture continuously, call vision only when needed.

- one cached mss grabs the screen every ~0.35s (cheap, local)
- a tiny grayscale thumbnail detects meaningful change
- an auto describer keeps a fresh one-line 'scene' on real change (throttled by
  min-gap + daily budget), so the assistant has live awareness without asking
- on-demand find_text()/describe() are NEVER throttled (an explicit look is
  always allowed); all vision routes through core.gemini (proxy+rotation+model)
"""
from __future__ import annotations
import io, os, threading, time
from typing import Callable, Optional

_INTERVAL = float(os.environ.get("VORNEX_EYE_INTERVAL", "0.35"))
_AUTO_GAP = float(os.environ.get("VORNEX_EYE_AUTO_GAP", "20"))
_BUDGET = int(os.environ.get("VORNEX_EYE_DAILY_BUDGET", "600"))
_AUTO = False  # disabled - causes 1011 Live session crash
_MODEL = os.environ.get("VORNEX_VISION_MODEL", "gemini-3.5-flash")

_lock = threading.Lock()
_S = {"img": None, "w": 0, "h": 0, "t": 0.0, "thumb": None, "changed_at": 0.0,
      "frames": 0, "changes": 0, "fg": "", "calls": 0, "day": "",
      "scene": "", "scene_at": 0.0}
_SCT = None
_thread = None
_auto_thread = None
_stop = threading.Event()
_paused = threading.Event()
_vision_fn: Optional[Callable] = None


def _grab(bbox=None):
    global _SCT
    import mss
    from PIL import Image
    if _SCT is None:
        _SCT = mss.mss()
    mon = ({"left": bbox[0], "top": bbox[1], "width": bbox[2]-bbox[0],
            "height": bbox[3]-bbox[1]} if bbox else _SCT.monitors[1])
    shot = _SCT.grab(mon)
    return Image.frombytes("RGB", shot.size, shot.rgb)


def _encode(img):
    buf = io.BytesIO(); img.save(buf, format="PNG"); return buf.getvalue()




def _proxy_addr():
    import os
    raw = (os.environ.get("VORNEX_PROXY") or os.environ.get("ALL_PROXY")
           or os.environ.get("all_proxy") or "socks5://127.0.0.1:10810")
    raw = raw.split("://")[-1].split("@")[-1]
    host, _, port = raw.partition(":")
    try:
        return host or "127.0.0.1", int(port or 10810)
    except ValueError:
        return "127.0.0.1", 10810


def _proxy_alive(timeout=0.5):
    """A dead proxy is what made 'Server disconnected' and the long hang. Check
    it FIRST so the eye fails in half a second with the truth."""
    import socket
    host, port = _proxy_addr()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _vision_bytes(img, maxw=1600):
    """Small JPEG for the API - a full-res PNG is what made the server drop us."""
    w, h = img.size
    if w > maxw:
        img = img.resize((maxw, max(1, round(h * maxw / w))))
    buf = io.BytesIO(); img.save(buf, format="JPEG", quality=85)
    return buf.getvalue(), "image/jpeg"


def _thumb(img, size=(64, 36)):
    return list(img.convert("L").resize(size).getdata())


def _diff(a, b):
    return 999 if not a or not b or len(a) != len(b) else sum(abs(x-y) for x, y in zip(a, b))/len(a)


def _foreground():
    try:
        import ctypes
        u = ctypes.windll.user32; h = int(u.GetForegroundWindow())
        n = int(u.GetWindowTextLengthW(h)); b = ctypes.create_unicode_buffer(n + 1)
        u.GetWindowTextW(h, b, n + 1); return b.value
    except Exception:
        return ""


def _loop():
    while not _stop.is_set():
        if not _paused.is_set():
            try:
                img = _grab(); th = _thumb(img)
                with _lock:
                    d = _diff(_S["thumb"], th)
                    _S.update(img=img, thumb=th, frames=_S["frames"]+1, w=img.size[0],
                              h=img.size[1], t=time.time(), fg=_foreground())
                    if d >= 4:
                        _S["changes"] += 1; _S["changed_at"] = time.time()
            except Exception:
                pass
        _stop.wait(_INTERVAL)


def _budget_ok():
    day = time.strftime("%Y-%m-%d")
    with _lock:
        if _S["day"] != day:
            _S["day"] = day; _S["calls"] = 0
        if _S["calls"] >= _BUDGET:
            return False
        _S["calls"] += 1
        return True


def _describer():
    while not _stop.is_set():
        try:
            with _lock:
                need = (_AUTO and _S["img"] is not None and _S["changed_at"] > _S["scene_at"])
                gap = time.time() - _S["scene_at"]
            if need and gap >= _AUTO_GAP and _budget_ok():
                txt = describe("In one short line, what is on screen now?")
                with _lock:
                    _S["scene"] = txt; _S["scene_at"] = time.time()
        except Exception:
            pass
        _stop.wait(2.0)


def start():
    global _thread
    if not (_thread and _thread.is_alive()):
        _stop.clear()
        with _lock:
            _S["thumb"] = None
        _thread = threading.Thread(target=_loop, daemon=True); _thread.start()


def start_auto():
    global _auto_thread
    start()
    if not (_auto_thread and _auto_thread.is_alive()):
        _auto_thread = threading.Thread(target=_describer, daemon=True); _auto_thread.start()


def stop(): _stop.set()
def pause(): _paused.set()
def resume(): _paused.clear()


def snapshot(bbox=None):
    img = _grab(bbox)
    return _encode(img), img.size[0], img.size[1]


def latest():
    with _lock:
        img = _S["img"]
    return (_encode(img), img.size[0], img.size[1]) if img is not None else (None, 0, 0)


def state():
    with _lock:
        return {k: _S[k] for k in ("frames", "changes", "changed_at", "fg", "calls",
                                   "t", "scene", "scene_at")}


def changed_since(t):
    with _lock:
        return _S["changed_at"] >= float(t or 0)


def set_vision(fn):
    global _vision_fn
    _vision_fn = fn


def _try_raw(data, mime, prompt, json_mode, model):
    from google import genai
    from google.genai import types
    from core import gemini as G
    cl = genai.Client(api_key=G.api_key(),
                      http_options=types.HttpOptions(api_version="v1beta", timeout=15000))
    part = types.Part.from_bytes(data=data, mime_type=mime)
    cfg = types.GenerateContentConfig(
        response_mime_type="application/json" if json_mode else "text/plain")
    return cl.models.generate_content(model=model, contents=[part, prompt], config=cfg).text or ""


def _try_tier(data, mime, prompt, json_mode, tier):
    import json as _j
    from google.genai import types
    from core import gemini as G
    part = types.Part.from_bytes(data=data, mime_type=mime)
    out = getattr(G, "as_json" if json_mode else "text")([part, prompt], tier=tier)
    if out is None:
        return ""
    return out if isinstance(out, str) else _j.dumps(out, ensure_ascii=False)


def _strategies():
    """Every way we can reach a vision model, tried in order - the project's own
    client (which carries the SOCKS proxy) first, then things that may also work."""
    out = []
    try:
        from core import gemini as G
        out += [("tier", G.FAST), ("tier", G.SEARCH)]
    except Exception:
        pass
    out += [("raw", _MODEL), ("raw", "gemini-2.5-flash"), ("raw", "gemini-flash-latest")]
    return out


def ask_image(data, mime, prompt, json_mode=True, tries=2):
    if not _proxy_alive():
        h, pt = _proxy_addr()
        raise RuntimeError('vision is unavailable: the proxy %s:%d is down '
                           '- start it and ask again' % (h, pt))
    last = None
    for _ in range(max(1, tries)):
        if _vision_fn is not None:
            try:
                return str(_vision_fn(data, prompt))
            except Exception as e:
                last = e
        for kind, arg in _strategies():
            try:
                out = (_try_raw(data, mime, prompt, json_mode, arg) if kind == "raw"
                       else _try_tier(data, mime, prompt, json_mode, arg))
                if out:
                    return out
            except Exception as e:
                last = e
        time.sleep(0.5)
    raise RuntimeError("vision failed: %s" % last)


def find_text(text, bbox=None):
    """On-demand: never throttled. Returns (x, y) screen centre or None."""
    import json
    if bbox is not None:
        img = _grab(bbox); ox, oy = bbox[0], bbox[1]
    else:
        with _lock:
            img = _S["img"]
        if img is None:
            img = _grab()
        ox = oy = 0
    w, h = img.size
    data, mime = _vision_bytes(img)
    prompt = ('Find the visible UI control whose text is exactly "%s". Return JSON '
              '{"found": bool, "box_2d": [ymin,xmin,ymax,xmax]} normalised 0-1000; '
              "null box if not visible." % text)
    for _ in range(2):
        try:
            d = json.loads(ask_image(data, mime, prompt))
        except Exception:
            continue
        b = d.get("box_2d")
        if d.get("found") and isinstance(b, list) and len(b) == 4:
            ymin, xmin, ymax, xmax = b
            return (ox + round((xmin+xmax)/2*w/1000), oy + round((ymin+ymax)/2*h/1000))
    return None


def describe(question="What is on the screen right now?"):
    with _lock:
        img = _S["img"]
    if img is None:
        img = _grab()
    data, mime = _vision_bytes(img)
    try:
        return ask_image(data, mime, question, json_mode=False)
    except Exception as e:
        return "I could not see (%s)." % e
