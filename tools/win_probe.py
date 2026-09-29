"""Read-only perception check.

    python tools/win_probe.py            # what do we see at all?
    python tools/win_probe.py Calc       # match one app + dump its controls
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core import window_agent as wa

q = sys.argv[1] if len(sys.argv) > 1 else ""

print("=== KEPT (windows the agent will consider) ===")
kept = wa.list_windows()
for w in kept:
    print("  %-42r pid=%-7s exe=%-18s cls=%-22r min=%-5s %s"
          % (w["name"][:40], w["pid"], w["exe"], (w.get("cls") or "")[:20],
             w.get("minimized"), w["rect"]))
if not kept:
    print("  (none)")

print("\n=== DROPPED, excluding no-title/invisible noise ===")
for row in wa.raw_windows():
    if "keep=True" in row:
        continue
    if "no-title,invisible" in row:
        continue
    print("  " + row)

if q:
    print("\n=== MATCH for %r ===" % q)
    print("  raised:", wa.activate(win) if (win := wa.find_window(q)) else "n/a")
    procs = wa.find_processes(q)
    if procs:
        print("  processes running: %s"
              % ", ".join("%s(pid %s)" % (n, p) for p, n in procs[:5]))
    if not win:
        print("  no WINDOW — if a process is listed above, it is probably in the tray.")
        sys.exit(0)
    print("  %r exe=%s cls=%r hwnd=%s min=%s"
          % (win["name"], win["exe"], win.get("cls"), win["hwnd"],
             win.get("minimized")))
    print(wa.snapshot_text(win)[:5000])
