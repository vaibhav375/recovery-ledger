"""Tier 1c — does targeting beat random, on real randomised data?

B1's central argument is that *targeting* recovers more than contacting the
same number of people at random. Everything in this repository that supports
that argument is simulator output. Tier 1 proves the estimators recover known
effects on real data; Tier 1b measures a real money effect; neither tests the
policy claim itself.

Tier 1b tried, on Hillstrom's spend, and could not settle it — not because the
answer was no, but because the question was unanswerable there. Spend is
brutally heavy-tailed (0.9% of customers buy; largest purchase $499), the
difference sat 0.44 standard errors from zero, and resolving it needed roughly
421,000 held-out customers against the 32,000 that pooling every arm supplies.

Criteo is the dataset that can answer it. ~13.98M rows from real randomised
incrementality tests, a known and constant propensity of 0.85 by design, and a
binary outcome whose variance is about 700x tighter than spend's. The
constraint that stopped Hillstrom is simply absent.

WHAT THIS BUYS AND WHAT IT DOES NOT. The outcome is `visit`, not money, so this
does not produce a rupee figure. It tests the *policy claim* — that ranking by
predicted uplift and contacting the top k beats contacting k people at random —
on real randomised data rather than in a simulator. If it holds, B1's thesis
stops being simulator-only. It still says nothing about Indian payment
recovery; Criteo is ad exposure.

THE RULE, FIXED BEFORE THE RUN, AND DELIBERATELY STRICTER THAN TIER 1b's.

  Targeting is claimable only if the paired bootstrap interval on
  (targeted − matched-volume random) EXCLUDES ZERO, and all three estimators
  agree on the sign.

  Tier 1b registered sign agreement alone and that rule was too weak: three
  estimators computed from the same rows will usually agree on a sign whether
  or not the difference is real. That weakness was found on Hillstrom and the
  rule is strengthened here BEFORE seeing any Criteo result. Strengthening a
  bar before a run is legitimate; weakening one after is the thing
  pre-registration exists to prevent.

  The policy is chosen out of sample — tau_hat is fitted on one half and the
  ranking applied to the other — because Tier 1b's first draft fitted and
  ranked the same rows and reported an advantage seven to twelve times the
  honest one.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
from sklearn.ensemble import GradientBoostingClassifier

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "tier1_criteo"))

from run_validation import load_criteo  # noqa: E402

from recovery_ledger.policy.ope.estimators import (  # noqa: E402
    _match_weights,
    doubly_robust_value,
    ips_value,
    snips_value,
)
from recovery_ledger.policy.uplift.learners import TLearnerModel  # noqa: E402

SEED = 20260823
RULE = (
    "Targeting is claimable only if the paired bootstrap interval on "
    "(targeted minus matched-volume random) excludes zero AND all three "
    "estimators agree on the sign. Sign agreement alone was Tier 1b's rule and "
    "proved too weak; the bar is raised here before seeing any result."
)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sample-frac", type=float, default=0.05)
    ap.add_argument("--target-frac", type=float, default=0.30)
    ap.add_argument("--n-boot", type=int, default=1000)
    ap.add_argument("--target-col", default="visit")
    args = ap.parse_args()

    t0 = time.time()
    X, T, Y, e, _ = load_criteo(sample_frac=args.sample_frac, target_col=args.target_col)
    print(f"Criteo: {len(Y):,} rows, {T.mean():.3f} treated by design, "
          f"{args.target_col} rate {Y.mean():.4f}  ({time.time()-t0:.0f}s)")

    idx = np.arange(len(Y))
    np.random.default_rng(SEED).shuffle(idx)
    cut = len(idx) // 2
    tr, te = idx[:cut], idx[cut:]

    print(f"fitting the uplift model on {len(tr):,} rows…")
    model = TLearnerModel(random_state=SEED)
    model.fit(X[tr], T[tr], Y[tr])
    tau = model.predict_cate(X[te])

    Xe, Te, Ye, ee = X[te], T[te], Y[te], e[te]
    k = int(len(Ye) * args.target_frac)
    targeted = np.zeros(len(Ye), dtype=int)
    targeted[np.argsort(-tau)[:k]] = 1

    rng = np.random.default_rng(SEED + 1)
    random_pol = np.zeros(len(Ye), dtype=int)
    random_pol[rng.choice(len(Ye), k, replace=False)] = 1

    out_model = GradientBoostingClassifier(random_state=SEED, n_estimators=100)
    res = {}
    for name, pol in (("targeted", targeted), ("random_matched", random_pol)):
        res[name] = {
            "ips": ips_value(Ye, Te, ee, pol, n_boot=args.n_boot, seed=SEED),
            "snips": snips_value(Ye, Te, ee, pol, n_boot=args.n_boot, seed=SEED),
            "dr": doubly_robust_value(Ye, Te, Xe, ee, pol, outcome_model=out_model,
                                      n_boot=args.n_boot, seed=SEED),
        }

    print(f"\nPolicy value per user, contacting {args.target_frac:.0%} "
          f"({k:,} of {len(Ye):,} held out):")
    print(f"  {'estimator':<8}{'targeted':>12}{'random':>12}{'difference':>14}")
    diffs = {}
    for est in ("ips", "snips", "dr"):
        a, b = res["targeted"][est].point_estimate, res["random_matched"][est].point_estimate
        diffs[est] = a - b
        print(f"  {est:<8}{a:>12.5f}{b:>12.5f}{a-b:>+14.5f}")

    # the paired interval — the statistic the rule actually turns on
    prng = np.random.default_rng(SEED + 7)
    per_t = _match_weights(Te, ee, targeted) * Ye
    per_r = _match_weights(Te, ee, random_pol) * Ye
    draws = np.array([
        (lambda i: per_t[i].mean() - per_r[i].mean())(prng.integers(0, len(Ye), len(Ye)))
        for _ in range(args.n_boot)
    ])
    d_point = float(per_t.mean() - per_r.mean())
    d_lo, d_hi = (float(x) for x in np.quantile(draws, [0.025, 0.975]))
    excludes = d_lo > 0 or d_hi < 0
    se = (d_hi - d_lo) / 2 / 1.96

    signs = {np.sign(v) for v in diffs.values()}
    agree = len(signs) == 1 and 0 not in signs
    holds = excludes and agree and d_point > 0

    print(f"\n  paired difference: {d_point:+.5f} per user  "
          f"95% CI [{d_lo:+.5f}, {d_hi:+.5f}]  -> "
          f"{'EXCLUDES ZERO' if excludes else 'covers zero'}")
    print(f"  {abs(d_point)/se:.1f} standard errors from zero")

    verdict = (
        "CLAIMABLE: targeting beats matched-volume random targeting on real "
        "randomised data. The paired interval excludes zero and all three "
        "estimators agree on the sign. B1's central claim is no longer "
        "simulator-only."
        if holds else
        "REFUTED: targeting does not beat matched-volume random on this data."
        if agree and d_point < 0 and excludes else
        "NOT ESTABLISHED: the paired interval covers zero, so the difference is "
        "not distinguishable from noise even at this sample size."
    )
    print(f"\n{verdict}")

    out = {
        "dataset": "criteo uplift (real randomised incrementality tests)",
        "outcome": args.target_col,
        "note": "binary outcome, not money — this tests the POLICY claim, not an effect size",
        "n_rows": int(len(Y)),
        "n_train": int(len(tr)),
        "n_evaluated_out_of_sample": int(len(te)),
        "propensity": round(float(T.mean()), 4),
        "rule": RULE,
        "target_fraction": args.target_frac,
        "n_targeted": int(k),
        "by_estimator": {
            est: {
                "targeted": round(float(res["targeted"][est].point_estimate), 7),
                "random_matched": round(float(res["random_matched"][est].point_estimate), 7),
                "difference": round(float(diffs[est]), 7),
            } for est in ("ips", "snips", "dr")
        },
        "paired_difference": round(d_point, 7),
        "paired_ci_low": round(d_lo, 7),
        "paired_ci_high": round(d_hi, 7),
        "paired_interval_excludes_zero": bool(excludes),
        "standard_errors_from_zero": round(float(abs(d_point) / se), 2),
        "estimators_agree_on_sign": bool(agree),
        "holds": bool(holds),
        "verdict": verdict,
    }
    # Runtime is printed, never written: a wall-clock field in the artifact
    # would make it differ between identical runs, and this project claims its
    # artifacts are byte-identical across re-runs.
    print(f"\n  ran in {time.time() - t0:.0f}s")
    (HERE / "results_targeting.json").write_text(json.dumps(out, indent=2))
    print(f"\nWrote {HERE / 'results_targeting.json'}")


if __name__ == "__main__":
    main()
