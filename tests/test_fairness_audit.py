"""The fairness audit's statistics, pinned against the ways they mislead.

A disparity audit is unusually easy to get wrong in a direction nobody
notices, because a null result is the comfortable one. Two failures already
happened while writing it:

* `_cell_gap` is a max-minus-min over several groups, so it is bounded below
  by sampling noise and never approaches zero. With four language groups over
  thirty thin cells, the *conditional* gap came out at 0.209 against a raw
  unconditional gap of 0.056 — the conditioning appeared to reveal a disparity
  four times larger than the one visible without it. The permutation p-value
  was fine; the effect size reported next to it was noise.
* Sixteen hypotheses were tested and the verdict was read off an uncorrected
  0.05, which is a coin flip's chance of manufacturing a finding.
* Measuring only customer contact reported failed subscriptions as neglected
  (0.9% contact) when the policy was working 80% of them by silent retry —
  correct behaviour, read as a disparity.

These tests fix the behaviour under known ground truth: planted disparities
must be detected, absent ones must not be, and the reported size must be
close to the size actually planted.
"""

from __future__ import annotations

import numpy as np
import pytest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "experiments" / "fairness"))

from run_fairness import _cell_gap, _quantile_labels, permutation_p  # noqa: E402


def _cells(n: int, k: int = 5) -> np.ndarray:
    return np.array([f"C{i % k}" for i in range(n)])


# ── the gap statistic ────────────────────────────────────────────────────

def test_identical_groups_still_produce_a_positive_raw_gap():
    """The property that made the first version misleading, pinned so nobody
    reads `observed` as an effect size again."""
    rng = np.random.default_rng(0)
    n = 2000
    labels = np.array(["a", "b", "c", "d"] * (n // 4))
    outcome = (rng.random(n) < 0.3).astype(float)  # identical for every group
    gap = _cell_gap(labels, outcome, _cells(n))
    assert gap > 0.02, "max-minus-min over four groups cannot be near zero by chance"


def test_excess_over_the_null_is_near_zero_when_no_disparity_exists():
    """What `observed` cannot do, `excess` can: report roughly nothing when
    there is roughly nothing."""
    rng = np.random.default_rng(1)
    n = 2400
    labels = np.array(["a", "b", "c"] * (n // 3))
    outcome = (rng.random(n) < 0.3).astype(float)
    res = permutation_p(labels, outcome, _cells(n), n_perm=300, seed=1)
    assert abs(res["excess"]) < 0.03
    assert res["p"] > 0.05


def test_a_planted_disparity_is_detected_and_sized_correctly():
    rng = np.random.default_rng(2)
    n = 2400
    labels = np.array(["a", "b"] * (n // 2))
    base = np.where(labels == "a", 0.6, 0.2)  # a planted 40-point gap
    outcome = (rng.random(n) < base).astype(float)
    res = permutation_p(labels, outcome, _cells(n), n_perm=300, seed=2)
    assert res["p"] < 0.01
    assert res["excess"] == pytest.approx(0.40, abs=0.06)


def test_a_disparity_fully_explained_by_the_conditioning_is_not_flagged():
    """The core of the design. Group `a` is contacted far more, but only
    because it sits in the high-uplift cells — exactly the situation the
    objective is entitled to produce. Conditioning must absorb it."""
    rng = np.random.default_rng(3)
    n = 3000
    score = rng.random(n)
    # Membership is driven by the score, so the raw gap is large...
    labels = np.where(rng.random(n) < score, "a", "b")
    # ...but within a cell of score, both groups are treated identically.
    outcome = (rng.random(n) < score).astype(float)
    cells = _quantile_labels(score, 10, "D")

    raw = abs(outcome[labels == "a"].mean() - outcome[labels == "b"].mean())
    res = permutation_p(labels, outcome, cells, n_perm=300, seed=3)
    assert raw > 0.15, "the unconditional gap should be obvious"
    assert res["p"] > 0.05, "conditioning should absorb a gap the cells explain"


def test_a_disparity_that_survives_conditioning_is_flagged():
    """The opposite case: same cell, different treatment. This is the one that
    should never be missed."""
    rng = np.random.default_rng(4)
    n = 3000
    score = rng.random(n)
    labels = np.array(["a", "b"] * (n // 2))
    # Within every cell of score, group a is favoured by 25 points.
    p = np.clip(score + np.where(labels == "a", 0.25, -0.25), 0.01, 0.99)
    outcome = (rng.random(n) < p).astype(float)
    cells = _quantile_labels(score, 10, "D")
    res = permutation_p(labels, outcome, cells, n_perm=300, seed=4)
    assert res["p"] < 0.01
    assert res["excess"] > 0.2


def test_cells_with_one_represented_group_are_skipped_not_counted_as_zero():
    """Counting an unmeasurable cell as a zero gap would dilute the statistic
    toward 'no disparity' precisely where the data is thinnest."""
    labels = np.array(["a"] * 50 + ["b"] * 50)
    outcome = np.concatenate([np.ones(50), np.zeros(50)])
    # One cell holds only group a, the other holds both.
    lonely = np.array(["C0"] * 50 + ["C1"] * 50)
    mixed = np.array(["C0"] * 25 + ["C1"] * 25 + ["C0"] * 25 + ["C1"] * 25)
    assert _cell_gap(labels, outcome, lonely) == 0.0  # nothing measurable at all
    assert _cell_gap(labels, outcome, mixed) == pytest.approx(1.0)


# ── multiple comparisons ─────────────────────────────────────────────────

def test_the_audit_corrects_for_the_number_of_hypotheses():
    from run_fairness import audit

    result = audit(n_train=600, n_eval=400, n_perm=50)
    assert result["n_hypotheses_tested"] == 4 * len(result["segments"])
    # The stored value is rounded for a readable artifact; the comparison the
    # verdict actually uses is unrounded (see `p_exact` in permutation_p).
    assert result["bonferroni_alpha"] == pytest.approx(
        0.05 / result["n_hypotheses_tested"], abs=1e-5
    )
    for seg in result["segments"].values():
        # The corrected verdict can never be laxer than the uncorrected one.
        if seg["unexplained"]:
            assert seg["unexplained_at_uncorrected_alpha"]


def test_every_segment_reports_model_quality_per_group():
    """A group the model understands worse gets worse decisions even when its
    contact rate looks even-handed. That must always be visible."""
    from run_fairness import audit

    result = audit(n_train=600, n_eval=400, n_perm=20)
    for seg in result["segments"].values():
        for group in seg["groups"].values():
            assert "model_correlation" in group
            assert "true_expected_value_of_contact" in group
            # Contact and "worked at all" must both be visible, or a group
            # served on a silent channel looks abandoned.
            assert group["worked_rate"] >= group["contact_rate"]


def test_permutation_p_is_never_zero():
    """(hits + 1) / (n + 1), not hits / n. A p-value of exactly zero from a
    finite permutation test is a claim the test cannot make."""
    rng = np.random.default_rng(5)
    n = 1200
    labels = np.array(["a", "b"] * (n // 2))
    outcome = np.where(labels == "a", 1.0, 0.0)  # maximal separation
    res = permutation_p(labels, outcome, _cells(n), n_perm=50, seed=5)
    assert res["p"] > 0
    assert res["p_exact"] == pytest.approx(1 / 51, abs=1e-12)
    assert res["p"] == pytest.approx(1 / 51, abs=1e-4)
