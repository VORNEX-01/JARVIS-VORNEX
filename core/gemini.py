"""
One place where the assistant's one-shot Gemini calls are made.

WHY THIS EXISTS
    The live conversation runs on the Live API and is not what this file is
    about. Everything else — reading a screenshot, parsing a flight page,
    turning a request into a shell command, working out which WhatsApp button
    answers a call — was a separate `genai.Client(...)` built at the point of
    use, with the model name written inline. Sixteen files did it, twenty-six
    times, and not one of them set a timeout.

    That is not tidiness, it is three real faults:

    NO TIMEOUT.  The SDK waits forever by default. `gemini-flash-latest` spent
    an afternoon returning 504 DEADLINE_EXCEEDED, and every one of those calls
    became an unbounded hang — measured at ten seconds of silence while a phone
    rang, and worse elsewhere, because nothing was there to give up.

    NO FALLBACK.  One hardcoded alias meant that when that alias was unwell,
    the feature was simply gone. A ladder costs nothing when the first rung
    works and saves the feature when it does not.

    NO SINGLE PLACE TO CHANGE.  A new model release meant editing sixteen files
    and hoping none were missed.

THE LIVE MODEL DOES THIS WORK, AND IT LEADS THE LADDER
    Not the user's conversation — a separate, throwaway session per call, so
    nothing a plugin asks is ever heard by the person at the microphone.

    It leads because of quota. This is a voice assistant; the Live API is the
    dependency it already has, and it draws on a different pool from the text
    models. On the free tier it is the TEXT pool that runs out, and when it does
    every side call fails and the feature behind it dies with it. Putting Live
    first means ordinary use stops spending the pool that runs dry.

    The reply arrives through output_transcription, because these models refuse
    response_modalities=["TEXT"] with a 1007 — they only speak. That sounds
    fatal for structured output and is not: the transcription is the model's own
    text of what it said, and it returned "Mum ❤ click here for contact info",
    indented Python inside markdown fences, and src/utils/helpers_v2.py
    character for character.

    It cannot carry grounding metadata, so grounded web search stays on REST.

THE LADDER, MEASURED
    Live, one throwaway session:
        connect                     0.24s
        short structured JSON       1.7 - 2.8s
        2300 characters of code     3.39s, not truncated
        three concurrent sessions   all fine, 4.77s wall clock
    REST text models, same prompt, same afternoon:
        gemini-2.5-flash-lite       0.76s   ...then 429, quota exhausted
        gemini-2.5-flash            0.80s   ...then 429
        gemini-flash-lite-latest    2.58s
        gemini-flash-latest         504, every time
    So REST is two to four times quicker while it lasts, and the whole point of
    the ladder is that it does not last. Pinned REST names sit behind Live;
    rolling `-latest` aliases sit behind those, because they were the ones
    having a bad day.

    Where the answer depends only on stable input, cache it and neither pool is
    touched twice: `plugins/_whatsapp_core.py` is the worked example — one
    request per WhatsApp language for the lifetime of the install.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
import threading
from pathlib import Path

if getattr(sys, "frozen", False):
    _BASE = Path(sys.executable).parent
else:
    _BASE = Path(__file__).resolve().parent.parent

_KEY_FILE = _BASE / "config" / "api_keys.json"

# Ladders, tried left to right. Change a model HERE and the whole app follows.
FAST = "fast"      # short classification, extraction, one-line decisions
SMART = "smart"    # reasoning, generation, long documents, images
SEARCH = "search"  # grounded search — REST only, see below

# A rung that means "ask the Live model instead", through a short throwaway
# session rather than the REST text API.
#
# WHY IT LEADS
#     This is a voice assistant: the Live API is the dependency it already has,
#     and it draws on a DIFFERENT quota pool from the text models. On the free
#     tier the text pool is the one that runs out — an afternoon of ordinary use
#     exhausts it, and when it does, every one of these side calls fails and the
#     feature behind it dies. The Live pool is untouched by that.
#
# WHAT IT COSTS, MEASURED
#     connect                      0.24s
#     short structured JSON        1.7 - 2.8s   (REST: 0.76s)
#     2300 characters of code      3.39s, not truncated
#     three concurrent sessions    all fine, 4.77s wall clock
#     So it is two to four times slower than REST when REST is available, and
#     infinitely faster than REST when REST is out of quota.
#
# THE THING WORTH KNOWING
#     These models only speak — response_modalities=["TEXT"] is refused with a
#     1007. The reply comes back through output_transcription, which sounds like
#     it would mangle anything structured. It does not: it is the model's own
#     text of what it said, and it survived "Mum ❤ click here for contact info",
#     indented Python inside markdown fences, and src/utils/helpers_v2.py
#     character for character. That is what makes this usable at all.
#
#     What it cannot carry is grounding metadata, so grounded web search stays
#     on REST — see SEARCH.
LIVE = "live"

_LADDERS = {
    FAST: (LIVE, "gemini-3.5-flash", "gemini-2.5-flash"),
    SMART: (LIVE, "gemini-3.5-flash", "gemini-2.5-flash"),
    # Grounded search needs response.candidates[...].grounding_metadata, which a
    # Live turn does not produce. REST only, and it says so rather than silently
    # returning an answer with no sources behind it.
    SEARCH: ("gemini-3.5-flash", "gemini-2.5-flash"),
}

# The Live model to use for one-shot calls. main.py owns the real one; this is
# only the fallback for when this module is imported without it (tests).
_LIVE_FALLBACK = "models/gemini-3.1-flash-live-preview"

# How many one-shot Live sessions may exist at once.
#
# THE USER'S CONVERSATION OUTRANKS EVERY SIDE CALL.
# Nothing here can reach the microphone or the speaker — main.py has exactly one
# `.receive()` and it is bound to its own session, and audio only reaches the
# speaker through that one loop — so a side call cannot answer the user or talk
# over the reply. Verified alongside a live main session: four side calls fired
# while it was connected, each got its own answer, and the main session replied
# correctly both before and after with no errors.
#
# What a side call CAN do is take up a concurrent-session slot. That is the one
# way it could hurt the conversation, so it is capped, and a call that cannot
# get a slot quickly does not queue behind the others — it falls to the REST
# rung, which is what the ladder is for.
# Three, from the measurement: four side calls plus the conversation ran
# together without complaint, so three leaves the conversation a slot in hand
# while still covering any burst this app actually produces — tool calls run one
# after another, and the screen agent's loop is sequential.
_LIVE_SLOTS = threading.BoundedSemaphore(3)
_LIVE_SLOT_WAIT = 3.0

_ONE_SHOT_SYSTEM = (
    "You are a data-processing function, not an assistant and not in a "
    "conversation. There is no person listening to you. Produce exactly the "
    "output the request asks for and nothing else: no greeting, no "
    "acknowledgement, no 'Understood', no explanation, no closing remark, no "
    "restating of the question. If the request asks for JSON, emit only the "
    "JSON. If it asks for code, emit only the code. If it asks for one word, "
    "emit that one word. Preserve the exact spelling, punctuation, capitals "
    "and whitespace of anything you are asked to copy or return."
)

# Milliseconds. Not a preference: the API rejects anything under ten seconds
# with "Minimum allowed deadline is 10s", so this is the tightest bound it will
# accept. Callers with a long job (a whole document, a big image) pass more.
DEFAULT_TIMEOUT_MS = 10_000
MIN_TIMEOUT_MS = 10_000

_key_lock = threading.Lock()
_cached_key: str | None = None       # mirrors the active key (back-compat)
_cached_keys: list[str] | None = None
_key_index: int = 0

# A rung that answered 429 is out of quota, and on the free tier it will stay
# that way for a while. Retrying it on every single call is a wasted round trip
# in front of every request the assistant makes — measured on this key, the
# lite rung was 429ing continuously, so every call was paying for it before
# reaching the model that could actually answer. Remembering that for a few
# minutes turns the ladder from a cost into a saving.
_COOLDOWN_SECONDS = 300
_cooldown: dict[tuple[str, str], float] = {}
_cool_lock = threading.Lock()


def _first_json(txt):
    """Return the FIRST JSON value in a model reply, ignoring trailing text.

    Gemini often answers with the object we asked for and then keeps talking
    ("{...}\n\nHope that helps"). json.loads() then dies with 'Extra data'.
    Decode the first complete value and ignore everything after it.
    """
    import json as _json
    t = (txt or "").strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t.split("\n", 1)[1] if "\n" in t else t
        t = t.rsplit("```", 1)[0]
    try:
        return _json.loads(t)
    except Exception:
        pass
    dec = _json.JSONDecoder()
    for i, ch in enumerate(t):
        if ch in "[{":
            try:
                obj, _ = dec.raw_decode(t[i:])
                return obj
            except Exception:
                continue
    raise ValueError("no JSON found in reply")


def _cool(key: str, model: str) -> None:
    with _cool_lock:
        _cooldown[(key, model)] = time.monotonic() + _COOLDOWN_SECONDS


def _cooling(key: str, model: str) -> bool:
    with _cool_lock:
        until = _cooldown.get((key, model), 0.0)
        if until and time.monotonic() < until:
            return True
        _cooldown.pop((key, model), None)
        return False


def _load_keys() -> list[str]:
    """Every key in config/api_keys.json, in the order the user typed them.
    Accepts BOTH a list (`gemini_api_keys`) and a single (`gemini_api_key`), so
    one, two or three keys all behave the same way. Duplicates are dropped —
    retrying the same key would only waste a round trip."""
    try:
        data = json.loads(_KEY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []
    raw = data.get("gemini_api_keys")
    if isinstance(raw, str):
        raw = [raw]
    listed = [str(k).strip() for k in raw] if isinstance(raw, list) else []
    listed = [k for k in listed if k]
    if not listed:
        single = str(data.get("gemini_api_key") or "").strip()
        if single:
            listed = [single]
    seen, out = set(), []
    for k in listed:
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out


def keys(refresh: bool = False) -> list[str]:
    """The configured keys, cached. Empty when none are set."""
    global _cached_keys
    with _key_lock:
        if _cached_keys is None or refresh:
            _cached_keys = _load_keys()
        return list(_cached_keys)


def api_key(refresh: bool = False) -> str:
    """The key currently in use. Cached; never raises."""
    global _cached_key, _cached_keys, _key_index
    with _key_lock:
        if _cached_keys is None or refresh:
            _cached_keys = _load_keys()
            _key_index = 0
        if not _cached_keys:
            _cached_key = ""
            return ""
        if not 0 <= _key_index < len(_cached_keys):
            _key_index = 0
        _cached_key = _cached_keys[_key_index]
        return _cached_key


def _use_key(k: str) -> None:
    """Remember which key answered, so the next call starts from it."""
    global _cached_key, _key_index
    with _key_lock:
        ks = _cached_keys or []
        if k in ks:
            _key_index = ks.index(k)
        _cached_key = k


_DEAD_KEY_MARKERS = (
    "429", "resource_exhausted", "quota",
    "api key not valid", "api_key_invalid", "invalid api key",
    "unauthenticated", "permission_denied",
)


def _key_is_dead(msg: str) -> bool:
    """True when the failure is about THIS key — its quota is spent, or it was
    rejected outright — so the next key is worth trying. A network error, a 5xx
    or an empty reply is not the key's fault and must NOT rotate."""
    m = msg.lower()
    return any(x in m for x in _DEAD_KEY_MARKERS)


