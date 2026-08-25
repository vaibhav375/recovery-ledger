"""RESULTS.md must agree with the artifacts it claims to report.

The project's first rule is that every number is produced by re-runnable code.
That rule was being kept in the code and broken in the document: `make eval`
was re-run, `results.json` changed, and the prose in RESULTS.md was not
updated. For several commits the headline read **₹310,910** while the artifact
it cited said **₹272,281**, and five of the six supporting diagnostics in the
same paragraph were from a run that no longer existed. Nothing caught it,
because nothing was looking.

This is what looks. Each check names an artifact field, renders it exactly the
way the document renders it, and asserts that string is present. Re-running an
experiment now fails the build until the document is brought with it — which
is the correct order of operations: the artifact is the source of truth and
the prose is downstream of it.

Deliberately not a general number-scraper. A regex that hunts every digit in a
markdown file produces false alarms on years, section numbers and prose, and a
test people learn to ignore is worse than no test. This checks the figures
that carry the project's claims.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RESULTS_MD = ROOT / "RESULTS.md"
README_MD = ROOT / "README.md"
BATCH = ROOT / "experiments" / "tier2_simulation" / "results.json"
BASELINES = ROOT / "experiments" / "tier2_simulation" / "results_baselines.json"
FLEET = ROOT / "experiments" / "fleet" / "results_fleet.json"
LISTENER = ROOT / "experiments" / "listener_eval" / "results_listener_gold.json"
SENSITIVITY = ROOT / "experiments" / "sensitivity" / "results_sensitivity.json"
REDTEAM = ROOT / "redteam" / "redteam_report.json"
OPE = ROOT / "experiments" / "ope_deployment" / "results_ope_deployment.json"
FAIRNESS = ROOT / "experiments" / "fairness" / "results_fairness.json"


def _load(path: Path) -> dict:
    if not path.exists():
        pytest.skip(f"{path.name} not generated yet")
    return json.loads(path.read_text())


@pytest.fixture(scope="module")
def results_md() -> str:
    return RESULTS_MD.read_text()


# ── B1: the headline ─────────────────────────────────────────────────────

def test_headline_incremental_matches_the_batch_artifact(results_md):
    inc = _load(BATCH)["incremental_per_1000_cases"]
    expected = (
        f"₹{inc['point']:,.0f} (95% CI ₹{inc['ci_low']:,.0f} – ₹{inc['ci_high']:,.0f})"
    )
    assert expected in results_md, (
        f"RESULTS.md does not state the current headline. Expected {expected!r} "
        f"from results.json. Re-run `make eval` and update the document, or "
        f"the document is quoting a run that no longer exists."
    )


@pytest.mark.parametrize(
    "key,render",
    [
        ("treatment_recovery_rate", lambda v: f"{v * 100:.2f}%"),
        ("holdout_recovery_rate", lambda v: f"{v * 100:.2f}%"),
        ("uplift_model_correlation_with_true_persuadability", lambda v: f"{v:.3f}"),
        ("contacts_sent", lambda v: f"{v} contacts"),
        ("pct_contacts_to_do_not_disturbs", lambda v: f"{v * 100:.1f}%"),
        ("ledger_entries", lambda v: f"{v:,}"),
        ("unresolved_exceptions", lambda v: str(v)),
        ("distinct_stop_reasons_fired", lambda v: f"{v} of 11 stopping reasons"),
    ],
)
def test_supporting_diagnostics_match_the_batch_artifact(results_md, key, render):
    """The paragraph that says 'from the same run' has to be from the same run.
    All six of these were stale at once."""
    value = render(_load(BATCH)[key])
    assert value in results_md, f"{key} renders as {value!r}, which RESULTS.md does not say"


def test_chain_is_reported_valid_only_if_it_is(results_md):
    assert _load(BATCH)["ledger_chain_valid"] is True
    assert "hash chain verified" in results_md


# ── stopping rules ───────────────────────────────────────────────────────

def test_stopping_rules_arithmetic_is_consistent(results_md):
    """`N fire naturally` and `the M that do not` must add to the real total,
    and both must match the artifact. They did not: the document said 7 and
    four while the artifact said 8, so the two halves of the same paragraph
    disagreed with each other as well as with the run."""
    from recovery_ledger.events.actions import StopReason

    total = len(list(StopReason))
    fired = _load(BATCH)["distinct_stop_reasons_fired"]
    assert f"**{fired} of {total}**" in results_md
    assert f"**{total} of {total}**" in results_md

    words = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}
    assert f"The {words[total - fired]}\nthat do not occur naturally" in results_md, (
        f"{total - fired} reasons did not fire; RESULTS.md names a different count"
    )


def test_the_unfired_stopping_reasons_are_named_correctly(results_md):
    from recovery_ledger.events.actions import StopReason

    fired = set(_load(BATCH)["stop_reason_counts"])
    unfired = sorted({r.value for r in StopReason} - fired)
    for reason in unfired:
        assert reason in results_md, (
            f"{reason} did not fire in the batch but RESULTS.md does not name it "
            f"among the reasons that need special conditions"
        )


# ── baselines ────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "policy", ["blast_everyone", "random_targeting", "ev_policy_greedy", "ev_policy_lookahead"]
)
def test_baseline_contacts_and_do_not_disturb_rates_match(results_md, policy):
    row = next(p for p in _load(BASELINES)["policies"] if p["policy"] == policy)
    assert f"{row['contacts_sent']:,}".replace(",", "") in results_md.replace(",", "")
    pct = row["pct_contacts_to_do_not_disturbs"]
    assert f"{pct * 100:.2f}%" in results_md


def test_baseline_incremental_figures_match(results_md):
    for row in _load(BASELINES)["policies"]:
        inc = row.get("incremental_per_1000_cases")
        point = inc["point"] if isinstance(inc, dict) else inc
        if not point:
            continue
        assert f"{point:,.0f}" in results_md, (
            f"{row['policy']} reports {point:,.0f} incremental ₹/1000, "
            f"which RESULTS.md does not state"
        )


# ── the other experiments ────────────────────────────────────────────────

def test_fleet_figures_match(results_md):
    f = _load(FLEET)
    assert f"{f['futile_retries_avoided']}" in results_md
    assert f"₹{f['gross_recovery_change']:,.0f}" in results_md
    assert f"{f['fleet_aware']['recovered_on_degraded_issuer']:,.0f}" in results_md


def test_listener_accuracy_matches(results_md):
    acc = _load(LISTENER)["accuracy"]
    assert f"{acc * 100:.1f}%" in results_md or f"{acc * 100:.2f}%" in results_md


def test_sensitivity_claims_match(results_md):
    s = _load(SENSITIVITY)["summary"]
    for key in ("c1_ev_beats_random", "c2_ev_more_contact_efficient_than_blast"):
        claim = s[key]
        assert f"**{claim['held']} / {claim['of']}**" in results_md
        assert ", ".join(claim["per_draw"]) in results_md
    assert f"**{s['eval_draws']} independent evaluation populations**" in results_md


def test_sensitivity_margin_is_quoted_as_a_median_not_a_max(results_md):
    """The largest ratio in the sweep is ~82x, produced by a near-zero
    denominator at the one unstable setting. Quoting it as the top of a range
    would be quoting an artifact, so the document must carry the median and
    percentiles instead — recomputed here from the artifact so the two cannot
    drift apart."""
    import statistics as st

    d = _load(SENSITIVITY)
    rows = [r for dr in d["draws"] for rs in dr["sweeps"].values() for r in rs]
    ratios = sorted(r["c1_margin_ratio"] for r in rows if r.get("c1_margin_ratio"))
    med = st.median(ratios)
    p10, p90 = ratios[len(ratios) // 10], ratios[-len(ratios) // 10]
    assert f"median margin {med:.2f}x, 10th–90th pct {p10:.2f}x–{p90:.2f}x" in results_md
    assert f"largest single ratio in\nthe sweep is {max(ratios):.0f}x" in results_md


def test_sensitivity_flips_are_reported_if_any_exist(results_md):
    """C2 was 24/25 on one evaluation draw and 25/25 on three others. If a
    flip ever reappears, the document must name it rather than reporting a
    clean sweep."""
    c2 = _load(SENSITIVITY)["summary"]["c2_ev_more_contact_efficient_than_blast"]
    if c2["settings_that_ever_flip"]:
        for setting in c2["settings_that_ever_flip"]:
            param = setting.split("=")[0]
            assert param in results_md, (
                f"C2 flips at {setting} but RESULTS.md does not mention {param}"
            )


def test_redteam_block_rate_matches(results_md):
    """The claim is 'N of M', where M is the attacks that MUST be denied — not
    the suite size. The suite also contains a legitimate action that must be
    allowed, and counting it as a block would inflate the rate."""
    na = _load(REDTEAM)["named_attacks"]
    assert f"**{na['blocked']} / {na['must_deny_attacks']} (100%)**" in results_md
    assert na["block_rate"] == 1.0
    fuzz = _load(REDTEAM)["fuzz"]
    assert f"({fuzz['samples']:,} states)" in results_md
    assert fuzz["leaks"] == 0


# ── off-policy evaluation in the deployment loop ─────────────────────────

def _ope_rep(metric: str, epsilon: float) -> dict:
    d = _load(OPE)
    return next(
        r for r in d["replication_study"]
        if r["metric"] == metric and r["epsilon"] == epsilon
    )


@pytest.mark.parametrize("epsilon", [0.05, 0.10, 0.20, 0.40])
@pytest.mark.parametrize("metric", ["payment_rate", "net_value"])
def test_ope_coverage_rates_match(results_md, metric, epsilon):
    """The whole point of this section is a coverage number. If the experiment
    is re-run and coverage moves, the prose must move with it."""
    cov = _ope_rep(metric, epsilon)["coverage"]["SNIPS"]
    assert f"{cov * 100:.0f}%" in results_md


@pytest.mark.parametrize("epsilon", [0.05, 0.10, 0.20, 0.40])
@pytest.mark.parametrize("metric", ["payment_rate", "net_value"])
def test_ope_ranking_agreement_matches(results_md, metric, epsilon):
    d = _load(OPE)
    reps = d["replications_per_epsilon"]
    rate = _ope_rep(metric, epsilon)["ranking_agreement"]
    assert f"{round(rate * reps)} / {reps}" in results_md


def test_ope_exploration_cost_matches(results_md):
    row = next(r for r in _load(OPE)["sweep"] if r["epsilon"] == 0.10)
    assert f"₹{abs(row['exploration_cost_per_case']):.0f} per case" in results_md
    assert f"₹{row['logged_net_value_per_case']:.0f} per case" in results_md


def test_ope_identification_counts_match(results_md):
    """At epsilon = 0 only the logging policy is estimable. If that ever stops
    being true the claim about deterministic logs is wrong."""
    row = next(r for r in _load(OPE)["sweep"] if r["epsilon"] == 0.0)
    identified = sum(1 for p in row["policies"].values() if p["overlap"]["identified"])
    assert identified == 1, "a deterministic log identified more than itself"
    assert f"| 0.00 | {identified} / 6 |" in results_md


def test_ope_states_its_contextual_bandit_limitation(results_md):
    """The framing is a real limitation and must not quietly disappear from
    the prose, because the number looks stronger without it."""
    assert "contextual bandit" in results_md
    assert "not*\nfull-sequence OPE" in results_md or "full-sequence OPE" in results_md
    assert "contextual bandit" in _load(OPE)["framing"]


# ── the disparity audit ──────────────────────────────────────────────────

@pytest.mark.parametrize(
    "segment", ["language", "b2b", "amount_quartile", "loss_type"]
)
def test_fairness_gaps_and_p_values_match(results_md, segment):
    seg = _load(FAIRNESS)["segments"][segment]
    j = seg["conditional_on_uplift_and_amount"]
    t = seg["true_benefit_gap_in_same_cells"]
    assert f"{j['excess']:+.3f} | {j['p']:.3f}" in results_md
    assert f"₹{t['excess']:+,.0f} | {t['p']:.3f}" in results_md


def test_fairness_verdicts_match(results_md):
    """If any segment ever becomes an unexplained disparity, the document must
    say so. A clean audit quietly going stale is the failure mode here."""
    d = _load(FAIRNESS)
    flagged = [k for k, v in d["segments"].items() if v["unexplained"]]
    if flagged:
        assert "**unexplained**" in results_md, (
            f"segments {flagged} are flagged in the artifact but RESULTS.md "
            f"still reports a clean audit"
        )
    else:
        assert "**No unexplained disparity in any segment.**" in results_md


def test_fairness_model_correlations_match(results_md):
    """The headline finding of this section is the per-group model quality.
    It is quoted to two decimals in the prose."""
    g = _load(FAIRNESS)["segments"]["b2b"]["groups"]
    assert f"{g['b2b']['model_correlation']:.2f} against {g['b2c']['model_correlation']:.2f}" in results_md
    q1 = _load(FAIRNESS)["segments"]["amount_quartile"]["groups"]["Q1"]
    assert f"correlation of {q1['model_correlation']:.2f}" in results_md


def test_fairness_correction_is_applied_to_the_disparity_test_only(results_md):
    """The rule that stops this audit crying wolf. If a future edit applies the
    Bonferroni threshold to the explanation test as well, an underpowered
    explanation becomes a 'disparity'."""
    d = _load(FAIRNESS)
    alpha = d["bonferroni_alpha"]
    for name, seg in d["segments"].items():
        if not seg["unexplained"]:
            continue
        assert seg["conditional_on_uplift_and_amount"]["p_exact"] < alpha, name
        # The explanation test is judged at an ordinary 0.05, deliberately.
        assert seg["true_benefit_gap_in_same_cells"]["p_exact"] >= 0.05, name


def test_fairness_reports_worked_rate_not_only_contact(results_md):
    """Measuring contact alone reported failed subscriptions as the most
    neglected group when the policy works all of them by silent retry."""
    sub = _load(FAIRNESS)["segments"]["loss_type"]["groups"]["FailedSubscription"]
    assert sub["worked_rate"] > sub["contact_rate"]
    assert f"works **{sub['worked_rate'] * 100:.0f}%** of them" in results_md


# ── the README quotes the headline too ───────────────────────────────────

def test_readme_does_not_quote_a_stale_headline():
    inc = _load(BATCH)["incremental_per_1000_cases"]
    readme = README_MD.read_text()
    current = f"₹{inc['point']:,.0f}"
    stale = [
        token for token in ("₹310,910", "₹150,240", "₹471,072")
        if token in readme and token != current
    ]
    assert not stale, f"README.md still quotes superseded figures: {stale}"
