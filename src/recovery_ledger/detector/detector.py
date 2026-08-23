"""Case-level detector (spec section 5.1). Stub for now: every ingested case
starts at-risk and stays at-risk until the loop observes a resolution signal
(a "paid" reply, or — once wired — a webhook). Fleet-level degradation
detection (change-point + contribution attribution, spec section 8.4, N6) is
a separate, later component; this module only answers "is this one case
still worth working."
"""

from __future__ import annotations

from recovery_ledger.events.schemas import RecoveryCase


class CaseDetector:
    def is_at_risk(self, case: RecoveryCase, *, resolved: bool) -> bool:
        return not resolved
