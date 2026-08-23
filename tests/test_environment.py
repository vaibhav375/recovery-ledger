from datetime import datetime, timezone

import numpy as np

from recovery_ledger.events.actions import ActionType
from recovery_ledger.events.schemas import Channel, CustomerProfile, FailedPaymentCase, FailedSubscriptionCase
from recovery_ledger.listener.listener import ReplyIntent
from recovery_ledger.sim.environment import (
    LatentTraits,
    SimulationEnvironment,
    generate_population,
    persuadability,
)

NOW = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)


def _payment_case(case_id="case_1", is_hard_decline=False, is_b2b=False, channel_pref=None, amount_at_risk=500.0) -> FailedPaymentCase:
    return FailedPaymentCase(
        case_id=case_id, customer=CustomerProfile(customer_id=f"cust_{case_id}", is_b2b=is_b2b, channel_pref=channel_pref),
        amount_at_risk=amount_at_risk, detected_at=NOW, failure_code="insufficient_funds",
        is_hard_decline=is_hard_decline, payment_method="upi",
    )


def _subscription_case(case_id="case_2") -> FailedSubscriptionCase:
    return FailedSubscriptionCase(
        case_id=case_id, customer=CustomerProfile(customer_id=f"cust_{case_id}"),
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
    cases = [_payment_case("c1"), _payment_case("c2"), _payment_case("c3")]
    a = generate_population(cases, seed=42)
    b = generate_population(cases, seed=42)
    assert a == b


def test_generate_population_covers_all_case_ids():
    cases = [_payment_case("c1"), _payment_case("c2")]
    pop = generate_population(cases, seed=1)
    assert set(pop.keys()) == {"c1", "c2"}


def test_generate_population_traits_correlate_with_observable_fields():
    """Regression test for the bug found 2026-08-24: hidden traits used to
    be drawn fully independently of any observable case field, which meant
    the true treatment effect (driven only by these traits) was
    statistically independent of everything the uplift model could see —
    there was nothing to learn, by construction. Confirms the fix: at
    least one observable field must now shift the traits distribution in
    the declared direction, checked over enough samples that the shift is
    unambiguous."""
    n = 2000
    b2b_cases = [_payment_case(f"b2b_{i}", is_b2b=True, amount_at_risk=100.0) for i in range(n)]
    non_b2b_cases = [_payment_case(f"solo_{i}", is_b2b=False, amount_at_risk=100.0) for i in range(n)]

    b2b_traits = generate_population(b2b_cases, seed=1)
    non_b2b_traits = generate_population(non_b2b_cases, seed=1)

    b2b_liquidity = np.mean([t.liquidity for t in b2b_traits.values()])
    non_b2b_liquidity = np.mean([t.liquidity for t in non_b2b_traits.values()])
    assert b2b_liquidity > non_b2b_liquidity + 0.05  # declared shift is 0.15; require most of it to show up


def test_generate_population_annoyance_threshold_correlates_with_channel_pref():
    n = 2000
    whatsapp_cases = [_payment_case(f"wa_{i}", channel_pref=Channel.WHATSAPP) for i in range(n)]
    sms_cases = [_payment_case(f"sms_{i}", channel_pref=Channel.SMS) for i in range(n)]

    whatsapp_traits = generate_population(whatsapp_cases, seed=1)
    sms_traits = generate_population(sms_cases, seed=1)

    whatsapp_mean = np.mean([t.annoyance_threshold for t in whatsapp_traits.values()])
    sms_mean = np.mean([t.annoyance_threshold for t in sms_traits.values()])
    assert whatsapp_mean > sms_mean + 0.10  # declared shift is +0.12 vs -0.10 = 0.22 gap


def test_wait_action_rarely_resolves():
    case = _payment_case()
    traits = generate_population([case], seed=1)
    env = SimulationEnvironment(traits, seed=1)
    outcomes = [env.step(case, ActionType.WAIT, i).paid for i in range(200)]
    rate = sum(outcomes) / len(outcomes)
    assert 0.0 < rate < 0.15  # should be low but not literally impossible


def test_hard_decline_retry_almost_never_succeeds():
    case = _payment_case(is_hard_decline=True)
    traits = generate_population([case], seed=1)
    env = SimulationEnvironment(traits, seed=1)
    outcomes = [env.step(case, ActionType.RETRY, i).paid for i in range(300)]
    rate = sum(outcomes) / len(outcomes)
    assert rate < 0.05


def test_soft_decline_retry_succeeds_meaningfully_more_than_hard_decline():
    soft_case = _payment_case("case_1", is_hard_decline=False)
    hard_case = _payment_case("case_2", is_hard_decline=True)
    traits = generate_population([soft_case, hard_case], seed=1)
    env = SimulationEnvironment(traits, seed=1)
    soft = [env.step(soft_case, ActionType.RETRY, i).paid for i in range(300)]
    hard = [env.step(hard_case, ActionType.RETRY, i).paid for i in range(300)]
    assert sum(soft) / len(soft) > sum(hard) / len(hard)


def test_subscription_retry_succeeds_more_than_generic_payment_retry():
    sub_case = _subscription_case("case_1")
    payment_case = _payment_case("case_2")
    traits = generate_population([sub_case, payment_case], seed=3)
    env = SimulationEnvironment(traits, seed=3)
    sub = [env.step(sub_case, ActionType.RETRY, i).paid for i in range(400)]
    payment = [env.step(payment_case, ActionType.RETRY, i).paid for i in range(400)]
    assert sum(sub) / len(sub) > sum(payment) / len(payment)


def test_environment_is_deterministic_given_seed():
    case = _payment_case()
    traits = generate_population([case], seed=5)
    env_a = SimulationEnvironment(traits, seed=5)
    env_b = SimulationEnvironment(traits, seed=5)
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
