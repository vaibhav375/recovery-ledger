"""The lambda_churn term — the spec's EV component this project originally
omitted, and the fix for the do-not-disturb problem (novelty claim N2)."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from recovery_ledger.diagnoser.diagnoser import CaseDiagnoser
from recovery_ledger.events.actions import ActionType
from recovery_ledger.events.schemas import (
    Channel,
    CheckoutAbandonmentCase,
    CustomerProfile,
    FailedPaymentCase,
    FailedSubscriptionCase,
)
from recovery_ledger.policy.churn import LTV_MULTIPLE, ChurnRiskModel, estimated_ltv
from recovery_ledger.policy.decision import EVDecisionPolicy

NOW = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)
DIAG = CaseDiagnoser()


class FixedUplift:
    def __init__(self, cate): self.cate = cate
    def predict_cate(self, X): return np.full(len(X), self.cate)


class FixedChurn:
    """Stands in for a fitted ChurnRiskModel with a known prediction."""
    def __init__(self, p): self.p = p
    def predict_incremental_churn(self, X): return np.full(len(X), self.p)


def _payment(amount=1000.0):
    return FailedPaymentCase(
        case_id="c", customer=CustomerProfile(customer_id="u", channel_pref=Channel.SMS),
        amount_at_risk=amount, detected_at=NOW, failure_code="insufficient_funds",
        is_hard_decline=False, payment_method="upi")


def _subscription(amount=1000.0):
    return FailedSubscriptionCase(
        case_id="s", customer=CustomerProfile(customer_id="u", channel_pref=Channel.SMS),
        amount_at_risk=amount, detected_at=NOW, subscription_id="sub",
        mandate_id="m", retry_count=1, razorpay_status="halted")


def test_subscription_relationship_is_worth_more_than_a_one_off():
    """A failed subscription implies recurring value at stake; an abandoned
    checkout is a not-yet-customer."""
    checkout = CheckoutAbandonmentCase(
        case_id="k", customer=CustomerProfile(customer_id="u"), amount_at_risk=1000.0,
        detected_at=NOW, cart_id="c", items_count=1, checkout_started_at=NOW)
    assert estimated_ltv(_subscription()) > estimated_ltv(_payment())
    assert estimated_ltv(_payment()) > estimated_ltv(checkout)
    assert LTV_MULTIPLE  # the assumptions are named and inspectable, not buried


def test_high_churn_risk_suppresses_a_contact_that_would_otherwise_happen():
    """The whole point: an uplift estimate alone says 'contact', and the
    independent churn signal overrides it.

    Uses a checkout-abandonment case deliberately — for a subscription, RETRY
    (incremental 0.30 x amount) already beats a modest nudge regardless of
    churn, so it could not demonstrate the override.
    """
    case = CheckoutAbandonmentCase(
        case_id="k", customer=CustomerProfile(customer_id="u", channel_pref=Channel.SMS),
        amount_at_risk=1000.0, detected_at=NOW, cart_id="c", items_count=1,
        checkout_started_at=NOW)
    without = EVDecisionPolicy(uplift_model=FixedUplift(0.10))
    with_churn = EVDecisionPolicy(uplift_model=FixedUplift(0.10),
                                  churn_model=FixedChurn(0.05), lambda_churn=4.0)
    # nudge EV without churn = 0.10*1000 - 0.5 = +99.5  -> contact
    assert without.decide(case, DIAG.diagnose(case), 0).action_type == ActionType.NUDGE
    # churn cost = 4.0 * 0.05 * (1000 * 1.0) = 200  -> EV negative, no contact
    assert with_churn.decide(case, DIAG.diagnose(case), 0).action_type != ActionType.NUDGE


def test_negligible_churn_risk_leaves_the_decision_unchanged():
    """The term must not suppress contact indiscriminately — only where churn
    risk is actually predicted."""
    case = _payment(amount=1000.0)
    policy = EVDecisionPolicy(uplift_model=FixedUplift(0.30),
                              churn_model=FixedChurn(0.0001), lambda_churn=4.0)
    assert policy.decide(case, DIAG.diagnose(case), 0).action_type == ActionType.NUDGE


def test_no_churn_model_means_no_behaviour_change():
    case = _payment()
    a = EVDecisionPolicy(uplift_model=FixedUplift(0.2)).decide(case, DIAG.diagnose(case), 0)
    b = EVDecisionPolicy(uplift_model=FixedUplift(0.2), churn_model=None).decide(case, DIAG.diagnose(case), 0)
    assert a.action_type == b.action_type


def test_churn_model_is_identified_from_randomised_data():
    """It is learnable from exactly the data the uplift model already uses —
    which is why omitting the term for 'no LTV estimate' conflated two
    separable things."""
    rng = np.random.default_rng(0)
    n = 2000
    X = rng.normal(size=(n, 4))
    treatment = rng.integers(0, 2, size=n)
    # churn only happens when contacted, and more for high X[:,0]
    p = np.where(treatment == 1, 0.02 + 0.08 * (X[:, 0] > 0), 0.0)
    churned = rng.binomial(1, p).astype(float)

    model = ChurnRiskModel().fit(X, treatment, churned, random_state=0)
    high = model.predict_incremental_churn(np.tile([2.0, 0, 0, 0], (50, 1)))
    low = model.predict_incremental_churn(np.tile([-2.0, 0, 0, 0], (50, 1)))
    assert high.mean() > low.mean(), "must recover the direction of the effect"


def test_predicted_churn_is_never_negative():
    """Contact cannot plausibly reduce opt-out risk; a negative estimate is
    noise and must not become a reward for contacting."""
    class NegativeCate:
        def predict_cate(self, X): return np.full(len(X), -0.5)
    model = ChurnRiskModel(model=NegativeCate())
    assert (model.predict_incremental_churn(np.zeros((5, 3))) >= 0).all()
