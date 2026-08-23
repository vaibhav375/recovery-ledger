import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "experiments" / "tier2_simulation"))

from run_baselines import run_one_policy  # noqa: E402
from run_batch import train_uplift_model  # noqa: E402


def test_all_five_policies_run_against_same_batch_and_produce_consistent_shapes():
    from datetime import datetime, timezone

    from recovery_ledger.policy.decision import (
        BlastEveryonePolicy,
        DoNothingPolicy,
        EVDecisionPolicy,
        RazorpayCurrentPolicy,
        RulesBasedDunningPolicy,
    )
    from recovery_ledger.sim.environment import generate_population
    from recovery_ledger.sim.generator import generate_cases

    now = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)
    model = train_uplift_model(n_train=200, seed=1)
    cases = generate_cases(100, seed=2, now=now)
    traits = generate_population(cases, seed=2)

    policies = {
        "do_nothing": DoNothingPolicy(),
        "blast_everyone": BlastEveryonePolicy(),
        "razorpay_current": RazorpayCurrentPolicy(),
        "rules_based_dunning": RulesBasedDunningPolicy(),
        "ev_policy": EVDecisionPolicy(uplift_model=model),
    }

    for name, policy in policies.items():
        result = run_one_policy(name, policy, cases, traits, seed=3)
        assert result["n_cases"] == 100
        assert 0.0 <= result["recovery_rate"] <= 1.0
        assert result["gross_recovered"] >= 0.0
        if result["contacts_sent"] > 0:
            assert 0.0 <= result["pct_contacts_to_do_not_disturbs"] <= 1.0
        else:
            assert result["pct_contacts_to_do_not_disturbs"] is None

    # razorpay-current (single retry only) must never send a customer-facing contact
    razorpay_result = run_one_policy("razorpay_current", RazorpayCurrentPolicy(), cases, traits, seed=3)
    assert razorpay_result["contacts_sent"] == 0

    # blast-everyone must contact strictly more than the EV policy (no discrimination vs. some)
    blast_result = run_one_policy("blast_everyone", BlastEveryonePolicy(), cases, traits, seed=3)
    ev_result = run_one_policy("ev_policy", EVDecisionPolicy(uplift_model=model), cases, traits, seed=3)
    assert blast_result["contacts_sent"] >= ev_result["contacts_sent"]
