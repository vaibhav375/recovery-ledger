"""RBI recovery-agent norms: no contact before 08:00 or after 19:00 IST
(spec section 9.2). Silent actions (RETRY) aren't customer contact and are
exempt from the contact-hours window."""

from __future__ import annotations

from recovery_ledger.events.actions import ActionType
from recovery_ledger.kernel.certificate import RuleResult
from recovery_ledger.kernel.engine import RuleContext

CONTACT_WINDOW_START_HOUR = 8
CONTACT_WINDOW_END_HOUR = 19


class ContactHoursRule:
    name = "RBI.RECOVERY.HOURS"

    def evaluate(self, context: RuleContext) -> RuleResult:
        if context.action_type in (ActionType.RETRY, ActionType.WAIT):
            return RuleResult(
                rule_name=self.name, passed=True,
                detail={"exempt": True, "reason": "not customer contact"},
            )
        hour = context.now_ist.hour
        ok = CONTACT_WINDOW_START_HOUR <= hour < CONTACT_WINDOW_END_HOUR
        return RuleResult(
            rule_name=self.name,
            passed=ok,
            detail={
                "now_ist": context.now_ist.strftime("%H:%M"),
                "window": f"{CONTACT_WINDOW_START_HOUR:02d}:00-{CONTACT_WINDOW_END_HOUR:02d}:00",
                "ok": ok,
            },
        )
