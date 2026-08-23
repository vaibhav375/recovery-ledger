"""Digital Personal Data Protection Act, 2023 (spec section 9.2: "purpose
limitation, consent record, retention").

DPDPA's requirements are mostly structural, not per-action predicates:
purpose limitation and retention are properties of what the system stores
and for how long (this project's event schemas hold only the fields each
loss type actually needs — no incidental PII — and the ledger has no
automatic purge/retention policy yet, which is an honest gap, not a solved
problem; see COMPLIANCE.md). The one part of DPDPA that *does* reduce to a
per-action check is: don't contact someone you hold no consent record for
at all.
"""

from __future__ import annotations

from recovery_ledger.events.actions import ActionType
from recovery_ledger.kernel.certificate import RuleResult
from recovery_ledger.kernel.engine import RuleContext


class ConsentRecordExistsRule:
    name = "DPDPA.CONSENT_RECORD"

    def evaluate(self, context: RuleContext) -> RuleResult:
        if context.action_type in (ActionType.RETRY, ActionType.WAIT):
            return RuleResult(rule_name=self.name, passed=True, detail={"exempt": True})
        ok = context.consent.captured_at is not None
        return RuleResult(rule_name=self.name, passed=ok, detail={"captured_at": str(context.consent.captured_at)})
