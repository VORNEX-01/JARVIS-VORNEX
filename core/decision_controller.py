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
    DECISION_ACTIONS = {
        "diagnose_health_check": "health_check",
        "diagnose_tool_failure": "runtime_status",
        "diagnose_resource": "runtime_status",
        "observe_reconnect": "runtime_status",
    }

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
                    "action": self.DECISION_ACTIONS["diagnose_tool_failure"],
                },
            )

        if kind == "resource_warning":
            return Decision(
                kind="diagnose_resource",
                reason="resource_warning",
                data={
                    "resource": data.get("resource", ""),
                    "value": data.get("value"),
                    "action": self.DECISION_ACTIONS["diagnose_resource"],
                },
            )

        if kind == "health_check_failed":
            return Decision(
                kind="diagnose_health_check",
                reason="health_check_failed",
                data={
                    "error": data.get("error", ""),
                    "action": self.DECISION_ACTIONS["diagnose_health_check"],
                },
            )

        if kind == "reconnect_requested":
            return Decision(
                kind="observe_reconnect",
                reason="reconnect_requested",
                data={
                    "reason": data.get("reason", ""),
                    "keep_context": bool(data.get("keep_context", True)),
                    "action": self.DECISION_ACTIONS["observe_reconnect"],
                },
            )

        return None
