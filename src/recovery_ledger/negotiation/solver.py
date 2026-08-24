"""Negotiation economics (spec section 9.4).

Division of labour, and it is the point of this module rather than an
implementation detail:

- the **LLM** runs the conversation (wording, tone, language)
- this **solver** runs the economics
- the **kernel** governs what may be conceded

An LLM asked "should I offer 6% to settle today?" will produce a fluent,
confident answer that is not arithmetic. Whether a discount is worth taking
is a net-present-value question with an exact answer, so it gets one.

The core quantity is the **breakeven discount**: the largest discount at
which taking cash now still beats waiting for the full amount.

    A x (1 - d)  =  A / (1 + r)^(days / 365)
    =>  d_breakeven = 1 - (1 + r)^(-days / 365)

Above that line a discount destroys value even if the counterparty accepts.
Everything the agent may actually offer is then further clipped by the
merchant's policy envelope — the solver proposes, the envelope disposes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class OfferType(str, Enum):
    NONE = "none"
    EARLY_PAYMENT_DISCOUNT = "early_payment_discount"
    INSTALMENT_PLAN = "instalment_plan"
    EXTENDED_TERMS = "extended_terms"


@dataclass(frozen=True)
class PolicyEnvelope:
    """Merchant-set bounds on the agent's authority to concede. The agent
    cannot exceed these, and the compliance kernel enforces it rather than
    trusting the policy to behave (see kernel/rules/negotiation.py)."""

    max_discount_pct: float = 0.04          # never concede more than 4%
    max_extension_days: int = 60            # never extend past 60 days
    max_instalments: int = 3
    human_escalation_above: float = 500_000.0   # Rs 5L to a human


@dataclass(frozen=True)
class Offer:
    offer_type: OfferType
    discount_pct: float = 0.0
    extension_days: int = 0
    instalments: int = 1
    rationale: str = ""
    npv_gain: float = 0.0

    @property
    def conceded_value(self) -> float:
        return self.discount_pct


def breakeven_discount(expected_delay_days: float, annual_discount_rate: float) -> float:
    """Largest NPV-neutral discount for pulling payment forward by
    `expected_delay_days`."""
    if expected_delay_days <= 0:
        return 0.0
    return 1.0 - (1.0 + annual_discount_rate) ** (-expected_delay_days / 365.0)


@dataclass
class NegotiationSolver:
    annual_discount_rate: float = 0.18       # merchant cost of capital
    envelope: PolicyEnvelope = PolicyEnvelope()

    def best_offer(
        self,
        *,
        amount: float,
        expected_delay_days: float,
        counterparty_wants_time: bool = False,
        days_until_43bh_deadline: int | None = None,
    ) -> Offer:
        """Choose the offer that maximises NPV within the envelope.

        `days_until_43bh_deadline`, when present, is leverage rather than a
        cost: the counterparty has their own reason to settle before it, so
        the agent should not pay for behaviour it can get for free.
        """
        if amount > self.envelope.human_escalation_above:
            return Offer(
                OfferType.NONE,
                rationale=(
                    f"Rs {amount:,.0f} exceeds the Rs "
                    f"{self.envelope.human_escalation_above:,.0f} autonomy limit; "
                    f"a human must handle this negotiation."
                ),
            )

        breakeven = breakeven_discount(expected_delay_days, self.annual_discount_rate)
        affordable = min(breakeven, self.envelope.max_discount_pct)

        # Leverage first. If the counterparty is inside their own 43B(h)
        # window they already have a tax reason to settle, so conceding
        # margin buys something that is available for nothing.
        if days_until_43bh_deadline is not None and 0 < days_until_43bh_deadline <= 21:
            return Offer(
                OfferType.NONE,
                rationale=(
                    f"No discount offered: {days_until_43bh_deadline} days remain in the "
                    f"counterparty's 45-day MSME window, so settling early is already in "
                    f"their interest under Section 43B(h). Leverage, not margin."
                ),
            )

        if counterparty_wants_time:
            extension = min(self.envelope.max_extension_days, 30)
            return Offer(
                OfferType.EXTENDED_TERMS,
                extension_days=extension,
                rationale=(
                    f"Counterparty asked for time. {extension} extra days costs "
                    f"~{breakeven_discount(extension, self.annual_discount_rate):.2%} in NPV "
                    f"and is within the {self.envelope.max_extension_days}-day envelope."
                ),
            )

        if affordable <= 0.0025:      # below ~0.25% a discount is not worth the message
            return Offer(
                OfferType.NONE,
                rationale=(
                    f"Breakeven discount is only {breakeven:.2%}; too little to be worth "
                    f"conceding. Ask for payment on existing terms."
                ),
            )

        gain = amount * (breakeven - affordable) if breakeven > affordable else 0.0
        return Offer(
            OfferType.EARLY_PAYMENT_DISCOUNT,
            discount_pct=affordable,
            npv_gain=gain,
            rationale=(
                f"{affordable:.2%} early-payment discount. Breakeven at "
                f"{breakeven:.2%} for a {expected_delay_days:.0f}-day delay at "
                f"{self.annual_discount_rate:.0%} cost of capital; envelope caps at "
                f"{self.envelope.max_discount_pct:.0%}."
            ),
        )
