"""Randomised exploration, so that tomorrow's policy can be evaluated from
today's logs.

A deterministic policy leaves logs that cannot be used to evaluate any other
policy. Every importance weight is either 0 or 1/1, the effective sample size
collapses to the cases where the two policies happened to agree, and the
answer for anything genuinely new is "we cannot tell you, deploy it and find
out". That is the position most production recovery systems are actually in,
and it is why they ship changes by A/B testing on live customers.

The alternative is to log a *known* amount of randomness. With propensities
recorded, IPS / SNIPS / DR (validated on real randomised data in Tier 1) can
estimate what a policy you have never run would have earned — from data you
already have, without exposing one additional customer to an untested rule.

That is not free. Exploration deliberately contacts people the current policy
would skip and skips people it would contact, and both cost money. This module
makes the cost explicit and measurable rather than hiding it;
`experiments/ope_deployment/` quantifies it and reports what it buys.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class LoggedDecision:
    """One decision, with everything an off-policy estimator needs.

    Two probabilities live here and they are NOT the same number. Confusing
    them is the single most common way an OPE pipeline produces confident
    nonsense, and it did exactly that here before the names were made explicit
    — `estimators._match_weights` wants the propensity *score*, and it was
    handed the probability of the action taken, which made every weight on an
    untreated row 1/(1-1) and every IPS estimate eight orders of magnitude
    wrong.

    p_contact       P(action = 1 | x) under the behaviour policy. The
                    propensity SCORE. This is what IPS / SNIPS / DR take.
    p_action_taken  P(action = a_i | x), the probability of what was actually
                    done. Useful for diagnostics; wrong as an estimator input.
    """

    action: int  # 1 = contact, 0 = do not
    p_contact: float
    p_action_taken: float
    greedy_action: int
    explored: bool


class EpsilonGreedy:
    """With probability `epsilon`, choose uniformly at random; otherwise take
    the greedy action.

    Propensity for a binary action space:

        P(a) = epsilon/2               if a != greedy
               epsilon/2 + (1-epsilon) if a == greedy

    Every action keeps probability at least `epsilon/2 > 0`, which is the
    overlap condition the estimators need. At `epsilon = 0` that condition
    fails and off-policy evaluation of a differing policy is not merely
    imprecise, it is undefined — the experiment sweeps epsilon down to show
    exactly that happening rather than asserting it.
    """

    N_ACTIONS = 2

    def __init__(self, epsilon: float, *, seed: int):
        if not 0.0 <= epsilon <= 1.0:
            raise ValueError(f"epsilon must be in [0, 1], got {epsilon}")
        self.epsilon = float(epsilon)
        self._rng = np.random.default_rng(seed)

    def p_of_action(self, action: int, greedy_action: int) -> float:
        """P(this action | x). Note the argument order: `action` first."""
        base = self.epsilon / self.N_ACTIONS
        return base + (1.0 - self.epsilon) * float(action == greedy_action)

    def p_contact(self, greedy_action: int) -> float:
        """The propensity score: P(action = 1 | x). What the estimators want."""
        return self.p_of_action(1, greedy_action)

    def choose(self, greedy_action: int) -> LoggedDecision:
        explored = bool(self._rng.random() < self.epsilon)
        action = (
            int(self._rng.integers(0, self.N_ACTIONS)) if explored else int(greedy_action)
        )
        return LoggedDecision(
            action=action,
            p_contact=self.p_contact(greedy_action),
            p_action_taken=self.p_of_action(action, greedy_action),
            greedy_action=int(greedy_action),
            # `explored` is whether the coin said "randomise", not whether the
            # result differed from greedy — a random draw that lands on the
            # greedy action is still an exploration step, and counting it as
            # exploitation would misstate the exploration rate.
            explored=explored,
        )


def effective_sample_size(weights: NDArray[np.float64]) -> float:
    """Kish's ESS: (sum w)^2 / sum(w^2).

    The honest diagnostic for any importance-weighted estimate. An IPS
    estimate over 2,000 logged cases whose ESS is 40 is an estimate over 40
    cases wearing a large-sample confidence interval, and reporting the
    interval without the ESS is how OPE gets used to justify bad deployments.
    """
    total = float(np.sum(weights))
    if total <= 0:
        return 0.0
    return float(total**2 / np.sum(weights**2))


def target_action_probability(
    p_contact: NDArray[np.float64], target_action: NDArray[np.int_]
) -> NDArray[np.float64]:
    """P(the target policy's action | x) under the behaviour policy.

    This is the quantity that decides whether the target policy is estimable
    at all. If it is zero anywhere, the behaviour policy would never have
    taken the action the target policy wants on that case, and no amount of
    data fixes it — the estimand is not identified.
    """
    return np.where(target_action == 1, p_contact, 1.0 - p_contact)


def importance_weights(
    logged_action: NDArray[np.int_],
    p_contact: NDArray[np.float64],
    target_action: NDArray[np.int_],
) -> NDArray[np.float64]:
    """w_i = 1{a_i = pi(x_i)} / P(a_i | x_i) — the weights IPS and SNIPS apply."""
    match = (logged_action == target_action).astype(float)
    p = target_action_probability(p_contact, target_action)
    return np.divide(match, p, out=np.zeros_like(match, dtype=float), where=p > 0)


def overlap_report(
    logged_action: NDArray[np.int_],
    p_contact: NDArray[np.float64],
    target_action: NDArray[np.int_],
) -> dict:
    """Can this log support an estimate of this policy at all?

    Two separate questions, and effective sample size alone answers only the
    second:

    **Identified?** Is there any case where the target policy's action had
    zero probability under the behaviour policy? If so the estimand does not
    exist, and importance weighting quietly answers a different question — the
    value of the target policy *restricted to the sub-population the logger
    happened to agree with*. With a deterministic logger (epsilon = 0) this is
    always violated, yet ESS can look perfectly healthy, because the agreeing
    rows are numerous and evenly weighted. That combination — an unusable log
    reporting a comfortable ESS — is precisely how OPE is used to justify a
    bad deployment.

    **Precise enough?** Given identification, is the effective sample size
    large enough for the interval to mean anything?
    """
    n = len(logged_action)
    p_target = target_action_probability(p_contact, target_action)
    w = importance_weights(logged_action, p_contact, target_action)
    ess = effective_sample_size(w)
    identified = bool(n and float(np.min(p_target)) > 0.0)
    return {
        "n": n,
        "agreement_rate": float(np.mean(logged_action == target_action)),
        "min_target_action_probability": round(float(np.min(p_target)) if n else 0.0, 4),
        "identified": identified,
        "unsupported_cases": int(np.sum(p_target <= 0.0)),
        "effective_sample_size": round(ess, 1),
        "ess_fraction": round(ess / n, 4) if n else 0.0,
        "max_weight": round(float(np.max(w)) if n else 0.0, 2),
        # A rule of thumb, stated as a rule of thumb: below a few per cent of
        # the sample the interval is being carried by a handful of rows. And
        # identification is a precondition, not a tie-breaker.
        "usable": bool(identified and n and ess / n >= 0.05),
    }
