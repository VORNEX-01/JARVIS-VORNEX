"""Read-only look at a window's UI Automation tree. Prints every Edit /
ComboBox / Document / List control with its name, rectangle, offscreen and
enabled state, class, automation id, and current Value. Writes nothing and
types nothing — it only reads, so it is safe to run with Telegram open.

    python tools/uia_probe.py Telegram
"""
import sys
import uiautomation as auto

FRAG = sys.argv[1] if len(sys.argv) > 1 else "Telegram"


def val_of(c):
    try:
        return repr(c.GetValuePattern().Value)
    except Exception as e:
        return "<none:%s>" % type(e).__name__


def find_window(frag):
    root = auto.GetRootControl()
    try:
        for w in root.GetChildren():
            try:
                if frag.lower() in (w.Name or "").lower():
                    return w
            except Exception:
                pass
    except Exception:
        pass
    return None


lines = []


def walk(c, d):
    if d > 12:
        return
    try:
        kids = c.GetChildren()
    except Exception:
        kids = []
    for x in kids:
        try:
            ct = x.ControlTypeName or ""
            low = ct.lower()
            if ("edit" in low or "combobox" in low or "document" in low
                    or "list" in low):
                r = x.BoundingRectangle

                def g(name):
                    try:
                        return getattr(x, name)
                    except Exception:
                        return "?"

                line = ("%s%-16s %-26r (%d,%d,%d,%d) off=%-5s en=%-5s cls=%-22r id=%r"
                        % ("  " * d, ct, (x.Name or "")[:24],
                           r.left, r.top, r.right, r.bottom,
                           g("IsOffscreen"), g("IsEnabled"),
                           g("ClassName"), g("AutomationId")))
                if "edit" in low or "combobox" in low or "document" in low:
                    line += "  VALUE=" + val_of(x)
                lines.append(line)
        except Exception as e:
            lines.append("%s<err %s>" % ("  " * d, e))
        walk(x, d + 1)


w = find_window(FRAG)
if w is None:
    lines.append("NO WINDOW matching %r — open it first and leave it visible." % FRAG)
else:
    lines.append("WINDOW: %r class=%r pid=%s" % (w.Name, w.ClassName, w.ProcessId))
    walk(w, 0)

text = "\n".join(lines) or "(nothing found)"
print(text)
try:
    open("tools/_uia_probe.txt", "w", encoding="utf-8").write(text)
except Exception:
    pass
