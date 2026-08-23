"""What happens to a case when the agent finishes working it — for now.

A case does not always *end*. Spec section 10, stopping rule 6 is "promise
to pay — pause until the promised date + grace, then re-evaluate", which is
a suspension, not a termination. Returning a bare `StopReason` from
`run_case` cannot express that difference, and treating a promise as an
ending abandons the case at exactly the moment the customer signalled they
intend to pay.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from recovery_ledger.events.actions import StopReason


@dataclass(frozen=True)
class CaseOutcome:
    case_id: str
    status: Literal["terminated", "paused"]
    stop_reason: StopReason | None = None
    resume_at: datetime | None = None
    pause_reason: StopReason | None = None

    def __post_init__(self) -> None:
        if self.status == "terminated":
            if self.stop_reason is None:
                raise ValueError("a terminated outcome must carry a stop_reason")
            if self.resume_at is not None:
                raise ValueError("a terminated outcome must not carry a resume_at")
        else:
            if self.resume_at is None:
                raise ValueError("a paused outcome must carry a resume_at")
            if self.stop_reason is not None:
                raise ValueError("a paused outcome is not terminated; use pause_reason")

    @property
    def is_terminated(self) -> bool:
        return self.status == "terminated"

    @classmethod
    def terminated(cls, case_id: str, reason: StopReason) -> "CaseOutcome":
        return cls(case_id=case_id, status="terminated", stop_reason=reason)

    @classmethod
    def paused(cls, case_id: str, resume_at: datetime, reason: StopReason) -> "CaseOutcome":
        return cls(case_id=case_id, status="paused", resume_at=resume_at, pause_reason=reason)
