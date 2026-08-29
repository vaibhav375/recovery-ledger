"""The churn-penalty curve, and the claim it is supposed to justify.

`lambda_churn = 4.0` is a policy default that costs real money, so the sweep
behind it is load-bearing. It spent months as a table in three markdown files
and a source comment with no artifact behind it, derived from a baselines run
the repo had stopped reproducing.

Two failure modes are pinned here. The first is drift: prose quoting numbers
the artifact no longer contains. The second is subtler and actually happened —
a dominance check written against confidence-interval overlap rather than the
point estimate, which cannot fail in the direction that matters and would have
published a 9% revenue loss as "strictly dominates".
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "experiments" / "churn_lambda" / "results_lambda_sweep.json"


def _artifact() -> dict:
    if not ARTIFACT.exists():
        pytest.skip("results_lambda_sweep.json not generated; run `make lambda-sweep`")
    return json.loads(ARTIFACT.read_text())


def test_dominance_is_judged_on_the_point_estimate_not_interval_overlap():
    """The check that was wrong. Overlapping intervals mean the difference is
    unresolved at this sample size, not that the point estimate is no worse."""
    d = _artifact()["dominance_4_over_2"]
    assert d is not None
    assert "value_point_not_worse" in d and "value_indistinguishable_at_95" in d
    expected = (d["value_point_not_worse"] and d["fewer_contacts"]
                and d["lower_dnd_exposure"])
    assert d["holds"] == expected, (
        "dominance verdict does not follow from its own components"
    )
    if d["value_indistinguishable_at_95"] and not d["value_point_not_worse"]:
        assert not d["holds"], (
            "dominance was granted on interval overlap alone, which is the "
            "exact defect this test exists for"
        )


def test_docs_do_not_assert_dominance_when_the_artifact_denies_it():
    d = _artifact()["dominance_4_over_2"]
    if d["holds"]:
        return
    results = (ROOT / "RESULTS.md").read_text()
    decision = (ROOT / "src" / "recovery_ledger" / "policy" / "decision.py").read_text()
    assert "does not dominate" in results, (
        "the artifact says 4.0 does not dominate 2.0; RESULTS.md must say so"
    )
    assert "does NOT dominate" in decision, (
        "the artifact says 4.0 does not dominate 2.0; the lambda_churn comment "
        "in decision.py must say so"
    )


def test_the_published_table_matches_the_artifact():
    rows = {r["lambda_churn"]: r for r in _artifact()["sweep"]}
    results = (ROOT / "RESULTS.md").read_text()
    section = results[results.index("| λ_churn |"):]
    for lam, row in rows.items():
        value = row["incremental_per_1000_cases"]["point"]
        assert f"{value:,.0f}" in section, (
            f"λ={lam} incremental {value:,.0f} is not in the RESULTS.md table"
        )
        assert f"{row['contacts']:,}" in section


def test_the_curve_is_monotone_so_no_setting_is_free():
    """The honest form of the default's justification: every increase in the
    penalty buys less exposure for less money. If a setting ever appears that
    improves both, the default should change and this test should say so."""
    rows = sorted(_artifact()["sweep"], key=lambda r: r["lambda_churn"])
    values = [r["incremental_per_1000_cases"]["point"] for r in rows]
    contacts = [r["contacts"] for r in rows]
    dnd = [r["pct_contacts_to_do_not_disturbs"] for r in rows]
    assert values == sorted(values, reverse=True), f"recovery not monotone: {values}"
    assert contacts == sorted(contacts, reverse=True), f"contacts not monotone: {contacts}"
    assert dnd == sorted(dnd, reverse=True), f"do-not-disturb rate not monotone: {dnd}"


def test_the_default_in_code_is_a_setting_that_was_measured():
    source = (ROOT / "src" / "recovery_ledger" / "policy" / "decision.py").read_text()
    m = re.search(r"lambda_churn: float = ([\d.]+)", source)
    assert m, "could not find the lambda_churn default"
    default = float(m.group(1))
    swept = {r["lambda_churn"] for r in _artifact()["sweep"]}
    assert default in swept, (
        f"the shipped default lambda_churn={default} is not in the swept grid "
        f"{sorted(swept)}; it is unjustified by this experiment"
    )
