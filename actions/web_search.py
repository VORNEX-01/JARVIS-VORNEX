#web_search.py
import json
import sys
import threading
import time
from pathlib import Path

# ── Gemini grounding quota circuit breaker ────────────────────────────────────
# The google_search grounding tool has its own small quota, separate from plain
# generation.  Once it is spent every call returns 429 — so retrying it at the
# top of every search only adds a dead round-trip before the DDG fallback runs.
# After a quota error, skip Gemini entirely for a cooldown period.
_QUOTA_COOLDOWN_SEC  = 900          # 15 minutes
_quota_blocked_until = 0.0
_quota_lock          = threading.Lock()


def _gemini_available() -> bool:
    with _quota_lock:
        return time.monotonic() >= _quota_blocked_until


def _note_gemini_error(exc: Exception) -> None:
    """Trip the breaker when the error is a quota / rate-limit rejection."""
    global _quota_blocked_until
    msg = str(exc)
    if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
        with _quota_lock:
            already = time.monotonic() < _quota_blocked_until
            _quota_blocked_until = time.monotonic() + _QUOTA_COOLDOWN_SEC
        if not already:
            print(
                "[WebSearch] Gemini grounding quota exhausted — skipping it for "
                f"{_QUOTA_COOLDOWN_SEC // 60} min and serving results from DDG."
            )


class _QuotaCooldown(RuntimeError):
    """Raised instead of calling Gemini while the quota breaker is open."""


def _log_gemini_failure(context: str, exc: Exception) -> None:
    """Log a Gemini failure — silently when it is just the expected cooldown."""
    if isinstance(exc, _QuotaCooldown):
        return          # announced once when the breaker tripped; not a warning
    print(f"[WebSearch] \u26a0\ufe0f {context} failed ({exc}) — using DDG instead")


def _run_bounded(fn, timeout: float, label: str = "task"):
    """Run fn() in a daemon thread; return its result, or None if it overruns."""
    box = [None]

    def _run():
        try:
            box[0] = fn()
        except Exception as e:
            _log_gemini_failure(label, e)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        print(f"[WebSearch] {label} exceeded {timeout:.0f}s — moving on")
    return box[0]

def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR        = _get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"


def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


def _gemini_search(query: str) -> str:
    if not _gemini_available():
        raise _QuotaCooldown("Gemini grounding is in quota cooldown")

    from core import gemini

    # Grounded search reads a live page, so it gets a longer deadline than the
    # default — but it still HAS one, and it still walks the fallback ladder.
    try:
        response = gemini.call(query, tier=gemini.SEARCH,
                               config={"tools": [{"google_search": {}}]},
                               timeout_ms=30_000)
        if response is None:
            raise RuntimeError("every Gemini model on the ladder failed")
    except Exception as e:
        _note_gemini_error(e)
        raise

    text = ""
    for part in response.candidates[0].content.parts:
        if hasattr(part, "text") and part.text:
            text += part.text

    text = text.strip()
    if not text:
        raise ValueError("Gemini returned an empty response.")
    return text


# -- DDG circuit breaker ------------------------------------------------------
# DuckDuckGo is unreachable from some networks (ISP blocks, sanctions). Without
# this, every search paid a full 8 s timeout before the RSS/Gemini fallback ran.
import time

_DDG_FAILS = 0
_DDG_UNTIL = 0.0
_DDG_FAIL_LIMIT = 3
_DDG_COOLDOWN = 300.0


def _ddg_ok() -> bool:
    return not (_DDG_FAILS >= _DDG_FAIL_LIMIT and time.monotonic() < _DDG_UNTIL)


def _ddg_failed() -> None:
    global _DDG_FAILS, _DDG_UNTIL
    _DDG_FAILS += 1
    if _DDG_FAILS >= _DDG_FAIL_LIMIT:
        _DDG_UNTIL = time.monotonic() + _DDG_COOLDOWN


def _ddg_ok_reset() -> None:
    global _DDG_FAILS
    _DDG_FAILS = 0


def _get_ddgs():
    """
    Returns the DDGS class.  The package was renamed duckduckgo-search -> ddgs;
    the legacy package's endpoints are now rejected by DuckDuckGo (news() gets a
    403 Ratelimit, text() silently returns zero results), so warn loudly if we
    end up on it instead of failing in silence.
    """
    try:
        from ddgs import DDGS
        return DDGS
    except ImportError:
        from duckduckgo_search import DDGS
        print(
            "[WebSearch] ⚠️ Using the deprecated 'duckduckgo-search' package — "
            "DuckDuckGo blocks its endpoints, so every search will come back "
            "empty.  Fix with:  pip install -U ddgs"
        )
        return DDGS


