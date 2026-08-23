"""RBI Digital Payments E-Mandate Framework, 2026 (spec section 9.2).

Only the pre-debit notification requirement is encoded so far — the only
rule that maps onto an action this project currently models. AFA
(Additional Factor Authentication) requirements for mandate registration,
modification, or withdrawal don't have a corresponding ActionType yet (the
agent loop only retries/nudges/negotiates/escalates against an *existing*
mandate; it never registers or modifies one) — noted as not-yet-applicable
in COMPLIANCE.md rather than encoded against nothing.
"""

from __future__ import annotations

from datetime import timedelta

from recovery_ledger.events.actions import ActionType
from recovery_ledger.events.schemas import FailedSubscriptionCase
from recovery_ledger.kernel.certificate import RuleResult
from recovery_ledger.kernel.engine import RuleContext

MIN_HOURS_BEFORE_DEBIT = 24


class PreDebitNotificationRule:
    """Pre-debit notification at least 24 hours before debit, with
    transaction details and an opt-out option. Applies when the candidate
    action is a debit attempt (RETRY) against a mandate-backed case."""

    name = "EMANDATE2026.PRE_DEBIT_NOTICE"

    def evaluate(self, context: RuleContext) -> RuleResult:
        is_mandate_debit_attempt = (
            context.action_type == ActionType.RETRY
            and isinstance(context.case, FailedSubscriptionCase)
        )
        if not is_mandate_debit_attempt:
            return RuleResult(rule_name=self.name, passed=True, detail={"exempt": True})

        sent_at = context.mandate.pre_debit_notice_sent_at
        if sent_at is None:
            return RuleResult(
                rule_name=self.name, passed=False,
                detail={"pre_debit_notice_sent_at": None},
            )

        hours_before = (context.now_ist - sent_at) / timedelta(hours=1)
        ok = hours_before >= MIN_HOURS_BEFORE_DEBIT
        return RuleResult(
            rule_name=self.name, passed=ok,
            detail={
                "pre_debit_notice_sent_at": str(sent_at),
                "hours_before_debit": round(hours_before, 2),
                "min_required_hours": MIN_HOURS_BEFORE_DEBIT,
            },
        )
