import os
import re
import sys
import json
import time
import shutil
import socket
import subprocess
import urllib.request
import functools
import http.server
import threading
import webbrowser
from html.parser import HTMLParser
from pathlib import Path


def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR         = get_base_dir()
API_CONFIG_PATH  = BASE_DIR / "config" / "api_keys.json"
PROJECTS_DIR     = Path.home() / "Desktop" / "JarvisProjects"
MAX_FIX_ATTEMPTS = 5

from core import gemini

MODEL_PLANNER = gemini.SMART
MODEL_WRITER  = gemini.SMART


def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


def _get_model(model_name: str = gemini.SMART):
    class _W:
        def generate_content(self, contents):
            resp = gemini.call(contents, tier=model_name, timeout_ms=60000)
            if resp is None:
                raise RuntimeError("every Gemini model on the ladder failed")
            return resp
    return _W()


def _strip_fences(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"^```[a-zA-Z]*\r?\n?", "", text)
    text = re.sub(r"\r?\n?```\s*$", "", text)
    return text.strip()


def _is_rate_limit(error: Exception) -> bool:
    msg = str(error).lower()
    return "429" in msg or "quota" in msg or "resource_exhausted" in msg


def _parse_traceback(output: str, project_files: list[str]) -> tuple[str | None, int | None]:
    pattern = re.compile(r'File ["\']([^"\']+\.py)["\'],\s+line\s+(\d+)', re.IGNORECASE)
    for raw_path, line_str in reversed(pattern.findall(output)):
        raw_name = Path(raw_path).name
        for pf in project_files:
            if Path(pf).name == raw_name or pf == raw_path or raw_path.endswith(pf):
                return pf, int(line_str)
    return None, None


def _classify_error(output: str) -> str:
    low = output.lower()
    if any(x in low for x in ("no module named", "modulenotfounderror", "importerror")):
        return "dependency_error"
    if "syntaxerror" in low or "invalid syntax" in low:
        return "syntax_error"
    if "cannot import" in low or "importerror" in low:
        return "import_error"
    if any(x in low for x in (
        "traceback", "exception", "error:", "nameerror", "typeerror",
        "attributeerror", "valueerror", "keyerror", "indexerror",
        "zerodivisionerror", "filenotfounderror", "permissionerror",
    )):
        return "runtime_error"
    return "none"


def _has_error(output: str, run_command: str) -> bool:
    low = output.lower()
    if "timed out" in low:
        return False
    if not output.strip():
        return False
    return _classify_error(output) != "none"


class RateLimitError(Exception):
    pass


# ── project folder de-duplication ───────────────────────────────────────────

_GENERIC_WORDS = {"page", "website", "site", "project", "app", "landing",
                  "landingpage", "web", "demo", "one", "simple"}


def _slug(name: str) -> str:
    s = re.sub(r"[^\w]+", "_", (name or "").lower()).strip("_")
    return re.sub(r"_+", "_", s)


def _canonical(name: str) -> str:
    parts = [p for p in _slug(name).split("_") if p]
    while parts and parts[-1] in _GENERIC_WORDS:
        parts.pop()
    return "_".join(parts) or _slug(name) or "jarvis_project"


def _resolve_project_dir(project_name: str, description: str) -> Path:
    """One folder per project. `portfolio_landing` and `portfolio_landing_page`
    collapse to the same canonical name, so repeated voice calls reuse a folder
    instead of piling up duplicates."""
    canon = _canonical(project_name or description[:48])
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    for d in PROJECTS_DIR.iterdir():
        if d.is_dir() and _canonical(d.name) == canon:
            return d
    d = PROJECTS_DIR / canon
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── deterministic verification (no LLM) ─────────────────────────────────────

class _TagChecker(HTMLParser):
    _VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input",
             "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.problems = []

    def handle_starttag(self, tag, attrs):
        if tag not in self._VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in self._VOID:
            return
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()
        elif tag in self.stack:
            while self.stack and self.stack[-1] != tag:
                self.problems.append(f"unclosed <{self.stack.pop()}>")
            if self.stack:
                self.stack.pop()
        else:
            self.problems.append(f"stray </{tag}>")