def _ddg_search(query: str, max_results: int = 6) -> list[dict]:
    if not _ddg_ok():
        return []
    DDGS = _get_ddgs()
    results = []
    try:
        with DDGS(timeout=8) as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append({
                    "title":   r.get("title",  ""),
                    "snippet": r.get("body",   ""),
                    "url":     r.get("href",   ""),
                })
        _ddg_ok_reset()
    except Exception as e:
        _ddg_failed()
        if not _ddg_ok():
            print("[WebSearch] ⚠️ DDG unreachable — skipping it for a few minutes, using fallback")
        else:
            print(f"[WebSearch] ⚠️ DDG text() failed: {e}")
    return results


def _ddg_news(query: str, max_results: int = 8) -> list[dict]:
    """DDG news search — returns actual articles, not website homepages."""
    if not _ddg_ok():
        return []
    DDGS = _get_ddgs()
    results = []
    try:
        with DDGS(timeout=8) as ddgs:
            for r in ddgs.news(query, max_results=max_results):
                results.append({
                    "title":   r.get("title",  ""),
                    "snippet": r.get("body",   ""),
                    "url":     r.get("url",    ""),
                    "source":  r.get("source", ""),
                })
        _ddg_ok_reset()
    except Exception as e:
        _ddg_failed()
        if not _ddg_ok():
            print("[WebSearch] ⚠️ DDG unreachable — skipping it for a few minutes, using fallback")
        else:
            print(f"[WebSearch] ⚠️ DDG news() failed ({e}) — falling back to text search")
    if not results:
        results = _ddg_search(query, max_results=max_results)
    return results


def _format_ddg(query: str, results: list[dict]) -> str:
    if not results:
        return f"No results found for: {query}"

    lines = [f"Search results for: {query}\n"]
    for i, r in enumerate(results, 1):
        if r.get("title"):   lines.append(f"{i}. {r['title']}")
        if r.get("snippet"): lines.append(f"   {r['snippet']}")
        if r.get("url"):     lines.append(f"   Source: {r['url']}")
        lines.append("")
    return "\n".join(lines).strip()


def _format_news(query: str, results: list[dict]) -> str:
    if not results:
        return f"No news found for: {query}"

    lines = [f"Latest news: {query}\n"]
    for i, r in enumerate(results, 1):
        title = r.get("title", "")
        if not title:
            continue
        src = f"  [{r['source']}]" if r.get("source") else ""
        lines.append(f"{i}. {title}{src}")
        if r.get("snippet"):
            lines.append(f"   {r['snippet'][:140]}")
        if r.get("url"):
            lines.append(f"   {r['url']}")
        lines.append("")
    return "\n".join(lines).strip()


# ── Briefing helper ────────────────────────────────────────────────────────────

def _gemini_headlines(n: int = 5) -> tuple[list[str], str]:
    """
    Fetches current headlines via Gemini grounded search.
    Optimised for speed: minimal prompt + strict token cap.
    Returns (headline_list, raw_text_for_display).
    """
    import re
    from core import gemini

    response = gemini.call(
        f"Current world news: {n} headlines. Numbered list, titles only.",
        tier=gemini.SEARCH,
        config={"tools": [{"google_search": {}}]},
        timeout_ms=30_000,
    )
    if response is None:
        return [], ""

    raw = ""
    for part in response.candidates[0].content.parts:
        if hasattr(part, "text") and part.text:
            raw += part.text

    headlines = []
    for line in raw.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        # Only accept lines that begin with a number — skips preamble/closing sentences
        if not re.match(r'^[\d]+[.\)\-]', line):
            continue
        clean = re.sub(r'^[\d]+[.\)\-]\s*', '', line)
        clean = re.sub(r'^\*+\s*',          '', clean).strip()
        if clean and len(clean) > 10:
            headlines.append(clean)

    return headlines[:n], raw.strip()


# ── Modes ──────────────────────────────────────────────────────────────────────

def _search(query: str) -> str:
    """Default search — Gemini grounded, DDG fallback."""
    try:
        return _gemini_search(query)
    except Exception as e:
        _log_gemini_failure("Gemini search", e)
        results = _ddg_search(query)
        return _format_ddg(query, results)


