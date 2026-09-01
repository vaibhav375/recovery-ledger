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
DR_DIAGNOSIS = ROOT / "experiments" / "tier1_criteo" / "results_dr_diagnosis.json"
DR_FOLDSWEEP = ROOT / "experiments" / "tier1_criteo" / "results_dr_foldsweep.json"
DR_REPORT = ROOT / "experiments" / "tier1_criteo" / "REPORT.md"


def _load(path: Path) -> dict:
    if not path.exists():
        pytest.skip(f"{path.name} not generated yet")
    return json.loads(path.read_text())


@pytest.fixture(scope="module")
def results_md() -> str:
    return RESULTS_MD.read_text()


@pytest.fixture(scope="module")
def dr_report() -> str:
    return DR_REPORT.read_text()


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


# ── DR fold-count sweep: does the cross-fitting mechanism respond at all ───
#
# PROJECT_STATE.md's Tier B backlog named the mechanism (a cross-fitted q_hat
# starved on Criteo's 15% control arm) but proposed "refit with stratified
# folds that guarantee minority-arm balance" as the untested fix -- half of
# which (stratified folds, one model per arm) was already shipped when that
# was written. What was actually untested is whether the residual gap
# responds to the fold count at all. `make dr-foldsweep` sweeps n_folds in
# {2, 5, 10, 20} across the same three disjoint blocks and applies a rule
# fixed before the run. These tests pin the rule, the sweep table and the
# verdict the same way the rest of this file pins every other artifact.


def test_fold_sweep_reused_the_prescribed_fold_counts_and_draws():
    d = _load(DR_FOLDSWEEP)
    assert [r["n_folds"] for r in d["rows"]] == [2, 5, 10, 20]
    assert d["draws"] == 3
    for r in d["rows"]:
        assert r["n_draws"] == 3


def test_fold_sweep_at_n_folds_5_matches_the_dr_diagnosis_artifact():
    """n_folds=5 is common to both `results_dr_diagnosis.json` and the sweep,
    computed by the same `dr_for_folds` code path on the same disjoint
    blocks. If the two disagree, exposing n_folds as a sweep parameter
    changed the estimator's behaviour rather than merely measuring it --
    which this experiment's brief forbids."""
    diag = _load(DR_DIAGNOSIS)
    sweep = _load(DR_FOLDSWEEP)
    row5 = next(r for r in sweep["rows"] if r["n_folds"] == 5)
    assert len(row5["per_draw"]) == len(diag["per_draw"])
    for sweep_draw, diag_draw in zip(row5["per_draw"], diag["per_draw"]):
        assert sweep_draw["seed"] == diag_draw["seed"]
        for field in ("ate", "ci_low", "ci_high"):
            assert sweep_draw["dr"][field] == pytest.approx(diag_draw["dr"][field]), (
                f"seed {sweep_draw['seed']}: sweep's n_folds=5 DR.{field} does not "
                f"match results_dr_diagnosis.json's own n_folds=5 run"
            )


def test_fold_sweep_rule_is_quoted_verbatim(dr_report):
    """The pre-registered rule must be quoted in REPORT.md, not just enforced
    silently in code -- otherwise a reader has no way to check the verdict
    against the rule that produced it (same discipline as the regret
    disagreement-replication rule elsewhere in this file)."""
    d = _load(DR_FOLDSWEEP)
    assert d["rule"] in dr_report


def test_fold_sweep_rows_match_the_artifact(dr_report):
    """Every row of the sweep table -- one per n_folds -- must match what the
    artifact actually measured."""
    d = _load(DR_FOLDSWEEP)
    for r in d["rows"]:
        row = (
            f"| {r['n_folds']} | {r['coverage']}/{r['n_draws']} "
            f"| {r['mean_gap']:+.5f} | {r['mean_abs_gap']:.5f} |"
        )
        assert row in dr_report, (
            f"fold-sweep row for n_folds={r['n_folds']} missing or stale: {row!r}"
        )


def test_fold_sweep_verdict_is_recomputed_from_the_rows_not_hand_typed(dr_report, results_md):
    """The verdict stored in the artifact must match what `fold_sweep_verdict()`
    -- the actual pre-registered rule in `run_dr_diagnosis.py` -- yields on
    the rows beside it in the same artifact. This imports and calls the real
    function rather than re-deriving its branches here: a re-derivation can
    only ever check itself, and with the real sweep landing on REFUTED, a
    hand-typed copy of the CONFIRMED/UNRESOLVED branches would never be
    exercised by anything. `test_dr_diagnosis.py` drives all three branches
    of the real function directly with constructed rows; this test only
    needs to confirm the artifact and the function agree, and pins the
    verdict word into both documents."""
    import sys
    sys.path.insert(0, str(ROOT / "experiments" / "tier1_criteo"))
    from run_dr_diagnosis import fold_sweep_verdict

    d = _load(DR_FOLDSWEEP)
    expected = fold_sweep_verdict(d["rows"])
    assert d["verdict"] == expected, (
        f"artifact verdict {d['verdict']!r} does not match what "
        f"fold_sweep_verdict() yields ({expected!r}) on the artifact's own rows"
    )
    assert expected in dr_report, f"REPORT.md does not state the verdict {expected!r}"
    assert expected in results_md, f"RESULTS.md does not state the verdict {expected!r}"


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


