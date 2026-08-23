from datetime import datetime, timezone

import numpy as np

from recovery_ledger.diagnoser.diagnoser import CaseDiagnoser
from recovery_ledger.events.actions import ActionType
from recovery_ledger.events.schemas import (
    Channel,
    CustomerProfile,
    FailedPaymentCase,
    FailedSubscriptionCase,
)
from recovery_ledger.policy.decision import (
    CHANNEL_COST,
    BlastEveryonePolicy,
    DoNothingPolicy,
    EVDecisionPolicy,
    LookaheadEVDecisionPolicy,
    RazorpayCurrentPolicy,
    RulesBasedDunningPolicy,
)

NOW = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)
DIAGNOSER = CaseDiagnoser()


class FakeUpliftModel:
    """Returns a fixed CATE regardless of input — lets tests control the
    policy's input precisely rather than depend on a real fitted model."""

    def __init__(self, cate: float):
        self.cate = cate

    def predict_cate(self, X):
        return np.full(len(X), self.cate)


def _payment_case(**overrides) -> FailedPaymentCase:
    defaults = dict(
        case_id="case_1", customer=CustomerProfile(customer_id="cust_1", channel_pref=Channel.SMS),
        amount_at_risk=1000.0, detected_at=NOW, failure_code="insufficient_funds",
        is_hard_decline=False, payment_method="upi",
    )
    defaults.update(overrides)
    return FailedPaymentCase(**defaults)


def _subscription_case(**overrides) -> FailedSubscriptionCase:
    defaults = dict(
        case_id="case_2", customer=CustomerProfile(customer_id="cust_2", channel_pref=Channel.SMS),
        amount_at_risk=1000.0, detected_at=NOW, subscription_id="sub_1",
        mandate_id="mandate_1", retry_count=1, razorpay_status="halted",
    )
    defaults.update(overrides)
    return FailedSubscriptionCase(**defaults)


def test_high_positive_uplift_chooses_nudge():
    policy = EVDecisionPolicy(uplift_model=FakeUpliftModel(cate=0.5))
    decision = policy.decide(_payment_case(), DIAGNOSER.diagnose(_payment_case()), attempts_so_far=0)
    assert decision.action_type == ActionType.NUDGE


def test_strongly_negative_uplift_never_nudges_do_not_disturb():
    """This is the do-not-disturb behaviour (spec N2) — negative uplift
    means contact actively destroys value, so the policy must never pick
    NUDGE regardless of amount at risk."""
    case = _payment_case(amount_at_risk=50000.0)  # even a huge amount shouldn't flip this
    policy = EVDecisionPolicy(uplift_model=FakeUpliftModel(cate=-0.5))
    decision = policy.decide(case, DIAGNOSER.diagnose(case), attempts_so_far=0)
    assert decision.action_type != ActionType.NUDGE


def test_zero_uplift_prefers_retry_over_nudge_when_retry_has_positive_ev():
    policy = EVDecisionPolicy(uplift_model=FakeUpliftModel(cate=0.0))
    case = _payment_case(is_hard_decline=False)
    decision = policy.decide(case, DIAGNOSER.diagnose(case), attempts_so_far=0)
    assert decision.action_type == ActionType.RETRY


def test_no_retry_available_and_zero_uplift_waits_rather_than_abandoning():
    """RETRY is only modelled for FailedPayment/FailedSubscription cases —
    for a CheckoutAbandonmentCase there's no positive-EV action at zero
    uplift. The policy must NOT nudge (no expected benefit), but it must
    also not STOP: waiting is free and preserves the chance of organic
    self-resolution. Conflating those two was a real bug (2026-08-24) that
    made the EV policy perform worse than doing nothing on some segments."""
    from recovery_ledger.events.schemas import CheckoutAbandonmentCase

    case = CheckoutAbandonmentCase(
        case_id="case_3", customer=CustomerProfile(customer_id="cust_3", channel_pref=Channel.SMS),
        amount_at_risk=100.0, detected_at=NOW, cart_id="cart_1", items_count=1,
        checkout_started_at=NOW,
    )
    policy = EVDecisionPolicy(uplift_model=FakeUpliftModel(cate=0.0))
    decision = policy.decide(case, DIAGNOSER.diagnose(case), attempts_so_far=0)
    assert decision.action_type == ActionType.WAIT


