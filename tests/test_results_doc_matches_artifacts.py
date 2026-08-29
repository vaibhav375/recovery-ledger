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
DND = ROOT / "experiments" / "dnd_signal" / "results_dnd_signal.json"
PESSIMISM = ROOT / "experiments" / "pessimism" / "results_pessimism.json"
CALIBRATION = ROOT / "experiments" / "uplift_calibration" / "results_uplift_calibration.json"
TIER1 = {
    "hillstrom": ROOT / "experiments" / "tier1_criteo" / "results_hillstrom.json",
    "criteo": ROOT / "experiments" / "tier1_criteo" / "results_criteo.json",
}


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


# ── Tier 1: the kill gate ────────────────────────────────────────────────

@pytest.mark.parametrize("dataset", ["hillstrom", "criteo"])
@pytest.mark.parametrize("estimator", ["ips", "snips", "dr"])
def test_tier1_ope_table_matches_the_artifacts(results_md, dataset, estimator):
    """The whole two-tier argument rests on this table. If the estimators are
    re-run and move, the claim that they reproduce a known effect on real
    randomised data has to move with them."""
    ope = _load(TIER1[dataset])["ope_validation"]
    assert f"{ope[estimator]['implied_ate']:+.4f}" in results_md


@pytest.mark.parametrize("dataset", ["hillstrom", "criteo"])
def test_tier1_ground_truth_ate_matches(results_md, dataset):
    direct = _load(TIER1[dataset])["ope_validation"]["direct_ate"]
    assert f"{direct:+.4f}" in results_md


def test_tier1_dr_is_still_reported_as_the_weak_spot(results_md):
    """DR is materially off on Criteo and that is stated rather than dropped.
    If it ever stops being off, the prose should stop saying it is."""
    c = _load(TIER1["criteo"])["ope_validation"]
    off_by = abs(c["dr"]["implied_ate"] - c["direct_ate"])
    if off_by > 0.001:
        assert "honest weak spot" in results_md
    else:
        assert "honest weak spot" not in results_md, (
            "DR now matches on Criteo; RESULTS.md still calls it a weak spot"
        )


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


# ── the README's own claims ──────────────────────────────────────────────
#
# RESULTS.md was tested against its artifacts; the README was not, and it had
# drifted further. Four claims were wrong at once: the kernel's rule count in
# two places, how many stopping rules fire naturally, and a headline paragraph
# quoting a policy variant that is not the one that ships.

@pytest.fixture(scope="module")
def readme() -> str:
    return README_MD.read_text()


def test_readme_states_the_real_number_of_kernel_rules(readme):
    from recovery_ledger.ledger.ledger import Ledger
    from recovery_ledger.cli import build_default_agent

    n = len(build_default_agent(Ledger(), clock=lambda: None).kernel.rules)
    for wrong in range(8, 20):
        if wrong == n:
            continue
        assert f"{wrong} rules" not in readme, (
            f"README claims {wrong} rules; the default kernel registers {n}"
        )
    assert f"{n} rules" in readme


def test_readme_stopping_rule_counts_match_the_batch(readme):
    from recovery_ledger.events.actions import StopReason

    total = len(list(StopReason))
    fired = _load(BATCH)["distinct_stop_reasons_fired"]
    words = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}
    assert f"**{fired} of {total} naturally**" in readme
    assert f"the other {words[total - fired]}" in readme


def test_readme_headline_quotes_the_deployed_policy(readme):
    """The headline compared the *no-churn* variant against random while the
    shipped policy is the lookahead with the churn term. Both numbers are
    real; only one describes the system a judge can run."""
    pol = {p["policy"]: p for p in _load(BASELINES)["policies"]}
    deployed, blast, rand = (
        pol["ev_policy_lookahead"], pol["blast_everyone"], pol["random_targeting"]
    )
    ratio = (
        deployed["incremental_per_1000_cases"]["point"]
        / rand["incremental_per_1000_cases"]["point"]
    )
    fewer = 1 - deployed["contacts_sent"] / blast["contacts_sent"]
    cost = blast["cost_per_incremental_rupee"] / deployed["cost_per_incremental_rupee"]
    assert f"**{ratio:.2f}x more incremental revenue" in readme
    assert f"**{fewer:.0%} fewer" in readme
    assert f"{cost:.1f}x better cost per incremental rupee" in readme