# ── Regret: what the silences cost, beside what contacting recovered ────

REGRET = ROOT / "experiments" / "regret" / "results_regret.json"
REGRET_REPORT = ROOT / "experiments" / "regret" / "REPORT.md"


def test_regret_totals_match_the_artifact(results_md):
    t = _load(REGRET)["totals"]
    for key in ("cost", "saved", "net"):
        assert f"₹{t[key]:,.0f}" in results_md, (
            f"RESULTS.md does not state the regret {key} of ₹{t[key]:,.0f}"
        )


def test_regret_bucket_rows_match_the_artifact(results_md):
    """Checks all six rendered columns, not just a four-column prefix. A
    four-column check would pass unchanged if Net or Model errors were edited
    to something the artifact no longer says — this was found in review and
    is exactly the drift this test file exists to catch."""
    for row in _load(REGRET)["buckets"]:
        rendered = (
            f"| {row['bucket']} | {row['n']} | ₹{row['cost']:,.0f} | "
            f"₹{row['saved']:,.0f} | ₹{row['net']:,.0f} | {row['model_errors']} |"
        )
        assert rendered in results_md, f"bucket row missing or stale: {rendered!r}"


def test_regret_total_row_matches_the_artifact(results_md):
    """Pins n_declined (554) against the bold Total row, which was otherwise
    asserted nowhere — found in review."""
    d = _load(REGRET)
    t = d["totals"]
    rendered = (
        f"| **Total** | **{d['n_declined']}** | **₹{t['cost']:,.0f}** | "
        f"**₹{t['saved']:,.0f}** | **₹{t['net']:,.0f}** | **{t['model_errors']}** |"
    )
    assert rendered in results_md, f"total row missing or stale: {rendered!r}"


def test_the_regret_prediction_verdict_is_reported_as_it_came_out(results_md):
    """The prediction can refute make calibration. If it does, RESULTS.md has
    to say so — this test fails when the document claims the friendlier
    outcome."""
    p = _load(REGRET)["prediction"]
    assert f"{p['model_errors_observed']} model errors" in results_md
    verdict = "holds" if p["holds"] else "refuted"
    assert verdict in results_md.lower()


def test_regret_was_measured_on_the_headline_population():
    assert _load(REGRET)["shares_population_with"] == "tier2_simulation/run_batch.py"


def test_regret_treatment_arm_size_matches_the_artifact(results_md, regret_report):
    """Finding 4: `n_treatment_arm` (1,037) and its 51.85% share of the
    2,000-case batch were quoted in both documents with nothing loading or
    asserting them from the artifact. `n_treatment_arm` is now a real
    artifact field (`results_regret.json`); this pins both renderings to it."""
    d = _load(REGRET)
    n_arm, n_eval = d["n_treatment_arm"], d["n_eval"]
    pct = f"{n_arm / n_eval * 100:.2f}%"
    assert f"{n_arm:,}" in results_md
    assert f"{n_arm:,}" in regret_report
    assert pct in regret_report, (
        f"REPORT.md does not state the treatment arm's share of the batch "
        f"as {pct}, computed from n_treatment_arm/n_eval in the artifact"
    )


def test_regret_resolved_excluded_matches_the_artifact(results_md, regret_report):
    """Finding 5: the published partition of the 1,037-case treatment arm
    (234 contacted + 6 deferred + 554 declined = 794) used to be 243 cases
    short of 1,037, with nothing naming where they went. `declined_cases()`
    now counts them as `n_resolved_excluded` (cases that resolved without
    ever being contacted) and both documents must state the number and show
    the partition adding up."""
    d = _load(REGRET)
    n_resolved = d["n_resolved_excluded"]
    total = d["n_worked"] + d["n_deferred"] + n_resolved + d["n_declined"]
    assert total == d["n_treatment_arm"], (
        "the artifact's own partition does not sum to n_treatment_arm — "
        "this would mean the fix for finding 5 has a bug, not just a doc gap"
    )
    for doc_name, doc in (("RESULTS.md", results_md), ("REPORT.md", regret_report)):
        assert str(n_resolved) in doc, (
            f"{doc_name} does not state n_resolved_excluded ({n_resolved})"
        )
        partition = (
            f"{d['n_worked']} + {d['n_deferred']} + {n_resolved} + "
            f"{d['n_declined']} = {d['n_treatment_arm']:,}"
        )
        assert partition in doc, (
            f"{doc_name} does not show the partition adding up: {partition!r}"
        )


