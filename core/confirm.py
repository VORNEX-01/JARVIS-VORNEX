"""
core/confirm.py — a confirmation the model cannot forge.

Supports two human-in-the-loop paths:
- HUD confirm (UI button)
- VOICE confirm (user says a one-time code)

VOICE is still human-sourced because main.py only accepts it from live user
transcription, never from model-written tool params.
"""
from __future__ import annotations

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
    code: str = ""
    voice_only: bool = False


_pending: Optional[_Pending] = None
_lock = threading.Lock()

_show_cb: Optional[Callable[[str, str], None]] = None
_hide_cb: Optional[Callable[[], None]] = None
_log_cb: Optional[Callable[[str], None]] = None

_results: list[tuple[str, str]] = []  # (title, result)
_results_lock = threading.Lock()


def bind(show, hide, log=None) -> None:
    global _show_cb, _hide_cb, _log_cb
    _show_cb, _hide_cb, _log_cb = show, hide, log


def _log(msg: str) -> None:
    if _log_cb:
        try:
            _log_cb(msg)
        except Exception:
            pass


def _expired(p: _Pending) -> bool:
    return (time.monotonic() - p.at) > TIMEOUT_SECONDS


def _new_code() -> str:
    return str(secrets.randbelow(9000) + 1000)  # 4 digits


def request(key: str, title: str, detail: str, run: Callable[[], str], *,
            voice_only: bool = False) -> str:
    """Park an irreversible action behind confirmation.

    If voice_only=True: do NOT show HUD banner; require voice code.
    """
    global _pending

    code = _new_code()

    with _lock:
        _pending = _Pending(
            key=key,
            title=title,
            detail=detail,
            run=run,
            at=time.monotonic(),
            code=code,
            voice_only=voice_only,
        )

    # HUD banner (optional)
    if not voice_only:
        if _show_cb is None:
            # No UI bound; refuse rather than silently doing irreversible action.
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

    # IMPORTANT: tool returns an instruction for the MODEL to speak.
    return (
        f"[CONFIRMATION_PENDING] Awaiting confirmation for: {title}. "
        f"Ask the user to CONFIRM BY VOICE by saying EXACTLY: 'تایید {code}' "
        f"(or 'confirm {code}'). To cancel: 'لغو {code}' (or 'cancel {code}'). "
        f"Do NOT claim it is done yet."
    )


def resolve(accepted: bool) -> None:
    global _pending

    with _lock:
        p, _pending = _pending, None

    if p is None:
        return

    # Hide HUD if shown
    if _hide_cb and not p.voice_only:
        try:
            _hide_cb()
        except Exception:
            pass

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
            err = f"{p.title} failed — {e}"
            _log(f"ERR: {err}")
            with _results_lock:
                _results.append((p.title, f"Failed: {e}"))

    threading.Thread(target=_worker, daemon=True, name=f"confirm-{p.key}").start()


def pending_title() -> str:
    with _lock:
        if _pending is None:
            return ""
        if _expired(_pending):
            return ""
        return _pending.title


def pending_code() -> str:
    with _lock:
        if _pending is None or _expired(_pending):
            return ""
        return _pending.code or ""


def try_voice(text: str) -> bool:
    """Consume a user's utterance if it confirms/cancels the current pending action."""
    t = (text or "").strip().casefold()
    if not t:
        return False

    with _lock:
        p = _pending
        if p is None or _expired(p) or not p.code:
            return False
        code = p.code

    if code.casefold() not in t:
        return False

    # confirm words
    if ("تایید" in t) or ("confirm" in t):
        resolve(True)
        return True

    # cancel words
    if ("لغو" in t) or ("cancel" in t):
        resolve(False)
        return True

    return False


def pop_result() -> Optional[tuple[str, str]]:
    with _results_lock:
        if not _results:
            return None
        return _results.pop(0)
