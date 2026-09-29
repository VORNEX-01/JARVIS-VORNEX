"""One rule for the whole assistant: no success claim without evidence.

Any action that says it "did" something must return an ActionResult whose
status is "verified" ONLY when an independent signal proves it. "verified"
cannot even be constructed without evidence - that is enforced here, not by
trusting callers.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class ActionResult:
    status: str          # "verified" | "unverified" | "failed"
    summary: str
    evidence: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "verified"


def verified(summary: str, evidence: str) -> ActionResult:
    if not str(evidence or "").strip():
        raise ValueError("verified() requires non-empty evidence")
    return ActionResult("verified", summary, str(evidence))


def unverified(summary: str) -> ActionResult:
    """The action was attempted but no independent signal proves it worked."""
    return ActionResult("unverified", summary)


def failed(summary: str) -> ActionResult:
    return ActionResult("failed", summary)
