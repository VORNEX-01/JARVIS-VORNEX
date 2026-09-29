"""core/plugin_runtime.py — the LIVE plugin registry.

plugin_loader discovers plugins/ only at startup, and Gemini Live freezes its tool
list at connect. So a plugin created DURING a session could never be called. This
registry is what make_tool adds to and call_tool dispatches to, so a tool built
mid-session works immediately, with no restart.
"""
from __future__ import annotations
import importlib.util, json, py_compile, time
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent
_PLUGINS = _BASE / "plugins"
_LEARN = _BASE / "memory" / "learned_tools.json"
_REGISTRY: dict = {}


def _learn(name, purpose, ok, err=""):
    try:
        _LEARN.parent.mkdir(parents=True, exist_ok=True)
        data = []
        if _LEARN.exists():
            try: data = json.loads(_LEARN.read_text(encoding="utf-8"))
            except Exception: data = []
        data.append({"name": name, "purpose": purpose, "ok": bool(ok),
                     "error": str(err)[:200], "at": time.strftime("%Y-%m-%d %H:%M")})
        _LEARN.write_text(json.dumps(data[-300:], ensure_ascii=False, indent=2),
                          encoding="utf-8")
    except Exception:
        pass


def _import(path: Path, name: str):
    mod_name = "vornex_dyn_%s_%d" % (name, int(time.time() * 1000) % 1000000)
    spec = importlib.util.spec_from_file_location(mod_name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def install(name: str, source: str, purpose: str = ""):
    name = str(name or "").strip()
    if not name or not name.replace("_", "a").isalnum() or name[0].isdigit():
        return False, "bad tool name %r (use snake_case)" % name
    _PLUGINS.mkdir(parents=True, exist_ok=True)
    path = _PLUGINS / (name + ".py")
    backup = path.read_text(encoding="utf-8") if path.exists() else None
    try:
        path.write_text(source, encoding="utf-8")
        py_compile.compile(str(path), doraise=True)
        mod = _import(path, name)
        meta, run = getattr(mod, "PLUGIN", None), getattr(mod, "run", None)
        if not isinstance(meta, dict) or not callable(run):
            raise ValueError("plugin must define PLUGIN (dict) and run()")
        pname = str(meta.get("name") or name)
        _REGISTRY[pname] = {"run": run, "schema": meta.get("parameters") or {},
                            "file": str(path),
                            "description": str(meta.get("description") or purpose)}
        _learn(name, purpose or meta.get("description", ""), True)
        return True, "live: %s" % pname
    except Exception as e:
        if backup is not None:
            try: path.write_text(backup, encoding="utf-8")
            except Exception: pass
        else:
            try: path.unlink()
            except Exception: pass
        _learn(name, purpose, False, repr(e))
        return False, repr(e)


def invoke(name: str, args: dict, player=None, memory=None):
    rec = _REGISTRY.get(str(name or "").strip())
    if rec is None:
        return None, ("No live tool named %r. Live tools: %s"
                      % (name, ", ".join(sorted(_REGISTRY)) or "(none)"))
    try:
        return True, str(rec["run"](args or {}, player=player, session_memory=memory))
    except Exception as e:
        return False, "Tool %r crashed: %r" % (name, e)


def names():
    return sorted(_REGISTRY)


def schema(name: str):
    rec = _REGISTRY.get(str(name or "").strip())
    return rec["schema"] if rec else None


# ── self-heal: a missing third-party module is installed, then retried once ───
# MEASURED: make_tool refused a tool with "ModuleNotFoundError: No module named
# 'keyboard'". The tool was fine; one small library was not installed, and the
# assistant reported that as its own failure. From now on: stdlib is never
# touched, a KNOWN library is pip-installed (default index, then the Iran-friendly
# mirrors) and the call is retried once. A name outside the allowlist is refused
# with the exact command - never silently installed.
import functools as _ft
import importlib as _il
import importlib.util as _ilu
import subprocess as _sp
import sys as _sys

_MIRRORS = [
    ("https://pypi.tuna.tsinghua.edu.cn/simple", None),
    ("https://mirrors.aliyun.com/pypi/simple/", None),
    ("https://mirror-pypi.runflare.com/simple", "mirror-pypi.runflare.com"),
]

# import name -> pip name, only where they differ
_PIP_NAME = {
    "PIL": "pillow", "cv2": "opencv-python",
    "win32api": "pywin32", "win32con": "pywin32", "win32gui": "pywin32",
    "win32com": "pywin32", "pythoncom": "pywin32", "pywintypes": "pywin32",
    "bs4": "beautifulsoup4", "yaml": "pyyaml", "dotenv": "python-dotenv",
    "socks": "pysocks", "sklearn": "scikit-learn", "pptx": "python-pptx",
    "docx": "python-docx", "paho": "paho-mqtt",
    "youtube_transcript_api": "youtube-transcript-api",
    "screen_brightness_control": "screen-brightness-control",
}

# small, known libraries that are safe to pull in for a tool the user asked for.
# Anything OUTSIDE this list is refused, not installed.
_ALLOWED = {
    "keyboard", "mouse", "pyperclip", "pyautogui", "pygetwindow", "pynput",
    "psutil", "requests", "python-dotenv", "beautifulsoup4", "pillow",
    "opencv-python", "numpy", "mss", "openpyxl", "python-docx", "python-pptx",
    "pdfplumber", "pandas", "ddgs", "qrcode", "win10toast", "wmi", "pycaw",
    "playwright", "send2trash", "comtypes", "pywin32", "paho-mqtt",
    "screen-brightness-control", "youtube-transcript-api", "rich", "schedule",
    "python-dateutil", "pytz", "websockets", "httpx", "aiohttp", "fastapi",
    "uvicorn", "cryptography", "pyserial", "tinytuya",
}


def _missing_module(exc) -> str:
    mod = (getattr(exc, "name", "") or "").split(".")[0]
    if not mod:
        for part in str(exc).split("'"):
            if part and "No module named" not in part:
                mod = part
                break
    return mod.strip()


def _pip_for(mod: str) -> str:
    return _PIP_NAME.get(mod, mod)


def _can_import(mod: str) -> bool:
    try:
        return _ilu.find_spec(mod) is not None
    except Exception:
        return False


def _pip_install(pkg: str) -> bool:
    base = [_sys.executable, "-m", "pip", "install", pkg,
            "--quiet", "--disable-pip-version-check"]
    try:
        if _sp.run(base, capture_output=True, timeout=300).returncode == 0:
            return True
    except Exception:
        pass
    for url, host in _MIRRORS:
        cmd = base + ["-i", url]
        if host:
            cmd += ["--trusted-host", host]
        try:
            if _sp.run(cmd, capture_output=True, timeout=300).returncode == 0:
                return True
        except Exception:
            continue
    return False


def _install_missing(mod: str) -> bool:
    """True when `mod` is importable afterwards. Never installs an unknown name."""
    if not mod or _can_import(mod):
        return True
    if mod in getattr(_sys, "stdlib_module_names", ()):   # stdlib: a real bug
        return False
    pkg = _pip_for(mod)
    if pkg.lower() not in _ALLOWED:
        return False
    if not _pip_install(pkg):
        return False
    _il.invalidate_caches()
    return _can_import(mod)


def _selfheal(fn):
    if getattr(fn, "_vornex_selfheal", False):
        return fn

    @_ft.wraps(fn)
    def wrapper(*a, **k):
        try:
            return fn(*a, **k)
        except ModuleNotFoundError as e:
            mod = _missing_module(e)
            if not _install_missing(mod):
                return ("I could not add it: the tool needs the '%s' module and it "
                        "is not installed. Install it with:  %s -m pip install %s"
                        % (mod, _sys.executable, _pip_for(mod)))
            try:
                return fn(*a, **k)
            except Exception as e2:
                return "I installed '%s' but the tool still failed: %r" % (mod, e2)

    wrapper._vornex_selfheal = True
    return wrapper


for _name, _obj in list(globals().items()):
    if (_name.startswith("_") or not callable(_obj)
            or getattr(_obj, "__module__", "") != __name__):
        continue
    globals()[_name] = _selfheal(_obj)

try:
    _MIRRORS.sort(key=lambda t: 0 if "runflare" in t[0] else 1)
except NameError:
    pass
