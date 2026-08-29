"""Uplift by decile, and whether tau_hat is on the right scale.

The spec's evaluation protocol (sections 8.1 and 11.2) asks for an
uplift-by-decile chart, and it is the one required artifact this repo did not
have. Everything else about the CATE model has been reported through a single
number — correlation 0.347 with the simulator's hidden persuadability trait —
which is a diagnostic no deployment could ever compute, because nothing in
production knows the trait.

This computes the version a deployment *can* compute. Rank a fresh, randomised
population by predicted uplift, cut it into deciles, and inside each decile
take the contrast between the contacted rows and the not-contacted rows. The
assignment is a coin flip, so each decile's contrast is a treatment effect,
and the chart answers a question the correlation cannot: does the ordering the
policy acts on correspond to an ordering in realised behaviour?

Two distinct claims come out of it, and they are not the same claim:

  RANKING     the top decile realises more uplift than the bottom decile.
  CALIBRATION the predicted magnitudes are on the scale of the realised ones.

The second matters more here than the ranking does, and this is the reason the
experiment is worth running rather than assuming. `LookaheadEVDecisionPolicy`
does not rank cases and take the top k. It contacts when `tau_hat * amount`
clears the cost of a message — a threshold on a product. A model can rank
perfectly and still put that threshold in the wrong place if its magnitudes are
inflated or shrunk, and the decile chart is where that shows up as a slope
away from 1.0. It is also the mechanism already suspected in
`experiments/uplift_ab`, where a better-correlated ensemble did not recover
more money.

DELIBERATELY NOT THE POLICY. The evaluation population here is assigned
contact at random, not by the agent. Running the deployed policy instead would
confound the picture beyond repair: the policy declines to contact the low
deciles, so their realised uplift would be near zero *because nobody was
contacted*, and the chart would come out monotone for a model that predicts
nothing. This measures the model. `make eval` measures the policy.

THE RULE, FIXED BEFORE THE RUN. Every claim below is a claim about a
population, so it must replicate across independent draws or it is not
claimable (this repo has now watched five single-draw findings evaporate).

  - RANKING holds only if `top_minus_bottom > 0` in *every* draw.
  - MONOTONE holds only if Spearman >= 0.9 in *every* draw. Near-monotone is
    reported separately at >= 0.7, and is a weaker statement.
  - CALIBRATION is reported, not judged: the slope is whatever it is, and a
    slope away from 1.0 is a finding about the shipped model, not a bug to
    tune away. No threshold is set for it precisely because setting one after
    seeing the number would make it unfalsifiable.

Whatever comes out goes into RESULTS.md as it stands.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from sklift.metrics import qini_auc_score, uplift_auc_score

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "tier2_simulation"))

from run_batch import NOW, SEED, train_uplift_model  # noqa: E402

from recovery_ledger.events.actions import ActionType  # noqa: E402
from recovery_ledger.policy.features import cases_to_feature_matrix  # noqa: E402
from recovery_ledger.policy.uplift.calibration import uplift_by_decile  # noqa: E402
from recovery_ledger.sim.environment import (  # noqa: E402
    SimulationEnvironment,
    generate_population,
    persuadability,
)
from recovery_ledger.sim.generator import generate_cases  # noqa: E402

EVAL_SEED = SEED + 11000  # disjoint; see tests/test_experiment_seeds.py

RANKING_HOLDS_IF = "top decile realises more uplift than bottom decile in every draw"
MONOTONE_SPEARMAN = 0.9
NEAR_MONOTONE_SPEARMAN = 0.7


def randomised_population(n: int, seed: int):
    """A fresh mini-RCT: fresh cases, a coin-flip contact assignment, one
    nudge, and the payment outcome. Same construction as the training phase of
    `make eval`, on a population disjoint from every other experiment's."""
    cases = generate_cases(n, seed=seed, now=NOW)
    traits = generate_population(cases, seed=seed)
    env = SimulationEnvironment(traits, seed=seed)

    rng = np.random.default_rng(seed)
    treatment = rng.integers(0, 2, size=n)
    paid = np.array([
        float(env.step(c, ActionType.NUDGE if treatment[i] else ActionType.WAIT, 0).paid)
        for i, c in enumerate(cases)
    ])
    tau_true = np.array([persuadability(traits[c.case_id]) for c in cases])
    return cases_to_feature_matrix(cases), treatment, paid, tau_true


