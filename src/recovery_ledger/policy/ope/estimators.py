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


# Below this, a logged action was so unlikely that the row carries no usable
# information about it. Matches the clip in `_match_weights`.
MIN_PROPENSITY = 1e-6


@dataclass(frozen=True)
class PolicyValueEstimate:
    """Estimated value of a policy, with a bootstrap confidence interval.

    The support fields are not decoration. These estimators fail *quietly*:
    given a logged policy that never takes the action the target policy wants
    on some cases, none of them raises, returns a NaN, or produces an absurd
    number. They return the value of the target policy **restricted to the
    rows where the logging policy happened to agree** — a perfectly plausible
    figure, with a confidence interval, answering a question nobody asked.

    Measured on this project's own simulator: with a deterministic logging
    policy, `contact_everyone` had 574 of 1,200 rows carrying zero probability
    for the action it wanted, and IPS returned a comfortable finite number
    with a maximum importance weight of 1.0. Nothing about the output looked
    wrong.

    So every estimate now carries what a reader needs to reject it:

    n_matched          rows where the logged action equals the policy's action
    n_unsupported      rows where the policy's action had ~zero probability
    identified         n_unsupported == 0; False means the estimand does not
                       exist and the point estimate is answering a different
                       question
    effective_sample_size
                       Kish's ESS over the importance weights. An estimate
                       over 2,000 rows with an ESS of 40 is an estimate over
                       40 rows wearing a large-sample interval.
    """

    method: str
    point_estimate: float
    ci_low: float
    ci_high: float
    n: int
    confidence: float = 0.95
    n_matched: int = -1
    n_unsupported: int = -1
    effective_sample_size: float = float("nan")
    min_action_propensity: float = float("nan")
    degenerate_bootstrap_draws: int = 0

    @property
    def identified(self) -> bool:
        """False when some case's policy action could never have been logged."""
        return self.n_unsupported == 0

    @property
    def ess_fraction(self) -> float:
        return self.effective_sample_size / self.n if self.n else 0.0

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        flag = "" if self.identified else "  [NOT IDENTIFIED]"
        return (
            f"{self.method}: {self.point_estimate:.4f} "
            f"[{self.ci_low:.4f}, {self.ci_high:.4f}] "
            f"(n={self.n}, ess={self.effective_sample_size:.0f}){flag}"
        )


def _support(
    treatment: NDArray[np.int_],
    propensity: NDArray[np.float64],
    policy_actions: NDArray[np.int_],
) -> dict:
    """How much of this log actually speaks to this policy."""
    action_propensity = np.where(policy_actions == 1, propensity, 1.0 - propensity)
    weights = _match_weights(treatment, propensity, policy_actions)
    total = float(np.sum(weights))
    ess = float(total**2 / np.sum(weights**2)) if total > 0 else 0.0
    return {
        "n_matched": int(np.sum(treatment == policy_actions)),
        "n_unsupported": int(np.sum(action_propensity < MIN_PROPENSITY)),
        "effective_sample_size": round(ess, 1),
        "min_action_propensity": float(np.min(action_propensity)) if len(treatment) else float("nan"),
    }


def _match_weights(
    treatment: NDArray[np.int_],
    propensity: NDArray[np.float64],
    policy_actions: NDArray[np.int_],
) -> NDArray[np.float64]:
    """Importance weight per sample: 1/e_i if the logged action matches the
    policy's chosen action for that sample, else 0."""
    matches = (treatment == policy_actions).astype(np.float64)
    action_propensity = np.where(treatment == 1, propensity, 1.0 - propensity)
    # The clip stabilises division. It does NOT make an unsupported row
    # informative — the weight is zero there anyway, because the actions
    # disagree. `_support` is what tells the caller those rows existed.
    action_propensity = np.clip(action_propensity, MIN_PROPENSITY, 1.0)
    return matches / action_propensity


def _bootstrap_ci(
    values: NDArray[np.float64],
    point_fn,
    n_boot: int,
    seed: int,
    confidence: float,
) -> tuple[float, float, int]:
    """Percentile bootstrap. Returns (lo, hi, degenerate_draws).

    Degenerate draws — resamples for which the statistic is undefined, e.g. a
    SNIPS resample containing no matched rows at all — are excluded via
    nanquantile and counted. Silently folding them in as zero would drag the
    interval toward zero and narrow it, which is the opposite of what missing
    evidence should do to an interval.
    """
    rng = np.random.default_rng(seed)
    n = len(values)
    boot_stats = np.empty(n_boot)
    for b in range(n_boot):
        idx = rng.integers(0, n, size=n)
        boot_stats[b] = point_fn(idx)
    degenerate = int(np.sum(~np.isfinite(boot_stats)))
    alpha = (1 - confidence) / 2
    if degenerate == n_boot:
        return float("nan"), float("nan"), degenerate
    lo, hi = np.nanquantile(boot_stats, [alpha, 1 - alpha])
    return float(lo), float(hi), degenerate


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

    lo, hi, degenerate = _bootstrap_ci(contrib, stat, n_boot, seed, confidence)
    return PolicyValueEstimate(
        "IPS", point, lo, hi, n=len(outcome), confidence=confidence,
        degenerate_bootstrap_draws=degenerate,
        **_support(treatment, propensity, policy_actions),
    )


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
            # No matched rows: this resample carries no information about the
            # policy. Previously this returned 0.0, which reports "we have no
            # evidence" as "it is worth exactly zero" — indistinguishable from
            # a real estimate, and for a monetary objective a plausible one.
            return float("nan")
        return float(np.sum(w * outcome[idx]) / denom)

    point = stat(np.arange(len(outcome)))
    lo, hi, degenerate = _bootstrap_ci(
        np.arange(len(outcome)), stat, n_boot, seed, confidence
    )
    return PolicyValueEstimate(
        "SNIPS", point, lo, hi, n=len(outcome), confidence=confidence,
        degenerate_bootstrap_draws=degenerate,
        **_support(treatment, propensity, policy_actions),
    )


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
    contrib = dr_contributions(
        outcome, treatment, features, propensity, policy_actions,
        outcome_model=outcome_model, n_folds=n_folds, seed=seed,
    )
    n = len(outcome)
    point = float(np.mean(contrib))

    def stat(idx: NDArray[np.int_]) -> float:
        return float(np.mean(contrib[idx]))

    lo, hi, degenerate = _bootstrap_ci(contrib, stat, n_boot, seed, confidence)
    return PolicyValueEstimate(
        "DR", point, lo, hi, n=n, confidence=confidence,
        degenerate_bootstrap_draws=degenerate,
        **_support(treatment, propensity, policy_actions),
    )


def dr_contributions(
    outcome: NDArray[np.float64],
    treatment: NDArray[np.int_],
    features: NDArray[np.float64],
    propensity: NDArray[np.float64],
    policy_actions: NDArray[np.int_],
    *,
    outcome_model: ClassifierMixin,
    n_folds: int = 5,
    seed: int = 0,
) -> NDArray[np.float64]:
    """The per-sample DR terms, before they are averaged.

    Exposed separately because the mean is not the only thing worth asking of
    them. Comparing two policies needs the *paired* difference of these terms
    on the same resampled rows: the two policy values share the data, the
    fitted q_hat, and most of the correction, so bootstrapping them
    independently and differencing the intervals overstates the uncertainty of
    the contrast by treating shared noise as if it cancelled twice.
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
    return q_hat_policy + correction


def always_treat_policy(n: int) -> NDArray[np.int_]:
    return np.ones(n, dtype=int)


def never_treat_policy(n: int) -> NDArray[np.int_]:
    return np.zeros(n, dtype=int)