def test_readme_and_results_agree_on_the_headline(readme, results_md):
    inc = _load(BATCH)["incremental_per_1000_cases"]
    figure = f"₹{inc['point']:,.0f}"
    assert figure in readme and figure in results_md


# ── the do-not-disturb signal behind novelty claim N2 ────────────────────

def test_dnd_ratio_matches_the_artifact_everywhere_it_is_asserted(readme, results_md):
    """Reported as 1.93x from a single n=5,000 draw, where the ratio ranges
    0.72x-1.87x across seeds. Asserted in five places at once."""
    d = _load(DND)
    stated = f"**{d['ratio']:.2f}x** (95% CI {d['ci_low']:.2f}–{d['ci_high']:.2f})"
    assert stated in readme
    assert stated in results_md

    src = ROOT / "src" / "recovery_ledger" / "policy"
    for f in ("churn.py", "decision.py"):
        text = (src / f).read_text()
        assert "1.93x" not in text, f"{f} still asserts the superseded figure"
        assert f"{d['ratio']:.2f}x" in text


def test_dnd_effect_is_real_and_the_old_figure_is_not_inside_the_interval():
    d = _load(DND)
    assert d["effect_excludes_one"] is True, "N2's supporting signal is not distinguishable from none"
    assert d["previously_reported_inside_ci"] is False
    assert d["opt_out_rate_without_contact"] == 0.0, (
        "the effect is only attributable to contact if there is no opt-out without it"
    )


def test_dnd_measurement_is_not_taken_at_a_sample_size_where_it_is_unstable():
    """The actual defect: measured at whatever n was convenient. The headline
    n must be one where repeated seeds agree."""
    d = _load(DND)
    by_n = {row["n"]: row["spread"] for row in d["stability_by_sample_size"]}
    assert d["headline_n"] == max(by_n), "headline is not taken at the largest sample measured"
    assert by_n[max(by_n)] < by_n[min(by_n)], "spread does not shrink with sample size"
    assert by_n[5000] > 0.5, (
        "n=5,000 is no longer unstable — if the simulator changed, the "
        "cautionary note in the docs should change with it"
    )


# ── acting on a lower bound ──────────────────────────────────────────────

def test_pessimism_correlation_comparison_is_matched(readme, results_md):
    """The ensemble's correlation may only be quoted against a single learner
    scored on the SAME populations. Comparing it to the 0.347 published from a
    different evaluation seed would not be a comparison."""
    import statistics as st

    d = _load(PESSIMISM)
    single = st.mean(d["correlation_per_draw"]["single"])
    ens = st.mean(d["correlation_per_draw"]["ensemble"])
    assert len(d["correlation_per_draw"]["single"]) == d["eval_draws"]
    assert f"{single:.3f}" in readme and f"{ens:.3f}" in readme
    assert f"{single:.3f}" in results_md and f"{ens:.3f}" in results_md


def test_pessimism_reports_best_k_as_a_range_when_it_is_unstable(readme, results_md):
    """Best k landed at 0.5, 0.5 and 0.25. Reporting a single tuned value from
    an unstable argmax is how a hyperparameter gets overfitted to one draw."""
    d = _load(PESSIMISM)
    if not d["best_k_is_stable"]:
        assert "not stable" in readme.lower()
        assert "range" in results_md.lower()
        assert str(d["best_k_per_draw"]) in results_md
    lo, hi = min(d["improvement_per_case_per_draw"]), max(d["improvement_per_case_per_draw"])
    assert f"₹{lo:.0f}" in results_md and f"₹{hi:.0f}" in results_md


def test_pessimism_k_zero_is_the_deployed_policy():
    """The sweep's origin must be the shipped behaviour, or every reported
    gain is measured against a baseline nobody runs."""
    from recovery_ledger.policy.decision import (
        EVDecisionPolicy,
        LookaheadEVDecisionPolicy,
    )

    d = _load(PESSIMISM)
    assert d["draws"][0]["sweep"][0]["uncertainty_k"] == 0.0
    for cls in (EVDecisionPolicy, LookaheadEVDecisionPolicy):
        assert cls.__dataclass_fields__["uncertainty_k"].default == 0.0