def _verify_project(project_dir: Path, files: list[dict], entry_point: str) -> list[str]:
    problems: list[str] = []

    for fi in files:
        rel = fi.get("path", "")
        if not rel:
            continue
        fp = project_dir / rel
        if not fp.exists():
            problems.append(f"missing file: {rel}")
        elif fp.stat().st_size == 0:
            problems.append(f"empty file: {rel}")

    if entry_point and not (project_dir / entry_point).exists():
        problems.append(f"entry point not found: {entry_point}")

    try:
        local_roots = {p.stem if p.is_file() else p.name for p in project_dir.iterdir()}
    except Exception:
        local_roots = set()

    for fi in files:
        rel = fi.get("path", "")
        fp  = project_dir / rel
        if not rel or not fp.exists():
            continue
        suffix = fp.suffix.lower()

        if suffix == ".py":
            r = subprocess.run([sys.executable, "-m", "py_compile", str(fp)],
                               capture_output=True, text=True)
            if r.returncode != 0:
                problems.append(f"syntax error in {rel}: {(r.stderr or r.stdout).strip()[:300]}")
            try:
                code = fp.read_text(encoding="utf-8", errors="replace")
                for m in re.finditer(r'^\s*(?:from\s+([\w\.]+)\s+import|import\s+([\w\.]+))',
                                     code, re.M):
                    mod  = (m.group(1) or m.group(2) or "").strip()
                    root = mod.split(".")[0]
                    if root and root in local_roots:
                        if not (project_dir / (mod.replace(".", "/") + ".py")).exists():
                            problems.append(f"{rel}: local import '{mod}' has no matching file")
            except Exception:
                pass

        elif suffix in (".js", ".mjs"):
            node = shutil.which("node")
            if node:
                r = subprocess.run([node, "--check", str(fp)], capture_output=True, text=True)
                if r.returncode != 0:
                    problems.append(f"JS syntax error in {rel}: {(r.stderr or r.stdout).strip()[:300]}")

        elif suffix in (".html", ".htm"):
            try:
                chk = _TagChecker()
                chk.feed(fp.read_text(encoding="utf-8", errors="replace"))
                if chk.problems:
                    problems.append(f"HTML structure in {rel}: {', '.join(chk.problems[:5])}")
            except Exception as e:
                problems.append(f"HTML parse failed in {rel}: {e}")
            try:
                html = fp.read_text(encoding="utf-8", errors="replace")
                for m in re.finditer(r'(?:src|href)\s*=\s*["\']([^"\']+)["\']', html, re.IGNORECASE):
                    ref = m.group(1).strip()
                    if not ref or ref.startswith(("http://", "https://", "//", "#",
                                                  "data:", "mailto:", "javascript:", "tel:")):
                        continue
                    ref_path = ref.split("?")[0].split("#")[0]
                    if not (project_dir / ref_path).exists():
                        problems.append(f"{rel}: referenced file not found -> {ref}")
            except Exception:
                pass

    return problems


# ── model-driven rewrite (self-review / design polish) ──────────────────────

def _model_rewrite(prompt: str, project_dir: Path, file_codes: dict) -> dict:
    model = _get_model(MODEL_WRITER)
    raw   = _strip_fences(model.generate_content(prompt).text)
    if not raw or raw.strip().upper() == "NONE":
        return {}

    parts   = re.split(r"^===+\s*FILE:\s*(.+?)\s*===+\s*$", raw, flags=re.M)
    updated = {}
    for i in range(1, len(parts) - 1, 2):
        path = parts[i].strip()
        body = _strip_fences(parts[i + 1])
        if not path or not body:
            continue
        p = project_dir / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
        updated[path] = body
    return updated


def _review_and_fix(project_dir: Path, file_codes: dict, description: str,
                    language: str) -> dict:
    if not file_codes:
        return {}
    bundle = "\n\n".join(f"===== {p} =====\n{c}" for p, c in file_codes.items())
    prompt = f"""You are a strict senior {language} reviewer. Find REAL bugs, missing
pieces and correctness problems — ignore pure style.

Project goal: {description}

{bundle[:14000]}

If everything is already correct and complete, output exactly: NONE
Otherwise, for each file that needs changes output a block:
=== FILE: <path> ===
<the FULL corrected file>
Output NONE or the blocks only. No explanation, no markdown fences."""
    return _model_rewrite(prompt, project_dir, file_codes)


