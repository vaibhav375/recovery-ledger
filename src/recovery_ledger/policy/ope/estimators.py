"""Off-policy value estimators for a binary contact decision.

Given logged data (X_i, T_i, Y_i) collected under a *known* propensity
e_i = P(T_i = 1 | X_i), these estimate the value V(pi) = E[Y(pi(X))] of a
candidate deterministic policy pi: X -> {0, 1} without ever running pi live.

Three estimators, in increasing sophistication:

- IPS   (Inverse Propensity Scoring): reweights observed outcomes by how
  likely the logging policy was to have taken the same action pi(X) would
  take. Unbiased given correct propensities; can have high variance when
  propensities are extreme.
- SNIPS (Self-Normalised IPS): IPS with the weights normalised to sum to 1
  instead of dividing by n. Slightly biased in finite samples, usually much
  lower variance.
- DR    (Doubly Robust): adds an outcome-regression correction term. Unbiased
  if EITHER the propensity model OR the outcome model is correct — hence
  "doubly" robust. Uses cross-fitting so the outcome model is never evaluated
  on the samples used to train it.

Reference: Dudik, Langford, Li (2011), "Doubly Robust Policy Evaluation and
Learning" (cited in RAZORPAY_BUILDATHON_TRACK3_SPEC.md, section 18).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from sklearn.base import ClassifierMixin, clone
from sklearn.model_selection import StratifiedKFold


@dataclass(frozen=True)
class PolicyValueEstimate:
    """Estimated value of a policy, with a bootstrap confidence interval."""

    method: str
    point_estimate: float
    ci_low: float
    ci_high: float
    n: int
    confidence: float = 0.95

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return (
            f"{self.method}: {self.point_estimate:.4f} "
            f"[{self.ci_low:.4f}, {self.ci_high:.4f}] (n={self.n})"
        )


def _match_weights(
    treatment: NDArray[np.int_],
    propensity: NDArray[np.float64],
    policy_actions: NDArray[np.int_],
) -> NDArray[np.float64]:
    """Importance weight per sample: 1/e_i if the logged action matches the
    policy's chosen action for that sample, else 0."""
    matches = (treatment == policy_actions).astype(np.float64)
    action_propensity = np.where(treatment == 1, propensity, 1.0 - propensity)
    action_propensity = np.clip(action_propensity, 1e-6, 1.0)
    return matches / action_propensity


def _bootstrap_ci(
    values: NDArray[np.float64],
    point_fn,
    n_boot: int,
    seed: int,
    confidence: float,
) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    n = len(values)
    boot_stats = np.empty(n_boot)
    for b in range(n_boot):
        idx = rng.integers(0, n, size=n)
        boot_stats[b] = point_fn(idx)
    alpha = (1 - confidence) / 2
    lo, hi = np.quantile(boot_stats, [alpha, 1 - alpha])
    return float(lo), float(hi)


def ips_value(
    outcome: NDArray[np.float64],
    treatment: NDArray[np.int_],
    propensity: NDArray[np.float64],
    policy_actions: NDArray[np.int_],
    *,
    n_boot: int = 500,
    seed: int = 0,
    confidence: float = 0.95,
) -> PolicyValueEstimate:
    """V_IPS(pi) = (1/n) * sum_i [ I(T_i = pi(X_i)) / e_i(T_i) ] * Y_i"""
    weights = _match_weights(treatment, propensity, policy_actions)
    contrib = weights * outcome
    point = float(np.mean(contrib))

    def stat(idx: NDArray[np.int_]) -> float:
        return float(np.mean(contrib[idx]))

    lo, hi = _bootstrap_ci(contrib, stat, n_boot, seed, confidence)
    return PolicyValueEstimate("IPS", point, lo, hi, n=len(outcome), confidence=confidence)


