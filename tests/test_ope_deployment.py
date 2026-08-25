"""Exploration and overlap, pinned.

Off-policy evaluation fails silently. There is no exception when you hand an
estimator the wrong probability or ask it about a policy the log cannot
support — it returns a number, with a confidence interval, and the number is
wrong. Both of those happened while this experiment was being written:

* `estimators._match_weights` wants the propensity **score**, P(contact | x),
  and derives the untreated arm as `1 - propensity`. It was handed the
  probability of the action actually taken. On untreated rows that made the
  denominator `1 - 1 = 0`, and IPS came back at 1.4e8 for an outcome whose
  true mean is about 200.
* `overlap_report` judged usability on effective sample size alone. At
  epsilon = 0 the deployed policy's log has a large, evenly weighted set of
  agreeing rows, so ESS looked healthy for policies that were not identified
  at all.

Neither is caught by types, and neither raises. They are caught here.
"""

from __future__ import annotations

import numpy as np
import pytest

from recovery_ledger.policy.exploration import (
    EpsilonGreedy,
    effective_sample_size,
    importance_weights,
    overlap_report,
    target_action_probability,
)
from recovery_ledger.policy.ope.estimators import ips_value


# ── the two probabilities are different numbers ──────────────────────────

def test_p_contact_is_the_propensity_score_not_the_probability_of_the_action():
    e = EpsilonGreedy(0.10, seed=1)
    # Greedy says do not contact. P(contact) is the exploration half-share.
    assert e.p_contact(greedy_action=0) == pytest.approx(0.05)
    # But the probability of the action it will usually take is 0.95.
    assert e.p_of_action(0, greedy_action=0) == pytest.approx(0.95)
    assert e.p_contact(greedy_action=1) == pytest.approx(0.95)


def test_action_probabilities_sum_to_one():
    e = EpsilonGreedy(0.3, seed=2)
    for greedy in (0, 1):
        assert e.p_of_action(0, greedy) + e.p_of_action(1, greedy) == pytest.approx(1.0)


def test_logged_decision_carries_both_and_they_differ_off_greedy():
    e = EpsilonGreedy(0.5, seed=3)
    decisions = [e.choose(1) for _ in range(200)]
    off_greedy = [d for d in decisions if d.action != d.greedy_action]
    assert off_greedy, "epsilon=0.5 should produce some non-greedy actions"
    for d in off_greedy:
        assert d.p_contact == pytest.approx(0.75)      # P(contact | greedy=1)
        assert d.p_action_taken == pytest.approx(0.25)  # P(the action taken)


def test_passing_the_wrong_probability_produces_a_wildly_wrong_estimate():
    """The bug, reproduced. This is why the two fields have different names.

    With a deterministic logger every untreated row has p_action_taken = 1, so
    `1 - p` is zero and the weight explodes. The estimator does not complain —
    it returns a number roughly six orders of magnitude too large.
    """
    n = 400
    rng = np.random.default_rng(0)
    greedy = rng.integers(0, 2, size=n)
    outcome = rng.normal(200, 50, size=n)
    target = np.zeros(n, dtype=int)

    e = EpsilonGreedy(0.0, seed=0)
    decisions = [e.choose(int(g)) for g in greedy]
    action = np.array([d.action for d in decisions])
    correct = np.array([d.p_contact for d in decisions])
    wrong = np.array([d.p_action_taken for d in decisions])

    right = ips_value(outcome, action, correct, target, n_boot=20, seed=0)
    broken = ips_value(outcome, action, wrong, target, n_boot=20, seed=0)
    assert abs(broken.point_estimate) > 1000 * abs(right.point_estimate)


# ── overlap and identification ───────────────────────────────────────────

def test_epsilon_zero_leaves_every_differing_policy_unidentified():
    n = 300
    rng = np.random.default_rng(1)
    greedy = rng.integers(0, 2, size=n)
    e = EpsilonGreedy(0.0, seed=1)
    decisions = [e.choose(int(g)) for g in greedy]
    action = np.array([d.action for d in decisions])
    p_contact = np.array([d.p_contact for d in decisions])

    same = overlap_report(action, p_contact, greedy)
    assert same["identified"] is True and same["usable"] is True

    for target in (np.ones(n, dtype=int), np.zeros(n, dtype=int), 1 - greedy):
        rep = overlap_report(action, p_contact, target)
        assert rep["identified"] is False
        assert rep["usable"] is False, "an unidentified estimand is never usable"
        assert rep["unsupported_cases"] > 0


