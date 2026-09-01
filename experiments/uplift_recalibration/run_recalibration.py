"""Does correcting tau_hat's over-spread recover more money?

`make calibration` measured the defect rather than inferring it: the shipped
T-learner's predictions are spread about a third wider than the effects they
predict, calibration slope 0.758 across three draws, tau_hat ranging -0.064 to
+0.285 where the truth ranges +0.041 to +0.206. The ranking is real; the
magnitudes are not.

That matters because the policy does not rank and take the top k. It contacts
when `tau_hat * amount` clears the cost of a message — a threshold on a
*product* — so an over-spread tau_hat mis-places that threshold in both
directions even with the ranking intact. It is also the mechanism
`experiments/uplift_ab` suspected when a better-correlated ensemble recovered
no more money.

So the obvious move is to shrink the predictions back onto the scale of the
effects and see whether the money follows. This is that experiment.

THE CORRECTION. A linear recalibration fitted on a CALIBRATION SPLIT the model
was not trained on: bin the split by predicted uplift, regress realised uplift
on mean predicted uplift across bins, and apply the resulting intercept and
slope to tau_hat. One parameter pair, targeting the measured defect directly.
Fitting it on the training data would be circular, and fitting it on the
evaluation population would be leakage, so it gets its own disjoint split.

THE RULE, FIXED BEFORE THE RUN.

  Recalibration is claimable only if it increases incremental recovery and
  EVERY draw agrees on the sign. This project has watched six single-draw
  findings evaporate; a mean improvement across draws that disagree in sign is
  reported as UNDETERMINED, not as a win.

  The slope moving toward 1.0 is NOT the result. It is near-certain by
  construction — the correction is fitted to do exactly that — and reporting it
  as a success would be reporting that arithmetic works. The result is whether
  the money follows.

  A refutation is a real outcome. `uplift_ab` already established that a model
  can be better as a predictor and worse as a decision rule, and this may be
  another instance.
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
from recovery_ledger.policy.features import cases_to_feature_matrix  # noqa: E402
from recovery_ledger.policy.uplift.calibration import uplift_by_decile  # noqa: E402
from recovery_ledger.sim.environment import (  # noqa: E402
    SimulationEnvironment,
    generate_population,
)
from recovery_ledger.sim.generator import generate_cases  # noqa: E402

EVAL_SEED = SEED + 16000        # disjoint; see tests/test_experiment_seeds.py
CALIBRATION_SEED = SEED + 17000  # the split the correction is fitted on

RULE = (
    "Recalibration is claimable only if it increases incremental recovery and "
    "every draw agrees on the sign. A mean improvement across draws that "
    "disagree in sign is UNDETERMINED. The slope moving toward 1.0 is not the "
    "result — the correction is fitted to do that — the money is."
)


class Recalibrated:
    """The shipped model with its magnitudes corrected. Ranking is untouched:
    a positive slope is monotone, so every ordering the policy would have made
    on tau_hat it still makes. Only the scale changes, which is the only thing
    the diagnosis said was wrong."""

    def __init__(self, base, intercept: float, slope: float):
        self.base, self.intercept, self.slope = base, intercept, slope

    def predict_cate(self, X):
        return self.intercept + self.slope * np.asarray(self.base.predict_cate(X))


def fit_correction(model, *, n: int, seed: int, n_bins: int = 10):
    """Regress realised uplift on predicted uplift over a disjoint randomised
    split, and return the (intercept, slope) that maps one onto the other."""
    cases = generate_cases(n, seed=seed, now=NOW)
    traits = generate_population(cases, seed=seed)
    env = SimulationEnvironment(traits, seed=seed)
    rng = np.random.default_rng(seed)
    T = rng.integers(0, 2, size=n)
    paid = np.array([
        float(env.step(c, ActionType.NUDGE if T[i] else ActionType.WAIT, 0).paid)
        for i, c in enumerate(cases)
    ])
    tau = model.predict_cate(cases_to_feature_matrix(cases))
    cal = uplift_by_decile(tau, T, paid, n_bins=n_bins, n_boot=0, seed=seed)
    # invert the calibration line: realised ~= a + b*predicted, so the
    # corrected prediction is that fitted value.
    return float(cal.calibration_intercept), float(cal.calibration_slope), cal


def slope_of(model, *, n: int, seed: int) -> float:
    _i, s, _c = fit_correction(model, n=n, seed=seed)
    return s


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n-train", type=int, default=5000)
    ap.add_argument("--n-calib", type=int, default=4000)
    ap.add_argument("--n-eval", type=int, default=2000)
    ap.add_argument("--eval-draws", type=int, default=3)
    args = ap.parse_args()

    print(f"Training the shipped single T-learner on {args.n_train} cases…")
    base, churn = train_models(args.n_train, seed=SEED, ensemble=False)

    intercept, slope, _ = fit_correction(base, n=args.n_calib, seed=CALIBRATION_SEED)
    fixed = Recalibrated(base, intercept, slope)
    print(f"correction fitted on {args.n_calib} disjoint cases: "
          f"tau' = {intercept:+.4f} + {slope:.4f} * tau")

    # Did it do what it was fitted to do? Checked on a THIRD population, so
    # this is not the calibration split marking its own homework.
    before = slope_of(base, n=args.n_calib, seed=CALIBRATION_SEED + 500)
    after = slope_of(fixed, n=args.n_calib, seed=CALIBRATION_SEED + 500)
    print(f"calibration slope on a held-out population: {before:.3f} -> {after:.3f} "
          f"(1.0 is perfect; this is arithmetic, not the result)")

    rows = []
    for d in range(args.eval_draws):
        seed = EVAL_SEED + 100 * d
        row = {"eval_seed": seed}
        for name, model in (("shipped", base), ("recalibrated", fixed)):
            res, _ = run_eval(args.n_eval, model, seed=seed, churn_model=churn)
            row[name] = {
                "incremental_per_1000_cases": res["incremental_per_1000_cases"]["point"],
                "contacts": res.get("contacts_sent"),
                "pct_to_do_not_disturbs": res.get("pct_contacts_to_do_not_disturbs"),
            }
        row["value_delta"] = (row["recalibrated"]["incremental_per_1000_cases"]
                              - row["shipped"]["incremental_per_1000_cases"])
        rows.append(row)
        print(f"  draw {seed}: shipped Rs {row['shipped']['incremental_per_1000_cases']:>9,.0f}   "
              f"recalibrated Rs {row['recalibrated']['incremental_per_1000_cases']:>9,.0f}   "
              f"delta {row['value_delta']:>+9,.0f}")

    deltas = [r["value_delta"] for r in rows]
    all_up = all(x > 0 for x in deltas)
    all_down = all(x < 0 for x in deltas)
    verdict = (
        "CLAIMABLE: recalibration increases incremental recovery and every draw "
        "agrees on the sign."
        if all_up else
        "REFUTED: recalibration reduces incremental recovery in every draw. "
        "Correcting the magnitudes does not pay — the same lesson uplift_ab "
        "found from the other direction."
        if all_down else
        "UNDETERMINED: the draws disagree on the sign, so no effect on recovered "
        "value is established. The correction is not shipped on this evidence."
    )
    print(f"\nmean delta Rs {np.mean(deltas):+,.0f} over {len(deltas)} draws  "
          f"({[f'{d:+,.0f}' for d in deltas]})")
    print(verdict)

    out = {
        "rule": RULE,
        "n_train": args.n_train, "n_calib": args.n_calib,
        "n_eval": args.n_eval, "eval_draws": args.eval_draws,
        "calibration_seed": CALIBRATION_SEED, "base_eval_seed": EVAL_SEED,
        "correction": {"intercept": round(intercept, 6), "slope": round(slope, 6)},
        "slope_on_heldout_population": {
            "before": round(before, 4), "after": round(after, 4),
            "note": "the correction was fitted to move this; it is not the result",
        },
        "draws": rows,
        "value_deltas": [round(x, 2) for x in deltas],
        "mean_value_delta": round(float(np.mean(deltas)), 2),
        "every_draw_agrees": bool(all_up or all_down),
        "holds": bool(all_up),
        "verdict": verdict,
    }
    (HERE / "results_recalibration.json").write_text(json.dumps(out, indent=2))
    print(f"\nWrote {HERE / 'results_recalibration.json'}")


if __name__ == "__main__":
    main()
