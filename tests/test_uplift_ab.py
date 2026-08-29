"""The A/B that decides whether a model change ships.

The failure this guards against is the one it was built after: a model
improvement measured on one evaluation population, found to help, and shipped —
where a second population would have shown the opposite sign. The guard is not
a threshold on the effect size, it is the requirement that the sign replicate.

These also pin the thing that makes the comparison an A/B at all. If the two
arms differ in anything except which uplift model the policy consults — a
different churn model, different training cases, different evaluation
populations — the measured delta is not attributable to the model and the
verdict means nothing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "experiments" / "uplift_ab" / "results_uplift_ab.json"


def _artifact() -> dict:
    if not ARTIFACT.exists():
        pytest.skip("results_uplift_ab.json not generated; run `make uplift-ab`")
    return json.loads(ARTIFACT.read_text())


def test_verdict_requires_the_sign_to_replicate():
    data = _artifact()
    deltas = data["value_delta_per_draw"]
    expected = all(d > 0 for d in deltas) or all(d < 0 for d in deltas)
    assert data["value_effect_consistent"] == expected, (
        f"value_effect_consistent={data['value_effect_consistent']} disagrees "
        f"with the per-draw deltas {deltas}"
    )


def test_enough_draws_to_be_a_result():
    data = _artifact()
    assert data["eval_draws"] >= 3
    assert len(data["value_delta_per_draw"]) == data["eval_draws"]
    seeds = [r["eval_seed"] for r in data["per_draw"]]
    assert len(set(seeds)) == len(seeds), "draws must use distinct populations"


def test_the_arms_are_evaluated_on_identical_populations():
    """Both arms must be measured on the same draw, or the delta is confounded
    with population differences that dwarf it."""
    data = _artifact()
    for row in data["per_draw"]:
        assert "single" in row and "ensemble" in row
        assert row["value_delta"] == pytest.approx(
            row["ensemble"]["incremental_per_1000_cases"]
            - row["single"]["incremental_per_1000_cases"]
        )


def test_the_ensemble_arm_really_is_a_different_model():
    """A flag that silently did nothing would produce a perfect zero delta and
    a clean 'no effect' verdict."""
    data = _artifact()
    assert data["correlation_gain_consistent"], (
        "the ensemble did not consistently change the model's correlation; "
        "the two arms may be the same model"
    )
    assert abs(data["mean_correlation_gain"]) > 0.01
    for row in data["per_draw"]:
        assert row["single"]["correlation"] != row["ensemble"]["correlation"]


def test_shipped_default_matches_the_verdict():
    """The deployed default may only be the ensemble if the A/B supported it.
    This is the check that stops a recommendation from outliving its evidence."""
    data = _artifact()
    source = (ROOT / "experiments" / "tier2_simulation" / "run_batch.py").read_text()
    ships_ensemble = 'choices=["ensemble", "single"], default="ensemble"' in source
    if ships_ensemble:
        assert data["value_effect_consistent"] and data["mean_value_delta_per_1000"] > 0, (
            "run_batch defaults to the ensemble, but the A/B did not establish "
            "that it recovers more value"
        )


def test_report_does_not_claim_an_undetermined_effect():
    data = _artifact()
    report = (ROOT / "experiments" / "uplift_ab" / "REPORT.md").read_text()
    if not data["value_effect_consistent"]:
        assert "undetermined" in report.lower(), (
            "the value effect did not replicate; REPORT.md must say so"
        )