def _polish_web_ui(project_dir: Path, file_codes: dict) -> dict:
    web = {p: c for p, c in file_codes.items()
           if p.lower().endswith((".html", ".htm", ".css", ".js"))}
    if not web:
        return {}
    bundle = "\n\n".join(f"===== {p} =====\n{c}" for p, c in web.items())
    prompt = f"""You are a top-tier web designer. Improve the VISUAL quality of this
static site — typography, spacing, colour, buttons, layout, responsiveness — while
keeping ALL existing text, ids, classes and functionality intact.

{bundle[:14000]}

If it already looks great, output exactly: NONE
Otherwise, for each file you changed output a block:
=== FILE: <path> ===
<the FULL new file>
No new external dependencies. Output NONE or the blocks only."""
    return _model_rewrite(prompt, project_dir, file_codes)


# ── local web server + smoke test ───────────────────────────────────────────

def _serve_and_open(project_dir: Path, entry_rel: str) -> str:
    try:
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()

        handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                                    directory=str(project_dir))
        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
        httpd.daemon_threads = True
        threading.Thread(target=httpd.serve_forever, daemon=True).start()

        url = f"http://127.0.0.1:{port}/{entry_rel.lstrip('/')}"
        ok = False
        for _ in range(40):
            try:
                with urllib.request.urlopen(url, timeout=1) as r:
                    if r.status == 200:
                        ok = True
                        break
            except Exception:
                time.sleep(0.1)
        webbrowser.open(url)
        return url if ok else f"{url} (server up, /{entry_rel} did not return 200)"
    except Exception as e:
        # never leave the user without a view
        target = (project_dir / entry_rel)
        if target.exists():
            webbrowser.open(target.resolve().as_uri())
            return f"file://{target} (server failed: {e})"
        return f"server failed: {e}"


# ── planning / writing / deps / vscode / run ────────────────────────────────

def _plan_project(description: str, language: str) -> dict:
    model = _get_model(MODEL_PLANNER)
    prompt = f"""You are a senior software architect. Create a minimal, complete file plan for this project.

Language: {language}
Description: {description}

Return ONLY valid JSON — no markdown, no explanation:
{{
  "project_name": "snake_case_name",
  "entry_point": "main.py",
  "files": [
    {{"path": "main.py", "description": "Entry point — what it does", "imports": ["utils.helpers"]}},
    {{"path": "utils/helpers.py", "description": "Helpers — what it exposes", "imports": []}}
  ],
  "run_command": "python main.py",
  "dependencies": ["requests"]
}}

Critical rules:
1. List files in DEPENDENCY ORDER — no-import files first, entry point last.
2. "imports" lists every other project module this file imports (dot-notation).
3. Keep it minimal — only files truly needed.
4. Entry point must be in the files list.
5. Relative paths only.
6. Standard library modules do NOT go in "dependencies".
7. For a static site use index.html + css/ + js/ and run_command "open index.html".

JSON:"""
    try:
        response = model.generate_content(prompt)
        return json.loads(_strip_fences(response.text))
    except json.JSONDecodeError as e:
        raise ValueError(f"Planner returned invalid JSON: {e}\nRaw: {response.text[:300]}")
    except Exception as e:
        if _is_rate_limit(e):
            raise RateLimitError(str(e))
        raise


