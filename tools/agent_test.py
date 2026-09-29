"""Run the desktop loop from the terminal - no UI, no voice.

    python tools/agent_test.py --app Calculator --task "calculate 12 times 7"
    python tools/agent_test.py --app Telegram  --task "..." --yes

--yes auto-CONFIRMs the gate; without it the gate is auto-CANCELLED.
"""
import argparse, importlib, sys, threading, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
wa = importlib.import_module("core.window_agent")
agent = importlib.import_module("core.desktop_agent")
cc = importlib.import_module("core.confirm")

_answer_count = [0]


class _P:
    def write_log(self, m): print("[agent]", m)

def _wire_confirm(auto_yes):
    def _show(t, d): print("[confirm] %s | %s" % (t, d))
    def _hide(): print("[confirm] dismissed")
    cc.bind(_show, _hide, lambda m: print("[sys]", m))
    def _loop():
        seen = None
        while True:
            t = cc.pending_title()
            if t and t != seen:
                seen = t
                print("[confirm] auto-%s in 0.5s" % ("CONFIRM" if auto_yes else "CANCEL"))
                time.sleep(0.5); cc.resolve(auto_yes)
            else:
                if not t: seen = None
                time.sleep(0.2)
    threading.Thread(target=_loop, daemon=True, name="cli-confirm").start()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app", required=True)
    ap.add_argument("--task", required=True)
    ap.add_argument("--details", default="")
    ap.add_argument("--steps", type=int, default=14)
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    _wire_confirm(a.yes)
    win = wa.find_window(a.app)
    print("=" * 66)
    print("app    :", a.app)
    print("task   :", a.task)
    print("window :", win["name"] if win else "NOT FOUND")
    if not win:
        for p, n in wa.find_processes(a.app)[:5]:
            print("  process:", n, "pid", p)
    print("=" * 66)
    t0 = time.time()
    out = agent.run_task(a.task, app=a.app, details=a.details,
                         player=_P(), max_steps=a.steps)
    print("\n(%.1fs) RESULT: %s" % (time.time() - t0, out))
    if cc.pending_title():
        deadline = time.time() + 25
        while time.time() < deadline and cc.pending_title():
            time.sleep(0.3)
        time.sleep(3.0)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
