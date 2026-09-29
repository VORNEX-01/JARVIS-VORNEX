"""The ONLY sanctioned way to change a file: validate -> write -> py_compile ->
import-smoke in a SEPARATE subprocess -> git commit; exact rollback on failure."""
from __future__ import annotations
import os, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _git(*a):
    return subprocess.run(["git", *a], capture_output=True, text=True, cwd=ROOT)


def _smoke(path):
    rel = path.relative_to(ROOT).with_suffix("")
    mod = ".".join(rel.parts)
    p = subprocess.run([sys.executable, "-c",
                        "import importlib; importlib.import_module('%s')" % mod],
                       capture_output=True, text=True, timeout=60, cwd=ROOT,
                       env={**os.environ, "PYTHONUTF8": "1"})
    return p.returncode == 0, (p.stderr or p.stdout)


def apply_edit(path, new_source, message="self-patch", smoke=True):
    from core.self_patch_guard import validate_candidate
    path = Path(path).resolve()
    old = path.read_text(encoding="utf-8") if path.exists() else ""
    try:
        validate_candidate(old, new_source, str(path))
    except Exception as e:
        return False, "REFUSED by guard: %s" % e
    try:
        compile(new_source, str(path), "exec")
    except SyntaxError as e:
        return False, "REFUSED: does not compile (%s)" % e
    path.write_text(new_source, encoding="utf-8")
    if smoke:
        ok, out = _smoke(path)
        if not ok:
            path.write_text(old, encoding="utf-8")
            return False, "ROLLED BACK: import failed (%s)" % out.strip()[-300:]
    _git("add", str(path)); _git("commit", "-q", "-m", message)
    return True, "applied, compile+import OK, committed"