def _is_quota(msg: str) -> bool:
    m = msg.lower()
    return "429" in m or "resource_exhausted" in m or "quota" in m


def client(timeout_ms: int = DEFAULT_TIMEOUT_MS, key: str = ""):
    """A configured genai.Client with a deadline on it. Raises if there is no
    key, because a caller that cannot work without one should say so."""
    from google import genai
    from google.genai import types as gtypes

    key = key or api_key()
    if not key:
        raise RuntimeError("no Gemini API key is configured")
    return genai.Client(
        api_key=key,
        http_options=gtypes.HttpOptions(timeout=max(MIN_TIMEOUT_MS, int(timeout_ms))),
    )


class _Reply:
    """What a Live turn hands back, shaped like the REST response's `.text` so
    every existing call site keeps working unchanged."""

    __slots__ = ("text",)

    def __init__(self, text: str):
        self.text = text


def _live_model() -> str:
    """Whatever main.py is running, so upgrading the assistant upgrades this."""
    return getattr(sys.modules.get("main"), "LIVE_MODEL", None) or _LIVE_FALLBACK


def _to_live_parts(contents) -> list:
    """REST `contents` -> Live `parts`. Accepts a bare string, a list of
    strings, and the SDK's Part objects (which is how every image is passed
    here), because those are the three shapes the call sites actually use."""
    import base64

    items = contents if isinstance(contents, (list, tuple)) else [contents]
    parts = []
    for item in items:
        if isinstance(item, str):
            parts.append({"text": item})
            continue
        blob = getattr(item, "inline_data", None)
        if blob is not None:
            data = getattr(blob, "data", None)
            mime = getattr(blob, "mime_type", None) or "application/octet-stream"
            if isinstance(data, bytes):
                data = base64.b64encode(data).decode("ascii")
            parts.append({"inline_data": {"mime_type": mime, "data": data}})
            continue
        txt = getattr(item, "text", None)
        if txt:
            parts.append({"text": txt})
            continue
        if isinstance(item, dict):
            parts.append(item)
    return parts


