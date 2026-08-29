"""Does a better-correlated uplift model make better decisions?

The single T-learner correlates 0.347 with true persuadability; a 20-member
bootstrap ensemble of the same learner reaches 0.445, and that gain replicated
across three draws. Correlation is the headline diagnostic for a CATE model, so
the obvious move is to ship the ensemble.

Two evaluation populations disagree about whether that helps:

    batch eval     (SEED+1000)   single Rs 272,281   ensemble Rs 291,588   +7.1%
    baselines eval (SEED+2000)   single Rs 317,168   ensemble Rs 290,581   -8.4%

Opposite signs, overlapping intervals. Either number quoted alone would be a
confident and unfounded claim about the ensemble, in whichever direction the
author preferred — which is exactly the failure this repo has already made
four times and now tests against everywhere else.

There is a reason to expect correlation and value to come apart here, and it is
not subtle. The policy does not rank cases by tau_hat; it contacts when
tau_hat * amount_at_risk exceeds the cost of the message. That is a *threshold
on a product*, so what matters is calibration of magnitude near the boundary and
the ranking of cases that sit close to it. Bagging improves global correlation
partly by shrinking extreme predictions toward the mean, which is exactly the
kind of change that can raise correlation while moving cases across a threshold
in both directions. A model can therefore be better as a predictor and worse as
a decision rule, and nothing about the correlation number would reveal it.

So this measures the thing the deployment actually cares about, on several
populations, with the two arms differing in one respect only. Both arms share
the same training cases, the same randomised assignment, the same churn model
(which the flag does not touch) and the same evaluation populations; the single
difference is which uplift model the EV policy consults.

The verdict rule is fixed here, before the run: an effect on recovered value is
claimable only if every draw agrees on its sign. Anything else is reported as
undetermined, however large the mean looks.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "tier2_simulation"))

from run_batch import NOW, SEED, build_uplift, run_eval  # noqa: E402

from recovery_ledger.events.actions import ActionType  # noqa: E402
from recovery_ledger.listener.listener import ReplyIntent  # noqa: E402
from recovery_ledger.policy.churn import ChurnRiskModel  # noqa: E402
from recovery_ledger.policy.features import cases_to_feature_matrix  # noqa: E402
from recovery_ledger.sim.environment import (  # noqa: E402
    SimulationEnvironment,
    generate_population,
    persuadability,
)
from recovery_ledger.sim.generator import generate_cases  # noqa: E402

EVAL_SEED = SEED + 10000  # disjoint; see tests/test_experiment_seeds.py


def train_both(n_train: int, seed: int):
    """One training set, one assignment, one churn model, two uplift models."""
    cases = generate_cases(n_train, seed=seed, now=NOW)
    traits = generate_population(cases, seed=seed)
    env = SimulationEnvironment(traits, seed=seed)
    rng = np.random.default_rng(seed)
    treatment = rng.integers(0, 2, size=n_train)

    paid = np.zeros(n_train)
    churned = np.zeros(n_train)
    for i, c in enumerate(cases):
        r = env.step(c, ActionType.NUDGE if treatment[i] else ActionType.WAIT, 0)
        paid[i] = float(r.paid)
        churned[i] = float(r.reply == ReplyIntent.OPT_OUT)

    X = cases_to_feature_matrix(cases)
    churn = ChurnRiskModel().fit(X, treatment, churned, random_state=seed)
    arms = {
        name: build_uplift(seed, ensemble=(name == "ensemble")).fit(X, treatment, paid)
        for name in ("single", "ensemble")
    }
    return arms, churn


def correlation(model, n: int, seed: int) -> float:
    cs = generate_cases(n, seed=seed, now=NOW)
    tr = generate_population(cs, seed=seed)
    return float(np.corrcoef(
        model.predict_cate(cases_to_feature_matrix(cs)),
        np.array([persuadability(tr[c.case_id]) for c in cs]),
    )[0, 1])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n-train", type=int, default=5000)
    ap.add_argument("--n-eval", type=int, default=2000)
    ap.add_argument("--eval-draws", type=int, default=3)
    args = ap.parse_args()

    print(f"Training both arms on {args.n_train} randomised cases (shared churn model)...")
    arms, churn = train_both(args.n_train, SEED)

    draws = [EVAL_SEED + 100 * d for d in range(args.eval_draws)]
    rows = []
    for seed in draws:
        row = {"eval_seed": seed}
        for name, model in arms.items():
            res, _ = run_eval(args.n_eval, model, seed=seed, churn_model=churn)
            row[name] = {
                "incremental_per_1000_cases": res["incremental_per_1000_cases"]["point"],
                "ci_low": res["incremental_per_1000_cases"]["ci_low"],
                "ci_high": res["incremental_per_1000_cases"]["ci_high"],
                "correlation": res["uplift_model_correlation_with_true_persuadability"],
                "treatment_recovery_rate": res["treatment_recovery_rate"],
                "contacts": res.get("contacts_sent"),
                "pct_contacts_to_do_not_disturbs": res.get("pct_contacts_to_do_not_disturbs"),
            }
        row["value_delta"] = (row["ensemble"]["incremental_per_1000_cases"]
                              - row["single"]["incremental_per_1000_cases"])
        row["corr_delta"] = row["ensemble"]["correlation"] - row["single"]["correlation"]
        rows.append(row)
        print(f"  draw {seed}: single Rs {row['single']['incremental_per_1000_cases']:>9,.0f}   "
              f"ensemble Rs {row['ensemble']['incremental_per_1000_cases']:>9,.0f}   "
              f"delta {row['value_delta']:>+9,.0f}   corr {row['single']['correlation']:.3f}"
              f" -> {row['ensemble']['correlation']:.3f}")

    vdeltas = [r["value_delta"] for r in rows]
    cdeltas = [r["corr_delta"] for r in rows]
    value_consistent = all(d > 0 for d in vdeltas) or all(d < 0 for d in vdeltas)
    corr_consistent = all(d > 0 for d in cdeltas) or all(d < 0 for d in cdeltas)

    dnd = [(r["single"]["pct_contacts_to_do_not_disturbs"],
            r["ensemble"]["pct_contacts_to_do_not_disturbs"]) for r in rows]
    dnd_consistent = (all(a is not None and b is not None for a, b in dnd)
                      and (all(b < a for a, b in dnd) or all(b > a for a, b in dnd)))

    print(f"\ncorrelation gain consistent across draws: {corr_consistent}  "
          f"(mean {np.mean(cdeltas):+.3f})")
    print(f"value effect consistent across draws:     {value_consistent}  "
          f"(mean {np.mean(vdeltas):+,.0f}, per draw {[round(d) for d in vdeltas]})")
    print(f"do-not-disturb contact rate consistent:   {dnd_consistent}")
    if not value_consistent:
        print("\n  -> The ensemble's effect on recovered value is UNDETERMINED.\n"
              "     Draws disagree on the sign, so neither direction is claimable.")

    out = {
        "n_train": args.n_train, "n_eval": args.n_eval, "eval_draws": args.eval_draws,
        "eval_seed": EVAL_SEED,
        "correlation_gain_consistent": corr_consistent,
        "mean_correlation_gain": float(np.mean(cdeltas)),
        "value_effect_consistent": value_consistent,
        "mean_value_delta_per_1000": float(np.mean(vdeltas)),
        "value_delta_per_draw": vdeltas,
        "dnd_rate_effect_consistent": dnd_consistent,
        "per_draw": rows,
    }
    (HERE / "results_uplift_ab.json").write_text(json.dumps(out, indent=2))
    print(f"\nWrote {HERE / 'results_uplift_ab.json'}")


if __name__ == "__main__":
    main()