def test_ess_alone_would_have_called_an_unidentified_log_usable():
    """The specific trap: healthy ESS, no identification. If this ever starts
    passing on ESS alone, the diagnostic has regressed to the broken version."""
    n = 400
    greedy = np.zeros(n, dtype=int)  # the logger never contacts anyone
    e = EpsilonGreedy(0.0, seed=2)
    decisions = [e.choose(int(g)) for g in greedy]
    action = np.array([d.action for d in decisions])
    p_contact = np.array([d.p_contact for d in decisions])

    target = np.zeros(n, dtype=int)  # agrees everywhere
    rep = overlap_report(action, p_contact, np.ones(n, dtype=int))
    healthy = overlap_report(action, p_contact, target)

    assert healthy["ess_fraction"] > 0.9  # ESS looks perfect on the agreeing target
    assert rep["identified"] is False     # but the differing one is not estimable
    assert rep["effective_sample_size"] == 0


@pytest.mark.parametrize("epsilon", [0.05, 0.1, 0.25, 0.5])
def test_any_positive_epsilon_identifies_every_policy(epsilon):
    n = 300
    rng = np.random.default_rng(3)
    greedy = rng.integers(0, 2, size=n)
    e = EpsilonGreedy(epsilon, seed=3)
    decisions = [e.choose(int(g)) for g in greedy]
    action = np.array([d.action for d in decisions])
    p_contact = np.array([d.p_contact for d in decisions])
    for target in (np.ones(n, dtype=int), np.zeros(n, dtype=int), 1 - greedy):
        assert overlap_report(action, p_contact, target)["identified"] is True


def test_overlap_degrades_monotonically_as_exploration_falls():
    """Less exploration must never look like better evidence."""
    n = 2000
    rng = np.random.default_rng(4)
    greedy = rng.integers(0, 2, size=n)
    target = 1 - greedy  # maximally different from the logger
    ess = []
    for epsilon in (0.5, 0.25, 0.1, 0.05):
        e = EpsilonGreedy(epsilon, seed=4)
        decisions = [e.choose(int(g)) for g in greedy]
        action = np.array([d.action for d in decisions])
        p_contact = np.array([d.p_contact for d in decisions])
        ess.append(overlap_report(action, p_contact, target)["effective_sample_size"])
    assert ess == sorted(ess, reverse=True), f"ESS did not fall with epsilon: {ess}"


# ── the primitives ───────────────────────────────────────────────────────

def test_effective_sample_size_bounds():
    assert effective_sample_size(np.ones(100)) == pytest.approx(100)
    spiky = np.array([100.0] + [0.0] * 99)
    assert effective_sample_size(spiky) == pytest.approx(1.0)
    assert effective_sample_size(np.zeros(10)) == 0.0


def test_importance_weights_are_zero_where_the_policies_disagree():
    action = np.array([1, 0, 1, 0])
    p_contact = np.array([0.9, 0.1, 0.9, 0.1])
    target = np.array([1, 1, 0, 0])
    w = importance_weights(action, p_contact, target)
    assert w[0] == pytest.approx(1 / 0.9)
    assert w[1] == 0.0  # logged 0, target wants 1
    assert w[2] == 0.0  # logged 1, target wants 0
    assert w[3] == pytest.approx(1 / 0.9)  # P(action 0) = 1 - 0.1


def test_target_action_probability_flips_for_the_untreated_arm():
    p_contact = np.array([0.8, 0.8])
    got = target_action_probability(p_contact, np.array([1, 0]))
    assert got[0] == pytest.approx(0.8)
    assert got[1] == pytest.approx(0.2)


def test_epsilon_outside_the_unit_interval_is_rejected():
    for bad in (-0.1, 1.5):
        with pytest.raises(ValueError):
            EpsilonGreedy(bad, seed=0)


def test_exploration_rate_counts_the_coin_not_the_outcome():
    """A random draw that lands on the greedy action is still exploration.
    Counting only the differing draws would report half the true rate."""
    e = EpsilonGreedy(0.4, seed=7)
    decisions = [e.choose(1) for _ in range(4000)]
    explored = np.mean([d.explored for d in decisions])
    differed = np.mean([d.action != d.greedy_action for d in decisions])
    assert explored == pytest.approx(0.4, abs=0.03)
    assert differed == pytest.approx(0.2, abs=0.03)