def _news(query: str) -> str:
    """News: DuckDuckGo and RSS run together; Gemini is a last resort."""
    from concurrent.futures import ThreadPoolExecutor

    gemini_query = f"latest news today: {query}" if query else "top world news today"
    ddg_query    = query if query else "world news today"

    def _ddg_attempt() -> str:
        return _format_news(ddg_query, _ddg_news(ddg_query, max_results=8))

    def _rss_attempt() -> str:
        return _format_news(ddg_query, _rss_news(query or ddg_query, max_results=8))

    def _ok(s: str) -> bool:
        return bool(s) and len(s) > 40 and not s.startswith("No news found")

    ddg_text = rss_text = ""
    ex = ThreadPoolExecutor(max_workers=2)
    f_ddg = ex.submit(_ddg_attempt)
    f_rss = ex.submit(_rss_attempt)
    try:
        ddg_text = f_ddg.result(timeout=6.0) or ""
    except Exception:
        ddg_text = ""
    try:
        rss_text = f_rss.result(timeout=6.0) or ""
    except Exception:
        rss_text = ""
    ex.shutdown(wait=False)

    if _ok(ddg_text):
        return ddg_text
    if _ok(rss_text):
        return rss_text

    text = _run_bounded(
        lambda: _gemini_search(gemini_query), timeout=6.0, label="Gemini news"
    )
    if text and len(text) > 60:
        return text

    return f"No news found for: {query}"


def _research(query: str) -> str:
    """
    Deep dive — asks Gemini for a comprehensive answer with context.
    Falls back to a wider DDG fetch.
    """
    research_query = (
        f"Comprehensive, detailed explanation of: {query}. "
        "Include background context, key facts, current state, and important nuances."
    )
    try:
        return _gemini_search(research_query)
    except Exception as e:
        _log_gemini_failure("Gemini research", e)
        results = _ddg_search(query, max_results=10)
        return _format_ddg(query, results)


def _price(query: str) -> str:
    """Product price lookup — searches for current market prices."""
    price_query = f"current price of {query} — how much does it cost today"
    try:
        return _gemini_search(price_query)
    except Exception as e:
        _log_gemini_failure("Gemini price", e)
        results = _ddg_search(f"{query} price buy", max_results=6)
        return _format_ddg(query, results)


def _compare(items: list[str], aspect: str) -> str:
    query = (
        f"Compare {', '.join(items)} in terms of {aspect}. "
        "Give specific facts and data."
    )
    try:
        return _gemini_search(query)
    except Exception as e:
        _log_gemini_failure("Gemini compare", e)

    all_results: dict[str, list] = {}
    for item in items:
        try:
            all_results[item] = _ddg_search(f"{item} {aspect}", max_results=3)
        except Exception:
            all_results[item] = []

    lines = [f"Comparison — {aspect.upper()}", "─" * 40]
    for item in items:
        lines.append(f"\n▸ {item}")
        for r in all_results.get(item, [])[:2]:
            if r.get("snippet"):
                lines.append(f"  • {r['snippet']}")
            if r.get("url"):
                lines.append(f"    {r['url']}")
    return "\n".join(lines)


# ── Public entry point ─────────────────────────────────────────────────────────

def web_search(
    parameters:     dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params = parameters or {}
    query  = params.get("query", "").strip()
    mode   = params.get("mode",  "search").lower().strip()
    items  = params.get("items", [])
    aspect = params.get("aspect", "general").strip() or "general"

    if not query and not items:
        return "Please provide a search query."

    if items and mode not in ("compare",):
        mode = "compare"

    if player:
        player.write_log(f"[Search:{mode}] {query or ', '.join(items)}")

    print(f"[WebSearch] 🔍 mode={mode!r}  query={query!r}")

    try:
        if mode == "compare" and items:
            return _compare(items, aspect)
        if mode == "news":
            out = _news(query)
            try:
                if player is not None and hasattr(player, "show_content"):
                    player.show_content("NEWS - " + (query or "top news"), out)
            except Exception:
                pass
            return out
        if mode == "research":
            return _research(query)
        if mode == "price":
            return _price(query)
        return _search(query)

    except Exception as e:
        print(f"[WebSearch] ❌ All backends failed: {e}")
        return f"Search failed: {e}"


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "web_search",
    "description": "Searches the web. Use for ANY question about current facts, events, prices, or topics — always prefer this over guessing. Modes: 'search' (default), 'news' (latest headlines on a topic), 'research' (deep comprehensive answer), 'price' (product cost lookup), 'compare' (side-by-side comparison of items).",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "query": {
                "type": "STRING",
                "description": "Search query or topic"
            },
            "mode": {
                "type": "STRING",
                "description": "search | news | research | price | compare"
            },
            "items": {
                "type": "ARRAY",
                "items": {
                    "type": "STRING"
                },
                "description": "Items to compare (compare mode)"
            },
            "aspect": {
                "type": "STRING",
                "description": "Comparison aspect: price | specs | reviews | features"
            }
        },
        "required": [
            "query"
        ]
    },
    "handler": web_search,
}


