"""Churn-risk model — the `λ_churn × P(churn) × LTV` term of the spec's EV
formula (section 8.3), which earlier versions of this project omitted.

The omission had a stated reason: no defensible lifetime-value estimate. But
that reasoning conflated two separable things. **P(churn | contact) is
learnable from exactly the same randomised data the uplift model already
trains on** — an opt-out is an observed outcome, and the contact/no-contact
assignment is randomised, so the causal effect of contact on churn is
identified the same way the effect on payment is. Only the LTV multiplier is
an assumption, and an assumption stated as one parameter is very different
from silently dropping a whole term.

Why this matters more than the arithmetic suggests. The do-not-disturb
problem (novelty claim N2) had the agent contacting them at 20.1% — level
with untargeted policies, not better. The cause is that avoiding them rested
entirely on `τ̂_pay` being right, and `τ̂_pay` correlates only ~0.35-0.42 with
truth. Churn risk is an **independent** signal: measured on this simulator,
true do-not-disturbs opt out **1.29x** (95% CI 1.09-1.51) more often than others when
contacted. Adding it means two models must both be wrong before a
do-not-disturb gets contacted, rather than one.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from recovery_ledger.events.schemas import FailedSubscriptionCase, LossType, RecoveryCase
from recovery_ledger.policy.uplift.learners import TLearnerModel, UpliftModel

# How many times the at-risk amount a customer relationship is worth, by loss
# type. STATED ASSUMPTION, not a measurement — the whole point of making it a
# named constant is that a reader can disagree with it and re-run.
#
# A failed subscription implies a recurring relationship worth several more
# billing periods; a one-off payment failure implies roughly the transaction
# itself plus some repeat likelihood; an abandoned checkout is a
# not-yet-customer, so the relationship at stake is smallest.
LTV_MULTIPLE: dict[LossType, float] = {
    LossType.FAILED_SUBSCRIPTION: 6.0,
    LossType.OVERDUE_RECEIVABLE: 3.0,
    LossType.FAILED_PAYMENT: 1.5,
    LossType.CHECKOUT_ABANDONMENT: 1.0,
}


def estimated_ltv(case: RecoveryCase) -> float:
    """Lifetime value at stake if this customer leaves."""
    multiple = LTV_MULTIPLE.get(case.loss_type, 1.0)
    if isinstance(case, FailedSubscriptionCase):
        return case.amount_at_risk * multiple
    return case.amount_at_risk * multiple


@dataclass
class ChurnRiskModel:
    """Estimates the INCREMENTAL churn probability caused by contacting —
    the causal effect of contact on opting out, not the base rate.

    Uses the same T-learner class validated in Tier 1, trained on the same
    randomised assignment, with the outcome swapped from "paid" to
    "opted out". Nothing new methodologically, which is the point.
    """

    model: UpliftModel | None = None

    def fit(self, X: NDArray, treatment: NDArray, churned: NDArray, *, random_state: int = 0) -> "ChurnRiskModel":
        learner = TLearnerModel(random_state=random_state)
        learner.fit(X, treatment, churned)
        self.model = learner
        return self

    def predict_incremental_churn(self, X: NDArray) -> NDArray[np.float64]:
        if self.model is None:
            return np.zeros(len(X))
        # Contact cannot plausibly *reduce* opt-out risk, so negative
        # estimates are model noise and are floored at zero rather than
        # allowed to become a spurious reward for contacting.
        return np.clip(self.model.predict_cate(X), 0.0, 1.0)
