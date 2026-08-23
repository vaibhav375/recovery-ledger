"""Contact budget per customer per rolling window (spec section 8.3 / 9.1).
Not tied to a specific regulation — an internal policy ceiling that also
backs stopping rule 3 (budget exhausted, section 10)."""

from __future__ import annotations

from recovery_ledger.events.actions import ActionType
from recovery_ledger.kernel.certificate import RuleResult
from recovery_ledger.kernel.engine import RuleContext


class ContactBudgetRule:
    name = "POLICY.CONTACT_BUDGET"

    def evaluate(self, context: RuleContext) -> RuleResult:
        if context.action_type in (ActionType.RETRY, ActionType.WAIT):
            return RuleResult(
                rule_name=self.name, passed=True,
                detail={"exempt": True, "reason": "not customer contact"},
            )
        ok = context.attempts_in_window < context.attempt_cap
        return RuleResult(
            rule_name=self.name,
            passed=ok,
            detail={
                "attempt": context.attempts_in_window + 1,
                "cap": context.attempt_cap,
                "window_days": context.window_days,
                "ok": ok,
            },
        )
