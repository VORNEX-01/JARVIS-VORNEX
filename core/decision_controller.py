"""
VORNEX Decision Controller.

Turns diagnostic events into bounded decisions.
This layer does NOT execute tools, modify files, or perform risky actions.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Decision:
    kind: str
    reason: str
    data: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)


class DecisionController:
    ALLOWED_EVENTS = {
        "tool_failure",
        "resource_warning",
        "health_check_failed",
        "reconnect_requested",
    }

    def decide(self, event, diagnostics) -> Decision | None:
        kind = getattr(event, "kind", "")
        data = dict(getattr(event, "data", {}) or {})

        if kind not in self.ALLOWED_EVENTS:
            return None

        if kind == "tool_failure":
            return Decision(
                kind="diagnose_tool_failure",
                reason="tool_failure",
                data={
                    "tool": data.get("tool", ""),
                    "error": data.get("error", ""),
                },
            )

        if kind == "resource_warning":
            return Decision(
                kind="diagnose_resource",
                reason="resource_warning",
                data={
                    "resource": data.get("resource", ""),
                    "value": data.get("value"),
                },
            )

        if kind == "health_check_failed":
            return Decision(
                kind="diagnose_health_check",
                reason="health_check_failed",
                data={
                    "error": data.get("error", ""),
                },
            )

        if kind == "reconnect_requested":
            return Decision(
                kind="observe_reconnect",
                reason="reconnect_requested",
                data={
                    "reason": data.get("reason", ""),
                    "keep_context": bool(data.get("keep_context", True)),
                },
            )

        return None
