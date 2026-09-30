"""
VORNEX Decision Controller.

Converts bounded diagnostic events into allowlisted runtime decisions.
No direct tool execution. No file writes.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Decision:
    kind: str
    reason: str
    data: dict[str, Any]


class DecisionController:
    TOOL_FAILURE_THRESHOLD = 3
    RECOVERY_COOLDOWN = 60.0

    DECISION_ACTIONS = {
        "diagnose_health_check": "health_check",
        "diagnose_tool_failure": "runtime_status",
        "diagnose_resource": "runtime_status",
        "observe_reconnect": "runtime_status",
        "recover_reconnect": "request_reconnect",
    }

    ALLOWED_EVENTS = {
        "tool_failure",
        "resource_warning",
        "health_check_failed",
        "reconnect_requested",
    }

    def __init__(self):
        self._last_recovery = 0.0

    def _recovery_allowed(self) -> bool:
        now = time.monotonic()
        if now - self._last_recovery < self.RECOVERY_COOLDOWN:
            return False
        self._last_recovery = now
        return True

    def decide(self, event, diagnostics) -> Decision | None:
        kind = getattr(event, "kind", "")
        data = dict(getattr(event, "data", {}) or {})

        if kind not in self.ALLOWED_EVENTS:
            return None

        if kind == "tool_failure":
            snapshot = diagnostics.snapshot()
            failures = int(snapshot.get("tool_failures", 0))

            if (
                failures >= self.TOOL_FAILURE_THRESHOLD
                and self._recovery_allowed()
            ):
                return Decision(
                    kind="recover_reconnect",
                    reason="repeated_tool_failures",
                    data={
                        "tool": data.get("tool", ""),
                        "error": data.get("error", ""),
                        "failures": failures,
                        "action": self.DECISION_ACTIONS["recover_reconnect"],
                    },
                )

            return Decision(
                kind="diagnose_tool_failure",
                reason="tool_failure",
                data={
                    "tool": data.get("tool", ""),
                    "error": data.get("error", ""),
                    "failures": failures,
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
            if self._recovery_allowed():
                return Decision(
                    kind="recover_reconnect",
                    reason="health_check_failed",
                    data={
                        "error": data.get("error", ""),
                        "action": self.DECISION_ACTIONS["recover_reconnect"],
                    },
                )

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