def _write_file(file_info: dict, project_description: str, all_files: list[dict],
                language: str, project_dir: Path, already_written: dict[str, str]) -> str:
    model = _get_model(MODEL_WRITER)

    file_path    = file_info["path"]
    file_desc    = file_info.get("description", "")
    file_imports = file_info.get("imports", [])

    file_list = "\n".join(
        f"  [{i+1}] {f['path']}: {f.get('description', '')}"
        for i, f in enumerate(all_files)
    )

    dependency_context = ""
    for dep_dotted in file_imports:
        dep_path = dep_dotted.replace(".", "/") + ".py"
        if dep_path in already_written:
            dependency_context += (f"\n\n--- {dep_path} (you must import from this) ---\n"
                                   f"{already_written[dep_path][:2000]}")

    lang_rules = ""
    if language.lower() == "python":
        lang_rules = """
Python-specific rules:
- Use type hints for all function signatures.
- Add docstrings for public functions/classes.
- Use if __name__ == "__main__": guard in the entry point.
- Import project modules exactly as their paths (e.g. from utils.helpers import foo).
- Do NOT use implicit relative imports unless there is a proper __init__.py."""
    elif language.lower() in ("javascript", "typescript", "js", "ts",
                              "html", "html/css/js", "html/css/javascript"):
        lang_rules = """
Web/JS rules:
- Use ES modules (import/export), not CommonJS.
- Modern, semantic, responsive HTML; clean CSS; no external CDNs unless required.
- All local asset paths must exist on disk."""

    prompt = f"""You are a senior {language} developer writing production-quality code.

Project goal: {project_description}

Complete file structure (dependency order):
{file_list}

{f"Dependencies this file must import from other project files:{dependency_context}" if dependency_context else ""}

Write the complete, working code for: {file_path}
Purpose: {file_desc}
{f"Imports from: {', '.join(file_imports)}" if file_imports else "No project-internal imports."}

{lang_rules}

General rules:
- Output ONLY raw code. No explanation, no markdown, no fences.
- COMPLETE and RUNNABLE — no placeholders, no "# TODO", no pass stubs.
- Every import must be stdlib, a listed dependency, or a project file shown above.
- Match import paths EXACTLY to the file structure.
- Add try/except around I/O and network calls.
- It must all work when run from the project root.

Code for {file_path}:"""

    try:
        response = model.generate_content(prompt)
        code = _strip_fences(response.text)
        full_path = project_dir / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(code, encoding="utf-8")
        print(f"[DevAgent] ✅ Written: {file_path} ({len(code)} chars)")
        return code
    except Exception as e:
        if _is_rate_limit(e):
            raise RateLimitError(str(e))
        raise


def _install_dependencies(dependencies: list[str], project_dir: Path) -> str:
    if not dependencies:
        return "No external dependencies."
    to_install = []
    for dep in dependencies:
        pkg = re.split(r"[>=<!]", dep)[0].strip()
        r = subprocess.run([sys.executable, "-m", "pip", "show", pkg],
                           capture_output=True, text=True)
        if r.returncode != 0:
            to_install.append(dep)
        else:
            print(f"[DevAgent] ✓ Already installed: {pkg}")
    if not to_install:
        return f"All dependencies already installed: {', '.join(dependencies)}"
    print(f"[DevAgent] 📦 Installing: {to_install}")
    try:
        r = subprocess.run([sys.executable, "-m", "pip", "install"] + to_install,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=120, cwd=str(project_dir))
        return (f"Installed: {', '.join(to_install)}" if r.returncode == 0
                else f"Install warning (non-fatal): {r.stderr[:200]}")
    except subprocess.TimeoutExpired:
        return "Dependency install timed out (non-fatal)."
    except Exception as e:
        return f"Install error (non-fatal): {e}"