def test_regret_saved_caveat_names_the_published_total_not_the_bucket(
    results_md, regret_report
):
    """Finding 1 (critical): the caveat that a "saved" figure must not be
    quoted as independently validated used to name ₹92,177 —
    `buckets[model_judgement].saved` — while the figure readers actually see
    published as *the* saved figure (in the Total row, the headline
    sentence, and PROJECT_STATE.md) is `totals.saved`, ₹93,679. A reader
    could note the caveat names a different number and quote ₹93,679 as
    validated — the exact overclaim the caveat exists to prevent. This pins
    the caveat to `totals.saved` as rendered, in both documents."""
    saved = f"₹{_load(REGRET)['totals']['saved']:,.0f}"
    assert saved == "₹93,679"
    assert f"{saved} saved figure must not be quoted as" in results_md, (
        f"RESULTS.md's caveat does not name {saved} (totals.saved) as the "
        f"figure that must not be quoted as independently validated"
    )
    assert f'quoting the {saved} "saved" figure as' in regret_report, (
        f"REPORT.md's caveat does not name {saved} (totals.saved) as the "
        f"figure that must not be quoted as independently validated"
    )


def test_regret_cost_interval_matches_the_artifact(results_md, regret_report):
    """Ruling B: the spec named `counterfactual_check.inside_headline_interval`
    before anyone knew the check is one-sided by selection. Implemented on
    the cost side only: a bootstrap interval and a real verdict against it,
    both now artifact fields. If the realised cost lands outside the
    interval, that must be published as a finding, not tuned away or
    quietly reworded back into agreement — this pins the interval bounds
    and the boolean verdict in both documents, and fails if the interval
    ever moves without the prose being revisited."""
    c = _load(REGRET)["counterfactual_check"]
    lo = f"₹{c['cost_interval_low']:,.0f}"
    hi = f"₹{c['cost_interval_high']:,.0f}"
    for doc_name, doc in (("RESULTS.md", results_md), ("REPORT.md", regret_report)):
        assert lo in doc, f"{doc_name} does not state the cost-interval low bound {lo}"
        assert hi in doc, f"{doc_name} does not state the cost-interval high bound {hi}"
        assert "cost_interval" in doc, (
            f"{doc_name} does not name the cost_interval_low/high artifact "
            f"fields the interval above is read from"
        )
        assert "realised_cost_inside_interval" in doc, (
            f"{doc_name} does not name the realised_cost_inside_interval "
            f"artifact field carrying the verdict"
        )
    verdict_word = "inside" if c["realised_cost_inside_interval"] else "outside"
    assert verdict_word in results_md.lower()
    assert verdict_word in regret_report.lower()
    # Ruling B is explicit: if the realised cost lands outside, publish it
    # as a finding rather than reusing agreement language. Fail loudly if
    # the verdict is False (outside) but the document still claims clean
    # agreement on the cost side.
    if not c["realised_cost_inside_interval"]:
        for doc_name, doc in (("RESULTS.md", results_md), ("REPORT.md", regret_report)):
            assert "ordinary sampling variance" not in doc, (
                f"{doc_name} still calls the realised/expected cost gap "
                f"'ordinary sampling variance' after the bootstrap test "
                f"showed the realised cost falls outside its own interval"
            )


def test_regret_prediction_threshold_is_disclosed_as_registered(results_md, regret_report):
    """Ruling A (finding 7): `MODEL_ERRORS_EXPECTED_ABOVE = 0` is the
    registered rule — `model_errors > 0` — which is weaker than the
    "non-trivial count" language in the prose. The code is not being
    tightened after seeing the result (that would be moving the goalposts);
    instead both documents must state the rule as actually registered and
    disclose that 170 clears it by a wide margin."""
    p = _load(REGRET)["prediction"]
    threshold = p["model_errors_expected_above"]
    assert threshold == 0, (
        "MODEL_ERRORS_EXPECTED_ABOVE has changed — Ruling A says this must "
        "not be raised after seeing the result; if it moved, that is exactly "
        "the goalpost-moving this ruling forbids"
    )
    for doc_name, doc in (("RESULTS.md", results_md), ("REPORT.md", regret_report)):
        assert f"model_errors > {threshold}" in doc, (
            f"{doc_name} does not state the registered rule as "
            f"'model_errors > {threshold}'"
        )
        assert "MODEL_ERRORS_EXPECTED_ABOVE" in doc, (
            f"{doc_name} does not name the actual registered constant"
        )