def test_ev_policy_still_terminates_at_max_attempts():
    """The WAIT-instead-of-STOP fix must not remove termination (B3)."""
    policy = EVDecisionPolicy(uplift_model=FakeUpliftModel(cate=0.0), max_attempts=3)
    case = _payment_case()
    decision = policy.decide(case, DIAGNOSER.diagnose(case), attempts_so_far=3)
    assert decision.action_type == ActionType.STOP


def test_hard_decline_retry_has_much_lower_ev_than_soft_decline():
    """Even though a hard-decline retry is technically free (so a tiny
    positive-EV retry can still beat WAIT), it should never be preferred
    over a competitive nudge the way a soft decline's much higher retry
    success rate would be."""
    hard = _payment_case(is_hard_decline=True, amount_at_risk=1000.0)
    soft = _payment_case(is_hard_decline=False, amount_at_risk=1000.0)
    policy = EVDecisionPolicy(uplift_model=FakeUpliftModel(cate=0.05))  # modest uplift: 50 EV before costs
    hard_decision = policy.decide(hard, DIAGNOSER.diagnose(hard), attempts_so_far=0)
    soft_decision = policy.decide(soft, DIAGNOSER.diagnose(soft), attempts_so_far=0)
    # hard decline retry EV = 0.01*1000=10 < nudge EV (~49.5) -> nudge wins
    # soft decline retry EV = 0.17*1000=170 > nudge EV (~49.5) -> retry wins
    assert hard_decision.action_type == ActionType.NUDGE
    assert soft_decision.action_type == ActionType.RETRY


def test_subscription_retry_beaten_by_strong_positive_uplift_nudge():
    case = _subscription_case(amount_at_risk=1000.0)
    policy = EVDecisionPolicy(uplift_model=FakeUpliftModel(cate=0.5))  # 0.5 * 1000 = 500 EV
    decision = policy.decide(case, DIAGNOSER.diagnose(case), attempts_so_far=0)
    # subscription retry EV = 0.35 * 1000 = 350, nudge EV = 500 - cost - annoyance(0) ~= 499.5
    assert decision.action_type == ActionType.NUDGE


def test_reaches_max_attempts_and_stops():
    policy = EVDecisionPolicy(uplift_model=FakeUpliftModel(cate=0.5), max_attempts=2)
    case = _payment_case()
    decision = policy.decide(case, DIAGNOSER.diagnose(case), attempts_so_far=2)
    assert decision.action_type == ActionType.STOP


def test_annoyance_cost_eventually_overwhelms_a_modest_positive_uplift():
    """A positive uplift strong enough to beat retry early (0.3*100=30 EV
    before costs, vs retry's fixed 17) should stop being worth contacting
    once enough attempts accumulate annoyance cost — even though the
    underlying uplift estimate hasn't changed."""
    case = _payment_case(amount_at_risk=100.0)
    policy = EVDecisionPolicy(uplift_model=FakeUpliftModel(cate=0.3), lambda_annoyance=30.0, max_attempts=10)
    decision_early = policy.decide(case, DIAGNOSER.diagnose(case), attempts_so_far=0)
    decision_late = policy.decide(case, DIAGNOSER.diagnose(case), attempts_so_far=5)
    assert decision_early.action_type == ActionType.NUDGE
    assert decision_late.action_type != ActionType.NUDGE


def test_do_nothing_policy_always_waits_until_max_attempts():
    policy = DoNothingPolicy(max_attempts=3)
    case = _payment_case()
    for attempt in range(3):
        decision = policy.decide(case, DIAGNOSER.diagnose(case), attempts_so_far=attempt)
        assert decision.action_type == ActionType.WAIT
    final = policy.decide(case, DIAGNOSER.diagnose(case), attempts_so_far=3)
    assert final.action_type == ActionType.STOP


