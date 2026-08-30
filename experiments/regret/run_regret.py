"""What the agent's silences cost, and what they saved.

This system's pitch is that its value is in NOT contacting people: 80% fewer
messages than mass-contact, a whole dashboard section about the three
mechanisms that produce silence. Nothing reported what that silence cost.

Every refusal is a bet that contacting would not have paid, and the simulator
knows which bets were wrong — `persuadability(traits)` is the true per-case
effect, already used for the do-not-disturb diagnostics. The information to
price the agent's own false negatives has been in the repo, unqueried.

POPULATION. This deliberately evaluates on run_batch.py's cases (SEED + 1000).
A regret figure is only quotable beside the B1 headline if it is measured on
the same customers. run_batch.py itself is untouched: submission week is the
wrong time to edit the script the headline rests on, and its results.json is
referenced by eight doc-test assertions.

THE PRE-REGISTERED PREDICTION, fixed before the run. `make calibration` showed
tau_hat's bottom bin is 43.8% true do-not-disturbs against 17.3% of the
population — so it is also 56% customers with positive true uplift, priced as
if they were not. If that result is true, the model-judgement bucket MUST
contain a non-trivial count of cases with tau_true > 0. If that cell comes back
at or near zero, the two experiments contradict each other and one of them is
wrong. That gets published as a contradiction, not reconciled.

THE REPLICATION RULE, fixed before the run. The counterfactual check found
that the realised cost disagrees with the model-based cost interval — but
that was measured on a single draw of the evaluation population, and this
project's governing rule is that a single-draw conclusion is a claim about
that draw, not about the method. The cost-side disagreement is a replicated
finding only if the realised cost falls outside the model-based interval in
EVERY draw. If it falls outside in some draws and inside in others, the
disagreement is NOT established and must be reported as unresolved — a
property of the headline draw rather than of the method. If it falls inside
in every draw, the headline draw was the outlier and that must be published
as such. Either conclusion requires at least MIN_DRAWS_FOR_VERDICT (3) draws
— the same floor every other experiment in this repo uses by default before
treating a replicated result as established; below it, this reports that
too few draws were run to conclude anything, neither a replicated finding
nor a resolved non-finding. Whatever comes out gets published as it is:
seeds, draw counts and interval widths are not tuned to reach a preferred
answer.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "tier2_simulation"))

from run_batch import NOW, SEED, run_eval, train_models  # noqa: E402

from recovery_ledger.events.actions import ActionType  # noqa: E402
from recovery_ledger.kernel.certificate import Decision  # noqa: E402
from recovery_ledger.policy.regret import (  # noqa: E402
    Bucket,
    CONTACT_ACTIONS,
    DeclinedCase,
    classify,
    regret_totals,
    totals_by_bucket,
    was_contacted,
)
from recovery_ledger.sim.environment import (  # noqa: E402
    SimulationEnvironment,
    generate_population,
    persuadability,
)
from recovery_ledger.sim.generator import generate_cases  # noqa: E402

# Deliberately run_batch.py's evaluation population; see the module docstring
# and tests/test_experiment_seeds.py.
EVAL_SEED = SEED + 1000

MODEL_ERROR_PREDICTION = (
    "make calibration reports the bottom tau_hat bin as 43.8% true "
    "do-not-disturbs, so it is also ~56% customers with positive true uplift. "
    "The model-judgement bucket must therefore contain a non-trivial count of "
    "tau_true > 0 refusals. Near zero refutes one of the two experiments."
)
MODEL_ERRORS_EXPECTED_ABOVE = 0

DISAGREEMENT_REPLICATION_RULE = (
    "The cost-side disagreement is a replicated finding only if the "
    "realised cost falls outside the model-based interval in every draw. "
    "If it falls outside in some draws and inside in others, the "
    "disagreement is not established and must be reported as unresolved -- "
    "a property of the headline draw rather than of the method. If it "
    "falls inside in every draw, the headline draw was the outlier and "
    "that must be published as such. Either conclusion requires at least "
    f"{{min_draws}} draws; below that floor, report that too few draws "
    "were run to conclude anything, not a replicated finding or a "
    "resolved non-finding."
)

# The same floor this project uses everywhere else before treating a
# replicated result as established -- every other experiment's default
# `--eval-draws` (horizon, pessimism, sensitivity, uplift_calibration,
# uplift_ab) is 3. Below this many total draws (the headline draw plus
# however many --replication-draws add), disagreement_verdict() must not
# return "replicates" or "the headline was the outlier": either would be a
# one- or two-draw claim wearing a replicated conclusion's clothes, which
# is the exact fallacy this feature exists to close. `--replication-draws
# 0` is therefore an honest "headline only, no replication claim" fast
# path, not a way to manufacture a false "replicates" verdict from n=1.
MIN_DRAWS_FOR_VERDICT = 3
DISAGREEMENT_REPLICATION_RULE = DISAGREEMENT_REPLICATION_RULE.format(
    min_draws=MIN_DRAWS_FOR_VERDICT
)


def treatment_arm(cases, *, seed: int):
    """The cases run_eval assigned to the treatment arm.

    run_eval writes BOTH arms into the same Ledger, so the ledger alone cannot
    say which cases the policy was ever allowed to work. It splits with
    `np.random.default_rng(seed + 1).integers(0, 2, size=n)`, so the identical
    call reproduces the assignment exactly. If run_eval's split ever changes,
    this must change with it — the assertion in main() is what catches that.
    """
    rng = np.random.default_rng(seed + 1)
    is_treatment = rng.integers(0, 2, size=len(cases)).astype(bool)
    return [c for c, t in zip(cases, is_treatment) if t]


def declined_cases(
    ledger, treatment, traits, *, cases, seed: int
) -> tuple[list[DeclinedCase], int, int]:
    """Every treatment-arm case that never received a message.

    The holdout arm is deliberately absent: it was left alone by design, as the
    experimental control, not by a refusal. Including it would roughly double
    the reported regret.

    Previously the only guard against a holdout case entering this function
    was an assert in `main()` on `len(treatment) / len(cases)` — a ratio
    computed independently of whatever collection was actually passed as
    `treatment` below. Swapping that argument for `cases` (both arms) left the
    ratio assert untouched and still passing, while silently doubling the
    priced universe. `cases` and `seed` are now required so this function can
    recompute the true treatment arm itself (via `treatment_arm()`, the exact
    same reconstruction `main()` uses) and refuse anything given to it that
    is not a member of that arm — the guard now constrains the collection
    that is actually priced, not a number computed alongside it.
    """
    expected_ids = {c.case_id for c in treatment_arm(cases, seed=seed)}
    given_ids = {c.case_id for c in treatment}
    outside_arm = given_ids - expected_ids
    assert not outside_arm, (
        f"declined_cases() was given {len(outside_arm)} case(s) not in the "
        f"reconstructed treatment arm — the holdout arm must never enter "
        f"the priced universe"
    )
    declined: list[DeclinedCase] = []
    worked = 0
    resolved_excluded = 0
    for case in treatment:
        case_id = case.case_id
        entries = ledger.entries_for_case(case_id)
        if was_contacted(entries):
            worked += 1
            continue
        stops = [e for e in entries if e.entry_type == "stop"]
        reason = stops[-1].payload.get("reason") if stops else None
        if reason == "resolved":
            # They paid; nothing was forgone. This is not bookkeeping noise —
            # it is the selection mechanism the counterfactual check's
            # one-sidedness rests on (see estimator_diagnostics() and
            # REPORT.md): every case where paid_0 = 1 is routed out here,
            # before the declined universe is built, which is why the
            # universe is conditioned on paid_0 ~= 0 by construction. Counted
            # so the treatment arm's partition adds up in the artifact.
            resolved_excluded += 1
            continue
        # Decision serialises as "DENY", not "deny". Compared against the
        # enum's own value rather than a literal: a lowercase literal here
        # would silently never match, filing every compliance-blocked refusal
        # as a model judgement and inflating the model-error count that the
        # pre-registered prediction turns on.
        kernel_denied = any(
            e.entry_type == "certificate"
            and e.payload.get("decision") == Decision.DENY.value
            and e.payload.get("action_type") in CONTACT_ACTIONS
            for e in entries
        )
        declined.append(DeclinedCase(
            case_id=case_id,
            amount_at_risk=float(case.amount_at_risk),
            tau_true=float(persuadability(traits[case_id])),
            bucket=classify(reason, kernel_denied_contact=kernel_denied),
            stop_reason=reason or "unknown",
        ))
    return declined, worked, resolved_excluded


def realised_pair(case, traits, *, seed: int) -> tuple[float, float]:
    """(paid_0, paid_1) for one case under WAIT and NUDGE respectively.

    SimulationEnvironment gives each case its own RNG stream seeded from
    (seed, case_id), independent of call order, so it is already a common
    random numbers design. Two instances at the same seed rather than two calls
    on one: a second call would advance that case's stream, and the point is
    that both arms see the identical sequence.
    """
    env_wait = SimulationEnvironment(traits, seed=seed)
    env_nudge = SimulationEnvironment(traits, seed=seed)
    paid_0 = float(env_wait.step(case, ActionType.WAIT, 0).paid)
    paid_1 = float(env_nudge.step(case, ActionType.NUDGE, 0).paid)
    return paid_0, paid_1


def realised_incremental(case, traits, *, seed: int) -> float:
    """The paired counterfactual for one declined case, in rupees."""
    paid_0, paid_1 = realised_pair(case, traits, seed=seed)
    return float(case.amount_at_risk) * (paid_1 - paid_0)


def bootstrap_cost_interval(
    costs: np.ndarray, *, n_boot: int, seed: int
) -> tuple[float, float]:
    """A 95% bootstrap interval on the model-based cost total.

    The spec named `counterfactual_check.inside_headline_interval` before
    anyone knew the check is one-sided by selection (see the module
    docstring and REPORT.md): `declined_cases()` excludes every `resolved`
    case, so `realised_saved` can only ever be `-0.0` here and comparing
    `realised_net` against `expected_net` compares a one-sided quantity to a
    two-sided one. That comparison is invalid; this implements the same
    intent on the half of the ledger the check actually can validate.

    `costs` is the per-case model-based `forgone` amount for every in-scope
    declined case (mirrors `totals.cost`, which is `costs.sum()`).
    Resampling with replacement at the same n and summing each draw gives a
    bootstrap distribution of the total cost estimate; the 2.5/97.5th
    percentiles of that distribution are the interval the realised
    (simulated) cost is checked against. Same technique as
    `tier2_simulation/run_batch.py`'s `_bootstrap_ci` and
    `dnd_signal/run_dnd_signal.py`'s `bootstrap_ci` — percentile bootstrap,
    no parametric assumption about the shape of `costs`.
    """
    rng = np.random.default_rng(seed)
    n = len(costs)
    boot = np.empty(n_boot)
    for b in range(n_boot):
        sample = rng.choice(costs, size=n, replace=True)
        boot[b] = sample.sum()
    lo, hi = np.quantile(boot, [0.025, 0.975])
    return float(lo), float(hi)


# A third, disjoint offset: not the training seed (SEED + 0), not the shared
# evaluation batch this experiment prices (EVAL_SEED = SEED + 1000). This
# population never enters `declined_cases()` and is never filtered by
# `resolved`, so it is the right place to check claims the resolved-filter
# would otherwise make unverifiable on its own population. SEED + 12000 is
# unused by every other experiment's declared offset (see
# tests/test_experiment_seeds.py); this module stays "shares" in that
# registry because its priced headline still shares run_batch.py's
# population — this is a diagnostic on a second, separate population, not a
# second evaluation of the headline.
DIAGNOSTICS_SEED = SEED + 12000
DIAGNOSTICS_N = 6000
DIAGNOSTICS_WAIT_SAMPLE_N = 400

# A fourth, disjoint offset -- SEED + 13000 is unused by every other
# experiment's declared offset (see tests/test_experiment_seeds.py), same
# precedent as DIAGNOSTICS_SEED above: an internal seed used to check a
# claim this module makes about its own result, not a second evaluation of
# the headline, so it does not need its own SEED_REGISTRY entry. Each
# replication draw d in 0..replication_draws-1 reseeds the *entire* pipeline
# (run_eval, treatment_arm, declined_cases, the paired replay, the
# bootstrap) at DISAGREEMENT_REPLICATION_SEED + 100*d -- an independent
# population the headline draw never saw, using the same trained models.
DISAGREEMENT_REPLICATION_SEED = SEED + 13000


def estimator_diagnostics(
    *,
    seed: int = DIAGNOSTICS_SEED,
    n: int = DIAGNOSTICS_N,
    wait_sample_n: int = DIAGNOSTICS_WAIT_SAMPLE_N,
) -> dict:
    """Three numbers REPORT.md used to cite out-of-band, now regenerated by
    committed code every time `make regret` runs, on a population disjoint
    from both the training seed and the shared evaluation batch above.

    1. The ratio of mean realised effect (paid_1 - paid_0) to mean tau_true
       across an *unselected* population, checking that `amount * tau_true`
       (what `totals.cost`/`totals.saved` are built from) is on the same
       scale as a directly-simulated replay.
    2. Of the true do-not-disturbs (tau_true < 0) in that same unselected
       population, how many nonetheless drew paid_0=1, paid_1=0 -- a
       genuine negative realised outcome -- which is the fact that makes
       `counterfactual_check`'s `realised_saved = -0.0` a selection artifact
       rather than evidence that negative draws cannot happen at all.
    3. The population's own WAIT-side pay rate, sampled directly. This is
       the low base rate that `declined_cases()` conditions away by
       dropping every `resolved` (paid_0 = 1) case before this experiment's
       priced universe is built.
    """
    cases = generate_cases(n, seed=seed, now=NOW)
    traits = generate_population(cases, seed=seed)
    tau = np.array([persuadability(traits[c.case_id]) for c in cases])

    pairs = np.array([realised_pair(c, traits, seed=seed + 1) for c in cases])
    paid_0, paid_1 = pairs[:, 0], pairs[:, 1]
    realised_effect = paid_1 - paid_0

    mean_tau = float(tau.mean())
    mean_realised_effect = float(realised_effect.mean())
    ratio = mean_realised_effect / mean_tau

    is_true_dnd = tau < 0
    n_true_dnd = int(is_true_dnd.sum())
    negative_draw = (paid_0 == 1) & (paid_1 == 0)
    n_true_dnd_negative_draw = int((is_true_dnd & negative_draw).sum())

    rng = np.random.default_rng(seed + 2)
    sample_idx = rng.choice(n, size=wait_sample_n, replace=False)
    wait_side_paid = int(paid_0[sample_idx].sum())

    return {
        "n": n,
        "seed": seed,
        "mean_tau": round(mean_tau, 6),
        "mean_realised_effect": round(mean_realised_effect, 6),
        "ratio_realised_to_tau": round(ratio, 3),
        "n_true_dnd": n_true_dnd,
        "n_true_dnd_negative_draw": n_true_dnd_negative_draw,
        "wait_side_pay_rate_n": wait_sample_n,
        "wait_side_pay_rate_paid": wait_side_paid,
        "wait_side_pay_rate": round(wait_side_paid / wait_sample_n, 4),
    }


def cost_side_disagreement_draw(
    uplift, churn, *, seed: int, n_eval: int
) -> dict:
    """One independent replication draw of the cost-side counterfactual
    check, on a population the headline draw (EVAL_SEED) never saw.

    This is the exact same computation as the `counterfactual_check` block
    in `main()` -- `run_eval`, `treatment_arm`, `declined_cases`, the paired
    WAIT/NUDGE replay, and the bootstrap interval -- reseeded from `seed`
    instead of `EVAL_SEED`, on the same trained `uplift`/`churn` models.
    "Replicate the disagreement" means rerun the identical code on a fresh
    population, not write a second, bespoke computation that could silently
    diverge from what draw 0 does.
    """
    cases = generate_cases(n_eval, seed=seed, now=NOW)
    traits = generate_population(cases, seed=seed)
    _results, ledger = run_eval(n_eval, uplift, seed=seed, churn_model=churn)
    treatment = treatment_arm(cases, seed=seed)
    assert 0.4 < len(treatment) / len(cases) < 0.6, (
        f"treatment arm is {len(treatment)}/{len(cases)} at seed {seed}; "
        f"run_eval's 50/50 assignment no longer matches treatment_arm()"
    )
    declined, _worked, _n_resolved_excluded = declined_cases(
        ledger, treatment, traits, cases=cases, seed=seed
    )
    by_id = {c.case_id: c for c in treatment}
    in_scope = [d for d in declined if d.bucket is not Bucket.DEFERRED]
    realised = np.array([
        realised_incremental(by_id[d.case_id], traits, seed=seed + 2)
        for d in in_scope
    ])
    costs = np.array([d.forgone for d in in_scope])
    realised_cost = float(realised[realised > 0].sum())
    cost_lo, cost_hi = bootstrap_cost_interval(costs, n_boot=2000, seed=seed + 3)
    inside = cost_lo <= realised_cost <= cost_hi
    return {
        "seed": seed,
        "n": int(realised.size),
        "realised_cost": realised_cost,
        "cost_interval_low": round(cost_lo, 2),
        "cost_interval_high": round(cost_hi, 2),
        "realised_cost_inside_interval": bool(inside),
    }


def disagreement_verdict(rows: list[dict]) -> tuple[bool, str]:
    """Apply THE REPLICATION RULE (see the module docstring) to a list of
    per-draw rows, each carrying `realised_cost_inside_interval`.

    Four outcomes, not three: below `MIN_DRAWS_FOR_VERDICT` (insufficient
    draws to conclude anything), outside in every draw (replicates), inside
    in every draw (the headline draw was the outlier), or a mix
    (unresolved). The floor check runs first and short-circuits the other
    three -- without it, `--replication-draws 0` would leave `rows = [draw0]`,
    `n_total = 1`, and the unanimity check below would return "replicates"
    from a single draw, which is exactly the single-draw-conclusion fallacy
    this whole feature exists to close. There is no fifth branch that
    reweights or averages the draws into a softer verdict -- past the floor,
    the rule is a straight per-draw unanimity check, on purpose.
    """
    n_total = len(rows)
    n_outside = sum(1 for r in rows if not r["realised_cost_inside_interval"])
    n_replications = n_total - 1
    if n_total < MIN_DRAWS_FOR_VERDICT:
        return False, (
            f"INSUFFICIENT DRAWS TO CONCLUDE ANYTHING: only {n_total} draw"
            f"{'s' if n_total != 1 else ''} run (the headline draw plus "
            f"{n_replications} replication draw"
            f"{'s' if n_replications != 1 else ''}), below the floor of "
            f"{MIN_DRAWS_FOR_VERDICT} this project requires before treating "
            f"any replicated result as established. This is neither a "
            f"replicated finding nor a resolved non-finding -- replication "
            f"was not run, or was run at too few draws to conclude "
            f"anything, and that is reported plainly rather than forcing a "
            f"verdict out of {n_total} draw{'s' if n_total != 1 else ''}."
        )
    if n_outside == n_total:
        return True, (
            f"REPLICATES: the realised cost fell OUTSIDE the model-based "
            f"cost interval in all {n_total} draws (the headline draw plus "
            f"{n_replications} independent replication draw"
            f"{'s' if n_replications != 1 else ''}). The cost-side "
            f"disagreement is a property of the method, not an artifact of "
            f"the headline draw."
        )
    if n_outside == 0:
        return False, (
            f"NOT REPLICATED -- THE HEADLINE DRAW WAS THE OUTLIER: the "
            f"realised cost fell INSIDE the model-based cost interval in "
            f"all {n_total} draws. The headline draw's disagreement did not "
            f"recur in any of the {n_replications} independent replication "
            f"draw{'s' if n_replications != 1 else ''}; the headline draw "
            f"was the outlier, and that is published as such rather than "
            f"as a property of the method."
        )
    return False, (
        f"UNRESOLVED: the realised cost fell outside the model-based cost "
        f"interval in {n_outside} of {n_total} draws (including the "
        f"headline). The cost-side disagreement is NOT established as a "
        f"replicated finding -- it is a property of which draw is examined, "
        f"not of the method -- and must be reported as unresolved rather "
        f"than as either a confirmed finding or a resolved non-finding."
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n-train", type=int, default=5000)
    ap.add_argument("--n-eval", type=int, default=2000)
    ap.add_argument("--counterfactual", action="store_true", default=True)
    ap.add_argument("--no-counterfactual", dest="counterfactual", action="store_false")
    ap.add_argument("--diagnostics", action="store_true", default=True)
    ap.add_argument("--no-diagnostics", dest="diagnostics", action="store_false")
    ap.add_argument(
        "--replication-draws", type=int, default=5,
        help="independent draws (beyond the headline draw) used to check "
             "whether the cost-side disagreement replicates; see THE "
             "REPLICATION RULE in the module docstring",
    )
    args = ap.parse_args()

    print(f"Training on {args.n_train} randomised-contact cases...")
    uplift, churn = train_models(args.n_train, seed=SEED, ensemble=False)

    print(f"Re-running run_batch's evaluation population (seed {EVAL_SEED})...")
    _results, ledger = run_eval(args.n_eval, uplift, seed=EVAL_SEED, churn_model=churn)

    cases = generate_cases(args.n_eval, seed=EVAL_SEED, now=NOW)
    traits = generate_population(cases, seed=EVAL_SEED)
    treatment = treatment_arm(cases, seed=EVAL_SEED)

    # The holdout arm must never enter the universe. If run_eval's assignment
    # drifts away from the reconstruction above, this is where it surfaces.
    assert 0.4 < len(treatment) / len(cases) < 0.6, (
        f"treatment arm is {len(treatment)}/{len(cases)}; run_eval's 50/50 "
        f"assignment no longer matches treatment_arm()"
    )
    print(f"Treatment arm: {len(treatment)} of {len(cases)} cases "
          f"({len(treatment) / len(cases) * 100:.2f}%)")
    declined, worked, n_resolved_excluded = declined_cases(
        ledger, treatment, traits, cases=cases, seed=EVAL_SEED
    )

    totals = regret_totals(declined)
    by_bucket = totals_by_bucket(declined)
    n_deferred = sum(1 for d in declined if d.bucket is Bucket.DEFERRED)

    print(
        f"  worked {worked}, deferred {n_deferred}, resolved (excluded) "
        f"{n_resolved_excluded}, declined (priced) {totals.n} "
        f"-> {worked + n_deferred + n_resolved_excluded + totals.n} of "
        f"{len(treatment)}"
    )

    print(f"\n{'bucket':<18}{'n':>6}{'cost':>14}{'saved':>14}{'net':>14}{'errors':>8}")
    for bucket, t in sorted(by_bucket.items(), key=lambda kv: -kv[1].cost):
        print(f"{bucket.value:<18}{t.n:>6}{t.cost:>14,.0f}{t.saved:>14,.0f}"
              f"{t.net:>14,.0f}{t.model_errors:>8}")
    print(f"{'TOTAL':<18}{totals.n:>6}{totals.cost:>14,.0f}{totals.saved:>14,.0f}"
          f"{totals.net:>14,.0f}{totals.model_errors:>8}")

    holds = totals.model_errors > MODEL_ERRORS_EXPECTED_ABOVE
    print(f"\nPre-registered prediction: model errors > {MODEL_ERRORS_EXPECTED_ABOVE}")
    print(f"  observed {totals.model_errors} -> {'HOLDS' if holds else 'REFUTED'}")
    if not holds:
        print("  REFUTED. This contradicts make calibration. Publish the "
              "contradiction; do not reconcile it.")

    check = None
    if args.counterfactual:
        print(f"\nPaired counterfactual over {len(declined)} declined cases...")
        by_id = {c.case_id: c for c in treatment}
        in_scope = [d for d in declined if d.bucket is not Bucket.DEFERRED]
        realised = np.array([
            realised_incremental(by_id[d.case_id], traits, seed=EVAL_SEED + 2)
            for d in in_scope
        ])
        costs = np.array([d.forgone for d in in_scope])
        realised_cost = float(realised[realised > 0].sum())
        cost_lo, cost_hi = bootstrap_cost_interval(
            costs, n_boot=2000, seed=EVAL_SEED + 3
        )
        inside_interval = cost_lo <= realised_cost <= cost_hi
        check = {
            "n": int(realised.size),
            "realised_cost": realised_cost,
            "realised_saved": float(-realised[realised < 0].sum()),
            "realised_net": float(-realised.sum()),
            "expected_net": totals.net,
            # The universe excludes `resolved` cases (they paid; nothing was
            # forgone), which conditions it on paid_0 ~= 0 — refusing can only
            # be observed to "save" money when paid_0=1 and paid_1=0, and
            # those cases are gone by construction. So this check can confirm
            # the cost side (positive tau_true, paid_1 > paid_0) but
            # structurally cannot produce a realised saved figure to compare
            # against `totals.saved`. Recorded here so the JSON carries the
            # caveat, not just the prose in REPORT.md.
            "validates": "cost side only",
            "one_sided_because": (
                "the universe excludes resolved cases, so paid_0 is ~0 by "
                "selection and a realised saving cannot be observed"
            ),
            # The spec named `inside_headline_interval` before anyone knew
            # the check is one-sided; implemented here on the half of the
            # ledger it actually validates — see bootstrap_cost_interval()'s
            # docstring. This is a real, computed verdict: if the realised
            # cost lands outside the interval, that is published as-is, not
            # tuned away.
            "cost_interval_low": round(cost_lo, 2),
            "cost_interval_high": round(cost_hi, 2),
            "realised_cost_inside_interval": bool(inside_interval),
        }
        print(f"  realised net {check['realised_net']:,.0f} vs "
              f"expected net {totals.net:,.0f}")
        print(
            f"  realised cost {realised_cost:,.0f} vs 95% bootstrap interval "
            f"[{cost_lo:,.0f}, {cost_hi:,.0f}] on the model-based cost -> "
            f"{'INSIDE' if inside_interval else 'OUTSIDE'}"
        )

    disagreement_replication = None
    if check is not None:
        print(
            f"\nReplicating the cost-side disagreement over "
            f"{args.replication_draws} independent draw(s), seed "
            f"{DISAGREEMENT_REPLICATION_SEED} + 100*d..."
        )
        draw0 = {
            "draw": 0,
            "seed": EVAL_SEED,
            "n": check["n"],
            "realised_cost": check["realised_cost"],
            "cost_interval_low": check["cost_interval_low"],
            "cost_interval_high": check["cost_interval_high"],
            "realised_cost_inside_interval": check["realised_cost_inside_interval"],
        }
        print(
            f"  draw 0 (seed {EVAL_SEED}, headline): realised cost "
            f"{draw0['realised_cost']:,.0f} vs interval "
            f"[{draw0['cost_interval_low']:,.0f}, "
            f"{draw0['cost_interval_high']:,.0f}] -> "
            f"{'INSIDE' if draw0['realised_cost_inside_interval'] else 'OUTSIDE'}"
        )
        rows = [draw0]
        for d in range(args.replication_draws):
            seed = DISAGREEMENT_REPLICATION_SEED + 100 * d
            row = {
                "draw": d + 1,
                **cost_side_disagreement_draw(
                    uplift, churn, seed=seed, n_eval=args.n_eval
                ),
            }
            rows.append(row)
            print(
                f"  draw {d + 1} (seed {seed}): realised cost "
                f"{row['realised_cost']:,.0f} vs interval "
                f"[{row['cost_interval_low']:,.0f}, "
                f"{row['cost_interval_high']:,.0f}] -> "
                f"{'INSIDE' if row['realised_cost_inside_interval'] else 'OUTSIDE'}"
            )
        n_outside = sum(1 for r in rows if not r["realised_cost_inside_interval"])
        replicates, verdict = disagreement_verdict(rows)
        print(f"\n{verdict}")
        disagreement_replication = {
            "rule": DISAGREEMENT_REPLICATION_RULE,
            "min_draws_for_verdict": MIN_DRAWS_FOR_VERDICT,
            "n_draws": len(rows),
            "replication_draws": args.replication_draws,
            "draws": rows,
            "n_outside": n_outside,
            "replicates": replicates,
            "verdict": verdict,
        }

    diagnostics = None
    if args.diagnostics:
        print(
            f"\nEstimator diagnostics on a fresh population of "
            f"{DIAGNOSTICS_N} (seed {DIAGNOSTICS_SEED}, disjoint from "
            f"{EVAL_SEED})..."
        )
        diagnostics = estimator_diagnostics()
        print(
            f"  mean realised effect / mean tau_true = "
            f"{diagnostics['ratio_realised_to_tau']:.3f}"
        )
        print(
            f"  true do-not-disturbs with a negative realised draw: "
            f"{diagnostics['n_true_dnd_negative_draw']} of "
            f"{diagnostics['n_true_dnd']}"
        )
        print(
            f"  WAIT-side pay rate: {diagnostics['wait_side_pay_rate'] * 100:.1f}% "
            f"({diagnostics['wait_side_pay_rate_paid']} of "
            f"{diagnostics['wait_side_pay_rate_n']} sampled)"
        )

    out = {
        "n_eval": args.n_eval,
        "eval_seed": EVAL_SEED,
        "shares_population_with": "tier2_simulation/run_batch.py",
        "n_treatment_arm": len(treatment),
        "n_declined": totals.n,
        "n_worked": worked,
        "n_deferred": n_deferred,
        "n_resolved_excluded": n_resolved_excluded,
        # Written above the results so it cannot be read as post-hoc.
        "prediction": {
            "rule": MODEL_ERROR_PREDICTION,
            "model_errors_expected_above": MODEL_ERRORS_EXPECTED_ABOVE,
            "model_errors_observed": totals.model_errors,
            "holds": bool(holds),
        },
        "totals": {
            "cost": round(totals.cost, 2),
            "saved": round(totals.saved, 2),
            "net": round(totals.net, 2),
            "model_errors": totals.model_errors,
        },
        "buckets": [
            {
                "bucket": b.value, "n": t.n,
                "cost": round(t.cost, 2), "saved": round(t.saved, 2),
                "net": round(t.net, 2), "model_errors": t.model_errors,
            }
            for b, t in sorted(by_bucket.items(), key=lambda kv: -kv[1].cost)
        ],
        "counterfactual_check": check,
        "disagreement_replication": disagreement_replication,
        "estimator_diagnostics": diagnostics,
    }
    (HERE / "results_regret.json").write_text(json.dumps(out, indent=2))
    print(f"\nWrote {HERE / 'results_regret.json'}")


if __name__ == "__main__":
    main()
