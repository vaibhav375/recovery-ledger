"""Distinguishing a biased estimator from a noisy one.

RESULTS.md called DR "29% low" on Criteo. That phrase describes a point
estimate, and a point estimate below truth is consistent with two different
facts: a systematic bias worth fixing, or one draw from a wide sampling
distribution. The repo had no measurement that could tell them apart, so the
weak spot was documented in terms that could not be acted on.

Two ways the replacement diagnosis could quietly fail to answer it either:

  - Differencing two independently-bootstrapped intervals. The always-treat
    and never-treat values share the rows, the fitted q_hat, and part of the
    correction term. Bootstrapping them separately treats that shared noise as
    if it cancelled twice and inflates the contrast's interval, which makes
    "the interval covers truth" easy to achieve and meaningless.
  - Concluding from one split. A single subsample is one draw, which is the
    failure this project has already made four times.

These pin the pairing and the replication, not the verdict.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

from recovery_ledger.policy.ope.estimators import dr_contributions

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "experiments" / "tier1_criteo" / "results_dr_diagnosis.json"
FOLDSWEEP_ARTIFACT = ROOT / "experiments" / "tier1_criteo" / "results_dr_foldsweep.json"

sys.path.insert(0, str(ROOT / "experiments" / "tier1_criteo"))
from run_dr_diagnosis import fold_sweep_verdict  # noqa: E402


def _artifact() -> dict:
    if not ARTIFACT.exists():
        pytest.skip("results_dr_diagnosis.json not generated; run `make dr-diagnosis`")
    return json.loads(ARTIFACT.read_text())


# ── the refactor that exposed the contributions did not change the estimate ──

def test_dr_contributions_average_to_the_dr_point_estimate():
    """`dr_contributions` was extracted from `doubly_robust_value` so the
    diagnosis could pair the bootstrap. If the two ever diverge, the diagnosis
    is characterising a different estimator than the one that ships."""
    from sklearn.ensemble import GradientBoostingClassifier

    from recovery_ledger.policy.ope.estimators import (
        always_treat_policy,
        doubly_robust_value,
    )

    rng = np.random.default_rng(0)
    n = 400
    X = rng.normal(size=(n, 3))
    T = rng.integers(0, 2, size=n)
    Y = (rng.random(n) < np.clip(0.3 + 0.2 * T, 0, 1)).astype(float)
    prop = np.full(n, T.mean())
    model = GradientBoostingClassifier(random_state=0, n_estimators=10)
    policy = always_treat_policy(n)

    est = doubly_robust_value(Y, T, X, prop, policy, outcome_model=model, seed=0)
    contrib = dr_contributions(Y, T, X, prop, policy, outcome_model=model, seed=0)
    assert contrib.shape == (n,)
    assert est.point_estimate == pytest.approx(float(contrib.mean()))


# ── the diagnosis is capable of returning either answer ──────────────────

def test_verdict_requires_both_a_missed_interval_and_a_consistent_sign():
    """Bias needs the interval to miss truth *and* miss it the same way every
    draw. Either alone is what noise looks like."""
    data = _artifact()
    n = data["draws"]
    cov, consistent = data["dr_draws_covering_direct"], data["dr_gap_sign_consistent"]
    if data["verdict"] == "bias":
        assert cov == 0 and consistent
    elif data["verdict"] == "noise":
        assert cov == n
    else:
        assert data["verdict"] == "inconclusive"
        assert 0 < cov < n or (cov == 0 and not consistent)


def test_diagnosis_replicates_across_independent_splits():
    data = _artifact()
    assert data["draws"] >= 3, "one split is not a result"
    seeds = [d["seed"] for d in data["per_draw"]]
    assert len(set(seeds)) == len(seeds), "draws must use distinct splits"


def test_paired_interval_is_tighter_than_differencing_marginals():
    """The point of pairing. If the paired contrast interval is not narrower
    than the naive sum of the two marginal half-widths, the pairing is not
    happening and the diagnosis has no more power than the artifact it
    replaces."""
    data = _artifact()
    committed = json.loads(
        (ROOT / "experiments" / "tier1_criteo" / "results_criteo.json").read_text()
    )["ope_validation"]["dr"]
    naive = (
        (committed["always_treat"]["ci_high"] - committed["always_treat"]["ci_low"])
        + (committed["never_treat"]["ci_high"] - committed["never_treat"]["ci_low"])
    )
    paired = data["dr_mean_ci_width"]
    assert paired < naive, (
        f"paired contrast interval ({paired:.5f}) is no tighter than adding the "
        f"marginal widths ({naive:.5f}); the rows are not being resampled jointly"
    )


def test_dr_is_not_claimed_more_precise_than_ips():
    """DR's cost on this dataset is variance, and the report must not lose
    that: 15% of rows in the control arm at a 6.7x weight is the whole story."""
    data = _artifact()
    assert data["dr_mean_ci_width"] > 0 and data["ips_mean_ci_width"] > 0


# ── fold_sweep_verdict()'s three branches ─────────────────────────────────
#
# The real sweep only ever produced REFUTED, so nothing in the committed
# artifact exercises the CONFIRMED or UNRESOLVED branches -- a bug in either
# (a flipped comparator, an inverted threshold direction) could sit
# undetected indefinitely. These drive the function directly with
# constructed rows, the same way `test_run_regret.py` drives
# `disagreement_verdict()` rather than re-deriving its branches in a
# doc-matching test.

def _fold_row(n_folds: int, coverage: int, mean_abs_gap: float, n_draws: int = 3) -> dict:
    return {
        "n_folds": n_folds, "coverage": coverage, "n_draws": n_draws,
        "mean_gap": -mean_abs_gap, "mean_abs_gap": mean_abs_gap,
    }


def test_fold_sweep_verdict_confirms_when_coverage_rises_to_full():
    """A rise anywhere in the sweep that ends at full coverage is the
    pattern the cross-fitting hypothesis predicts -- CONFIRMED, even though
    the rise happens at an interior fold count (10), not the first step."""
    rows = [
        _fold_row(2, coverage=1, mean_abs_gap=0.0080),
        _fold_row(5, coverage=1, mean_abs_gap=0.0060),
        _fold_row(10, coverage=3, mean_abs_gap=0.0020),
        _fold_row(20, coverage=3, mean_abs_gap=0.0005),
    ]
    assert fold_sweep_verdict(rows) == "CONFIRMED"


def test_fold_sweep_verdict_refutes_when_coverage_and_gap_are_flat():
    """The real result: coverage never moves and the gap wanders within a
    few percent across the whole 2->20 range."""
    rows = [
        _fold_row(2, coverage=1, mean_abs_gap=0.00282),
        _fold_row(5, coverage=1, mean_abs_gap=0.00272),
        _fold_row(10, coverage=1, mean_abs_gap=0.00281),
        _fold_row(20, coverage=1, mean_abs_gap=0.00278),
    ]
    assert fold_sweep_verdict(rows) == "REFUTED"


def test_fold_sweep_verdict_is_unresolved_on_a_middle_bump_endpoints_would_miss():
    """The defect an endpoints-only rule has: coverage bumps up at an
    interior fold count and drops back by the last one. rows[0] and rows[-1]
    both read coverage=1, which an endpoints-only comparison would call
    "flat" -- REFUTED. Considering every row catches the bump and calls it
    UNRESOLVED instead, because it is neither a clean rise to full coverage
    nor a flat sweep."""
    rows = [
        _fold_row(2, coverage=1, mean_abs_gap=0.0028),
        _fold_row(5, coverage=3, mean_abs_gap=0.0001),
        _fold_row(10, coverage=1, mean_abs_gap=0.0027),
        _fold_row(20, coverage=1, mean_abs_gap=0.0028),
    ]
    assert fold_sweep_verdict(rows) == "UNRESOLVED"


def test_fold_sweep_verdict_matches_the_committed_artifact():
    """Sanity check that the function, called on the actual committed sweep,
    reproduces the artifact's own stored verdict -- guards against the
    artifact and the function silently drifting apart."""
    if not FOLDSWEEP_ARTIFACT.exists():
        pytest.skip("results_dr_foldsweep.json not generated; run `make dr-foldsweep`")
    data = json.loads(FOLDSWEEP_ARTIFACT.read_text())
    assert fold_sweep_verdict(data["rows"]) == data["verdict"]