def test_regret_counterfactual_check_matches_the_artifact(results_md):
    """`counterfactual_check` was quoted in RESULTS.md's Counterfactual-check
    subsection with nothing loading or asserting it — found in review, and
    it is exactly the failure mode this file exists to close: a later change
    to the counterfactual logic or its seeded population could move
    realised_cost/realised_net while the prose kept the old figures and the
    suite stayed green.

    realised_saved is included deliberately, not just cost/net: it is
    currently exactly -0.0, which is the load-bearing evidence that the
    check is one-sided (see REPORT.md and the surrounding prose in
    RESULTS.md). It must not be able to drift to a nonzero value while the
    document still calls the check one-sided.
    """
    c = _load(REGRET)["counterfactual_check"]
    assert f"{c['n']} cases" in results_md
    assert f"₹{c['realised_cost']:,.0f}" in results_md
    assert f"₹{c['realised_net']:,.0f}" in results_md
    # Not a bare f"{value:.1f}" substring check: this document also carries
    # unrelated decimals like -0.0642 (the calibration decile table) that
    # contain "-0.0" as a literal substring, which would make a bare check
    # unable to fail. Anchored to the specific phrase RESULTS.md uses so a
    # mutation of the actual claim is what this test responds to.
    assert f"exactly `{c['realised_saved']:.1f}`" in results_md, (
        f"RESULTS.md does not state realised_saved as exactly "
        f"{c['realised_saved']:.1f} — if this is now nonzero, the prose "
        f"calling the counterfactual check one-sided needs to be revisited, "
        f"not just this assertion"
    )


# ── Regret's estimator diagnostics: three numbers REPORT.md used to cite
# out-of-band, now regenerated by `run_regret.py` on every run and pinned so
# the report cannot drift back to an unbacked figure.

@pytest.fixture(scope="module")
def regret_report() -> str:
    return REGRET_REPORT.read_text()


def test_regret_report_ratio_diagnostic_matches_the_artifact(regret_report):
    """REPORT.md cites the ratio of mean realised effect to mean tau_true as
    proof the expectation estimator is correctly scaled. It used to be an
    out-of-band number nothing regenerated; `estimator_diagnostics()` now
    computes it on every `make regret` run, so the report must quote exactly
    what the artifact says."""
    diag = _load(REGRET)["estimator_diagnostics"]
    assert f"{diag['ratio_realised_to_tau']:.3f}" in regret_report, (
        f"REPORT.md does not state the current ratio of "
        f"{diag['ratio_realised_to_tau']:.3f} from results_regret.json"
    )


def test_regret_report_dnd_negative_draw_diagnostic_matches_the_artifact(regret_report):
    """The brief only required pinning the ratio ('at least'); the other two
    estimator_diagnostics figures were left unpinned and flagged as a known
    hole in review. This closes it: REPORT.md's '32 of 1,003 true
    do-not-disturbs' claim must match what estimator_diagnostics() actually
    computed."""
    diag = _load(REGRET)["estimator_diagnostics"]
    rendered = f"{diag['n_true_dnd_negative_draw']} of {diag['n_true_dnd']:,}"
    assert rendered in regret_report, (
        f"REPORT.md does not state {rendered!r} from results_regret.json's "
        f"estimator_diagnostics"
    )


def test_regret_report_wait_side_pay_rate_diagnostic_matches_the_artifact(regret_report):
    """The third out-of-band figure REPORT.md used to cite unbacked: the
    WAIT-side pay rate. Same closure as the negative-draw test above."""
    diag = _load(REGRET)["estimator_diagnostics"]
    rate = f"{diag['wait_side_pay_rate'] * 100:.1f}%"
    assert rate in regret_report, (
        f"REPORT.md does not state the WAIT-side pay rate as {rate!r} from "
        f"results_regret.json's estimator_diagnostics"
    )


# ── Replicating the cost-side disagreement: the counterfactual check's
# realised-cost-vs-interval disagreement was originally measured on a single
# draw of the evaluation population. This project's governing rule is that a
# single-draw conclusion is a claim about that draw, not the method — so the
# disagreement itself had to be replicated across independent draws before
# being published as a standing finding. `disagreement_replication` in
# results_regret.json carries the per-draw rows and the verdict; these tests
# pin both documents to it exactly, the same way the rest of this file pins
# every other regret figure.