# ---- RSS news fallback (works without a proxy: Iranian + international) ----
_RSS_FEEDS = [
    ("https://www.irna.ir/rss", "IRNA"),
    ("https://www.mehrnews.com/rss", "Mehr"),
    ("https://www.tabnak.ir/fa/rss/allnews", "Tabnak"),
    ("https://www.khabaronline.ir/rss", "KhabarOnline"),
    ("https://www.isna.ir/rss", "ISNA"),
    ("https://www.asriran.com/fa/rss/allnews", "Asriran"),
    ("https://www.hamshahrionline.ir/rss", "Hamshahri"),
    ("https://techcrunch.com/feed/", "TechCrunch"),
    ("https://feeds.bbci.co.uk/news/world/rss.xml", "BBC"),
]

_RSS_TECH = [
    ("https://www.zoomit.ir/feed", "Zoomit"),
    ("https://digiato.com/feed", "Digiato"),
    ("https://mobile.ir/news/rss.aspx", "Mobile.ir"),
    ("https://techcrunch.com/feed/", "TechCrunch"),
    ("https://feeds.bbci.co.uk/news/world/rss.xml", "BBC"),
]


def _rss_clean(s: str) -> str:
    import re as _re
    s = _re.sub(r"<[^>]+>", " ", s or "")
    for a, b in (("&nbsp;", " "), ("&amp;", "&"), ("&quot;", '"'),
                 ("&#39;", "'"), ("&lt;", "<"), ("&gt;", ">")):
        s = s.replace(a, b)
    return " ".join(s.split())


def _rss_parse(raw: bytes, source: str) -> list:
    import xml.etree.ElementTree as ET
    root = ET.fromstring(raw)
    items = []
    for node in root.iter():
        tag = node.tag.split("}")[-1].lower()
        if tag not in ("item", "entry"):
            continue
        title = link = desc = ""
        for ch in node:
            ct = ch.tag.split("}")[-1].lower()
            if ct == "title" and not title:
                title = _rss_clean(ch.text)
            elif ct == "link" and not link:
                link = (ch.text or "").strip() or ch.attrib.get("href", "")
            elif ct in ("description", "summary") and not desc:
                desc = _rss_clean(ch.text)
        if title:
            items.append({"title": title, "snippet": desc[:160],
                          "url": link, "source": source})
    return items


def _rss_fetch(url: str, source: str, timeout: float = 4.0) -> list:
    import urllib.request
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (VORNEX news reader)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    return _rss_parse(raw, source)


def _rss_news(query: str, max_results: int = 8) -> list:
    """Pull fresh headlines from many feeds, mixed across sources each time."""
    import random
    from concurrent.futures import ThreadPoolExecutor
    q = (query or "").lower()
    tech = any(k in q for k in ("tech", "technology", "apple", "gadget", "ai"))
    feeds = list(_RSS_TECH if tech else _RSS_FEEDS)
    random.shuffle(feeds)
    print(f"[WebSearch] RSS fallback ({'tech' if tech else 'general'}) ...")
    ex = ThreadPoolExecutor(max_workers=6)
    futs = [ex.submit(_rss_fetch, u, s) for u, s in feeds]
    groups = []
    for f in futs:
        try:
            groups.append(f.result(timeout=9))
        except Exception:
            groups.append([])
    ex.shutdown(wait=False)
    seen, out, i = set(), [], 0
    while len(out) < max_results and any(i < len(g) for g in groups):
        for g in groups:
            if i < len(g):
                it = g[i]
                key = it["title"][:60]
                if key in seen:
                    continue
                seen.add(key)
                out.append(it)
                if len(out) >= max_results:
                    break
        i += 1
    return out
