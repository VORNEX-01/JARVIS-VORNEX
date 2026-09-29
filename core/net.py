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
    proxy = _config_proxy() or os.environ.get("HTTPS_PROXY", "").strip()
    if proxy and not _applied:
        os.environ.setdefault("HTTPS_PROXY", proxy)
        os.environ.setdefault("HTTP_PROXY", proxy)
        os.environ.setdefault("ALL_PROXY", proxy)
        os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1,::1")
        _applied = True
    return proxy