def one_draw(model, n_eval: int, seed: int, *, n_bins: int, n_boot: int) -> dict:
    X, treatment, paid, tau_true = randomised_population(n_eval, seed)
    tau_hat = model.predict_cate(X)

    cal = uplift_by_decile(
        tau_hat, treatment, paid, n_bins=n_bins, n_boot=n_boot, seed=seed
    )

    return {
        "seed": seed,
        "n": int(n_eval),
        "deciles": [
            {
                "decile": b.index + 1,
                "n": b.n,
                "n_treated": b.n_treated,
                "n_control": b.n_control,
                "mean_predicted_uplift": round(b.mean_predicted_uplift, 5),
                "realised_uplift": None if b.realised_uplift is None else round(b.realised_uplift, 5),
                "ci_low": None if b.ci_low is None else round(b.ci_low, 5),
                "ci_high": None if b.ci_high is None else round(b.ci_high, 5),
                "contacted_payment_rate": round(b.treated_outcome_rate, 5),
                "not_contacted_payment_rate": round(b.control_outcome_rate, 5),
                # Simulator-only, like the 0.347 correlation: the hidden trait
                # nothing in production can see. Here to answer the one
                # question the decile chart raises and cannot settle on its
                # own — whether the deciles the model calls negative are
                # actually where the do-not-disturbs are (claim N2).
                "true_do_not_disturb_share": round(float((tau_true[b.row_indices] < 0).mean()), 4),
                "mean_true_persuadability": round(float(tau_true[b.row_indices].mean()), 5),
            }
            for b in cal.bins
        ],
        "spearman_rank_correlation": round(cal.spearman, 4),
        "top_minus_bottom_decile_uplift": round(cal.top_minus_bottom, 5),
        "calibration_slope": round(cal.calibration_slope, 4),
        "calibration_intercept": round(cal.calibration_intercept, 5),
        "mean_predicted_uplift": round(cal.overall_predicted, 5),
        "realised_average_uplift": round(cal.overall_realised, 5),
        "bins_undefined": cal.n_bins_undefined,
        # Cross-references to numbers the documents already quote, so this
        # population can be compared to the ones they came from.
        "qini_coefficient": round(float(qini_auc_score(paid, tau_hat, treatment)), 5),
        "auuc": round(float(uplift_auc_score(paid, tau_hat, treatment)), 5),
        "correlation_with_true_persuadability": round(float(np.corrcoef(tau_hat, tau_true)[0, 1]), 4),
        "population_true_do_not_disturb_share": round(float((tau_true < 0).mean()), 4),
    }