async def _live_turn(parts: list, system: str, key: str, timeout_s: float) -> str:
    from google import genai
    from google.genai import types as gtypes

    cl = genai.Client(api_key=key, http_options={"api_version": "v1alpha"})
    # Silence the persona, or it answers instead of complying.
    #
    # These are conversational models and they behave like it: asked "Reply with
    # one word: ok" a Live turn came back with "Understood." — it treated the
    # instruction as something to acknowledge rather than something to do. The
    # REST models do not, because nobody ever taught them to be in a
    # conversation. Every call through this module wants a value, not a reply,
    # so the session is told what it is before it is told what to do.
    kwargs = {
        "response_modalities": ["AUDIO"],
        "output_audio_transcription": {},
        "system_instruction": _ONE_SHOT_SYSTEM + (f"\n\n{system}" if system else ""),
    }

    cm = cl.aio.live.connect(model=_live_model(),
                             config=gtypes.LiveConnectConfig(**kwargs))
    session = await asyncio.wait_for(cm.__aenter__(), 30)
    try:
        await session.send_client_content(
            turns={"role": "user", "parts": parts}, turn_complete=True)
        chunks: list[str] = []

        async def drain():
            async for resp in session.receive():
                sc = getattr(resp, "server_content", None)
                if sc and sc.output_transcription and sc.output_transcription.text:
                    chunks.append(sc.output_transcription.text)

        await asyncio.wait_for(drain(), timeout=timeout_s)
        # The transcription can trail the audio turn by a beat; a short second
        # drain stops a reply being cut mid-token. chat_takeover learned this
        # the same way and for the same reason.
        try:
            await asyncio.wait_for(drain(), timeout=1.5)
        except asyncio.TimeoutError:
            pass
        return "".join(chunks).strip()
    finally:
        try:
            await cm.__aexit__(None, None, None)
        except Exception:
            pass


