"""Off-policy estimators must not answer a question nobody asked.

These three estimators fail quietly. Given a logging policy that never takes
the action a target policy wants on some cases, none of them raises, returns
NaN, or produces an absurd number. They return the value of the target policy
**restricted to the rows where the logging policy happened to agree** — a
plausible figure, with a confidence interval, that is not an estimate of the
thing it claims to estimate.

Measured on this project's own simulator with a deterministic logger:
`contact_everyone` had 574 of 1,200 rows carrying zero probability for the
action it wanted, IPS returned 0.109 against a truth of 0.186, and the 95%
interval [0.094, 0.128] excluded the truth. Maximum importance weight: 1.0.
Nothing about the output looked wrong.

Every estimate now carries the support that lets a reader reject it. These
tests pin that, and pin the two degenerate cases that used to be swallowed.
"""

from __future__ import annotations

import numpy as np
import pytest
from sklearn.ensemble import GradientBoostingClassifier

from recovery_ledger.policy.ope.estimators import (
    doubly_robust_value,
    ips_value,
    snips_value,
)

METHODS = ("ips", "snips", "dr")


def _call(method: str, outcome, treatment, propensity, target, features=None, **kw):
    if method == "ips":
        return ips_value(outcome, treatment, propensity, target, n_boot=60, seed=0, **kw)
    if method == "snips":
        return snips_value(outcome, treatment, propensity, target, n_boot=60, seed=0, **kw)
    return doubly_robust_value(
        outcome, treatment, features, propensity, target,
        outcome_model=GradientBoostingClassifier(random_state=0),
        n_folds=3, n_boot=60, seed=0, **kw
    )


def _randomised(n=600, seed=0):
    rng = np.random.default_rng(seed)
    features = rng.normal(size=(n, 3))
    propensity = np.full(n, 0.5)
    treatment = (rng.random(n) < propensity).astype(int)
    outcome = (rng.random(n) < 0.2 + 0.2 * treatment).astype(float)
    return features, treatment, propensity, outcome


# ── identification is reported ───────────────────────────────────────────

@pytest.mark.parametrize("method", METHODS)
def test_a_well_supported_estimate_is_marked_identified(method):
    features, treatment, propensity, outcome = _randomised()
    target = np.ones(len(outcome), dtype=int)
    est = _call(method, outcome, treatment, propensity, target, features)
    assert est.identified is True
    assert est.n_unsupported == 0
    assert est.effective_sample_size > 0
    assert est.min_action_propensity == pytest.approx(0.5)


@pytest.mark.parametrize("method", METHODS)
def test_a_deterministic_log_marks_a_differing_policy_unidentified(method):
    """The exact failure that shipped. The point estimate is still a number —
    that is the whole problem — but it now announces that it is not an
    estimate of the target policy."""
    features, treatment, propensity, outcome = _randomised()
    # The logging policy is deterministic: propensity is 0 or 1, matching what
    # it did. Any policy that disagrees anywhere is not identified.
    propensity = treatment.astype(float)
    target = np.ones(len(outcome), dtype=int)
    est = _call(method, outcome, treatment, propensity, target, features)
    assert est.identified is False
    assert est.n_unsupported == int(np.sum(treatment == 0))
    assert np.isfinite(est.point_estimate), (
        "the estimate is still finite and plausible — which is why the flag "
        "has to exist"
    )


@pytest.mark.parametrize("method", METHODS)
def test_matched_row_count_is_reported(method):
    features, treatment, propensity, outcome = _randomised()
    target = np.zeros(len(outcome), dtype=int)
    est = _call(method, outcome, treatment, propensity, target, features)
    assert est.n_matched == int(np.sum(treatment == 0))
    assert est.n == len(outcome)


def test_effective_sample_size_collapses_under_extreme_propensities():
    """ESS is the second half of the diagnostic: a log can be identified and
    still carry almost no information."""
    n = 2000
    rng = np.random.default_rng(1)
    propensity = np.full(n, 0.02)  # contact is rare but never impossible
    treatment = (rng.random(n) < propensity).astype(int)
    outcome = rng.random(n)
    target = np.ones(n, dtype=int)
    est = ips_value(outcome, treatment, propensity, target, n_boot=40, seed=0)
    assert est.identified is True
    assert est.ess_fraction < 0.05, "a 2% logging rate cannot support a full-contact policy"


# ── the degenerate cases that used to be swallowed ───────────────────────

def test_snips_reports_no_evidence_as_nan_not_zero():
    """`no evidence` and `worth exactly zero` are different answers, and for a
    monetary objective the second is a plausible one. SNIPS used to return
    0.0 when no row matched."""
    n = 200
    treatment = np.zeros(n, dtype=int)
    propensity = np.full(n, 0.5)
    outcome = np.full(n, 500.0)
    target = np.ones(n, dtype=int)  # nothing the logger did matches
    est = snips_value(outcome, treatment, propensity, target, n_boot=30, seed=0)
    assert est.n_matched == 0
    assert np.isnan(est.point_estimate), "no support must not be reported as 0.0"


def test_degenerate_bootstrap_draws_are_counted_not_folded_in_as_zero():
    """A resample with no matched rows says nothing. Counting it as zero drags
    the interval toward zero and narrows it — missing evidence making an
    interval *more* confident."""
    n = 300
    rng = np.random.default_rng(2)
    treatment = np.zeros(n, dtype=int)
    treatment[:3] = 1  # only three matched rows; some resamples will miss all
    propensity = np.full(n, 0.5)
    outcome = np.full(n, 100.0)
    target = np.ones(n, dtype=int)
    est = snips_value(outcome, treatment, propensity, target, n_boot=400, seed=3)
    assert est.degenerate_bootstrap_draws > 0
    # The surviving draws all see outcome == 100, so the interval must sit
    # there rather than being pulled down toward zero.
    assert est.ci_low == pytest.approx(100.0)
    assert est.ci_high == pytest.approx(100.0)


def test_ips_is_unbiased_on_a_genuine_randomised_log():
    """The estimators still have to work. A diagnostic that made them wrong
    would be a poor trade."""
    n = 20000
    rng = np.random.default_rng(4)
    propensity = np.full(n, 0.5)
    treatment = (rng.random(n) < propensity).astype(int)
    truth_if_treated = 0.4
    outcome = (rng.random(n) < np.where(treatment == 1, truth_if_treated, 0.1)).astype(float)
    est = ips_value(outcome, treatment, propensity, np.ones(n, dtype=int), n_boot=60, seed=0)
    assert est.point_estimate == pytest.approx(truth_if_treated, abs=0.02)
    assert est.ci_low <= truth_if_treated <= est.ci_high
