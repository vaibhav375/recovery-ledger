import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "experiments" / "tier2_simulation"))

from run_batch import run_eval, train_uplift_model  # noqa: E402


def test_train_uplift_model_runs_and_produces_usable_model():
    model = train_uplift_model(n_train=100, seed=1)
    from recovery_ledger.sim.generator import generate_cases
    from recovery_ledger.policy.features import cases_to_feature_matrix
    from datetime import datetime, timezone

    cases = generate_cases(10, seed=2, now=datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc))
    X = cases_to_feature_matrix(cases)
    cate = model.predict_cate(X)
    assert cate.shape == (10,)


def test_run_eval_produces_internally_consistent_results():
    model = train_uplift_model(n_train=100, seed=1)
    results, ledger = run_eval(n_eval=100, uplift_model=model, seed=2)

    assert results["n_treatment"] + results["n_holdout"] == results["n_eval"]
    assert ledger.verify_chain() is True
    assert results["ledger_entries"] == len(ledger)

    # incremental point estimate should equal (treatment mean - holdout mean) * 1000
    treatment_mean = results["gross_treatment_recovered"] / results["n_treatment"]
    holdout_mean = results["gross_holdout_recovered"] / results["n_holdout"]
    expected_point = (treatment_mean - holdout_mean) * 1000
    assert abs(results["incremental_per_1000_cases"]["point"] - expected_point) < 1e-6

    ci = results["incremental_per_1000_cases"]
    assert ci["ci_low"] <= ci["point"] <= ci["ci_high"]

    if results["contacts_sent"] > 0:
        assert 0.0 <= results["pct_contacts_to_do_not_disturbs"] <= 1.0


def test_run_eval_is_deterministic():
    model = train_uplift_model(n_train=100, seed=7)
    results_a, _ = run_eval(n_eval=100, uplift_model=model, seed=9)
    results_b, _ = run_eval(n_eval=100, uplift_model=model, seed=9)
    assert results_a == results_b