def test_disagreement_replication_headline_draw_matches_counterfactual_check(): # noqa: E501
    """Draw 0 of `disagreement_replication` must be the same headline draw
    `counterfactual_check` already reports — not a second, independently
    computed number that could silently drift from it. This is the guard
    against the replication path quietly re-deriving draw 0 instead of
    reusing the one true computation."""
    d = _load(REGRET)
    check = d["counterfactual_check"]
    draw0 = d["disagreement_replication"]["draws"][0]
    assert draw0["draw"] == 0
    assert draw0["seed"] == d["eval_seed"]
    assert draw0["n"] == check["n"]
    assert draw0["realised_cost"] == check["realised_cost"]
    assert draw0["cost_interval_low"] == check["cost_interval_low"]
    assert draw0["cost_interval_high"] == check["cost_interval_high"]
    assert (
        draw0["realised_cost_inside_interval"]
        == check["realised_cost_inside_interval"]
    )


def test_disagreement_replication_draw_rows_match_the_artifact(results_md, regret_report):
    """Every draw's seed, realised cost, interval bounds and inside/outside
    verdict must appear in both documents exactly as the artifact computed
    them — a rerun that moves any one draw (a non-deterministic pipeline, a
    changed seed offset, a changed n_boot) must fail this test rather than
    let the prose keep quoting a stale table."""
    draws = _load(REGRET)["disagreement_replication"]["draws"]
    for row in draws:
        seed = str(row["seed"])
        cost = f"{row['realised_cost']:,.0f}"
        lo = f"{row['cost_interval_low']:,.0f}"
        hi = f"{row['cost_interval_high']:,.0f}"
        for doc_name, doc in (("RESULTS.md", results_md), ("REPORT.md", regret_report)):
            assert seed in doc, (
                f"{doc_name} does not state draw {row['draw']}'s seed {seed}"
            )
            assert cost in doc, (
                f"{doc_name} does not state draw {row['draw']}'s realised "
                f"cost {cost}"
            )
            assert lo in doc, (
                f"{doc_name} does not state draw {row['draw']}'s interval "
                f"low bound {lo}"
            )
            assert hi in doc, (
                f"{doc_name} does not state draw {row['draw']}'s interval "
                f"high bound {hi}"
            )


def _line_containing(text: str, *, needle: str, doc_name: str, seed: int) -> str:
    """The single physical line of `text` naming this seed — used to check
    that a per-draw figure or label is attached to THAT draw's own row, not
    merely present somewhere in the document. A bare `x in doc` check (as
    used elsewhere in this file for figures that appear only once) cannot
    catch a transposed label between two rows, because both labels would
    still be present somewhere in the document; anchoring to the row's own
    line is what makes that failure visible."""
    matches = [line for line in text.splitlines() if needle in line]
    assert matches, f"{doc_name} has no line naming seed {seed} ({needle!r})"
    assert len(matches) == 1, (
        f"{doc_name} has {len(matches)} lines naming seed {seed}, expected "
        f"exactly one to anchor the per-draw check to"
    )
    return matches[0]


def test_disagreement_replication_n_and_label_match_their_own_row(results_md, regret_report):
    """Review findings: (1) REPORT.md's per-draw table states each draw's
    `n` (declined-and-priced case count for that draw's population) with
    nothing pinning it — a rerun that moved any draw's `n` could drift the
    table silently. (2) No test checked that an INSIDE/OUTSIDE (or
    inside/outside) label sits next to the *correct* draw's numbers — a
    transposed pair of labels between two rows would still pass a test that
    only checks both words appear somewhere in the document. This ties both
    the `n` and the label to the physical line naming that draw's own seed,
    in both documents, so a transposition or a drifted `n` fails here."""
    draws = _load(REGRET)["disagreement_replication"]["draws"]
    for row in draws:
        seed = row["seed"]
        n = row["n"]
        inside = row["realised_cost_inside_interval"]
        right_word, wrong_word = ("INSIDE", "OUTSIDE") if inside else ("OUTSIDE", "INSIDE")

        report_line = _line_containing(
            regret_report, needle=str(seed), doc_name="REPORT.md", seed=seed
        )
        assert str(n) in report_line, (
            f"REPORT.md's row for seed {seed} does not state n={n}"
        )
        assert right_word in report_line, (
            f"REPORT.md's row for seed {seed} does not say {right_word} "
            f"(realised_cost_inside_interval={inside})"
        )
        assert wrong_word not in report_line, (
            f"REPORT.md's row for seed {seed} says {wrong_word}, but "
            f"realised_cost_inside_interval={inside} means it should say "
            f"{right_word} -- labels may be transposed between rows"
        )

        results_line = _line_containing(
            results_md, needle=str(seed), doc_name="RESULTS.md", seed=seed
        )
        assert right_word.lower() in results_line, (
            f"RESULTS.md's row for seed {seed} does not say "
            f"{right_word.lower()} (realised_cost_inside_interval={inside})"
        )
        assert wrong_word.lower() not in results_line, (
            f"RESULTS.md's row for seed {seed} says {wrong_word.lower()}, "
            f"but realised_cost_inside_interval={inside} means it should "
            f"say {right_word.lower()} -- labels may be transposed between "
            f"rows"
        )


