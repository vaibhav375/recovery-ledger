"""RBI recovery-agent norms: no harassment or intimidation — encode
intensity ceilings on tone escalation (spec section 9.2). This is also the
machine-checked half of B2 ("compliant escalation... every rung is legally
justified"): the ceiling only loosens as genuine attempt history
accumulates, it's never a free choice made per-message.
"""

from __future__ import annotations

from recovery_ledger.events.actions import ActionType
from recovery_ledger.kernel.certificate import RuleResult
from recovery_ledger.kernel.engine import RuleContext

# attempt index (0-based) -> maximum permitted tone_intensity (0=neutral .. 3=firm)
TONE_CEILING_BY_ATTEMPT = {0: 1, 1: 2}
TONE_CEILING_DEFAULT = 3  # attempt 2 and beyond


class ToneIntensityCeilingRule:
    name = "RBI.RECOVERY.TONE_CEILING"

    def evaluate(self, context: RuleContext) -> RuleResult:
        if context.action_type == ActionType.RETRY:
            return RuleResult(rule_name=self.name, passed=True, detail={"exempt": True})
        ceiling = TONE_CEILING_BY_ATTEMPT.get(context.attempts_in_window, TONE_CEILING_DEFAULT)
        ok = context.tone_intensity <= ceiling
        return RuleResult(
            rule_name=self.name, passed=ok,
            detail={
                "attempt": context.attempts_in_window,
                "tone_intensity": context.tone_intensity,
                "ceiling": ceiling,
            },
        )
