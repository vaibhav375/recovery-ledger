"""TRAI TCCCPR: after opt-out, no consent requests for 90 days unless the
customer opts back in (spec section 9.2). RETRY and WAIT are exempt — neither
is customer contact, and opting out of messages doesn't withdraw payment
authorisation."""

from __future__ import annotations

from datetime import timedelta

from recovery_ledger.events.actions import ActionType
from recovery_ledger.kernel.certificate import RuleResult
from recovery_ledger.kernel.engine import RuleContext

COOLING_PERIOD_DAYS = 90


class OptOutRule:
    name = "TCCCPR.OPT_OUT.COOLING"

    def evaluate(self, context: RuleContext) -> RuleResult:
        if context.action_type in (ActionType.RETRY, ActionType.WAIT):
            return RuleResult(
                rule_name=self.name, passed=True,
                detail={"exempt": True, "reason": "not customer contact"},
            )
        customer = context.case.customer
        if not customer.opted_out:
            return RuleResult(rule_name=self.name, passed=True, detail={"opted_out": False})

        cooling_until = None
        if customer.opted_out_at is not None:
            cooling_until = customer.opted_out_at + timedelta(days=COOLING_PERIOD_DAYS)
        still_cooling = cooling_until is None or context.now_ist < cooling_until
        return RuleResult(
            rule_name=self.name,
            passed=not still_cooling,
            detail={
                "opted_out": True,
                "opted_out_at": str(customer.opted_out_at),
                "cooling_until": str(cooling_until),
                "still_cooling": still_cooling,
            },
        )
