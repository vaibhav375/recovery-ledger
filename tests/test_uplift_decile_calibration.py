"""The uplift-by-decile computation, checked against data whose answer is known.

The spec's evaluation protocol (section 8.1, 11.2) asks for an uplift-by-decile
chart. A decile chart is easy to draw and easy to draw *wrong*: bin by the
wrong variable, drop the untreated rows, or compare a decile's treated mean
against the whole population's control mean, and you get a beautifully monotone
picture of nothing.

So the arithmetic is pinned here on constructed populations where the realised
uplift of every decile is exact by construction, before it is ever pointed at
the simulator. Two of these tests exist specifically to fail: an anti-ranked
predictor must produce a *negative* monotonicity score, and a decile with no
control rows must report an undefined uplift rather than a confident zero.

That second one is the lesson from the lambda_churn dominance check, which was
written against an interval overlap that could not fail in the direction that
mattered. A metric that cannot come out badly is not evidence.
"""

from __future__ import annotations

import numpy as np
import pytest

from recovery_ledger.policy.uplift.calibration import uplift_by_decile


def _staircase(n_bins: int = 10, per_bin: int = 200):
    """A population whose realised uplift in decile d is exactly d/10.

    Rows are pre-sorted by the predictor, alternating treated/control, and the
    outcomes are deterministic — no sampling noise anywhere, so any deviation
    from the staircase is the estimator's own arithmetic.

    The baseline payment rate *falls* across the deciles (0.45 down to 0.00)
    while uplift rises. That opposition is the point of the fixture: it is what
    a real ranking looks like, and it is what punishes the classic mistake of
    scoring a decile's treated rows against the whole population's control
    mean. With a flat baseline that bug is invisible; here it inverts the
    staircase.
    """
    n = n_bins * per_bin
    tau_hat = np.arange(n, dtype=float) / n
    treatment = np.tile([1, 0], n // 2)
    outcome = np.zeros(n)
    for d in range(n_bins):
        rows = np.arange(d * per_bin, (d + 1) * per_bin)
        treated, control = rows[treatment[rows] == 1], rows[treatment[rows] == 0]
        control_rate = (n_bins - 1 - d) / (2 * n_bins)
        treated_rate = control_rate + d / n_bins
        outcome[control[: round(control_rate * len(control))]] = 1.0
        outcome[treated[: round(treated_rate * len(treated))]] = 1.0
    return tau_hat, treatment, outcome


def test_a_decile_is_scored_against_its_own_control_rows_not_the_population():
    """The confounded comparison the fixture is built to expose: baseline falls
    as uplift rises, so borrowing the global control mean overstates the low
    deciles and understates the high ones."""
    tau_hat, treatment, outcome = _staircase()

    result = uplift_by_decile(tau_hat, treatment, outcome, n_bins=10, seed=0)

    global_control = outcome[treatment == 0].mean()
    for b in result.bins:
        assert b.control_outcome_rate == pytest.approx(b.treated_outcome_rate - b.index / 10)
    assert result.bins[0].control_outcome_rate != pytest.approx(global_control)


def test_realised_uplift_per_decile_is_the_within_decile_treated_minus_control_gap():
    tau_hat, treatment, outcome = _staircase()

    result = uplift_by_decile(tau_hat, treatment, outcome, n_bins=10, seed=0)

    realised = [b.realised_uplift for b in result.bins]
    assert realised == pytest.approx([d / 10 for d in range(10)], abs=1e-12)


def test_every_row_lands_in_exactly_one_decile():
    tau_hat, treatment, outcome = _staircase()

    result = uplift_by_decile(tau_hat, treatment, outcome, n_bins=10, seed=0)

    assert len(result.bins) == 10
    assert sum(b.n for b in result.bins) == len(tau_hat)
    assert all(b.n_treated + b.n_control == b.n for b in result.bins)


def test_a_perfectly_ranked_predictor_scores_monotonicity_one():
    tau_hat, treatment, outcome = _staircase()

    result = uplift_by_decile(tau_hat, treatment, outcome, n_bins=10, seed=0)

    assert result.spearman == pytest.approx(1.0)
    assert result.top_minus_bottom == pytest.approx(0.9)


def test_an_anti_ranked_predictor_scores_monotonicity_minus_one():
    """The failure direction. If this cannot go negative the chart is decorative."""
    tau_hat, treatment, outcome = _staircase()

    result = uplift_by_decile(-tau_hat, treatment, outcome, n_bins=10, seed=0)

    assert result.spearman == pytest.approx(-1.0)
    assert result.top_minus_bottom == pytest.approx(-0.9)


def test_calibration_slope_is_one_when_predictions_track_realised_uplift():
    tau_hat, treatment, outcome = _staircase()

    result = uplift_by_decile(tau_hat, treatment, outcome, n_bins=10, seed=0)

    assert result.calibration_slope == pytest.approx(1.0, abs=1e-9)


def test_calibration_slope_is_zero_when_predictions_carry_no_signal():
    """Same outcomes, a predictor that ranks nothing: flat, not steep."""
    tau_hat, treatment, outcome = _staircase()
    rng = np.random.default_rng(7)
    order = rng.permutation(len(outcome))

    result = uplift_by_decile(tau_hat, treatment[order], outcome[order], n_bins=10, seed=0)

    assert abs(result.calibration_slope) < 0.25
    assert abs(result.spearman) < 0.7


def test_a_decile_with_no_control_rows_reports_undefined_not_zero():
    tau_hat, treatment, outcome = _staircase()
    treatment[:200] = 1  # the lowest-predicted decile: all treated, no control arm

    result = uplift_by_decile(tau_hat, treatment, outcome, n_bins=10, seed=0)

    assert result.bins[0].realised_uplift is None
    assert result.bins[0].n_control == 0
    assert all(b.realised_uplift is not None for b in result.bins[1:])


def test_bootstrap_interval_brackets_the_point_estimate():
    tau_hat, treatment, outcome = _staircase()

    result = uplift_by_decile(tau_hat, treatment, outcome, n_bins=10, n_boot=200, seed=0)

    for b in result.bins[1:]:
        assert b.ci_low <= b.realised_uplift <= b.ci_high


def test_overall_realised_uplift_is_the_population_gap():
    tau_hat, treatment, outcome = _staircase()

    result = uplift_by_decile(tau_hat, treatment, outcome, n_bins=10, seed=0)

    expected = outcome[treatment == 1].mean() - outcome[treatment == 0].mean()
    assert result.overall_realised == pytest.approx(expected)
    assert result.overall_predicted == pytest.approx(tau_hat.mean())


def test_each_bin_reports_which_rows_it_holds():
    """The bins have to be joinable back to the population, or a caller that
    wants a per-decile breakdown of anything else — true persuadability, amount
    at risk — has to re-derive the binning and risks deriving it differently."""
    tau_hat, treatment, outcome = _staircase()

    result = uplift_by_decile(tau_hat, treatment, outcome, n_bins=10, seed=0)

    covered = np.concatenate([b.row_indices for b in result.bins])
    assert sorted(covered.tolist()) == list(range(len(tau_hat)))
    for lower, upper in zip(result.bins, result.bins[1:]):
        assert tau_hat[lower.row_indices].max() <= tau_hat[upper.row_indices].min()
        assert len(lower.row_indices) == lower.n


def test_a_model_that_predicts_a_constant_does_not_crash_the_chart():
    """A degenerate model — one that gives every case the same uplift — has no
    ranking to score, but it must not take the calibration down with it.

    `np.polyfit` goes singular on zero-variance input and raises LinAlgError.
    The Spearman helper immediately above already guards for exactly this case
    and returns 0.0; the slope did not, so the same degenerate input produced a
    clean 0.0 from one statistic and a crash from the other.
    """
    n = 200
    tau_flat = np.zeros(n)
    treatment = np.tile([1, 0], n // 2)
    outcome = np.tile([1.0, 0.0, 0.0, 0.0], n // 4)

    result = uplift_by_decile(tau_flat, treatment, outcome, n_bins=10, n_boot=0, seed=0)

    assert result.spearman == 0.0
    assert result.calibration_slope == 0.0, (
        "a predictor with no spread has no slope to report; 0.0 says that, a "
        "crash says nothing"
    )
    assert len(result.bins) == 10