def _live_call(contents, config, timeout_ms: int, key: str):
    """One throwaway Live session, run on its own loop in its own thread.

    A dedicated thread rather than asyncio.run() on the caller's: these are
    invoked from plugin executor threads, from UI worker threads and from
    main.py's own event loop, and asyncio.run() inside a thread that already has
    a running loop raises. Its own thread has no loop to collide with, wherever
    it was called from.

    Reconnecting costs 0.24s, so nothing is kept alive between calls — no
    session lifetime cap to manage, no GoAway to handle, no shared state.
    """
    system = ""
    if config is not None:
        system = getattr(config, "system_instruction", None) or \
            (config.get("system_instruction") if isinstance(config, dict) else "") or ""

    parts = _to_live_parts(contents)
    if not parts:
        return None

    if not _LIVE_SLOTS.acquire(timeout=_LIVE_SLOT_WAIT):
        # Every slot is busy. Do not wait it out: falling to REST costs less
        # than holding a session the user's conversation might want.
        raise RuntimeError("no free Live slot — leaving them for the conversation")

    box: dict = {}

    def runner():
        try:
            box["text"] = asyncio.run(
                _live_turn(parts, str(system), key, max(10.0, timeout_ms / 1000.0)))
        except BaseException as e:                     # noqa: BLE001
            box["error"] = e

    try:
        th = threading.Thread(target=runner, daemon=True, name="gemini-live-oneshot")
        th.start()
        th.join(timeout=max(15.0, timeout_ms / 1000.0 + 20.0))
    finally:
        _LIVE_SLOTS.release()
    if "error" in box:
        raise box["error"]
    text = box.get("text")
    return _Reply(text) if text else None


