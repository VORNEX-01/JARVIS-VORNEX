from __future__ import annotations

import re
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

TIMEOUT_SECONDS = 90.0

@dataclass
class _Pending:
    key: str
    title: str
    detail: str
    run: Callable[[], str]
    at: float
    code: str
    voice_only: bool

_pending: Optional[_Pending] = None
_lock = threading.Lock()

_show_cb: Optional[Callable[[str, str], None]] = None
_hide_cb: Optional[Callable[[], None]] = None
_log_cb:  Optional[Callable[[str], None]] = None

_results: list[tuple[str, str]] = []
_results_lock = threading.Lock()

_DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")

def bind(show, hide, log=None) -> None:
    global _show_cb, _hide_cb, _log_cb
    _show_cb, _hide_cb, _log_cb = show, hide, log

def _log(msg: str) -> None:
    if _log_cb:
        try: _log_cb(msg)
        except Exception: pass

def _expired(p: _Pending) -> bool:
    return (time.monotonic() - p.at) > TIMEOUT_SECONDS

def _new_code() -> str:
    return str(secrets.randbelow(9000) + 1000)  # 4 digits

def pending_title() -> str:
    with _lock:
        if _pending is None or _expired(_pending):
            return ""
        return _pending.title

def pending_code() -> str:
    with _lock:
        if _pending is None or _expired(_pending):
            return ""
        return _pending.code or ""

def _pending_msg(title: str, code: str) -> str:
    return (
        f"[CONFIRMATION_PENDING] Awaiting confirmation for: {title}. "
        f"Ask the user to CONFIRM BY VOICE by saying EXACTLY: 'تایید {code}' "
        f"(or 'confirm {code}'). To cancel: 'لغو {code}' (or 'cancel {code}'). "
        f"Do NOT claim it is done yet."
    )

def request(key: str, title: str, detail: str, run: Callable[[], str], *, voice_only: bool=False) -> str:
    """Idempotent: if something is already pending, DO NOT replace it / change code."""
    global _pending

    with _lock:
        if _pending is not None and not _expired(_pending):
            # Same key => return SAME code, do not overwrite
            if _pending.key == key:
                return _pending_msg(_pending.title, _pending.code)
            # Different key => refuse to stack
            return _pending_msg(_pending.title, _pending.code)

        code = _new_code()
        _pending = _Pending(
            key=key, title=title, detail=detail, run=run,
            at=time.monotonic(), code=code, voice_only=voice_only
        )

    # HUD banner only when not voice_only
    if not voice_only:
        if _show_cb is None:
            with _lock:
                _pending = None
            return (f"I cannot confirm '{title}' right now because the interface is "
                    f"not available, so I have not done it.")
        try:
            _show_cb(title, detail)
        except Exception as e:
            with _lock:
                _pending = None
            return f"Could not ask for confirmation: {e}. Nothing was done."

    _log(f"SYS: Awaiting confirmation — {title} (code {code})")
    return _pending_msg(title, code)

def resolve(accepted: bool) -> None:
    global _pending
    with _lock:
        p, _pending = _pending, None
    if p is None:
        return

    if not p.voice_only and _hide_cb:
        try: _hide_cb()
        except Exception: pass

    if _expired(p):
        _log(f"SYS: Confirmation expired — {p.title}")
        return
    if not accepted:
        _log(f"SYS: Cancelled — {p.title}")
        return

    def _worker():
        try:
            result = p.run() or "Done."
            _log(f"SYS: Confirmed — {p.title}. {result}")
            with _results_lock:
                _results.append((p.title, result))
        except Exception as e:
            _log(f"ERR: {p.title} failed — {e}")
            with _results_lock:
                _results.append((p.title, f"Failed: {e}"))
    threading.Thread(target=_worker, daemon=True, name=f"confirm-{p.key}").start()

def try_voice(text: str) -> bool:
    """Consume user's utterance if it confirms/cancels current pending action."""
    t = (text or "").strip().casefold()
    if not t:
        return False

    with _lock:
        p = _pending
        if p is None or _expired(p) or not p.code:
            return False
        code = p.code

    # normalize Persian digits -> English, then extract digits
    norm = t.translate(_DIGIT_MAP)
    digits = "".join(re.findall(r"\d+", norm))
    if code not in digits:
        return False

    if ("تایید" in norm) or ("confirm" in norm) or (digits == code):
        resolve(True)
        return True
    if ("لغو" in norm) or ("cancel" in norm):
        resolve(False)
        return True
    return False

def pop_result() -> Optional[tuple[str, str]]:
    with _results_lock:
        if not _results:
            return None
        return _results.pop(0)