def test_blast_everyone_always_nudges_regardless_of_case():
    policy = BlastEveryonePolicy(max_attempts=3)
    case = _payment_case()
    for attempt in range(3):
        decision = policy.decide(case, DIAGNOSER.diagnose(case), attempts_so_far=attempt)
        assert decision.action_type == ActionType.NUDGE
    final = policy.decide(case, DIAGNOSER.diagnose(case), attempts_so_far=3)
    assert final.action_type == ActionType.STOP


def test_razorpay_current_retries_once_then_stops():
    policy = RazorpayCurrentPolicy()
    case = _payment_case()
    first = policy.decide(case, DIAGNOSER.diagnose(case), attempts_so_far=0)
    second = policy.decide(case, DIAGNOSER.diagnose(case), attempts_so_far=1)
    assert first.action_type == ActionType.RETRY
    assert second.action_type == ActionType.STOP


def test_rules_based_dunning_fixed_three_contact_ladder():
    policy = RulesBasedDunningPolicy(max_attempts=3)
    case = _payment_case()
    for attempt in range(3):
        decision = policy.decide(case, DIAGNOSER.diagnose(case), attempts_so_far=attempt)
        assert decision.action_type == ActionType.NUDGE
    final = policy.decide(case, DIAGNOSER.diagnose(case), attempts_so_far=3)
    assert final.action_type == ActionType.STOP


# --- LookaheadEVDecisionPolicy ------------------------------------------------

def test_lookahead_high_uplift_nudges():
    policy = LookaheadEVDecisionPolicy(uplift_model=FakeUpliftModel(cate=0.5))
    case = _payment_case()
    decision = policy.decide(case, DIAGNOSER.diagnose(case), attempts_so_far=0)
    assert decision.action_type == ActionType.NUDGE


def test_lookahead_negative_uplift_never_nudges():
    """Do-not-disturb protection (N2) must survive the lookahead
    reformulation — continuation value must never make contacting a
    negative-uplift customer look attractive."""
    case = _payment_case(amount_at_risk=50000.0)
    policy = LookaheadEVDecisionPolicy(uplift_model=FakeUpliftModel(cate=-0.5))
    for attempt in range(3):
        decision = policy.decide(case, DIAGNOSER.diagnose(case), attempts_so_far=attempt)
        assert decision.action_type != ActionType.NUDGE


def test_lookahead_terminates_at_max_attempts():
    policy = LookaheadEVDecisionPolicy(uplift_model=FakeUpliftModel(cate=0.5), max_attempts=3)
    case = _payment_case()
    decision = policy.decide(case, DIAGNOSER.diagnose(case), attempts_so_far=3)
    assert decision.action_type == ActionType.STOP


def test_lookahead_waits_rather_than_abandoning_when_nothing_is_worthwhile():
    from recovery_ledger.events.schemas import CheckoutAbandonmentCase

    case = CheckoutAbandonmentCase(
        case_id="case_9", customer=CustomerProfile(customer_id="cust_9", channel_pref=Channel.SMS),
        amount_at_risk=10.0, detected_at=NOW, cart_id="cart_9", items_count=1,
        checkout_started_at=NOW,
    )
    policy = LookaheadEVDecisionPolicy(uplift_model=FakeUpliftModel(cate=-0.5))
    decision = policy.decide(case, DIAGNOSER.diagnose(case), attempts_so_far=0)
    assert decision.action_type == ActionType.WAIT


def test_lookahead_values_a_sequence_at_least_as_highly_as_one_step():
    """The whole point of the lookahead reformulation: the value it assigns
    to acting now includes the option to keep working the case, so it can
    never be lower than the single-step value the greedy policy sees."""
    case = _payment_case(amount_at_risk=1000.0)
    policy = LookaheadEVDecisionPolicy(uplift_model=FakeUpliftModel(cate=0.2), lambda_annoyance=0.0)
    _, _, seq_value = policy._solve(case, tau_hat=0.2, attempts_so_far=0)

    greedy_immediate = 0.2 * 1000.0 - CHANNEL_COST[Channel.SMS]
    assert seq_value >= greedy_immediate