def test_pessimism_harm_reduction_figures_match(readme, results_md):
    import statistics as st

    d = _load(PESSIMISM)
    ks = [r["uncertainty_k"] for r in d["draws"][0]["sweep"]]
    i0, ib = 0, ks.index(0.5)
    m = lambda i, f: st.mean(dr["sweep"][i][f] for dr in d["draws"])
    for doc in (readme, results_md):
        assert f"{m(i0, 'harmful_contacts'):.0f} → {m(ib, 'harmful_contacts'):.0f}" in doc
        assert f"₹{m(ib, 'net_value_per_contact'):,.0f}" in doc


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


# ── Uplift by decile ─────────────────────────────────────────────────────
#
# The decile chart is the spec's required evaluation artifact and it reports
# two results that are not flattering: the ranking misses the pre-registered
# monotonicity bar, and the bottom decile's realised uplift is not negative.
# Unflattering numbers are the ones a document drifts away from, so they are
# pinned the same way the headline is.


def test_decile_table_matches_the_calibration_artifact(results_md):
    d = _load(CALIBRATION)
    for i in range(d["n_bins"]):
        rows = [dr["deciles"][i] for dr in d["draws"]]
        mean = lambda k: sum(r[k] for r in rows) / len(rows)
        row = (
            f"| {i + 1} | {mean('mean_predicted_uplift'):+.4f} "
            f"| {mean('realised_uplift'):+.4f} "
            f"| {mean('mean_true_persuadability'):+.4f} "
            f"| {mean('true_do_not_disturb_share') * 100:.1f}% |"
        )
        assert row in results_md, f"decile {i + 1} in RESULTS.md does not match the artifact: expected {row!r}"


def test_the_monotonicity_verdict_is_reported_at_the_threshold_it_was_judged_against(results_md):
    """Spearman 0.879 fails a bar of 0.9. The document must carry both numbers,
    so the failing draw cannot quietly become 'monotone'."""
    v = _load(CALIBRATION)["verdict"]
    assert ", ".join(f"{s:.3f}" for s in v["spearman_by_draw"]) in results_md
    assert f"against a pre-registered {v['monotone_threshold']}" in results_md
    assert v["monotone_all_draws"] is False, (
        "the deciles now pass the 0.9 bar — RESULTS.md still says they do not"
    )
    assert v["near_monotone_all_draws"] is True


def test_ranking_and_calibration_figures_match_the_artifact(results_md):
    v = _load(CALIBRATION)["verdict"]
    assert ", ".join(f"{t:+.4f}" for t in v["top_minus_bottom_by_draw"]) in results_md
    assert ", ".join(f"{s:.3f}" for s in v["calibration_slope_by_draw"]) in results_md
    assert f"mean **{v['mean_calibration_slope']:.3f}**" in results_md
    assert f"Qini {v['mean_qini']:.3f}" in results_md
    assert v["ranking_holds"] is True


def test_the_bottom_decile_claim_matches_the_artifact(results_md):
    """The load-bearing cell: the decile the policy declines to contact. The
    document says it is enriched in do-not-disturbs but does NOT realise
    negative uplift. Both halves are checked, because reporting only the first
    would turn a calibration failure into a targeting success."""
    v = _load(CALIBRATION)["verdict"]
    assert f"{v['bottom_decile_true_dnd_share'] * 100:.1f}% of that decile" in results_md
    assert f"{v['population_true_dnd_share'] * 100:.1f}% of the\npopulation" in results_md
    assert f"{v['top_decile_true_dnd_share'] * 100:.1f}% of the top decile" in results_md
    assert f"realises {v['bottom_decile_realised_uplift']:+.4f}" in results_md
    assert f"calls it {v['bottom_decile_predicted_uplift']:+.4f}" in results_md
    assert v["bottom_decile_realised_negative_in_every_draw"] is False, (
        "the bottom decile now realises negative uplift in every draw — that is "
        "a stronger N2 result than RESULTS.md claims, and the document should "
        "be updated to claim it"
    )


def test_the_calibration_run_used_the_shipped_model_not_the_ensemble():
    """The chart is evidence about the model that ships. An artifact produced
    by the ensemble arm would describe a model no document quotes."""
    assert _load(CALIBRATION)["uplift_model"] == "single"