def test_disagreement_replication_verdict_matches_the_artifact(results_md, regret_report):
    """Ruling: the replicated verdict is one of four outcomes (insufficient
    draws / replicates / the headline was the outlier / unresolved),
    computed fresh by `disagreement_verdict()` on every run — it must not be
    hand-typed into the docs independently of what the artifact says, and it
    must not be silently reworded into a friendlier or harsher outcome than
    the one the code actually reached.

    This imports and calls the real `disagreement_verdict()` on the
    artifact's own draws rather than re-deriving its n_outside/n_total
    branches here — a re-derivation only ever checks itself against itself.
    `test_run_regret.py` drives all four branches of the real function
    directly with constructed rows, including the below-floor branch this
    artifact's data (>= MIN_DRAWS_FOR_VERDICT) never exercises; this test
    only needs to confirm the artifact and the function agree, and pins the
    verdict word into both documents."""
    import sys
    sys.path.insert(0, str(ROOT / "experiments" / "regret"))
    from run_regret import disagreement_verdict

    rep = _load(REGRET)["disagreement_replication"]
    n_outside = rep["n_outside"]
    n_draws = rep["n_draws"]
    assert n_outside == sum(
        1 for r in rep["draws"] if not r["realised_cost_inside_interval"]
    ), "n_outside does not match the draws it is supposed to summarise"

    replicates, message = disagreement_verdict(rep["draws"])
    assert replicates == rep["replicates"], (
        f"disagreement_verdict() on the artifact's own draws returns "
        f"replicates={replicates}, but the artifact's stored 'replicates' "
        f"field says {rep['replicates']}"
    )
    for word in ("INSUFFICIENT", "REPLICATES", "NOT REPLICATED", "UNRESOLVED"):
        if word in message:
            verdict_word = word
            break
    else:
        raise AssertionError(f"disagreement_verdict() message names no known verdict: {message!r}")

    for doc_name, doc in (("RESULTS.md", results_md), ("REPORT.md", regret_report)):
        assert verdict_word in doc, (
            f"{doc_name} does not state the disagreement_replication verdict "
            f"as {verdict_word!r} (n_outside={n_outside} of {n_draws})"
        )
        assert str(n_outside) in doc and str(n_draws) in doc, (
            f"{doc_name} does not state the {n_outside} of {n_draws} draw "
            f"count the verdict is based on"
        )


def test_disagreement_replication_rule_is_stated_in_both_documents(regret_report):
    """The verdict rule itself (fixed before running the replication, in the
    style of MODEL_ERROR_PREDICTION) must be quoted in REPORT.md, not just
    enforced silently in code — otherwise a reader has no way to check the
    verdict against the rule that produced it."""
    rule = _load(REGRET)["disagreement_replication"]["rule"]
    assert rule in regret_report, (
        "REPORT.md does not quote the disagreement_replication rule from "
        "results_regret.json verbatim"
    )


def test_disagreement_replication_does_not_move_the_pinned_headline_totals():
    """The four figures stable since the first regret run --
    134347.46 / 93678.91 / -40668.55 / 170 -- must not move because
    replication was added. If they do, something non-deterministic (or a
    changed seed) entered the pipeline, which is a much bigger problem than
    this feature."""
    d = _load(REGRET)
    t = d["totals"]
    assert t["cost"] == 134347.46
    assert t["saved"] == 93678.91
    assert t["net"] == -40668.55
    assert t["model_errors"] == 170


# ── N6: detection latency ────────────────────────────────────────────────
#
# The claim these pin is that N6's speed is measured rather than demonstrated.
# A latency without its false-alarm rate is not a result, so the rate is pinned
# beside the table it qualifies — the document must not be able to quote one
# without the other.

FLEET_LATENCY = ROOT / "experiments" / "fleet" / "results_fleet_latency.json"


def test_fleet_latency_rows_match_the_artifact(results_md):
    for e in _load(FLEET_LATENCY)["effect_sizes"]:
        row = (
            f"| {e['post_rate']:.2f} | {e['drop']:.2f} | "
            f"{e['n_detected']}/{e['n_draws']} | "
            f"{e['median_latency_attempts']:.0f} | "
            f"{e['min_latency_attempts']}–{e['max_latency_attempts']} |"
        )
        assert row in results_md, f"latency row missing or stale: {row!r}"


