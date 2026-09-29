"""
Standalone test harness for actions/send_message.py - no UI, no PyQt.

    python tools/send_test.py --app Telegram --stage describe
    python tools/send_test.py --app Telegram --to "NAME" --stage find
    python tools/send_test.py --app Telegram --to "NAME" --stage search
    python tools/send_test.py --app Telegram --to "NAME" --msg "hi" --stage draft
    python tools/send_test.py --app Telegram --to "NAME" --msg "hi" --stage send --yes

Every stage prints each vision answer and saves the screenshots it looked at.
"""
import argparse
import importlib
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("SM_DEBUG", "1")

sm = importlib.import_module("actions.send_message")


def _open(spec):
    if spec["kind"] == "desktop":
        sm._open_app(spec["app"])
    else:
        sm._open_browser_url(spec.get("url", ""))
    time.sleep(2.0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--app", required=True)
    ap.add_argument("--to", default="")
    ap.add_argument("--msg", default="")
    ap.add_argument("--stage", default="find",
                    choices=["describe", "find", "search", "draft", "send"])
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("--yes", action="store_true", help="required for --stage send")
    a = ap.parse_args()

    spec  = sm._platform_for(a.app)
    hints = sm._DESKTOP_SEARCH_HINTS if spec["kind"] == "desktop" else sm._WEB_SEARCH_HINTS

    print("=" * 66)
    print(f"app    : {spec['app']}   kind: {spec['kind']}")
    print(f"shots  : {sm._DEBUG_DIR}")
    print(f"front  : {sm._foreground_title()!r}")
    print("=" * 66)

    if a.stage == "describe":
        print(sm._look("Describe what is on this screen in 3 short lines: which "
                       "application is in front, and what is visible.", sm._png()))
        return 0

    if not a.no_open and a.stage in ("find", "search"):
        print("opening the app...")
        _open(spec)
        print(f"front  : {sm._foreground_title()!r}")

    if a.stage == "find":
        for hint in hints:
            print(f"\nhint: {hint}")
            print(f"  -> {sm._find(hint)}")
        return 0

    if not a.to:
        print("--to is required for this stage")
        return 2

    if a.stage == "search":
        ok, why = sm._type_in_search(spec["app"], hints, a.to, None)
        print(f"\nname landed: {ok}   {why}")
        return 0 if ok else 1

    if a.stage == "draft":
        state = sm._prepare(spec, a.to, a.msg or "test message", None)
        print(f"\nstate: {state}")
        return 0 if state.get("ok") else 1

    if not a.yes:
        print("refusing to actually send without --yes")
        return 2
    state = sm._prepare(spec, a.to, a.msg or "test message", None)
    if not state.get("ok"):
        print(f"\ncould not prepare: {state.get('reason')}")
        return 1
    print("\n--- pressing send ---")
    print(sm._send_and_verify(state))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