def _open_vscode(project_dir: Path) -> bool:
    for cmd in (
        "code",
        rf"C:\Users\{Path.home().name}\AppData\Local\Programs\Microsoft VS Code\bin\code.cmd",
        r"C:\Program Files\Microsoft VS Code\bin\code.cmd",
    ):
        try:
            subprocess.Popen([cmd, str(project_dir)], shell=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(1.5)
            print(f"[DevAgent] 💻 VSCode opened: {project_dir}")
            return True
        except Exception:
            continue
    return False


def _run_project(run_command: str, project_dir: Path, timeout: int = 30,
                 entry: str = "") -> str:
    print(f"[DevAgent] 🚀 Running: {run_command}")
    try:
        parts = run_command.split()
        low   = [q.lower() for q in parts] if parts else []

        # A page is not "run" by shelling out to `open` — a macOS idiom that
        # does not exist on Windows. Serve it, prove it answers, then open the
        # URL that actually works.
        if low and low[0] in ("open", "start") and (project_dir / "index.html").exists():
            served = _serve_web(project_dir, entry or "index.html")
            if served:
                url, _srv = served
                webbrowser.open(url)
                return (f"Serving {project_dir.name} at {url} — opened in the "
                        f"browser.")
            print("[DevAgent] ⚠️ Local server did not answer; opening the file")
            target = (project_dir / (entry or "index.html")).resolve()
            if target.exists():
                webbrowser.open(target.as_uri())
                return f"Opened {target.name} in the default browser."

        if len(parts) >= 2 and low[0] in ("open", "start"):
            target = (project_dir / parts[-1]).resolve()
            if target.exists():
                webbrowser.open(target.as_uri())
                return f"Opened {target.name} in the default browser."

        if low and low[0] in ("python", "python3", "py"):
            parts[0] = sys.executable

        result = subprocess.run(
            parts,
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout,
            cwd=str(project_dir)
        )

        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        combined_parts = []
        if stdout:
            combined_parts.append(f"STDOUT:\n{stdout}")
        if stderr:
            combined_parts.append(f"STDERR:\n{stderr}")

        return "\n\n".join(combined_parts) if combined_parts else "Ran with no output."

    except subprocess.TimeoutExpired:
        return f"Timed out after {timeout}s — long-running app (server/GUI) is likely working."
    except FileNotFoundError as e:
        return f"Command not found: {e}"
    except Exception as e:
        return f"Run error: {e}"

def _try_auto_install(error_output: str, project_dir: Path) -> bool:
    match = re.search(r"No module named ['\"]([a-zA-Z0-9_\-\.]+)['\"]", error_output, re.IGNORECASE)
    if not match:
        return False
    pkg = match.group(1).replace("_", "-").split(".")[0]
    print(f"[DevAgent] 🔧 Auto-installing missing package: {pkg}")
    try:
        r = subprocess.run([sys.executable, "-m", "pip", "install", pkg],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=60, cwd=str(project_dir))
        return r.returncode == 0
    except Exception:
        return False


def _fix_files(error_output: str, project_description: str, all_files: list[dict],
               file_codes: dict[str, str], language: str, project_dir: Path,
               entry_point: str) -> dict[str, str]:
    model = _get_model(MODEL_PLANNER)
    error_file, error_line = _parse_traceback(error_output, list(file_codes.keys()))
    error_type = _classify_error(error_output)

    files_to_fix: list[str] = []
    if error_file:
        files_to_fix.append(error_file)
        if error_type == "import_error":
            for fi in all_files:
                if error_file.replace("/", ".").replace(".py", "") in fi.get("imports", []):
                    if fi["path"] not in files_to_fix:
                        files_to_fix.append(fi["path"])
    else:
        files_to_fix.append(entry_point)

    updated_codes: dict[str, str] = {}
    for fix_path in files_to_fix:
        current_code = file_codes.get(fix_path, "")

        other_ctx = ""
        for fp, code in file_codes.items():
            if fp != fix_path and code:
                other_ctx += f"\n--- {fp} ---\n{code[:1500]}\n"

        line_hint = (f"\nError appears to be near line {error_line} in this file."
                     if (error_line and fix_path == error_file) else "")

        prompt = f"""You are an expert {language} debugger. Fix the broken file below.

Project goal: {project_description}

All project files:
{chr(10).join(f"  - {f['path']}: {f.get('description', '')}" for f in all_files)}

Other files (read-only — fix only the target file):
{other_ctx[:3500]}

File to fix: {fix_path}{line_hint}
Error type: {error_type}

Error output:
{error_output[:2500]}

Current (broken) code:
{current_code}

Rules:
- Output ONLY the complete fixed code. No explanation, no markdown, no backticks.
- Fix ALL errors visible in the error output.
- Keep all existing correct logic.
- Match import paths to the real structure.
- Do NOT introduce new bugs or remove error handling.

Fixed code for {fix_path}:"""

        try:
            fixed = _strip_fences(model.generate_content(prompt).text)
            full_path = project_dir / fix_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(fixed, encoding="utf-8")
            updated_codes[fix_path] = fixed
            print(f"[DevAgent] 🔧 Fixed: {fix_path}")
        except Exception as e:
            if _is_rate_limit(e):
                raise RateLimitError(str(e))
            print(f"[DevAgent] ⚠️ Could not fix {fix_path}: {e}")

    return updated_codes


# ── orchestrator ────────────────────────────────────────────────────────────

def _build_project(description: str, language: str, project_name: str,
                   timeout: int, speak=None, player=None) -> str:

    def log(msg: str):
        print(f"[DevAgent] {msg}")
        if player:
            player.write_log(f"[DevAgent] {msg}")

    def done(msg: str):
        if speak:
            speak(msg)
        return msg

    log("Planning project structure...")
    try:
        plan = _plan_project(description, language)
    except RateLimitError:
        return done("Rate limit reached, sir. Please try again in a moment.")
    except ValueError as e:
        return done(f"Planning failed: {e}")

    name         = project_name or plan.get("project_name", "jarvis_project")
    project_dir  = _resolve_project_dir(name, description)
    files        = plan.get("files", [])
    entry_point  = plan.get("entry_point", "main.py")
    run_command  = plan.get("run_command", f"python {entry_point}")
    dependencies = plan.get("dependencies", [])
    is_web       = any(f.get("path", "").lower().endswith((".html", ".htm")) for f in files)

    log(f"Project: {project_dir.name} | Files: {len(files)} | Entry: {entry_point}")

    file_codes: dict[str, str] = {}
    for file_info in sorted(files, key=lambda fi: len(fi.get("imports", []))):
        file_path = file_info.get("path", "")
        if not file_path:
            continue
        log(f"Writing {file_path}...")
        for attempt in range(2):
            try:
                file_codes[file_path] = _write_file(
                    file_info=file_info, project_description=description,
                    all_files=files, language=language,
                    project_dir=project_dir, already_written=file_codes)
                time.sleep(0.4)
                break
            except RateLimitError:
                if attempt == 0:
                    log("Rate limit — waiting 20s...")
                    time.sleep(20)
                else:
                    log(f"Rate limit retry failed for {file_path}, skipping.")
            except Exception as e:
                log(f"Failed to write {file_path}: {e}")
                break

    if not file_codes:
        return done("I could not write any project files, sir.")

    if dependencies:
        log(_install_dependencies(dependencies, project_dir))

    # 1) deterministic verify → fix → re-verify
    log("Verifying files (compile / structure / assets)...")
    problems  = _verify_project(project_dir, files, entry_point)
    verify_rounds = 0
    while problems and verify_rounds < 2:
        verify_rounds += 1
        log(f"Fixing {len(problems)} verification issue(s)...")
        try:
            file_codes.update(_fix_files(
                error_output="Build verification found these issues:\n" + "\n".join(problems),
                project_description=description, all_files=files, file_codes=file_codes,
                language=language, project_dir=project_dir, entry_point=entry_point))
        except RateLimitError:
            break
        except Exception as e:
            log(f"Fix step failed: {e}")
            break
        problems = _verify_project(project_dir, files, entry_point)

    # 2) LLM self-review
    try:
        updated = _review_and_fix(project_dir, file_codes, description, language)
        if updated:
            log(f"Self-review improved {len(updated)} file(s).")
            file_codes.update(updated)
    except RateLimitError:
        pass
    except Exception as e:
        log(f"Self-review skipped: {e}")

    # 3) design polish (web only)
    if is_web:
        try:
            updated = _polish_web_ui(project_dir, file_codes)
            if updated:
                log(f"Design polish updated {len(updated)} file(s).")
                file_codes.update(updated)
        except RateLimitError:
            pass
        except Exception as e:
            log(f"Design polish skipped: {e}")

    # 4) final verify-and-fix
    problems = _verify_project(project_dir, files, entry_point)
    if problems:
        try:
            file_codes.update(_fix_files(
                error_output="Final verification issues:\n" + "\n".join(problems),
                project_description=description, all_files=files, file_codes=file_codes,
                language=language, project_dir=project_dir, entry_point=entry_point))
        except Exception:
            pass
        problems = _verify_project(project_dir, files, entry_point)

    _open_vscode(project_dir)

    web      = _is_web(file_codes, entry_point)
    verified: list[str] = []

    def _show(problems: list[str]):
        if problems:
            log(f"Checker found {len(problems)} problem(s):")
            for pr in problems[:6]:
                log(f"   · {pr}")
        else:
            log("Checker passed: files exist, they parse, every link resolves.")

    problems = _verify_project(project_dir, file_codes, entry_point)
    _show(problems)
    if not problems:
        verified.append("every file parses and every local link resolves")

    if not problems:
        log("Reviewing my own output...")
        issues = []
        try:
            issues = _self_review(project_dir, file_codes, description, language)
        except RateLimitError:
            log("Rate limit during review — skipping it.")
        if issues:
            log(f"Reviewer flagged {len(issues)} issue(s) — fixing them.")
            try:
                file_codes.update(_apply_issues(project_dir, file_codes, issues,
                                                description, language))
                verified.append(f"self-review found and fixed {len(issues)} issue(s)")
            except RateLimitError:
                log("Rate limit while applying the fixes — leaving them.")
        else:
            verified.append("self-review found nothing to fix")
        problems = _verify_project(project_dir, file_codes, entry_point)
        if problems:
            _show(problems)

    if web and not problems:
        log("Polishing the design...")
        try:
            if _polish_web_ui(project_dir, file_codes, description):
                verified.append("design pass applied")
        except RateLimitError:
            log("Rate limit during the design pass — skipping it.")
        problems = _verify_project(project_dir, file_codes, entry_point)
        if problems:
            _show(problems)

    last_output   = ""
    auto_installs = 0

    for attempt in range(1, MAX_FIX_ATTEMPTS + 1):
        log(f"Running project (attempt {attempt}/{MAX_FIX_ATTEMPTS})...")
        last_output = _run_project(run_command, project_dir, timeout,
                                   entry=entry_point)
        log(f"Output preview: {last_output[:150]}")

        if not _has_error(last_output, run_command):
            return _report(proj_name, project_dir, last_output, verified,
                           speak, attempts=attempt)

        if attempt == MAX_FIX_ATTEMPTS:
            break

        error_type = _classify_error(last_output)
        if error_type == "dependency_error" and auto_installs < 3:
            installed = _try_auto_install(last_output, project_dir)
            if installed:
                auto_installs += 1
                log("Missing dependency installed, retrying...")
                time.sleep(1)
                continue

        log(f"Fixing errors (type: {error_type})...")
        try:
            updated = _fix_files(
                error_output=last_output,
                project_description=description,
                all_files=files,
                file_codes=file_codes,
                language=language,
                project_dir=project_dir,
                entry_point=entry_point,
            )
            file_codes.update(updated)
            time.sleep(1)
        except RateLimitError:
            msg = "Rate limit reached during fix. Project saved, check it manually in VSCode."
            if speak: speak(msg)
            return msg
        except Exception as e:
            log(f"Fix step failed: {e}")

    msg = (f"I couldn't get '{proj_name}' running cleanly after "
           f"{MAX_FIX_ATTEMPTS} attempts, sir. It is saved at {project_dir} — "
           f"open it in VSCode and I'll dig in further if you want.")
    if speak: speak(msg)
    return f"{msg}\n\nLast error:\n{last_output[:600]}"

def dev_agent(parameters: dict, response=None, player=None,
              session_memory=None, speak=None) -> str:
    p            = parameters or {}
    description  = p.get("description", "").strip()
    language     = p.get("language", "python").strip()
    project_name = p.get("project_name", "").strip()
    timeout      = int(p.get("timeout", 30))

    if not description:
        return "Please describe the project you want me to build, sir."

    return _build_project(description=description, language=language,
                          project_name=project_name, timeout=timeout,
                          speak=speak, player=player)


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "dev_agent",
    "description": "Builds a complete multi-file project from scratch and proves it before reporting: plans it, writes every file, checks each one compiles/parses and that every local link resolves, reviews its own output, polishes the design of a web page, runs it (serving a page over a local HTTP server) and fixes whatever fails.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "description":  {"type": "STRING", "description": "What the project should do"},
            "language":     {"type": "STRING", "description": "Programming language (default: python)"},
            "project_name": {"type": "STRING", "description": "Optional project folder name"},
            "timeout":      {"type": "INTEGER", "description": "Run timeout in seconds (default: 30)"}
        },
        "required": ["description"]
    },
    "handler": dev_agent,
}
