"""
VORNEX Controlled Action Executor.

Only explicitly allowlisted actions may execute.
Every execution must return an ActionResult.
No arbitrary tool dispatch. No code execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from core.action_result import ActionResult, failed, unverified, verified


@dataclass(frozen=True)
class ActionSpec:
    name: str
    handler: Callable[..., ActionResult]
    requires_confirmation: bool = False


class ControlledExecutor:
    def __init__(self):
        self._actions: dict[str, ActionSpec] = {}

    def register(
        self,
        name: str,
        handler: Callable[..., ActionResult],
        *,
        requires_confirmation: bool = False,
    ) -> None:
        if not name or name.startswith("_"):
            raise ValueError("invalid action name")

        if name in self._actions:
            raise ValueError(f"action already registered: {name}")

        self._actions[name] = ActionSpec(
            name=name,
            handler=handler,
            requires_confirmation=requires_confirmation,
        )

    def allowed(self, name: str) -> bool:
        return name in self._actions

    def requires_confirmation(self, name: str) -> bool:
        spec = self._actions.get(name)
        return bool(spec and spec.requires_confirmation)

    def execute(self, name: str, **kwargs: Any) -> ActionResult:
        spec = self._actions.get(name)

        if spec is None:
            return failed(f"Action '{name}' is not allowlisted")

        try:
            result = spec.handler(**kwargs)
        except Exception as exc:
            return failed(f"Action '{name}' failed: {exc}")

        if not isinstance(result, ActionResult):
            return failed(
                f"Action '{name}' returned invalid result type"
            )

        return result

    def snapshot(self) -> dict[str, dict[str, Any]]:
        return {
            name: {
                "requires_confirmation": spec.requires_confirmation,
            }
            for name, spec in self._actions.items()
        }
