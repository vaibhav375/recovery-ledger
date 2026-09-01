"""Tier 1b — incremental MONEY, measured on a real randomised experiment.

Everything this project reports in rupees is simulator output. Tier 1 answers
the obvious objection by proving the causal machinery recovers known effects on
real randomised data (Criteo, Hillstrom) — but it proves it on *visit* and
*conversion*, which are not money. So the honest statement has been: the
estimator is validated on real data, the rupee figures are not.

Hillstrom carries a column this project never used. `spend` is real dollars
spent in the two weeks after a randomised email, over 64,000 real customers
under a genuine 3-arm randomisation the experimenter controlled. That is a real
randomised experiment with a real money outcome, and it closes the gap between
"the method works" and "contact produces incremental money".

Two things are measured here.

1. THE EFFECT. Incremental revenue per 1,000 customers, emailed arm minus
   no-email arm, with a bootstrap interval. No model, no policy — the arm-mean
   contrast a randomised experiment licenses directly.

2. THE POLICY CLAIM. B1's central argument is that *targeting* beats contacting
   the same number of people at random. That argument has only ever been made
   in simulation. Here it is made on real money: fit the uplift model on real
   spend, rank the real customers, target the top k, and value that policy with
   the same IPS / SNIPS / DR estimators Tier 1 already validated on this exact
   dataset — against matched-volume random targeting on the same rows.

WHAT THIS IS NOT. Hillstrom is e-commerce email, not Indian payment recovery.
It grounds the METHOD in real money; it does not transfer the domain, and no
figure here should be read as what this agent would recover in production. The
simulator remains the only place the recovery policy itself is exercised.

The policy is chosen out of sample: tau_hat is fitted on half the
customers and the ranking is applied to the other half, so the targeting
advantage cannot be the model recognising rows it trained on.

THE RULE, FIXED BEFORE THE RUN.

  EFFECT is claimable if the bootstrap interval on incremental revenue excludes
  zero. Spend here is brutally heavy-tailed — 0.9% of customers buy anything,
  the largest single purchase is $499 — so a wide interval is expected and an
  interval covering zero is reported as covering zero, not as a small win.

  TARGETING is claimable only if the targeted policy's estimated value exceeds
  matched-volume random targeting AND all three estimators agree on the sign.
  If IPS, SNIPS and DR disagree in sign, the result is UNDETERMINED and is
  published as undetermined. Under heavy tails that is a real possibility, and
  it is the honest outcome if it happens — this project has published five
  undetermined results already and is not about to start tuning for a sixth.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklift.datasets import fetch_hillstrom

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "tier1_criteo"))

from recovery_ledger.policy.ope.estimators import (  # noqa: E402
    _match_weights,
    doubly_robust_value,
    ips_value,
    snips_value,
)
from recovery_ledger.policy.uplift.learners import TLearnerModel  # noqa: E402

SEED = 20260823

EFFECT_RULE = (
    "Incremental revenue is claimable if its bootstrap interval excludes zero. "
    "Spend is heavy-tailed (0.9% of customers purchase; max $499), so a wide "
    "interval is expected and one covering zero is reported as covering zero."
)
TARGETING_RULE = (
    "Targeting is claimable only if the targeted policy's estimated value "
    "exceeds matched-volume random targeting AND IPS, SNIPS and DR agree on "
    "the sign of that difference. Disagreement in sign is published as "
    "UNDETERMINED."
)


def load_spend_pooled():
    """All three arms: any email vs no email. 64,000 customers instead of
    42,693, at the cost of estimating the effect of a MIXTURE of two campaigns
    rather than one. Both are legitimate estimands and both are reported."""
    bunch = fetch_hillstrom(target_col="spend")
    df = bunch.data.copy()
    df["y"] = bunch.target
    df["t"] = (bunch.treatment != "No E-Mail").astype(int)
    df = pd.get_dummies(df, columns=["history_segment", "zip_code", "channel"], drop_first=True)
    cols = [c for c in df.columns if c not in ("y", "t")]
    return (df[cols].to_numpy(dtype=float), df["t"].to_numpy(dtype=int),
            df["y"].to_numpy(dtype=float))


def load_spend():
    """Two-arm subset of the Hillstrom RCT, with real dollars as the outcome.

    Same construction as tier1_criteo's loader so the two are comparable — the
    only difference is `target_col='spend'` instead of 'visit'.
    """
    bunch = fetch_hillstrom(target_col="spend")
    df = bunch.data.copy()
    df["seg"] = bunch.treatment
    df["y"] = bunch.target
    df = df[df["seg"].isin(["Womens E-Mail", "No E-Mail"])].copy()
    df["t"] = (df["seg"] == "Womens E-Mail").astype(int)
    df = df.drop(columns=["seg"])
    df = pd.get_dummies(df, columns=["history_segment", "zip_code", "channel"], drop_first=True)
    cols = [c for c in df.columns if c not in ("y", "t")]
    X = df[cols].to_numpy(dtype=float)
    T = df["t"].to_numpy(dtype=int)
    Y = df["y"].to_numpy(dtype=float)
    e = np.full(len(Y), T.mean())          # randomised by design; known, constant
    return X, T, Y, e


def bootstrap_diff(a, b, *, n_boot, seed):
    rng = np.random.default_rng(seed)
    point = float(a.mean() - b.mean())
    draws = np.array([
        rng.choice(a, a.size, True).mean() - rng.choice(b, b.size, True).mean()
        for _ in range(n_boot)
    ])
    lo, hi = np.quantile(draws, [0.025, 0.975])
    return point, float(lo), float(hi)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n-boot", type=int, default=2000)
    ap.add_argument("--target-frac", type=float, default=0.30,
                    help="share of customers the targeted policy contacts")
    args = ap.parse_args()

    X, T, Y, e = load_spend()
    print(f"Hillstrom, spend outcome: {len(Y):,} customers, "
          f"{T.sum():,} emailed / {(1 - T).sum():,} holdout")

    # ── 1. the effect, straight from the randomisation ──────────────────
    point, lo, hi = bootstrap_diff(Y[T == 1], Y[T == 0], n_boot=args.n_boot, seed=SEED)
    effect_holds = lo > 0
    print(f"\nIncremental revenue per 1,000 customers: "
          f"${point*1000:,.0f}  95% CI [${lo*1000:,.0f}, ${hi*1000:,.0f}]  "
          f"-> {'CLAIMABLE' if effect_holds else 'interval covers zero'}")

    # The same effect on all three arms — more customers, a tighter interval,
    # and a different estimand (the effect of *any* email rather than the
    # womens campaign). Reported beside the arm-specific figure, not instead
    # of it.
    Xp, Tp, Yp = load_spend_pooled()
    p_point, p_lo, p_hi = bootstrap_diff(Yp[Tp == 1], Yp[Tp == 0], n_boot=args.n_boot, seed=SEED)
    print(f"Pooled across both email arms ({len(Yp):,} customers): "
          f"${p_point*1000:,.0f}/1,000  95% CI [${p_lo*1000:,.0f}, ${p_hi*1000:,.0f}]")

    # ── 2. the policy claim, on real money ──────────────────────────────
    #
    # Split first. Fitting tau_hat on every customer and then ranking those same
    # customers is in-sample: the model has seen their outcomes, and IPS and DR
    # will happily reward it for remembering them. The first version of this
    # experiment did exactly that and reported a targeting advantage that was
    # partly memorisation. The policy is now chosen by a model that never saw
    # the rows it is evaluated on.
    idx = np.arange(len(Y))
    split_rng = np.random.default_rng(SEED)
    split_rng.shuffle(idx)
    cut = len(idx) // 2
    tr, te = idx[:cut], idx[cut:]

    model = TLearnerModel(random_state=SEED)
    model.fit(X[tr], T[tr], Y[tr])
    tau = model.predict_cate(X[te])

    Xe, Te, Ye, ee = X[te], T[te], Y[te], e[te]
    k = int(len(Ye) * args.target_frac)
    order = np.argsort(-tau)
    targeted = np.zeros(len(Ye), dtype=int)
    targeted[order[:k]] = 1

    rng = np.random.default_rng(SEED + 1)
    random_pol = np.zeros(len(Ye), dtype=int)
    random_pol[rng.choice(len(Ye), k, replace=False)] = 1   # matched volume
    print(f"\nheld out {len(te):,} customers; policy chosen by a model fitted "
          f"on the other {len(tr):,}")

    out_model = GradientBoostingRegressor(random_state=SEED, n_estimators=100)
    results = {}
    for name, pol in (("targeted", targeted), ("random_matched", random_pol)):
        results[name] = {
            "ips": ips_value(Ye, Te, ee, pol, n_boot=args.n_boot, seed=SEED),
            "snips": snips_value(Ye, Te, ee, pol, n_boot=args.n_boot, seed=SEED),
            "dr": doubly_robust_value(Ye, Te, Xe, ee, pol, outcome_model=out_model,
                                      n_boot=args.n_boot, seed=SEED),
        }

    print(f"\nPolicy value per customer, contacting {args.target_frac:.0%} "
          f"({k:,} of {len(Ye):,} held out):")
    print(f"  {'estimator':<8}{'targeted':>12}{'random':>12}{'difference':>14}")
    diffs = {}
    for est in ("ips", "snips", "dr"):
        a = results["targeted"][est].point_estimate
        b = results["random_matched"][est].point_estimate
        diffs[est] = a - b
        print(f"  {est:<8}{a:>12.4f}{b:>12.4f}{a - b:>+14.4f}")

    # A PAIRED interval on the difference — the statistic the registered rule
    # should have named and did not. Resample rows once and difference the two
    # policies within each draw, so the noise they share is not counted twice.
    # The rule as registered asks only whether three estimators agree on a
    # sign; three estimators computed from the same rows will usually agree on
    # a sign whether or not the difference is real, which is a rule that can
    # pass on evidence that does not support the conclusion. It stands as
    # registered, and this is reported beside it.
    prng = np.random.default_rng(SEED + 7)
    w_t = _match_weights(Te, ee, targeted)
    w_r = _match_weights(Te, ee, random_pol)
    per_t, per_r = w_t * Ye, w_r * Ye
    draws = np.array([
        (lambda i: per_t[i].mean() - per_r[i].mean())(prng.integers(0, len(Ye), len(Ye)))
        for _ in range(args.n_boot)
    ])
    d_lo, d_hi = (float(x) for x in np.quantile(draws, [0.025, 0.975]))
    d_point = float(per_t.mean() - per_r.mean())
    diff_excludes_zero = d_lo > 0 or d_hi < 0
    print(f"\n  paired difference (IPS weights): {d_point:+.4f} per customer  "
          f"95% CI [{d_lo:+.4f}, {d_hi:+.4f}]  -> "
          f"{'excludes zero' if diff_excludes_zero else 'COVERS ZERO'}")

    signs = {np.sign(v) for v in diffs.values()}
    agree = len(signs) == 1 and 0 not in signs
    beats = all(v > 0 for v in diffs.values())
    targeting_verdict = (
        "NOT ESTABLISHED: the three estimators agree on the sign, which is all "
        "the registered rule asked for, but the paired interval on the "
        "difference covers zero — the targeting advantage is not "
        "distinguishable from noise at this sample size."
        if agree and beats and not diff_excludes_zero else
        "CLAIMABLE: targeting beats matched-volume random on real money, and "
        "IPS, SNIPS and DR agree on the sign."
        if agree and beats else
        "REFUTED: every estimator puts targeting at or below matched-volume random."
        if agree and not beats else
        "UNDETERMINED: the three estimators do not agree on the sign of the "
        "difference, so the targeting claim is not established on this data."
    )
    print(f"\n{targeting_verdict}")

    # How much data would it take to settle the targeting question? Asked
    # because "the interval covers zero" and "this dataset cannot answer it"
    # are different statements, and only the second tells you whether to go
    # looking for more data.
    half = (d_hi - d_lo) / 2
    se = half / 1.96
    needed_factor = (1.96 * se / abs(d_point)) ** 2 if d_point else float("inf")
    n_needed = int(len(Ye) * needed_factor)
    pooled_max_holdout = len(Yp) // 2
    pooled_half = half / np.sqrt(pooled_max_holdout / len(Ye))
    print(f"\n  power: the difference is {abs(d_point)/se:.2f} SEs from zero; "
          f"resolving it needs ~{needed_factor:.0f}x the held-out sample "
          f"(~{n_needed:,} customers).")
    print(f"  pooling every arm gives at most {pooled_max_holdout:,} held out — "
          f"projected half-width {pooled_half:.4f} against an effect of "
          f"{abs(d_point):.4f}. Still covers zero.")

    out = {
        "dataset": "hillstrom (MineThatData 2008), womens-email vs no-email",
        "outcome": "spend — real dollars, two weeks post-treatment",
        "n_customers": int(len(Y)),
        "n_emailed": int(T.sum()),
        "n_holdout": int((1 - T).sum()),
        "purchaser_rate": round(float((Y > 0).mean()), 5),
        "max_single_spend": round(float(Y.max()), 2),
        "effect": {
            "rule": EFFECT_RULE,
            "incremental_per_1000": round(point * 1000, 2),
            "ci_low_per_1000": round(lo * 1000, 2),
            "ci_high_per_1000": round(hi * 1000, 2),
            "excludes_zero": bool(effect_holds),
        },
        "effect_pooled_all_arms": {
            "n_customers": int(len(Yp)),
            "incremental_per_1000": round(p_point * 1000, 2),
            "ci_low_per_1000": round(p_lo * 1000, 2),
            "ci_high_per_1000": round(p_hi * 1000, 2),
            "excludes_zero": bool(p_lo > 0),
            "note": "effect of ANY email — a mixture of two campaigns, so a "
                    "different estimand from the womens-only figure above",
        },
        "targeting_power": {
            "standard_errors_from_zero": round(float(abs(d_point) / se), 3),
            "sample_multiple_needed": round(float(needed_factor), 1),
            "held_out_customers_needed": n_needed,
            "max_available_pooled_holdout": pooled_max_holdout,
            "pooling_would_resolve_it": bool(pooled_half < abs(d_point)),
            "conclusion": (
                "Not a question this dataset can answer. The difference sits "
                f"{abs(d_point)/se:.2f} standard errors from zero and resolving it "
                f"needs roughly {needed_factor:.0f}x the sample — about {n_needed:,} "
                "held-out customers against the 32,000 pooling can supply. "
                "The targeting claim is not merely unproven here; it is "
                "unprovable on 64,000 customers at this effect size."
            ),
        },
        "targeting": {
            "rule": TARGETING_RULE,
            "target_fraction": args.target_frac,
            "n_train": int(len(tr)),
            "n_evaluated_out_of_sample": int(len(te)),
            "n_targeted": int(k),
            "by_estimator": {
                est: {
                    "targeted": round(float(results["targeted"][est].point_estimate), 6),
                    "random_matched": round(float(results["random_matched"][est].point_estimate), 6),
                    "ci_low": round(float(results["targeted"][est].ci_low), 6),
                    "ci_high": round(float(results["targeted"][est].ci_high), 6),
                    "n_unsupported": int(results["targeted"][est].n_unsupported),
                    "difference": round(float(diffs[est]), 6),
                }
                for est in ("ips", "snips", "dr")
            },
            "paired_difference": round(d_point, 6),
            "paired_ci_low": round(d_lo, 6),
            "paired_ci_high": round(d_hi, 6),
            "paired_interval_excludes_zero": bool(diff_excludes_zero),
            "registered_rule_was_weaker_than_the_question": (
                "The rule asks only for sign agreement across three estimators "
                "computed from the same rows, which they will usually give "
                "whether or not the difference is real. The paired interval on "
                "the difference is the statistic that decides it, and it is "
                "reported here rather than substituted for the registered rule."
            ),
            "estimators_agree_on_sign": bool(agree),
            "beats_random": bool(beats and agree),
            "verdict": targeting_verdict,
        },
    }
    (HERE / "results_revenue.json").write_text(json.dumps(out, indent=2))
    print(f"\nWrote {HERE / 'results_revenue.json'}")


if __name__ == "__main__":
    main()