def test_fleet_false_alarm_rate_is_published_with_the_latency(results_md):
    fa = _load(FLEET_LATENCY)["false_alarm"]
    stated = (
        f"**False alarms: {fa['n_false_alarms']} of {fa['n_draws']} control draws "
        f"({fa['false_alarm_rate']:.1%}).**"
    )
    assert stated in results_md, (
        "RESULTS.md quotes latency without the false-alarm rate that makes it "
        f"meaningful. Expected {stated!r}"
    )


def test_fleet_latency_claim_is_reported_as_the_rule_judged_it():
    """The rule requires the detector to fire in EVERY draw at the largest
    effect size before a latency is claimable. If a future run misses one, the
    document must stop quoting a latency and report the miss rate instead."""
    d = _load(FLEET_LATENCY)
    largest = min(d["effect_sizes"], key=lambda e: e["post_rate"])
    assert largest["n_missed"] == 0, (
        "the detector missed the change-point at the largest effect size — "
        "RESULTS.md must report the miss rate, not a latency"
    )
    assert d["claimable"] is True


def test_fleet_latency_is_monotone_in_severity():
    """A bigger collapse must not take longer to notice than a small one. If
    this inverts, the detector is not behaving like a two-proportion test and
    the report's explanation of its own numbers is wrong."""
    rows = sorted(_load(FLEET_LATENCY)["effect_sizes"], key=lambda e: e["drop"])
    medians = [r["median_latency_attempts"] for r in rows]
    assert medians == sorted(medians, reverse=True), (
        f"latency is not monotone in severity: {medians}"
    )


# ── N6: the figures that drifted ─────────────────────────────────────────
#
# `futile_retries_avoided` was quoted as 351 in README and RESULTS while the
# artifact reproduced 340 — the experiment is deterministic, but the committed
# artifact had gone stale against a behavioural change and nothing was pinning
# it. Every other headline figure had a test; this one did not, which is
# exactly why it was the one that drifted.

def test_fleet_futile_retries_match_the_artifact(results_md, readme):
    f = _load(FLEET)
    n = f["futile_retries_avoided"]
    assert f"| Retries into the degraded issuer | {n} | **0** |" in results_md
    assert f"stopping {n}" in results_md
    assert f"**{n} → 0**" in readme


def test_fleet_recovery_change_matches_the_artifact(results_md, readme):
    f = _load(FLEET)
    money = f"₹{round(f['gross_recovery_change']):,}"
    assert money in results_md, f"RESULTS.md does not state {money}"
    assert money in readme, f"README.md does not state {money}"


def test_the_fleet_detection_claim_still_holds():
    assert _load(FLEET)["detection_correct"] is True


# ── Tier 1b: the one money figure grounded outside the simulator ─────────
#
# This is the project's only rupee-denominated claim that does not come from
# its own generator, so it is pinned harder than most — including the part
# that did NOT work, because a document that keeps the effect and drops the
# failed targeting claim would be telling half the truth.

REVENUE = ROOT / "experiments" / "tier1_revenue" / "results_revenue.json"


def test_real_incremental_revenue_matches_the_artifact(results_md):
    e = _load(REVENUE)["effect"]
    stated = (
        f"${e['incremental_per_1000']:,.0f} per 1,000 customers, 95% CI\n"
        f"[${e['ci_low_per_1000']:,.0f}, ${e['ci_high_per_1000']:,.0f}]"
    )
    assert stated in results_md, f"RESULTS.md does not state {stated!r}"
    assert e["excludes_zero"] is True, (
        "the real-data revenue interval now covers zero — RESULTS.md still "
        "claims it excludes zero"
    )


def test_the_targeting_claim_is_reported_as_not_established(results_md):
    """The unflattering half. If a future run establishes targeting on real
    money that is a stronger result and the document should say so — but it
    must not say so while the paired interval still covers zero."""
    t = _load(REVENUE)["targeting"]
    assert t["paired_interval_excludes_zero"] is False, (
        "the paired interval now excludes zero — targeting IS established on "
        "real money, and RESULTS.md should be upgraded to claim it"
    )
    stated = (
        f"{t['paired_difference']:+.4f} per customer, 95% CI "
        f"[{t['paired_ci_low']:+.4f}, {t['paired_ci_high']:+.4f}] — covers zero."
    )
    assert stated in results_md
    assert "not established" in results_md.lower()


