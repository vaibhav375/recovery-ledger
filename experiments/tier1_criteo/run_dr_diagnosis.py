"""Is the DR estimator biased on Criteo, or just noisy?

RESULTS.md records DR recovering an ATE of +0.0067 where the RCT's own arm
means give +0.0094, and calls it "29% low" — an honest weak spot, but an
underspecified one. "29% low" is a statement about a point estimate, and a
point estimate 29% below truth is either a real bias worth fixing or a draw
from a wide sampling distribution. Those need different responses, and the
number as recorded cannot tell them apart.

The reason to suspect noise rather than bias: on this dataset the propensity
is *known and constant* (0.85, by the RCT's design), so the DR correction term
is unbiased no matter how badly the outcome model q_hat fits. A miscalibrated
q_hat inflates DR's variance; it does not move its expectation. Meanwhile 85%
treated leaves the control arm only 15% of the rows, and the control arm's
importance weight is 1/0.15 = 6.7 against the treated arm's 1/0.85 = 1.2 — so
the never-treat value is estimated from a sixth of the data at nearly six times
the weight. That is a recipe for a wide interval, not a systematic offset.

Two things are measured here that the committed artifact does not have:

1. A **paired** bootstrap CI on the implied ATE. The artifact reports separate
   intervals for the always-treat and never-treat values; differencing those
   by eye double-counts the noise they share (same rows, same fitted q_hat,
   overlapping correction terms). Resampling rows once and differencing within
   each draw gives the contrast its own honest interval.

2. **Replication across genuinely disjoint subsamples.** One subsample is one
   draw. If DR were biased, the gap would persist across draws with a
   consistent sign; if it is noise, the gap should wander and straddle zero.

   "Disjoint" is doing real work in that sentence. The first version of this
   script drew three different train/test splits of the *same* pooled sample,
   which is not replication: two 30% test sets drawn from one pool share about
   a third of their rows, so a consistent sign across them is partly an
   artifact of the shared data rather than evidence about the estimator. The
   draws here partition the pool into non-overlapping blocks instead, so no
   row informs two draws and agreement between them means something.

The outcome decides what RESULTS.md should say. If truth falls inside the
paired interval, "29% low" is the wrong description and gets replaced by a
statement about precision. If it falls outside consistently, the bias is real
and stays documented as a weak spot.

--fold-sweep: is the named mechanism (cross-fitted q_hat, starved on a 15%
minority arm) actually the cause?

PROJECT_STATE.md's Tier B once proposed "refit with stratified folds that
guarantee minority-arm balance" as the untested fix. Half of that already
existed when it was written: `dr_contributions` already stratifies its
k-fold split on the *joint* of treatment and outcome, and `q_hat` is already
one model per arm rather than a joint model with T as a feature (the
docstring on `doubly_robust_value` records that an earlier joint-model
version *was* measurably biased for exactly this reason). So "refit with
stratified folds" is not an outstanding step -- it is already what ships.

What is untested is narrower and still open: does the residual gap respond
to the cross-fitting configuration *at all*? If starving the minority arm's
fold-local training set is really the mechanism, more folds should help --
each fold then holds out a smaller slice, leaving more of the scarce control
arm available to train on. This flag sweeps n_folds in {2, 5, 10, 20} across
the same three disjoint blocks above and checks whether coverage and the gap
respond.

FOLD_SWEEP_RULE (pre-registered before running, same discipline as the
bias/noise/inconclusive rule above): "The cross-fitting hypothesis predicts
the gap shrinks as folds increase -- more folds means more training data per
fold and a better-conditioned minority arm. It is CONFIRMED if coverage rises
to 3/3 at higher fold counts. It is REFUTED if coverage and the mean gap are
essentially flat across 2 -> 20 folds, which would mean the residual gap has
some other cause and the named mechanism is not it. Anything else is
UNRESOLVED."
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from sklearn.ensemble import GradientBoostingClassifier

from recovery_ledger.policy.ope.estimators import (
    _match_weights,
    always_treat_policy,
    dr_contributions,
    never_treat_policy,
)
from run_validation import SEED, load_criteo

HERE = Path(__file__).parent

FOLD_SWEEP_RULE = (
    "The cross-fitting hypothesis predicts the gap shrinks as folds increase "
    "-- more folds means more training data per fold and a better-conditioned "
    "minority arm. It is CONFIRMED if coverage rises to 3/3 at higher fold "
    "counts. It is REFUTED if coverage and the mean gap are essentially flat "
    "across 2 -> 20 folds, which would mean the residual gap has some other "
    "cause and the named mechanism is not it. Anything else is UNRESOLVED."
)


def paired_ate(contrib_treat, contrib_ctrl, *, n_boot: int, seed: int,
               confidence: float = 0.95) -> dict:
    """CI for E[treat] - E[ctrl], resampling rows once per draw."""
    diff = contrib_treat - contrib_ctrl
    rng = np.random.default_rng(seed)
    n = len(diff)
    stats = np.array([diff[rng.integers(0, n, size=n)].mean() for _ in range(n_boot)])
    alpha = (1 - confidence) / 2
    lo, hi = np.nanquantile(stats, [alpha, 1 - alpha])
    return {"ate": float(diff.mean()), "ci_low": float(lo), "ci_high": float(hi)}


def disjoint_blocks(n: int, k: int, seed: int) -> list[np.ndarray]:
    """Partition row indices into k non-overlapping evaluation samples."""
    idx = np.arange(n)
    np.random.default_rng(seed).shuffle(idx)
    return [np.sort(b) for b in np.array_split(idx, k)]


def dr_for_folds(Xt, Tt, Yt, pt, treat, ctrl, *, n_folds: int, n_boot: int) -> dict:
    """The paired DR contrast at a given cross-fitting fold count.

    Split out of `one_draw` so `--fold-sweep` can vary n_folds without
    recomputing the direct ATE and IPS, neither of which depends on n_folds
    at all -- the only thing that changes with n_folds is what
    `dr_contributions` does internally.
    """
    model = GradientBoostingClassifier(random_state=SEED, n_estimators=80)
    return paired_ate(
        dr_contributions(Yt, Tt, Xt, pt, treat, outcome_model=model, n_folds=n_folds, seed=SEED),
        dr_contributions(Yt, Tt, Xt, pt, ctrl, outcome_model=model, n_folds=n_folds, seed=SEED),
        n_boot=n_boot, seed=SEED,
    )


def one_draw(X, T, Y, prop, block, *, seed: int, n_boot: int, n_folds: int = 5) -> dict:
    Xt, Tt, Yt, pt = X[block], T[block], Y[block], prop[block]
    n = len(Yt)
    treat, ctrl = always_treat_policy(n), never_treat_policy(n)

    direct = float(Yt[Tt == 1].mean() - Yt[Tt == 0].mean())

    dr = dr_for_folds(Xt, Tt, Yt, pt, treat, ctrl, n_folds=n_folds, n_boot=n_boot)
    ips = paired_ate(
        _match_weights(Tt, pt, treat) * Yt,
        _match_weights(Tt, pt, ctrl) * Yt,
        n_boot=n_boot, seed=SEED,
    )
    for name, est in (("dr", dr), ("ips", ips)):
        est["covers_direct"] = bool(est["ci_low"] <= direct <= est["ci_high"])
        est["gap_to_direct"] = est["ate"] - direct
        est["name"] = name
    return {"seed": seed, "n_test": n, "n_folds": n_folds, "direct_ate": direct, "dr": dr, "ips": ips}


def fold_sweep(X, T, Y, prop, blocks, fold_counts: list[int], *, n_boot: int) -> list[dict]:
    """Re-run the DR diagnosis at each n_folds in `fold_counts`, on the same
    three disjoint blocks, holding everything else (sample, seeds, n_boot,
    model) fixed. Direct ATE and IPS are computed once per block and reused
    across the sweep since neither depends on n_folds; only the cross-fitted
    q_hat inside `dr_contributions` does.
    """
    block_ctx = []
    for d, block in enumerate(blocks):
        seed = SEED + 500 * d
        Xt, Tt, Yt, pt = X[block], T[block], Y[block], prop[block]
        n = len(Yt)
        treat, ctrl = always_treat_policy(n), never_treat_policy(n)
        direct = float(Yt[Tt == 1].mean() - Yt[Tt == 0].mean())
        ips = paired_ate(
            _match_weights(Tt, pt, treat) * Yt,
            _match_weights(Tt, pt, ctrl) * Yt,
            n_boot=n_boot, seed=SEED,
        )
        ips["covers_direct"] = bool(ips["ci_low"] <= direct <= ips["ci_high"])
        ips["gap_to_direct"] = ips["ate"] - direct
        ips["name"] = "ips"
        block_ctx.append({
            "seed": seed, "n": n, "Xt": Xt, "Tt": Tt, "Yt": Yt, "pt": pt,
            "treat": treat, "ctrl": ctrl, "direct": direct, "ips": ips,
        })

    rows = []
    for n_folds in fold_counts:
        per_draw = []
        for ctx in block_ctx:
            dr = dr_for_folds(
                ctx["Xt"], ctx["Tt"], ctx["Yt"], ctx["pt"], ctx["treat"], ctx["ctrl"],
                n_folds=n_folds, n_boot=n_boot,
            )
            dr["covers_direct"] = bool(dr["ci_low"] <= ctx["direct"] <= dr["ci_high"])
            dr["gap_to_direct"] = dr["ate"] - ctx["direct"]
            dr["name"] = "dr"
            per_draw.append({
                "seed": ctx["seed"], "n_test": ctx["n"], "n_folds": n_folds,
                "direct_ate": ctx["direct"], "dr": dr, "ips": ctx["ips"],
            })
        gaps = [d["dr"]["gap_to_direct"] for d in per_draw]
        rows.append({
            "n_folds": n_folds,
            "coverage": sum(d["dr"]["covers_direct"] for d in per_draw),
            "n_draws": len(per_draw),
            "mean_gap": float(np.mean(gaps)),
            "mean_abs_gap": float(np.mean(np.abs(gaps))),
            "per_draw": per_draw,
        })
    return rows


def fold_sweep_verdict(rows: list[dict]) -> str:
    """Apply FOLD_SWEEP_RULE to the sweep's two extremes (lowest and highest
    n_folds), fixed here before the sweep is run so the same rule always
    yields the same verdict for the same numbers -- no eyeballing a curve
    after seeing it.

    CONFIRMED  coverage at the highest fold count is a clean 3/3, and that is
               a rise from the lowest fold count (the monotone pattern
               cross-fitting predicts).
    REFUTED    coverage is identical at both extremes, and the mean absolute
               gap at the highest fold count has not shrunk by more than 20%
               relative to the lowest -- "essentially flat" operationalised
               as a threshold fixed before the run, not tuned after it.
    UNRESOLVED anything else.
    """
    lo, hi = rows[0], rows[-1]
    n_draws = lo["n_draws"]
    if hi["coverage"] == n_draws and hi["coverage"] > lo["coverage"]:
        return "CONFIRMED"
    if (hi["coverage"] == lo["coverage"] and lo["mean_abs_gap"] > 0
            and abs(hi["mean_abs_gap"] - lo["mean_abs_gap"]) < 0.2 * lo["mean_abs_gap"]):
        return "REFUTED"
    return "UNRESOLVED"


def run_fold_sweep(X, T, Y, prop, blocks, args) -> None:
    fold_counts = [int(x) for x in args.fold_counts.split(",")]
    rows = fold_sweep(X, T, Y, prop, blocks, fold_counts, n_boot=args.n_boot)

    print(f"{'n_folds':>8}{'coverage':>10}{'mean gap':>12}{'mean |gap|':>12}")
    for r in rows:
        print("%8d%7d/%d%12.5f%12.5f" % (
            r["n_folds"], r["coverage"], r["n_draws"], r["mean_gap"], r["mean_abs_gap"]))

    verdict = fold_sweep_verdict(rows)
    print(f"\nrule: {FOLD_SWEEP_RULE}")
    print(f"\nfold-sweep verdict: {verdict}")

    out = {
        "sample_frac": args.sample_frac, "n_boot": args.n_boot, "draws": args.draws,
        "disjoint_blocks": True, "fold_counts": fold_counts,
        "rule": FOLD_SWEEP_RULE, "verdict": verdict, "rows": rows,
    }
    path = HERE / "results_dr_foldsweep.json"
    path.write_text(json.dumps(out, indent=2))
    print(f"Wrote {path}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sample-frac", type=float, default=0.02)
    ap.add_argument("--n-boot", type=int, default=500)
    ap.add_argument("--draws", type=int, default=3,
                    help="independent train/test splits; one draw is not a result")
    ap.add_argument("--fold-sweep", action="store_true",
                    help="sweep dr_contributions' n_folds (see --fold-counts) across the "
                         "same disjoint blocks instead of running the single-n_folds "
                         "diagnosis; tests whether the cross-fitting mechanism named in "
                         "PROJECT_STATE.md responds to the fold count at all")
    ap.add_argument("--fold-counts", type=str, default="2,5,10,20",
                    help="comma-separated n_folds values for --fold-sweep")
    args = ap.parse_args()

    X, T, Y, prop, _ = load_criteo(args.sample_frac, "visit")
    print(f"criteo n={len(Y)} treated={T.mean():.3f} base_rate={Y.mean():.4f}\n")

    blocks = disjoint_blocks(len(Y), args.draws, SEED)
    assert sum(len(b) for b in blocks) == len(Y)
    assert len(set().union(*(set(b.tolist()) for b in blocks))) == len(Y), "blocks overlap"

    if args.fold_sweep:
        run_fold_sweep(X, T, Y, prop, blocks, args)
        return

    draws = [one_draw(X, T, Y, prop, b, seed=SEED + 500 * d, n_boot=args.n_boot)
             for d, b in enumerate(blocks)]

    print(f"{'draw':>5}{'direct':>10}{'DR ate':>10}{'DR 95% CI':>24}{'covers':>8}{'gap':>10}")
    for d in draws:
        e = d["dr"]
        ci = "[%+.5f, %+.5f]" % (e["ci_low"], e["ci_high"])
        print("%5d%+10.5f%+10.5f%24s%8s%+10.5f" % (
            d["seed"], d["direct_ate"], e["ate"], ci,
            "yes" if e["covers_direct"] else "NO", e["gap_to_direct"]))

    dr_cov = sum(d["dr"]["covers_direct"] for d in draws)
    ips_cov = sum(d["ips"]["covers_direct"] for d in draws)
    gaps = [d["dr"]["gap_to_direct"] for d in draws]
    same_sign = all(g < 0 for g in gaps) or all(g > 0 for g in gaps)
    widths = [d["dr"]["ci_high"] - d["dr"]["ci_low"] for d in draws]
    ips_widths = [d["ips"]["ci_high"] - d["ips"]["ci_low"] for d in draws]

    print(f"\nDR  covers the direct ATE in {dr_cov}/{len(draws)} draws")
    print(f"IPS covers the direct ATE in {ips_cov}/{len(draws)} draws")
    print(f"DR gap sign consistent across draws: {same_sign}  (gaps {[round(g,5) for g in gaps]})")
    print(f"mean CI width  DR {np.mean(widths):.5f}  vs  IPS {np.mean(ips_widths):.5f} "
          f"({np.mean(widths)/np.mean(ips_widths):.2f}x)")
    # A bias claim needs both: the interval missing truth, and missing it the
    # same way every time. Either one alone is consistent with noise.
    verdict = ("bias" if dr_cov == 0 and same_sign
               else "noise" if dr_cov == len(draws)
               else "inconclusive")
    print(f"\nverdict: {verdict}")

    out = {
        "sample_frac": args.sample_frac, "n_boot": args.n_boot, "draws": args.draws, "disjoint_blocks": True,
        "dr_draws_covering_direct": dr_cov, "ips_draws_covering_direct": ips_cov,
        "dr_gap_sign_consistent": same_sign,
        "dr_mean_ci_width": float(np.mean(widths)),
        "ips_mean_ci_width": float(np.mean(ips_widths)),
        "verdict": verdict,
        "per_draw": draws,
    }
    (HERE / "results_dr_diagnosis.json").write_text(json.dumps(out, indent=2))
    print(f"Wrote {HERE / 'results_dr_diagnosis.json'}")


if __name__ == "__main__":
    main()
