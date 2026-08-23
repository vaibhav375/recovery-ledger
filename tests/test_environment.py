from datetime import datetime, timezone

from recovery_ledger.events.actions import ActionType
from recovery_ledger.events.schemas import CustomerProfile, FailedPaymentCase, FailedSubscriptionCase
from recovery_ledger.listener.listener import ReplyIntent
from recovery_ledger.sim.environment import (
    LatentTraits,
    SimulationEnvironment,
    generate_population,
    persuadability,
)

NOW = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)


def _payment_case(case_id="case_1", is_hard_decline=False) -> FailedPaymentCase:
    return FailedPaymentCase(
        case_id=case_id, customer=CustomerProfile(customer_id="cust_1"),
        amount_at_risk=500.0, detected_at=NOW, failure_code="insufficient_funds",
        is_hard_decline=is_hard_decline, payment_method="upi",
    )


def _subscription_case(case_id="case_2") -> FailedSubscriptionCase:
    return FailedSubscriptionCase(
        case_id=case_id, customer=CustomerProfile(customer_id="cust_2"),
        amount_at_risk=500.0, detected_at=NOW, subscription_id="sub_1",
        mandate_id="mandate_1", retry_count=1, razorpay_status="halted",
    )


def test_persuadability_is_higher_for_liquid_low_dispute_customers():
    liquid_agreeable = LatentTraits(liquidity=0.9, annoyance_threshold=0.8, dispute_propensity=0.05)
    illiquid_disputatious = LatentTraits(liquidity=0.1, annoyance_threshold=0.2, dispute_propensity=0.8)
    assert persuadability(liquid_agreeable) > persuadability(illiquid_disputatious)


def test_persuadability_can_go_negative_do_not_disturbs_exist():
    worst_case = LatentTraits(liquidity=0.0, annoyance_threshold=0.0, dispute_propensity=1.0)
    assert persuadability(worst_case) < 0


def test_generate_population_deterministic():
    a = generate_population(["c1", "c2", "c3"], seed=42)
    b = generate_population(["c1", "c2", "c3"], seed=42)
    assert a == b


def test_generate_population_covers_all_case_ids():
    pop = generate_population(["c1", "c2"], seed=1)
    assert set(pop.keys()) == {"c1", "c2"}


def test_wait_action_rarely_resolves():
    traits = generate_population(["case_1"], seed=1)
    env = SimulationEnvironment(traits, seed=1)
    case = _payment_case()
    outcomes = [env.step(case, ActionType.WAIT, i).paid for i in range(200)]
    rate = sum(outcomes) / len(outcomes)
    assert 0.0 < rate < 0.15  # should be low but not literally impossible


def test_hard_decline_retry_almost_never_succeeds():
    traits = generate_population(["case_1"], seed=1)
    env = SimulationEnvironment(traits, seed=1)
    case = _payment_case(is_hard_decline=True)
    outcomes = [env.step(case, ActionType.RETRY, i).paid for i in range(300)]
    rate = sum(outcomes) / len(outcomes)
    assert rate < 0.05


def test_soft_decline_retry_succeeds_meaningfully_more_than_hard_decline():
    traits = generate_population(["case_1", "case_2"], seed=1)
    env = SimulationEnvironment(traits, seed=1)
    soft = [env.step(_payment_case("case_1", is_hard_decline=False), ActionType.RETRY, i).paid for i in range(300)]
    hard = [env.step(_payment_case("case_2", is_hard_decline=True), ActionType.RETRY, i).paid for i in range(300)]
    assert sum(soft) / len(soft) > sum(hard) / len(hard)


def test_subscription_retry_succeeds_more_than_generic_payment_retry():
    traits = generate_population(["case_1", "case_2"], seed=3)
    env = SimulationEnvironment(traits, seed=3)
    sub = [env.step(_subscription_case("case_1"), ActionType.RETRY, i).paid for i in range(400)]
    payment = [env.step(_payment_case("case_2"), ActionType.RETRY, i).paid for i in range(400)]
    assert sum(sub) / len(sub) > sum(payment) / len(payment)


def test_environment_is_deterministic_given_seed():
    traits = generate_population(["case_1"], seed=5)
    env_a = SimulationEnvironment(traits, seed=5)
    env_b = SimulationEnvironment(traits, seed=5)
    case = _payment_case()
    results_a = [env_a.step(case, ActionType.NUDGE, i).reply for i in range(20)]
    results_b = [env_b.step(case, ActionType.NUDGE, i).reply for i in range(20)]
    assert results_a == results_b


def test_repeated_nudges_eventually_risk_opt_out_for_low_annoyance_threshold():
    """A customer with annoyance_threshold=0 has zero contact capacity —
    every nudge beyond the first should carry meaningfully elevated
    opt-out risk relative to a high-threshold customer."""
    low_threshold = {"case_1": LatentTraits(liquidity=0.5, annoyance_threshold=0.0, dispute_propensity=0.1)}
    high_threshold = {"case_2": LatentTraits(liquidity=0.5, annoyance_threshold=1.0, dispute_propensity=0.1)}

    env_low = SimulationEnvironment(low_threshold, seed=10)
    env_high = SimulationEnvironment(high_threshold, seed=10)
    case_low = _payment_case("case_1")
    case_high = _payment_case("case_2")

    # burn through several contacts first so overcontacted > 0 for the low-threshold customer
    for i in range(5):
        env_low.step(case_low, ActionType.NUDGE, i)
        env_high.step(case_high, ActionType.NUDGE, i)

    opt_outs_low = sum(
        env_low.step(case_low, ActionType.NUDGE, 5 + i).reply == ReplyIntent.OPT_OUT for i in range(500)
    )
    opt_outs_high = sum(
        env_high.step(case_high, ActionType.NUDGE, 5 + i).reply == ReplyIntent.OPT_OUT for i in range(500)
    )
    assert opt_outs_low > opt_outs_high
