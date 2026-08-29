"""What the churn penalty buys, and what it costs.

`EVDecisionPolicy.lambda_churn` defaults to 4.0, and the docstring justifies
that choice with a table: contacts to do-not-disturbs falling from 20.1% to
13.6%, incremental rupees per contact rising from 302 to 450, and a claim that
4.0 "strictly dominates" 2.0. RESULTS.md prints the same curve.

Those numbers had no artifact behind them. They existed in two markdown files
and a source comment, and nothing regenerated or checked them — in a repo whose
first rule is that every published number comes from re-runnable code. They
were also derived from a `results_baselines.json` that had drifted out of sync
with the code, so by the time they were found they were quoting a run that the
current repo no longer reproduces.

This regenerates the curve as an artifact. It sweeps lambda_churn over the
published grid against the same evaluation batch the baselines table uses, with
common random numbers across settings so the comparison is paired.

The dominance claim gets tested rather than asserted. "4.0 strictly dominates
2.0" means 4.0 is no worse on recovered value AND better on contact volume and
do-not-disturb exposure. The script evaluates that conjunction, and the value
test is on the point estimate rather than on interval overlap — overlapping
CIs mean the difference is unresolved at this sample size, which is not the
same as "no worse", and treating it as such would let a real drop in recovered
value be published as dominance.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "tier2_simulation"))

from run_baselines import _paired_bootstrap_ci, run_one_policy  # noqa: E402
from run_batch import NOW, SEED, train_models  # noqa: E402

from recovery_ledger.policy.decision import (  # noqa: E402
    DoNothingPolicy,
    EVDecisionPolicy,
)
from recovery_ledger.sim.environment import generate_population  # noqa: E402
from recovery_ledger.sim.generator import generate_cases  # noqa: E402

EVAL_SEED = SEED + 2000  # deliberately the baselines batch: this curve is a
# decomposition of that table, not an independent measurement, and using a
# different population would make the two silently non-comparable.


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n-train", type=int, default=5000)
    ap.add_argument("--n-eval", type=int, default=2000)
    ap.add_argument("--lambdas", type=float, nargs="+", default=[0.0, 1.0, 2.0, 4.0, 8.0])
    ap.add_argument("--uplift", choices=["ensemble", "single"], default="single")
    args = ap.parse_args()

    uplift, churn = train_models(args.n_train, seed=SEED,
                                 ensemble=args.uplift == "ensemble")
    cases = generate_cases(args.n_eval, seed=EVAL_SEED, now=NOW)
    traits = generate_population(cases, seed=EVAL_SEED)

    base = run_one_policy("do_nothing", DoNothingPolicy(max_attempts=3),
                          cases, traits, seed=EVAL_SEED + 1)

    rows = []
    print(f"{'lambda':>7}{'incr/1000':>12}{'contacts':>10}{'dnd %':>8}{'Rs/contact':>12}")
    for lam in args.lambdas:
        policy = EVDecisionPolicy(uplift_model=uplift, churn_model=churn,
                                  lambda_churn=lam)
        r = run_one_policy(f"lambda_{lam}", policy, cases, traits, seed=EVAL_SEED + 1)
        point, lo, hi = _paired_bootstrap_ci(r["_recovered"], base["_recovered"],
                                             n_boot=2000, seed=EVAL_SEED)
        dnd = r["pct_contacts_to_do_not_disturbs"]
        row = {
            "lambda_churn": lam,
            "incremental_per_1000_cases": {"point": point * 1000,
                                           "ci_low": lo * 1000, "ci_high": hi * 1000},
            "contacts": r["contacts_sent"],
            "pct_contacts_to_do_not_disturbs": dnd,
            "incremental_rupees_per_contact": (
                (point * 1000 * args.n_eval / 1000) / r["contacts_sent"]
                if r["contacts_sent"] else None),
        }
        rows.append(row)
        print(f"{lam:>7.1f}{row['incremental_per_1000_cases']['point']:>12,.0f}"
              f"{row['contacts']:>10}{(dnd * 100 if dnd is not None else float('nan')):>7.1f}%"
              f"{(row['incremental_rupees_per_contact'] or float('nan')):>12,.0f}")

    def get(lam):
        return next(r for r in rows if r["lambda_churn"] == lam)

    # "4.0 strictly dominates 2.0" — tested, not asserted.
    #
    # Strict dominance means not worse on ANY axis. Overlapping confidence
    # intervals do not establish that: they say the difference is not resolved
    # at this sample size, which is a statement about power, not about the
    # point estimate being no worse. Recording only the CI test would let a
    # 9% drop in recovered value be published as "dominates", so both are
    # recorded and `holds` requires the stricter one.
    dominance = None
    if any(r["lambda_churn"] == 4.0 for r in rows) and any(r["lambda_churn"] == 2.0 for r in rows):
        a, b = get(4.0), get(2.0)
        va, vb = a["incremental_per_1000_cases"], b["incremental_per_1000_cases"]
        dominance = {
            "claim": "lambda_churn=4.0 strictly dominates 2.0",
            "value_point_not_worse": bool(va["point"] >= vb["point"]),
            "value_indistinguishable_at_95": bool(not (vb["ci_low"] > va["ci_high"])),
            "value_delta_per_1000": va["point"] - vb["point"],
            "fewer_contacts": bool(a["contacts"] < b["contacts"]),
            "lower_dnd_exposure": bool(
                a["pct_contacts_to_do_not_disturbs"] < b["pct_contacts_to_do_not_disturbs"]),
        }
        dominance["holds"] = bool(dominance["value_point_not_worse"]
                                  and dominance["fewer_contacts"]
                                  and dominance["lower_dnd_exposure"])
        print(f"\ndominance of 4.0 over 2.0: holds={dominance['holds']}")
        for k, v in dominance.items():
            if k not in ("claim", "holds"):
                print(f"    {k}: {v}")

    out = {"n_train": args.n_train, "n_eval": args.n_eval, "eval_seed": EVAL_SEED,
           "uplift_model": args.uplift, "dominance_4_over_2": dominance, "sweep": rows}
    (HERE / "results_lambda_sweep.json").write_text(json.dumps(out, indent=2))
    print(f"\nWrote {HERE / 'results_lambda_sweep.json'}")


if __name__ == "__main__":
    main()
