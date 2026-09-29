"""A LIVE eye: capture continuously and cheaply, call vision only when needed.

The background thread grabs the screen every ~350ms (mss) and keeps the RAW PIL
image + a tiny grayscale thumbnail; a PNG is encoded only on demand. Change is
detected locally. Gemini vision runs behind a min-interval + daily budget, with
retries, routed through core.gemini when available (so model/proxy/rotation are
the project's working ones)."""
from __future__ import annotations
import io, os, threading, time
from typing import Callable, Optional

_INTERVAL = float(os.environ.get("VORNEX_EYE_INTERVAL", "0.35"))
_MIN_GAP = float(os.environ.get("VORNEX_EYE_MIN_VISION_GAP", "4.0"))
_BUDGET = int(os.environ.get("VORNEX_EYE_DAILY_BUDGET", "400"))
_MODEL = os.environ.get("VORNEX_VISION_MODEL", "gemini-3.5-flash")

_lock = threading.Lock()
_S = {"img": None, "w": 0, "h": 0, "t": 0.0, "thumb": None, "changed_at": 0.0,
      "frames": 0, "changes": 0, "fg": "", "last_vision": 0.0, "calls": 0, "day": ""}
_thread = None
_stop = threading.Event()
_paused = threading.Event()
_vision_fn: Optional[Callable] = None


_SCT = None


def _grab(bbox=None):
    global _SCT
    import mss
    from PIL import Image
    if _SCT is None:
        _SCT = mss.mss()            # created once, not per frame (was the slowdown)
    mon = ({"left": bbox[0], "top": bbox[1], "width": bbox[2]-bbox[0],
            "height": bbox[3]-bbox[1]} if bbox else _SCT.monitors[1])
    shot = _SCT.grab(mon)
    return Image.frombytes("RGB", shot.size, shot.rgb)


def _encode(img):
    buf = io.BytesIO(); img.save(buf, format="PNG"); return buf.getvalue()


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
                    _S.update(img=img, thumb=th, frames=_S["frames"] + 1,
                              w=img.size[0], h=img.size[1], t=time.time(), fg=_foreground())
                    if d >= 4:
                        _S["changes"] += 1; _S["changed_at"] = time.time()
            except Exception:
                pass
        _stop.wait(_INTERVAL)


def start():
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    with _lock:
        _S["thumb"] = None
    _thread = threading.Thread(target=_loop, daemon=True); _thread.start()


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
        return {k: _S[k] for k in ("frames", "changes", "changed_at", "fg", "calls", "t")}


def changed_since(t):
    with _lock:
        return _S["changed_at"] >= float(t or 0)


def _budget_ok():
    day = time.strftime("%Y-%m-%d"); now = time.time()
    with _lock:
        if _S["day"] != day:
            _S["day"] = day; _S["calls"] = 0
        if _S["calls"] >= _BUDGET or now - _S["last_vision"] < _MIN_GAP:
            return False
        _S["calls"] += 1; _S["last_vision"] = now
        return True


def set_vision(fn):
    """Inject vision function(png_bytes, prompt) -> str (e.g. core.gemini's)."""
    global _vision_fn
    _vision_fn = fn


def _via_gemini(png, prompt):
    try:
        from core import gemini as G
        for fn in ("generate_with_image", "image_query", "vision_generate",
                   "vision", "ask_with_image", "ask", "generate", "generate_content"):
            f = getattr(G, fn, None)
            if callable(f):
                try:
                    out = f(png, prompt)
                except TypeError:
                    continue
                if out:
                    return str(out)
    except Exception:
        pass
    return None


def _direct(png, prompt, json_mode):
    from google import genai
    from google.genai import types
    from core import gemini as G
    client = genai.Client(api_key=G.api_key(), http_options={"api_version": "v1beta"})
    part = types.Part.from_bytes(data=png, mime_type="image/png")
    cfg = types.GenerateContentConfig(response_mime_type="application/json" if json_mode else "text/plain")
    return client.models.generate_content(model=_MODEL, contents=[part, prompt], config=cfg).text or ""


def ask_image(png, prompt, json_mode=True, tries=3):
    """Route vision through core.gemini's resilient REST path (proxy + rotation +
    model ladder), so we never build our own flaky client."""
    import json as _json
    last = None
    try:
        from google.genai import types
        part = types.Part.from_bytes(data=png, mime_type="image/png")
    except Exception:
        part = None
    for _ in range(max(1, tries)):
        if _vision_fn is not None:
            try:
                return str(_vision_fn(png, prompt))
            except Exception as e:
                last = e
        if part is not None:
            try:
                from core import gemini as G
                fn = getattr(G, "as_json" if json_mode else "text")
                out = fn([part, prompt], tier=G.FAST)
                if out is not None:
                    return out if isinstance(out, str) else _json.dumps(out, ensure_ascii=False)
            except Exception as e:
                last = e
        try:
            return _direct(png, prompt, json_mode)
        except Exception as e:
            last = e
            time.sleep(0.6)
    raise RuntimeError("vision failed: %s" % last)


def find_text(text, bbox=None):
    import json
    if not _budget_ok():
        return None
    if bbox is None:
        with _lock:
            img = _S["img"]
        if img is None:
            return None
        png, w, h = _encode(img), img.size[0], img.size[1]
    else:
        png, w, h = snapshot(bbox)
    prompt = ('Find the visible UI control whose text is exactly "%s". Return JSON '
              '{"found": bool, "box_2d": [ymin,xmin,ymax,xmax]} normalised 0-1000; '
              "null box if not visible." % text)
    try:
        d = json.loads(ask_image(png, prompt))
    except Exception:
        return None
    b = d.get("box_2d")
    if d.get("found") and isinstance(b, list) and len(b) == 4:
        ymin, xmin, ymax, xmax = b
        ox, oy = (bbox[0], bbox[1]) if bbox else (0, 0)
        return (ox + round((xmin+xmax)/2*w/1000), oy + round((ymin+ymax)/2*h/1000))
    return None


def describe(question="What is on the screen right now?"):
    if not _budget_ok():
        return "I am not looking right now (vision budget/interval)."
    png, _, _ = latest()
    if not png:
        return "No frame yet - start() the eye first."
    try:
        return ask_image(png, question, json_mode=False)
    except Exception as e:
        return "I could not see (%s)." % e
