"""
VORNEX Diagnostic Controller.

Consumes runtime events and produces bounded diagnostic state.
No tool execution. No file writes. No self-repair.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DiagnosticState:
    events: int = 0
    tool_failures: int = 0
    reconnects: int = 0
    reconnect_verified: int = 0
    resource_warnings: int = 0
    health_failures: int = 0
    last_event: str = ""
    last_error: str = ""
    last_update: float = 0.0
    recent: list[dict[str, Any]] = field(default_factory=list)


class DiagnosticController:
    MAX_RECENT = 32

    def __init__(self):
        self.state = DiagnosticState()

    def handle(self, event) -> dict[str, Any]:
        kind = getattr(event, "kind", "")
        data = dict(getattr(event, "data", {}) or {})

        self.state.events += 1
        self.state.last_event = kind
        self.state.last_update = time.time()

        if kind == "tool_failure":
            self.state.tool_failures += 1
            self.state.last_error = str(data.get("error", ""))

        elif kind == "reconnect_requested":
            self.state.reconnects += 1

        elif kind == "reconnect_verified":
            self.state.reconnect_verified += 1

        elif kind == "resource_warning":
            self.state.resource_warnings += 1

        elif kind == "health_check_failed":
            self.state.health_failures += 1
            self.state.last_error = str(data.get("error", ""))

        record = {
            "kind": kind,
            "data": data,
            "ts": getattr(event, "ts", time.time()),
        }

        self.state.recent.append(record)
        if len(self.state.recent) > self.MAX_RECENT:
            del self.state.recent[:-self.MAX_RECENT]

        return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        return {
            "events": self.state.events,
            "tool_failures": self.state.tool_failures,
            "reconnects": self.state.reconnects,
            "reconnect_verified": self.state.reconnect_verified,
            "resource_warnings": self.state.resource_warnings,
            "health_failures": self.state.health_failures,
            "last_event": self.state.last_event,
            "last_error": self.state.last_error,
            "last_update": self.state.last_update,
            "recent": list(self.state.recent),
        }