def call(contents, tier: str = FAST, config=None,
         timeout_ms: int = DEFAULT_TIMEOUT_MS, key: str = ""):
    """Run one generation, walking the model ladder until one answers.

    Keys are used in the order they appear in config/api_keys.json. A key is
    abandoned only when it is genuinely spent — out of quota (429 /
    RESOURCE_EXHAUSTED) or rejected outright — which is what makes "one key
    behaves as one, three behave as three" true. A network blip, a 5xx or an
    empty reply is not the key's fault, so the next model is tried on the SAME
    key. "All keys exhausted" is only reported once every key has been tried.
    """
    ladder = _LADDERS.get(tier)
    if ladder is None:
        ladder = (tier,) + tuple(m for m in _LADDERS[SMART] if m != tier)

    key_list = [key] if key else keys()
    if not key_list:
        print("[Gemini] no Gemini API key is configured")
        return None

    for idx, k in enumerate(key_list):
        if len(key_list) > 1:
            print(f"[Gemini] key #{idx + 1}/{len(key_list)}")
        # A fresh client per key, or the old one keeps sending the old key.
        cl = None
        # Cooldowns are per (key, model): a rung that ran out of quota on one
        # key is NOT out for the next one — quotas are per key.
        tried = [m for m in ladder if not _cooling(k, m)] or list(ladder)
        for model in tried:
            try:
                if model == LIVE:
                    reply = _live_call(contents, config, timeout_ms, k)
                    if reply is not None:
                        _use_key(k)
                        return reply
                    raise RuntimeError("the Live turn came back empty")
                if cl is None:
                    cl = client(timeout_ms=timeout_ms, key=k)
                kwargs = {"model": model, "contents": contents}
                if config is not None:
                    kwargs["config"] = config
                resp = cl.models.generate_content(**kwargs)
                _use_key(k)
                return resp
            except Exception as e:
                msg = str(e)
                if _key_is_dead(msg):
                    _cool(k, model)
                    why = "out of quota" if _is_quota(msg) else "rejected"
                    print(f"[Gemini] key #{idx + 1} · {model}: {why} — "
                          f"moving to the next key")
                    break                    # this key is spent
                print(f"[Gemini] {model}: {type(e).__name__}: {msg[:140]}")
        else:
            # Every rung failed for a reason that is not this key's fault, so
            # swapping in another key would repeat the same failures.
            print("[Gemini] every model failed — not a key problem, not rotating")
            return None
    else:
        print(f"[Gemini] all {len(key_list)} key(s) exhausted")
    return None

def text(contents, tier: str = FAST, config=None,
         timeout_ms: int = DEFAULT_TIMEOUT_MS, key: str = "", default: str = "") -> str:
    """`call`, reduced to the reply text. `default` when nothing answered."""
    resp = call(contents, tier=tier, config=config,
                timeout_ms=timeout_ms, key=key)
    if resp is None:
        return default
    return (getattr(resp, "text", None) or "").strip() or default


def as_json(contents, tier: str = FAST, config=None,
            timeout_ms: int = DEFAULT_TIMEOUT_MS, key: str = "", default=None):
    """`text`, parsed as JSON, tolerating the fences and prose a model wraps it
    in. `default` when nothing answered or the answer would not parse."""
    raw = text(contents, tier=tier, config=config, timeout_ms=timeout_ms, key=key)
    if not raw:
        return default
    if "{" in raw and "}" in raw:
        raw = raw[raw.find("{"): raw.rfind("}") + 1]
    elif "[" in raw and "]" in raw:
        raw = raw[raw.find("["): raw.rfind("]") + 1]
    try:
        return _first_json(raw)
    except Exception as e:
        print(f"[Gemini] reply was not JSON: {e}")
        return default


# ── route outbound traffic through the configured proxy (Iran-safe) ──────────
try:
    from core import net as _net
    _net.apply_proxy()
except Exception:
    pass
