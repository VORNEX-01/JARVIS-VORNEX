"""core/net.py - one place that points outbound traffic through a proxy.

google-genai (HTTPX) honours HTTPS_PROXY / HTTP_PROXY, so we export them from
config BEFORE any client is built, and keep localhost direct so a local model
(Ollama) still works. Config (config/api_keys.json):
    "proxy": ""                           # no proxy (direct / system VPN)
    "proxy": "http://127.0.0.1:10809"     # local HTTP proxy (VPN app)
    "proxy": "socks5://127.0.0.1:10808"   # SOCKS5 (needs httpx[socks])
"""
from __future__ import annotations
import json, os
from pathlib import Path

_CFG = Path(__file__).resolve().parent.parent / "config" / "api_keys.json"
_applied = False

def _config_proxy() -> str:
    try:
        return str(json.load(open(_CFG, encoding="utf-8")).get("proxy") or "").strip()
    except Exception:
        return ""

def apply_proxy():
    global _applied

    proxy = _config_proxy().strip()

    if not proxy:
        proxy = os.environ.get("HTTPS_PROXY", "").strip()

    if proxy:
        for key in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY",
                    "WS_PROXY", "WSS_PROXY"):
            os.environ[key] = proxy

        os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1,::1")
        _applied = True
    else:
        # No configured/system proxy: remove stale websocket proxy settings
        # that can force Live API through a dead local proxy.
        os.environ.pop("WS_PROXY", None)
        os.environ.pop("WSS_PROXY", None)

    return proxy
