"""Validate IPS / SNIPS / DR against a fully-controlled synthetic RCT where the
true policy value is known because we wrote the data-generating process.

This is the same validation *logic* Tier 1 applies to real data (Hillstrom /
Criteo): compute a policy's value with each estimator, and check it against a
ground truth computed independently of the estimator under test. Here the
ground truth is an oracle Monte Carlo estimate from a very large sample of the
same generative process; on real RCT data (see experiments/tier1_criteo/) the
role of "independent ground truth" is played by the raw empirical arm means,
which is what IPS/SNIPS/DR are all trying to recover under reweighting.
"""

from __future__ import annotations

import numpy as np
import pytest
from sklearn.ensemble import GradientBoostingClassifier

from recovery_ledger.policy.ope.estimators import (
    always_treat_policy,
    doubly_robust_value,
    ips_value,
    never_treat_policy,
    snips_value,
)

PROPENSITY = 0.5


def _sample(n: int, seed: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """A known DGP: 3 covariates, randomised binary treatment, binary outcome
    with a treatment effect on the log-odds scale."""
    rng = np.random.default_rng(seed)
    X = rng.normal(size=(n, 3))
    T = rng.binomial(1, PROPENSITY, size=n)
    logit = -0.4 + 0.5 * X[:, 0] - 0.3 * X[:, 1] + 0.2 * X[:, 2] + 1.1 * T
    prob = 1.0 / (1.0 + np.exp(-logit))
    Y = rng.binomial(1, prob).astype(np.float64)
    return X, T, Y


@pytest.fixture(scope="module")
def oracle() -> dict[str, float]:
    """True policy values from a 500k-sample Monte Carlo draw of the same DGP.
    Not touched by any estimator under test."""
    X, T, Y = _sample(500_000, seed=999)
    return {
        "always_treat": float(Y[T == 1].mean()),
        "never_treat": float(Y[T == 0].mean()),
    }


@pytest.fixture(scope="module")
def logged_data() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    X, T, Y = _sample(8_000, seed=42)
    propensity = np.full(len(Y), PROPENSITY)
    return Y, T, X, propensity


def test_ips_recovers_always_treat_value(logged_data, oracle):
    Y, T, X, propensity = logged_data
    est = ips_value(Y, T, propensity, always_treat_policy(len(Y)), seed=1)
    assert abs(est.point_estimate - oracle["always_treat"]) < 0.03
    assert est.ci_low <= est.point_estimate <= est.ci_high


def test_ips_recovers_never_treat_value(logged_data, oracle):
    Y, T, X, propensity = logged_data
    est = ips_value(Y, T, propensity, never_treat_policy(len(Y)), seed=1)
    assert abs(est.point_estimate - oracle["never_treat"]) < 0.03


def test_snips_recovers_treatment_effect(logged_data, oracle):
    Y, T, X, propensity = logged_data
    treated = snips_value(Y, T, propensity, always_treat_policy(len(Y)), seed=2)
    control = snips_value(Y, T, propensity, never_treat_policy(len(Y)), seed=2)
    true_effect = oracle["always_treat"] - oracle["never_treat"]
    estimated_effect = treated.point_estimate - control.point_estimate
    assert abs(estimated_effect - true_effect) < 0.04


def test_doubly_robust_recovers_treatment_effect(logged_data, oracle):
    Y, T, X, propensity = logged_data
    base_model = GradientBoostingClassifier(random_state=0, n_estimators=50)
    treated = doubly_robust_value(
        Y, T, X, propensity, always_treat_policy(len(Y)),
        outcome_model=base_model, seed=3,
    )
    control = doubly_robust_value(
        Y, T, X, propensity, never_treat_policy(len(Y)),
        outcome_model=base_model, seed=3,
    )
    true_effect = oracle["always_treat"] - oracle["never_treat"]
    estimated_effect = treated.point_estimate - control.point_estimate
    assert abs(estimated_effect - true_effect) < 0.04


def test_doubly_robust_has_lower_variance_than_ips(logged_data):
    """The headline reason to use DR over IPS: tighter confidence intervals
    at the same sample size, because the outcome-regression term soaks up
    variance that IPS leaves entirely to the importance weights."""
    Y, T, X, propensity = logged_data
    base_model = GradientBoostingClassifier(random_state=0, n_estimators=50)
    ips_est = ips_value(Y, T, propensity, always_treat_policy(len(Y)), seed=4)
    dr_est = doubly_robust_value(
        Y, T, X, propensity, always_treat_policy(len(Y)),
        outcome_model=base_model, seed=4,
    )
    ips_width = ips_est.ci_high - ips_est.ci_low
    dr_width = dr_est.ci_high - dr_est.ci_low
    assert dr_width < ips_width


def test_deterministic_given_seed(logged_data):
    Y, T, X, propensity = logged_data
    est_a = ips_value(Y, T, propensity, always_treat_policy(len(Y)), seed=7)
    est_b = ips_value(Y, T, propensity, always_treat_policy(len(Y)), seed=7)
    assert est_a.point_estimate == est_b.point_estimate
    assert est_a.ci_low == est_b.ci_low
    assert est_a.ci_high == est_b.ci_high
