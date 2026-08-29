"""The lookahead comparison, and the ways it could measure nothing.

A policy comparison can fail in two directions that look identical in the
output. If the sequential solver silently degenerates to greedy, the two
policies agree everywhere and the rupee difference is zero — which reads as
"planning does not help here". If the evaluation only ever plays one attempt,
the lookahead is charged for every deferral and credited for none, and the
rupee difference is also ~zero — which reads the same way. Both produce a
confident negative result about a claim that was never actually tested.

This project shipped the second one. The first version of the horizon grid
evaluated with a single `env.step` per case and concluded across 25 settings
and 3 draws that the lookahead never wins, which was true of that measurement
and uninformative about the policy.

So these pin the two properties that make the comparison capable of returning
a real answer, rather than pinning the answer itself.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HORIZON = ROOT / "experiments" / "horizon"


def _artifact(mode: str) -> dict:
    path = HORIZON / f"results_horizon_{mode}.json"
    if not path.exists():
        pytest.skip(f"{path.name} not generated yet; run `make horizon`")
    return json.loads(path.read_text())


# ── the comparison is wired up ───────────────────────────────────────────

@pytest.mark.parametrize("mode", ["rollout", "single"])
def test_horizon_one_is_a_control_that_passes(mode):
    """With one attempt in the budget there is no future to plan over, so the
    two policies are the same algorithm. Anything less than exact agreement
    means the harness is comparing something other than planning."""
    data = _artifact(mode)
    assert data["control_horizon1_agrees_everywhere"] is True
    for row in data["grid"]:
        if row["max_attempts"] == 1:
            assert row["decision_agreement"] == 1.0, (
                f"horizon 1 disagreed on {row['disagreements']} cases at "
                f"lambda {row['lambda_annoyance']}: the comparison is broken, "
                "not the policy"
            )


def test_the_solver_actually_differs_from_greedy_somewhere():
    """The other degenerate case: a lookahead that always returns the greedy
    action would pass the control above and report a clean zero everywhere."""
    data = _artifact("rollout")
    assert data["settings_where_policies_differ"] > 0, (
        "the lookahead never once chose differently from greedy — it is not "
        "being exercised, so the comparison says nothing about planning"
    )


def test_disagreement_grows_with_the_horizon():
    """A solver that plans should diverge more when given more to plan over.
    Flat disagreement across horizons means `max_attempts` is not reaching it."""
    data = _artifact("rollout")
    by_h: dict[int, list[int]] = {}
    for row in data["grid"]:
        by_h.setdefault(row["max_attempts"], []).append(row["disagreements"])
    means = [sum(v) / len(v) for _, v in sorted(by_h.items())]
    assert means[-1] > means[0], (
        f"disagreement did not increase with horizon ({means}): the lookahead "
        "is not using the extra budget"
    )


# ── the evaluation can detect a deferral advantage ───────────────────────

def test_rollout_plays_more_than_one_attempt():
    """The bug this file exists for. A multi-attempt budget must recover more
    than a single-attempt one, or the episode is not being played out and no
    deferral strategy can ever be credited."""
    data = _artifact("rollout")
    by_h = {}
    for row in data["grid"]:
        by_h.setdefault(row["max_attempts"], []).append(row["greedy_value"])
    one = sum(by_h[1]) / len(by_h[1])
    most = sum(by_h[max(by_h)]) / len(by_h[max(by_h)])
    assert most > one, (
        f"a {max(by_h)}-attempt budget recovered no more than a 1-attempt one "
        f"({most:.1f} vs {one:.1f}): the evaluation is not rolling out"
    )


def test_mode_is_recorded_in_the_artifact():
    """Two artifacts differing only in how they were measured must say so;
    the single-step numbers are not interchangeable with the rollout ones."""
    assert _artifact("rollout")["mode"] == "rollout"


# ── replication discipline ───────────────────────────────────────────────

def test_advantage_claims_require_agreement_across_draws():
    data = _artifact("rollout")
    assert data["eval_draws"] >= 3, "one evaluation population is not a result"
    for row in data["grid"]:
        deltas = row["per_draw_delta"]
        expected = all(d > 0 for d in deltas) or all(d < 0 for d in deltas)
        assert row["advantage_consistent"] == expected, (
            f"advantage_consistent disagrees with the per-draw deltas {deltas}"
        )


# ── the report cannot drift from the artifact ────────────────────────────

def test_report_bolds_exactly_the_settings_that_replicated():
    """REPORT.md bolds the two settings where the lookahead wins in every
    draw. If a future run changes which settings replicate, the prose must
    change with it — this is the check that makes that mandatory."""
    import re

    data = _artifact("rollout")
    winners = {
        (r["max_attempts"], r["lambda_annoyance"])
        for r in data["grid"]
        if r["advantage_consistent"] and r["value_delta_per_case"] > 0
    }
    report = (HORIZON / "REPORT.md").read_text()

    claimed = set()
    for m in re.finditer(r"\*\*λ = (\d+), budget (\d+):\*\*", report):
        claimed.add((int(m.group(2)), float(m.group(1))))
    assert claimed == winners, (
        f"REPORT.md claims wins at {sorted(claimed)} but the artifact "
        f"replicated {sorted(winners)}"
    )
    assert data["settings_with_consistent_lookahead_advantage"] == len(winners)


def test_report_states_the_deployed_setting_is_within_noise():
    """The deployed configuration is budget 3, lambda 30. The report's whole
    argument for shipping greedy rests on that cell not replicating."""
    data = _artifact("rollout")
    cell = next(r for r in data["grid"]
                if r["max_attempts"] == 3 and r["lambda_annoyance"] == 30)
    assert not cell["advantage_consistent"], (
        "the deployed setting now shows a consistent lookahead advantage; "
        "REPORT.md says greedy is within noise there and must be rewritten"
    )
