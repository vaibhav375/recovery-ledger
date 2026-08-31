"""Branch coverage for `experiments/fleet/run_fleet_latency.py`'s
`latency_claim_verdict()` — the function that applies LATENCY_CLAIM_RULE.

The real sweep (see `results_fleet_latency.json`) only ever produced the
CLAIMABLE branch: the detector fired in every draw at the largest effect
size, and a false-alarm rate was always computed alongside it. That leaves
three other branches — a miss at the largest effect size, a missing
false-alarm rate, and a non-finite median — with nothing in the committed
artifact to exercise them. A bug in any of the four branches (an inverted
comparator, a flipped `is None`, wrong branch order swallowing another
case) could sit undetected indefinitely if the only test were a doc-matching
check against the one artifact this repo happens to have.

Same discipline `tests/test_run_regret.py` uses for `disagreement_verdict()`
and `tests/test_dr_diagnosis.py` uses for `fold_sweep_verdict()`: drive the
real function directly with constructed inputs, one per branch, rather than
re-deriving its logic in a test file.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "experiments" / "fleet"))
sys.path.insert(0, str(Path(__file__).parent.parent / "experiments" / "tier2_simulation"))

from run_fleet_latency import latency_claim_verdict  # noqa: E402


def _kwargs(**overrides) -> dict:
    base = dict(
        all_detected_at_largest_effect=True,
        n_missed_at_largest_effect=0,
        n_draws_at_largest_effect=8,
        median_latency_at_largest_effect=50.0,
        false_alarm_rate=0.0,
    )
    base.update(overrides)
    return base


def test_verdict_not_claimable_when_the_detector_missed_at_the_largest_effect_size():
    claimable, verdict = latency_claim_verdict(**_kwargs(
        all_detected_at_largest_effect=False,
        n_missed_at_largest_effect=2,
        n_draws_at_largest_effect=8,
    ))
    assert claimable is False
    assert "NOT CLAIMABLE" in verdict
    assert "2 of 8" in verdict
    assert "miss rate" in verdict


def test_verdict_not_claimable_without_a_false_alarm_rate():
    """Fires in every draw at the largest effect size, but no false-alarm
    control was run — LATENCY_CLAIM_RULE says neither figure is claimed
    without the other, so this must not slip through as claimable just
    because the detection side looks clean."""
    claimable, verdict = latency_claim_verdict(**_kwargs(false_alarm_rate=None))
    assert claimable is False
    assert "NOT CLAIMABLE" in verdict
    assert "false-alarm" in verdict


def test_verdict_not_claimable_when_the_median_latency_is_not_finite():
    for bad_median in (None, float("nan"), float("inf")):
        claimable, verdict = latency_claim_verdict(
            **_kwargs(median_latency_at_largest_effect=bad_median)
        )
        assert claimable is False, f"median={bad_median!r} must not be claimable"
        assert "NOT CLAIMABLE" in verdict


def test_verdict_claimable_when_every_condition_holds():
    claimable, verdict = latency_claim_verdict(**_kwargs())
    assert claimable is True
    assert "CLAIMABLE" in verdict
    assert "NOT CLAIMABLE" not in verdict
    assert "50" in verdict
    assert "0.0%" in verdict


def test_a_miss_takes_priority_over_a_missing_false_alarm_rate():
    """Both failure conditions present at once — the function must not
    silently pick the false-alarm branch's message and hide the miss."""
    claimable, verdict = latency_claim_verdict(**_kwargs(
        all_detected_at_largest_effect=False,
        n_missed_at_largest_effect=1,
        n_draws_at_largest_effect=8,
        false_alarm_rate=None,
    ))
    assert claimable is False
    assert "miss rate" in verdict
    assert "false-alarm" not in verdict


def test_math_isfinite_agrees_with_the_function_on_the_boundary_it_checks():
    """Sanity check on the finiteness test itself, since a hand-rolled
    `!= None` check would silently accept nan (nan != None is True)."""
    assert math.isfinite(50.0) is True
    assert math.isfinite(float("nan")) is False
    assert math.isfinite(float("inf")) is False