def plot(draws: list[dict], n_bins: int) -> Path:
    """Realised uplift per predicted-uplift decile, one line per draw plus the
    mean, with the model's own predictions overlaid. The gap between the bars
    and the dashed line IS the calibration error — drawn on the same axis
    rather than in a separate panel, because the two being on the same scale is
    the entire question."""
    x = np.arange(1, n_bins + 1)
    realised = np.array([[d["realised_uplift"] for d in dr["deciles"]] for dr in draws])
    predicted = np.array([[d["mean_predicted_uplift"] for d in dr["deciles"]] for dr in draws])

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(x, realised.mean(axis=0), color="#2b6cb0", alpha=0.85,
           label=f"realised uplift (mean of {len(draws)} draws)")
    for i, row in enumerate(realised):
        ax.plot(x, row, color="#1a365d", alpha=0.5, linewidth=1, marker="o", markersize=3,
                label="individual draws" if i == 0 else None)
    ax.plot(x, predicted.mean(axis=0), "k--", marker="s", markersize=4,
            label="predicted uplift (tau_hat)")
    ax.axhline(0, color="#444", linewidth=0.8)
    ax.set_xticks(x)
    ax.set_xlabel("Predicted-uplift decile (1 = lowest predicted)")
    ax.set_ylabel("Change in payment probability from one contact")
    ax.set_title("Uplift by decile — shipped T-learner, randomised holdout")
    ax.legend(fontsize=8)
    fig.tight_layout()
    out = HERE / "uplift_by_decile.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n-train", type=int, default=5000)
    ap.add_argument("--n-eval", type=int, default=4000)
    ap.add_argument("--eval-draws", type=int, default=3)
    ap.add_argument("--n-bins", type=int, default=10)
    ap.add_argument("--n-boot", type=int, default=2000)
    args = ap.parse_args()

    print(f"Training the shipped single T-learner on {args.n_train} randomised-contact cases...")
    model = train_uplift_model(args.n_train, seed=SEED, ensemble=False)

    draws = []
    for d in range(args.eval_draws):
        seed = EVAL_SEED + 100 * d
        print(f"\nDraw {d + 1}/{args.eval_draws}  (seed {seed}, n={args.n_eval})")
        res = one_draw(model, args.n_eval, seed, n_bins=args.n_bins, n_boot=args.n_boot)
        draws.append(res)

        print(f"  {'decile':>6}  {'predicted':>10}  {'realised':>10}  {'95% CI':>20}")
        for row in res["deciles"]:
            ci = f"[{row['ci_low']:+.4f}, {row['ci_high']:+.4f}]"
            print(f"  {row['decile']:>6}  {row['mean_predicted_uplift']:>+10.4f}  "
                  f"{row['realised_uplift']:>+10.4f}  {ci:>20}")
        print(f"  spearman {res['spearman_rank_correlation']:+.3f}   "
              f"top-bottom {res['top_minus_bottom_decile_uplift']:+.4f}   "
              f"slope {res['calibration_slope']:.3f}   "
              f"qini {res['qini_coefficient']:+.4f}")

    bottoms = [d["deciles"][0] for d in draws]
    tops = [d["top_minus_bottom_decile_uplift"] for d in draws]
    spearmans = [d["spearman_rank_correlation"] for d in draws]
    slopes = [d["calibration_slope"] for d in draws]

    ranking_holds = all(t > 0 for t in tops)
    monotone = all(s >= MONOTONE_SPEARMAN for s in spearmans)
    near_monotone = all(s >= NEAR_MONOTONE_SPEARMAN for s in spearmans)

    verdict = {
        "ranking_claim": RANKING_HOLDS_IF,
        "ranking_holds": bool(ranking_holds),
        "monotone_all_draws": bool(monotone),
        "near_monotone_all_draws": bool(near_monotone),
        "monotone_threshold": MONOTONE_SPEARMAN,
        "near_monotone_threshold": NEAR_MONOTONE_SPEARMAN,
        "spearman_by_draw": spearmans,
        "top_minus_bottom_by_draw": tops,
        "calibration_slope_by_draw": slopes,
        "mean_spearman": round(float(np.mean(spearmans)), 4),
        "mean_top_minus_bottom": round(float(np.mean(tops)), 5),
        "mean_calibration_slope": round(float(np.mean(slopes)), 4),
        "mean_predicted_uplift": round(float(np.mean([d["mean_predicted_uplift"] for d in draws])), 5),
        "mean_realised_uplift": round(float(np.mean([d["realised_average_uplift"] for d in draws])), 5),
        "mean_qini": round(float(np.mean([d["qini_coefficient"] for d in draws])), 5),
        "mean_correlation_with_true_persuadability": round(
            float(np.mean([d["correlation_with_true_persuadability"] for d in draws])), 4),
        # The bottom decile is the one the policy declines to contact, so what
        # it actually contains is the decile chart's load-bearing cell.
        "bottom_decile_predicted_uplift": round(float(np.mean([b["mean_predicted_uplift"] for b in bottoms])), 5),
        "bottom_decile_realised_uplift": round(float(np.mean([b["realised_uplift"] for b in bottoms])), 5),
        "bottom_decile_realised_negative_in_every_draw": bool(all(b["realised_uplift"] < 0 for b in bottoms)),
        "bottom_decile_ci_excludes_zero_in_every_draw": bool(all(b["ci_high"] < 0 for b in bottoms)),
        "bottom_decile_true_dnd_share": round(float(np.mean([b["true_do_not_disturb_share"] for b in bottoms])), 4),
        "top_decile_true_dnd_share": round(float(np.mean([d["deciles"][-1]["true_do_not_disturb_share"] for d in draws])), 4),
        "population_true_dnd_share": round(float(np.mean([d["population_true_do_not_disturb_share"] for d in draws])), 4),
    }

    print("\n" + "=" * 72)
    print(f"RANKING   top decile beats bottom in every draw: "
          f"{'YES' if ranking_holds else 'NO'}  ({[f'{t:+.4f}' for t in tops]})")
    print(f"MONOTONE  spearman >= {MONOTONE_SPEARMAN} in every draw: "
          f"{'YES' if monotone else 'NO'}  ({[f'{s:+.3f}' for s in spearmans]})")
    print(f"          near-monotone (>= {NEAR_MONOTONE_SPEARMAN}): {'YES' if near_monotone else 'NO'}")
    print(f"CALIBRATION  slope {verdict['mean_calibration_slope']:.3f}  "
          f"(1.0 = predictions on the realised scale)")
    print(f"          predicted mean {verdict['mean_predicted_uplift']:+.4f}  vs  "
          f"realised mean {verdict['mean_realised_uplift']:+.4f}")
    print(f"BOTTOM DECILE  predicted {verdict['bottom_decile_predicted_uplift']:+.4f}  "
          f"realised {verdict['bottom_decile_realised_uplift']:+.4f}  "
          f"(negative in every draw: {'YES' if verdict['bottom_decile_realised_negative_in_every_draw'] else 'NO'})")
    print(f"          true do-not-disturbs: {verdict['bottom_decile_true_dnd_share'] * 100:.1f}% of the bottom "
          f"decile vs {verdict['population_true_dnd_share'] * 100:.1f}% of the population "
          f"and {verdict['top_decile_true_dnd_share'] * 100:.1f}% of the top")

    out = {
        "n_train": args.n_train,
        "n_eval": args.n_eval,
        "eval_draws": args.eval_draws,
        "n_bins": args.n_bins,
        "uplift_model": "single",
        "base_eval_seed": EVAL_SEED,
        "verdict": verdict,
        "draws": draws,
    }
    (HERE / "results_uplift_calibration.json").write_text(json.dumps(out, indent=2))
    png = plot(draws, args.n_bins)
    print(f"\nWrote {HERE / 'results_uplift_calibration.json'} and {png}")


if __name__ == "__main__":
    main()