def snips_value(
    outcome: NDArray[np.float64],
    treatment: NDArray[np.int_],
    propensity: NDArray[np.float64],
    policy_actions: NDArray[np.int_],
    *,
    n_boot: int = 500,
    seed: int = 0,
    confidence: float = 0.95,
) -> PolicyValueEstimate:
    """V_SNIPS(pi) = sum_i w_i Y_i / sum_i w_i, w_i as in IPS."""
    weights = _match_weights(treatment, propensity, policy_actions)

    def stat(idx: NDArray[np.int_]) -> float:
        w = weights[idx]
        denom = np.sum(w)
        if denom <= 0:
            return 0.0
        return float(np.sum(w * outcome[idx]) / denom)

    point = stat(np.arange(len(outcome)))
    lo, hi = _bootstrap_ci(np.arange(len(outcome)), stat, n_boot, seed, confidence)
    return PolicyValueEstimate("SNIPS", point, lo, hi, n=len(outcome), confidence=confidence)


def doubly_robust_value(
    outcome: NDArray[np.float64],
    treatment: NDArray[np.int_],
    features: NDArray[np.float64],
    propensity: NDArray[np.float64],
    policy_actions: NDArray[np.int_],
    *,
    outcome_model: ClassifierMixin,
    n_folds: int = 5,
    n_boot: int = 500,
    seed: int = 0,
    confidence: float = 0.95,
) -> PolicyValueEstimate:
    """V_DR(pi) = (1/n) * sum_i [ q_hat(X_i, pi(X_i))
                                  + I(T_i=pi(X_i))/e_i(T_i) * (Y_i - q_hat(X_i, T_i)) ]

    q_hat is cross-fitted: each sample's q_hat is predicted by a model that
    never saw that sample during training, so the correction term doesn't
    leak information and the estimator stays valid even if q_hat overfits.

    q_hat(x, t) is estimated with ONE MODEL PER ARM (m0 fit only on T=0 rows,
    m1 fit only on T=1 rows), not a single model with T concatenated as a
    feature. That distinction matters under treatment-ratio imbalance: a
    joint model tends to under-weight a treatment indicator that is one
    feature among many, especially when the minority arm is a small share of
    every training fold — on the Criteo data (0.85 treated) an earlier joint
    -model version of this estimator was measurably biased for exactly this
    reason (see ENGINEERING_LOG.md, 2026-08-23). Per-arm models don't have
    that failure mode: each model only ever needs to represent one arm's
    outcome surface.
    """
    n = len(outcome)
    q_hat_logged = np.zeros(n)
    q_hat_policy = np.zeros(n)

    skf = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=seed)
    # stratify on the joint of treatment and outcome so every fold sees both arms
    strata = treatment * 2 + outcome.astype(int)
    for train_idx, test_idx in skf.split(features, strata):
        arm_models = {}
        for arm in (0, 1):
            arm_train_idx = train_idx[treatment[train_idx] == arm]
            model = clone(outcome_model)
            model.fit(features[arm_train_idx], outcome[arm_train_idx])
            arm_models[arm] = model

        for arm, model in arm_models.items():
            logged_mask = test_idx[treatment[test_idx] == arm]
            if len(logged_mask):
                q_hat_logged[logged_mask] = model.predict_proba(features[logged_mask])[:, 1]

            policy_mask = test_idx[policy_actions[test_idx] == arm]
            if len(policy_mask):
                q_hat_policy[policy_mask] = model.predict_proba(features[policy_mask])[:, 1]

    weights = _match_weights(treatment, propensity, policy_actions)
    correction = weights * (outcome - q_hat_logged)
    contrib = q_hat_policy + correction
    point = float(np.mean(contrib))

    def stat(idx: NDArray[np.int_]) -> float:
        return float(np.mean(contrib[idx]))

    lo, hi = _bootstrap_ci(contrib, stat, n_boot, seed, confidence)
    return PolicyValueEstimate("DR", point, lo, hi, n=n, confidence=confidence)


def always_treat_policy(n: int) -> NDArray[np.int_]:
    return np.ones(n, dtype=int)


def never_treat_policy(n: int) -> NDArray[np.int_]:
    return np.zeros(n, dtype=int)
