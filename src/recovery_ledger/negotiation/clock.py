"""Section 43B(h) clock — the counterparty's own tax incentive to pay.

Under Section 43B(h) of the Income Tax Act (inserted by Finance Act 2023,
effective AY 2024-25), a buyer who does not pay an MSME supplier within the
time limit set by Section 15 of the MSMED Act 2006 cannot claim that expense
as a deduction **in the year it was incurred**. The deduction is instead
allowed in the previous year in which payment is *actually* made.

**Being precise about this matters, because the loose version is wrong.**
The deduction is not forfeited — it is *deferred*. The buyer's cost is the
time value of losing it for a year, not the whole amount, plus exposure to
MSMED Act interest. Saying "you lose the deduction" would overstate it, and
a CFO on the other end of this conversation would know that immediately and
stop taking the agent seriously.

The Section 15 limit is **45 days** where there is a written agreement (15
days where there is none). This models the 45-day case, and says so.

Why this is worth encoding at all: it inverts the negotiating position. A
normal dunning agent asks a buyer to do something that costs them money.
An agent that knows this rule is pointing out something in the *buyer's own*
interest — settling before the deadline keeps the deduction in the current
financial year. That is a fundamentally different conversation, and it is
available only for MSME suppliers, which is exactly the counterparty type
this project's B2B receivables track deals with.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

# Section 15, MSMED Act 2006: 45 days where a written agreement exists.
MSME_PAYMENT_WINDOW_DAYS = 45

# Indicative corporate tax rate used to size the deferral cost. A parameter,
# not a fact about any specific buyer — rates vary by entity type and regime.
ASSUMED_CORPORATE_TAX_RATE = 0.25

# Cost of deferring a deduction by roughly one financial year.
ASSUMED_ANNUAL_DISCOUNT_RATE = 0.12


@dataclass(frozen=True)
class Section43BhStatus:
    applies: bool
    days_until_deadline: int
    deadline: datetime | None
    breached: bool
    deferral_cost: float

    @property
    def urgency(self) -> str:
        if not self.applies:
            return "not_applicable"
        if self.breached:
            return "breached"
        if self.days_until_deadline <= 7:
            return "critical"
        if self.days_until_deadline <= 21:
            return "elevated"
        return "routine"

    def leverage_note(self) -> str:
        """One plain sentence an operator (or a drafted message) can stand
        behind. Deliberately understated — the accurate version is more
        persuasive than the exaggerated one, and survives scrutiny."""
        if not self.applies:
            return "Section 43B(h) does not apply to this counterparty."
        if self.breached:
            return (
                f"The 45-day MSME payment window closed {abs(self.days_until_deadline)} days ago. "
                f"Under Section 43B(h) this expense is no longer deductible in the current "
                f"financial year; the deduction moves to the year payment is actually made."
            )
        return (
            f"{self.days_until_deadline} days remain in the 45-day MSME payment window. "
            f"Settling within it keeps this expense deductible in the current financial year "
            f"under Section 43B(h) — worth roughly Rs {self.deferral_cost:,.0f} in deferral "
            f"cost avoided."
        )


def evaluate_43bh(
    *,
    invoice_due_date: datetime,
    now: datetime,
    is_msme_counterparty: bool,
    amount: float,
    tax_rate: float = ASSUMED_CORPORATE_TAX_RATE,
    discount_rate: float = ASSUMED_ANNUAL_DISCOUNT_RATE,
) -> Section43BhStatus:
    """Where the invoice sits against the 45-day clock, and what missing it
    costs the buyer.

    `deferral_cost` = tax_rate x amount x discount_rate — the time value of
    having the deduction pushed out by about one year. NOT the deduction
    itself, which is the mistake the docstring above warns about.
    """
    if not is_msme_counterparty:
        return Section43BhStatus(False, 0, None, False, 0.0)

    deadline = invoice_due_date + timedelta(days=MSME_PAYMENT_WINDOW_DAYS)
    days_left = (deadline - now).days
    return Section43BhStatus(
        applies=True,
        days_until_deadline=days_left,
        deadline=deadline,
        breached=days_left < 0,
        deferral_cost=tax_rate * amount * discount_rate,
    )
