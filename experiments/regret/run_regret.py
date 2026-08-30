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


def declined_cases(ledger, treatment, traits) -> tuple[list[DeclinedCase], int]:
    """Every treatment-arm case that never received a message.

    The holdout arm is deliberately absent: it was left alone by design, as the
    experimental control, not by a refusal. Including it would roughly double
    the reported regret, which is why `treatment` is passed in rather than the
    full batch and why the caller asserts the arm size.
    """
    declined: list[DeclinedCase] = []
    worked = 0
    for case in treatment:
        case_id = case.case_id
        entries = ledger.entries_for_case(case_id)
        if was_contacted(entries):
            worked += 1
            continue
        stops = [e for e in entries if e.entry_type == "stop"]
        reason = stops[-1].payload.get("reason") if stops else None
        if reason == "resolved":
            continue  # they paid; nothing was forgone
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
    return declined, worked


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


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n-train", type=int, default=5000)
    ap.add_argument("--n-eval", type=int, default=2000)
    ap.add_argument("--counterfactual", action="store_true", default=True)
    ap.add_argument("--no-counterfactual", dest="counterfactual", action="store_false")
    ap.add_argument("--diagnostics", action="store_true", default=True)
    ap.add_argument("--no-diagnostics", dest="diagnostics", action="store_false")
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
    declined, worked = declined_cases(ledger, treatment, traits)

    totals = regret_totals(declined)
    by_bucket = totals_by_bucket(declined)
    n_deferred = sum(1 for d in declined if d.bucket is Bucket.DEFERRED)

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
        realised = np.array([
            realised_incremental(by_id[d.case_id], traits, seed=EVAL_SEED + 2)
            for d in declined if d.bucket is not Bucket.DEFERRED
        ])
        check = {
            "n": int(realised.size),
            "realised_cost": float(realised[realised > 0].sum()),
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
        }
        print(f"  realised net {check['realised_net']:,.0f} vs "
              f"expected net {totals.net:,.0f}")

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
        "n_declined": totals.n,
        "n_worked": worked,
        "n_deferred": n_deferred,
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
        "estimator_diagnostics": diagnostics,
    }
    (HERE / "results_regret.json").write_text(json.dumps(out, indent=2))
    print(f"\nWrote {HERE / 'results_regret.json'}")


if __name__ == "__main__":
    main()
