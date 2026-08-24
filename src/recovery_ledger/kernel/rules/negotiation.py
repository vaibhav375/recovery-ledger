"""Bounded negotiating authority (spec section 9.4).

"The kernel governs what may be conceded — a merchant-set policy envelope,
e.g. never concede >4%, never extend past 60 days, escalate above Rs 5L to
a human."

The point is *where* this check lives. The solver already refuses to exceed
the envelope, so on the happy path this rule never fires — which is exactly
why it belongs in the kernel rather than being left to the solver. Giving
away margin is a money-affecting action, and this project's whole argument
is that money-affecting actions are permitted by a deterministic gate rather
than by the good behaviour of the component that proposed them.

Concretely, this holds even if the solver has a bug, is swapped for a
different one, or an LLM-drafted message is somehow allowed to name a number
of its own. The envelope is enforced at the boundary, not upstream of it.
"""

from __future__ import annotations

from recovery_ledger.events.actions import ActionType
from recovery_ledger.kernel.certificate import RuleResult
from recovery_ledger.kernel.engine import RuleContext

MAX_DISCOUNT_PCT = 0.04
MAX_EXTENSION_DAYS = 60
MAX_INSTALMENTS = 3
HUMAN_ESCALATION_ABOVE = 500_000.0


class NegotiationEnvelopeRule:
    name = "POLICY.NEGOTIATION_ENVELOPE"

    def evaluate(self, context: RuleContext) -> RuleResult:
        # Only negotiation concedes anything. Every other action type is
        # outside this rule's scope.
        if context.action_type != ActionType.NEGOTIATE:
            return RuleResult(
                rule_name=self.name, passed=True,
                detail={"exempt": True, "reason": "action concedes nothing"},
            )

        breaches: list[str] = []
        if context.offer_discount_pct > MAX_DISCOUNT_PCT:
            breaches.append(
                f"discount {context.offer_discount_pct:.2%} exceeds cap {MAX_DISCOUNT_PCT:.0%}"
            )
        if context.offer_extension_days > MAX_EXTENSION_DAYS:
            breaches.append(
                f"extension {context.offer_extension_days}d exceeds cap {MAX_EXTENSION_DAYS}d"
            )
        if context.offer_instalments > MAX_INSTALMENTS:
            breaches.append(
                f"{context.offer_instalments} instalments exceeds cap {MAX_INSTALMENTS}"
            )
        if context.case.amount_at_risk > HUMAN_ESCALATION_ABOVE:
            breaches.append(
                f"amount Rs {context.case.amount_at_risk:,.0f} exceeds autonomy limit "
                f"Rs {HUMAN_ESCALATION_ABOVE:,.0f}; requires a human"
            )

        return RuleResult(
            rule_name=self.name,
            passed=not breaches,
            detail={
                "discount_pct": context.offer_discount_pct,
                "extension_days": context.offer_extension_days,
                "instalments": context.offer_instalments,
                "caps": {
                    "max_discount_pct": MAX_DISCOUNT_PCT,
                    "max_extension_days": MAX_EXTENSION_DAYS,
                    "max_instalments": MAX_INSTALMENTS,
                    "human_escalation_above": HUMAN_ESCALATION_ABOVE,
                },
                "breaches": breaches,
            },
        )
