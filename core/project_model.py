"""A fresh map of the WHOLE project - every module, class, function, signature.
Nothing is imported (safe). Writes .jarvis/project_model.json and surfaces the
duplicate top-level defs that appending patches created."""
from __future__ import annotations
import ast, hashlib, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / ".jarvis" / "project_model.json"


def scan():
    model = {}
    for p in sorted(ROOT.rglob("*.py")):
        if any(x in p.parts for x in (".git", "__pycache__", ".jarvis")):
            continue
        try:
            src = p.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(src)
        except Exception:
            continue
        defs = []
        for n in tree.body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defs.append({"kind": "def", "name": n.name, "line": n.lineno,
                             "args": [a.arg for a in n.args.args]})
            elif isinstance(n, ast.ClassDef):
                defs.append({"kind": "class", "name": n.name, "line": n.lineno})
        names = [d["name"] for d in defs if d["kind"] == "def"]
        dup = sorted({x for x in names if names.count(x) > 1})
        model[str(p.relative_to(ROOT)).replace("\\", "/")] = {
            "sha1": hashlib.sha1(src.encode()).hexdigest(), "defs": defs, "duplicate_defs": dup}
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(model, indent=1, ensure_ascii=False), encoding="utf-8")
    return model


def summary():
    m = scan()
    return {"files": len(m),
            "duplicate_defs": {f: v["duplicate_defs"] for f, v in m.items() if v["duplicate_defs"]}}