def test_the_policy_was_evaluated_out_of_sample():
    """The in-sample version reported 7-12x the honest advantage. If this ever
    reverts to fitting and ranking the same rows, the number stops meaning
    anything."""
    t = _load(REVENUE)["targeting"]
    assert t["n_train"] > 0 and t["n_evaluated_out_of_sample"] > 0
    assert t["n_train"] + t["n_evaluated_out_of_sample"] == _load(REVENUE)["n_customers"]


def test_pooled_real_money_effect_matches_the_artifact(results_md):
    p = _load(REVENUE)["effect_pooled_all_arms"]
    stated = (
        f"${p['incremental_per_1000']:,.0f} per 1,000 over {p['n_customers']:,} customers, 95% CI\n"
        f"[${p['ci_low_per_1000']:,.0f}, ${p['ci_high_per_1000']:,.0f}]"
    )
    assert stated in results_md
    assert p["excludes_zero"] is True


def test_the_targeting_question_is_reported_as_unanswerable_here(results_md):
    """Stronger than 'the interval covers zero': the document must say the
    dataset cannot settle it, and carry the sample size that could. If pooling
    ever WOULD resolve it, this fails and the claim should be re-run."""
    pw = _load(REVENUE)["targeting_power"]
    assert pw["pooling_would_resolve_it"] is False, (
        "pooling now resolves the targeting question — re-run and upgrade the claim"
    )
    assert f"{pw['standard_errors_from_zero']} standard errors from zero" in results_md
    assert f"{pw['held_out_customers_needed']:,} customers" in results_md


# ── Tier 1c: B1's thesis, off the simulator ──────────────────────────────

TARGETING = ROOT / "experiments" / "tier1_targeting" / "results_targeting.json"


def test_criteo_targeting_result_matches_the_artifact(results_md):
    d = _load(TARGETING)
    stated = (
        f"**Paired difference {d['paired_difference']:+.5f} per user, 95% CI\n"
        f"[{d['paired_ci_low']:+.5f}, {d['paired_ci_high']:+.5f}] — excludes zero, "
        f"{d['standard_errors_from_zero']} standard errors out.**"
    )
    assert stated in results_md, f"RESULTS.md does not state {stated!r}"


def test_criteo_targeting_rows_match_the_artifact(results_md):
    for est, v in _load(TARGETING)["by_estimator"].items():
        row = (f"| {est} | {v['targeted']:.5f} | {v['random_matched']:.5f} "
               f"| {v['difference']:+.5f} |")
        assert row in results_md, f"stale estimator row: {row!r}"


def test_the_targeting_claim_holds_under_the_stricter_rule():
    """If this ever flips, RESULTS.md must stop saying B1 is off the simulator."""
    d = _load(TARGETING)
    assert d["paired_interval_excludes_zero"] is True
    assert d["estimators_agree_on_sign"] is True
    assert d["holds"] is True


def test_the_criteo_policy_was_chosen_out_of_sample():
    d = _load(TARGETING)
    assert d["n_train"] > 0 and d["n_evaluated_out_of_sample"] > 0
    assert d["n_train"] + d["n_evaluated_out_of_sample"] == d["n_rows"]


RECAL = ROOT / "experiments" / "uplift_recalibration" / "results_recalibration.json"


def test_recalibration_is_reported_as_undetermined(results_md):
    """The correction is not shipped. If a future run establishes it, that is a
    stronger result and the document should claim it — but not while the draws
    disagree on the sign."""
    d = _load(RECAL)
    assert d["every_draw_agrees"] is False, (
        "the draws now agree — re-run and upgrade or retract the claim"
    )
    assert d["holds"] is False
    assert "**UNDETERMINED**" in results_md
    assert f"Mean **{d['mean_value_delta']:+,.0f}**" in results_md


def test_recalibration_draw_rows_match_the_artifact(results_md):
    for r in _load(RECAL)["draws"]:
        row = (f"| {r['eval_seed']} | ₹{r['shipped']['incremental_per_1000_cases']:,.0f} | "
               f"₹{r['recalibrated']['incremental_per_1000_cases']:,.0f} | {r['value_delta']:+,.0f} |")
        assert row in results_md, f"stale recalibration row: {row!r}"


def test_the_slope_correction_is_shown_working_before_it_is_shown_not_paying(results_md):
    """The finding depends on both halves being stated. The correction DOES fix
    the calibration — if the document dropped that, the reader would conclude
    the fix simply failed, when the point is that a fix which demonstrably works
    still does not move recovered value."""
    sl = _load(RECAL)["slope_on_heldout_population"]
    assert f"**{sl['before']} → {sl['after']}**" in results_md, (
        "RESULTS.md does not show the slope correction working, which is half "
        "the finding"
    )
    assert "not shipped" in results_md
