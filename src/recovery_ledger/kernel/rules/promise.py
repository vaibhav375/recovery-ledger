"""Promise-to-pay silence window (spec section 10, rule 6).

A customer who says "I'll pay on the 5th" has made a commitment, and the
agent honouring it is not merely good manners — contacting them on the 3rd
anyway is the pattern the RBI recovery-agent norms on harassment exist to
prevent. So the promise window belongs in the compliance kernel as an
admissibility rule that emits a certificate, not in the agent loop as
private control flow. That way the audit trail shows *why* the agent went
quiet, which is the whole point of B4.

Silent actions (RETRY, WAIT) are exempt: a promise concerns not being
pestered, and does not withdraw payment authorisation.
"""

from __future__ import annotations

from recovery_ledger.events.actions import ActionType
from recovery_ledger.kernel.certificate import RuleResult
from recovery_ledger.kernel.engine import RuleContext


class PromiseToPayWindowRule:
    name = "POLICY.PROMISE_TO_PAY_WINDOW"

    def evaluate(self, context: RuleContext) -> RuleResult:
        if context.action_type in (ActionType.RETRY, ActionType.WAIT):
            return RuleResult(
                rule_name=self.name, passed=True,
                detail={"exempt": True, "reason": "not customer contact"},
            )
        promised_until = context.promise_to_pay_until
        if promised_until is None:
            return RuleResult(rule_name=self.name, passed=True, detail={"promise_active": False})

        inside_window = context.now_ist < promised_until
        return RuleResult(
            rule_name=self.name,
            passed=not inside_window,
            detail={
                "promise_active": True,
                "promised_payment_by": str(promised_until),
                "now_ist": str(context.now_ist),
                "inside_silence_window": inside_window,
            },
        )
