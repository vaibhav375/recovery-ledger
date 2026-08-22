"""Tier 1 validation (spec section 7.2) — the kill gate.

Proves the causal machinery (uplift meta-learners + off-policy value
estimators) reproduces known treatment effects on GENUINELY RANDOMISED public
data, before any of it touches the domain simulator. If this doesn't work,
nothing downstream is trustworthy — see ENGINEERING_LOG.md for why that
ordering matters.

Usage:
    python experiments/tier1_criteo/run_validation.py --dataset hillstrom
    python experiments/tier1_criteo/run_validation.py --dataset criteo --sample-frac 0.05

Writes results_<dataset>.json and two PNG plots into this directory. Every
number in those files was produced by this script — nothing here is
hand-entered.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import train_test_split
from sklift.datasets import fetch_hillstrom
from sklift.metrics import qini_auc_score, qini_curve, uplift_auc_score

from recovery_ledger.policy.ope.estimators import (
    always_treat_policy,
    doubly_robust_value,
    ips_value,
    never_treat_policy,
    snips_value,
)
from recovery_ledger.policy.uplift.learners import ALL_LEARNERS

SEED = 20260823  # date this validation was first run — fixed everywhere below
HERE = Path(__file__).parent


def load_hillstrom(target_col: str = "visit"):
    """Two-arm subset (Womens E-Mail vs No E-Mail) of a classic email RCT.
    Randomisation is genuine and by design (Hillstrom, MineThatData 2008)."""
    bunch = fetch_hillstrom(target_col=target_col)
    df = bunch.data.copy()
    df["treatment_segment"] = bunch.treatment
    df["y"] = bunch.target
    df = df[df["treatment_segment"].isin(["Womens E-Mail", "No E-Mail"])].copy()
    df["t"] = (df["treatment_segment"] == "Womens E-Mail").astype(int)
    df = df.drop(columns=["treatment_segment"])
    df = pd.get_dummies(df, columns=["history_segment", "zip_code", "channel"], drop_first=True)
    feature_cols = [c for c in df.columns if c not in ("y", "t")]
    X = df[feature_cols].to_numpy(dtype=float)
    T = df["t"].to_numpy(dtype=int)
    Y = df["y"].to_numpy(dtype=float)
    propensity = np.full(len(Y), T.mean())
    return X, T, Y, propensity, feature_cols


CRITEO_PARQUET_URL = (
    "https://huggingface.co/datasets/criteo/criteo-uplift/resolve/"
    "refs%2Fconvert%2Fparquet/default/train/{i:04d}.parquet"
)
CRITEO_LOCAL_DIR = HERE.parent.parent / "data"
CRITEO_N_SHARDS = 4


def _ensure_criteo_shards_downloaded() -> list[Path]:
    """sklift's fetch_criteo points at a Criteo-hosted S3 bucket that now
    returns 403 Forbidden (confirmed 2026-08-23 — see ENGINEERING_LOG.md).
    Falls back to the dataset's HuggingFace mirror, which serves it as 4
    parquet shards. Note the shards are NOT row-shuffled — they're
    contiguous blocks of the original file, so a single shard can be (and
    shard 0 is) 100% one treatment arm. All shards must be concatenated
    before sampling, or the sample isn't a valid random subsample."""
    paths = []
    for i in range(CRITEO_N_SHARDS):
        path = CRITEO_LOCAL_DIR / f"criteo_{i:04d}.parquet"
        if not path.exists():
            import requests

            url = CRITEO_PARQUET_URL.format(i=i)
            print(f"  downloading {url} -> {path}")
            resp = requests.get(url, timeout=120)
            resp.raise_for_status()
            path.write_bytes(resp.content)
        paths.append(path)
    return paths


def load_criteo(sample_frac: float = 0.05, target_col: str = "visit"):
    """Criteo Uplift Prediction Dataset — ~13.98M rows from real randomised
    incrementality tests, loaded from the HuggingFace parquet mirror (see
    `_ensure_criteo_shards_downloaded`). Subsampled via a shuffled random
    sample over the full pooled dataset, so the treatment ratio in the
    subsample reflects the true 0.85 design ratio."""
    paths = _ensure_criteo_shards_downloaded()
    df = pd.concat((pd.read_parquet(p) for p in paths), ignore_index=True)
    df = df.rename(columns={"treatment": "t", target_col: "y"})
    if sample_frac < 1.0:
        df = df.sample(frac=sample_frac, random_state=SEED)
    feature_cols = [c for c in df.columns if c.startswith("f")]
    X = df[feature_cols].to_numpy(dtype=float)
    T = df["t"].to_numpy(dtype=int)
    Y = df["y"].to_numpy(dtype=float)
    propensity = np.full(len(Y), T.mean())
    return X, T, Y, propensity, feature_cols


def run(dataset: str, sample_frac: float, target_col: str) -> dict:
    if dataset == "hillstrom":
        X, T, Y, propensity, feature_cols = load_hillstrom(target_col)
    elif dataset == "criteo":
        X, T, Y, propensity, feature_cols = load_criteo(sample_frac, target_col)
    else:
        raise ValueError(f"unknown dataset {dataset!r}")

    print(
        f"[{dataset}] n={len(Y)}  treated={T.sum()} ({T.mean():.3f})  "
        f"features={len(feature_cols)}  base_rate={Y.mean():.4f}"
    )

    strata = T * 2 + Y.astype(int)
    idx = np.arange(len(Y))
    train_idx, test_idx = train_test_split(
        idx, test_size=0.3, random_state=SEED, stratify=strata
    )
    X_train, X_test = X[train_idx], X[test_idx]
    T_train, T_test = T[train_idx], T[test_idx]
    Y_train, Y_test = Y[train_idx], Y[test_idx]
    prop_test = propensity[test_idx]

    results: dict = {
        "dataset": dataset,
        "target_col": target_col,
        "seed": SEED,
        "n_total": int(len(Y)),
        "n_train": int(len(train_idx)),
        "n_test": int(len(test_idx)),
        "treated_fraction": float(T.mean()),
        "base_rate": float(Y.mean()),
        "learners": {},
    }

    cate_predictions: dict[str, np.ndarray] = {}
    for name, cls in ALL_LEARNERS.items():
        t0 = time.time()
        try:
            model = cls(random_state=SEED)
            model.fit(X_train, T_train, Y_train)
            cate_test = model.predict_cate(X_test)
            elapsed = time.time() - t0
            qini = qini_auc_score(Y_test, cate_test, T_test)
            auuc = uplift_auc_score(Y_test, cate_test, T_test)
            cate_predictions[name] = cate_test
            results["learners"][name] = {
                "qini_coefficient": float(qini),
                "auuc": float(auuc),
                "mean_predicted_cate": float(np.mean(cate_test)),
                "std_predicted_cate": float(np.std(cate_test)),
                "fit_seconds": round(elapsed, 2),
            }
            print(
                f"  {name:15s} qini={qini:+.4f}  auuc={auuc:+.4f}  "
                f"mean_cate={np.mean(cate_test):+.4f}  ({elapsed:.1f}s)"
            )
        except Exception as e:  # noqa: BLE001 — deliberately keep going; report failure honestly
            results["learners"][name] = {"error": f"{type(e).__name__}: {e}"}
            print(f"  {name:15s} FAILED: {type(e).__name__}: {e}")

    # --- OPE validation ---------------------------------------------------
    # The real ground truth here isn't a model — it's the RCT's own arm means.
    # If IPS/SNIPS/DR (which never see the arm labels directly, only
    # propensity-reweighted outcomes) can't recover a number close to the
    # trivial direct arm-mean difference, the estimators are broken.
    direct_treated_mean = float(Y_test[T_test == 1].mean())
    direct_control_mean = float(Y_test[T_test == 0].mean())
    direct_effect = direct_treated_mean - direct_control_mean

    ope_model = GradientBoostingClassifier(random_state=SEED, n_estimators=80)
    ope_results: dict = {
        "direct_treated_mean": direct_treated_mean,
        "direct_control_mean": direct_control_mean,
        "direct_ate": direct_effect,
    }
    for est_name, fn in [
        ("ips", lambda actions: ips_value(Y_test, T_test, prop_test, actions, seed=SEED)),
        ("snips", lambda actions: snips_value(Y_test, T_test, prop_test, actions, seed=SEED)),
    ]:
        treated_est = fn(always_treat_policy(len(Y_test)))
        control_est = fn(never_treat_policy(len(Y_test)))
        ope_results[est_name] = {
            "always_treat": _est_dict(treated_est),
            "never_treat": _est_dict(control_est),
            "implied_ate": treated_est.point_estimate - control_est.point_estimate,
        }
        print(
            f"  OPE[{est_name:5s}] implied ATE = "
            f"{ope_results[est_name]['implied_ate']:+.4f}  (direct = {direct_effect:+.4f})"
        )

    dr_treated = doubly_robust_value(
        Y_test, T_test, X_test, prop_test, always_treat_policy(len(Y_test)),
        outcome_model=ope_model, seed=SEED,
    )
    dr_control = doubly_robust_value(
        Y_test, T_test, X_test, prop_test, never_treat_policy(len(Y_test)),
        outcome_model=ope_model, seed=SEED,
    )
    ope_results["dr"] = {
        "always_treat": _est_dict(dr_treated),
        "never_treat": _est_dict(dr_control),
        "implied_ate": dr_treated.point_estimate - dr_control.point_estimate,
    }
    print(
        f"  OPE[dr   ] implied ATE = {ope_results['dr']['implied_ate']:+.4f}  "
        f"(direct = {direct_effect:+.4f})"
    )
    results["ope_validation"] = ope_results

    _plot_qini_curves(dataset, Y_test, T_test, cate_predictions)
    _plot_ate_comparison(dataset, direct_effect, ope_results)

    return results


def _est_dict(est) -> dict:
    return {"point": est.point_estimate, "ci_low": est.ci_low, "ci_high": est.ci_high}


def _plot_qini_curves(dataset: str, Y_test, T_test, cate_predictions: dict[str, np.ndarray]) -> None:
    fig, ax = plt.subplots(figsize=(7, 6))
    for name, cate in cate_predictions.items():
        x, y = qini_curve(Y_test, cate, T_test)
        # normalise x-axis to a 0-1 fraction of population for comparability
        ax.plot(x / x[-1], y, label=name)
    ax.plot([0, 1], [0, y[-1] if len(cate_predictions) else 1], "k--", alpha=0.4, label="random")
    ax.set_xlabel("Fraction of population targeted")
    ax.set_ylabel("Cumulative incremental gain")
    ax.set_title(f"Qini curves — {dataset}")
    ax.legend()
    fig.tight_layout()
    fig.savefig(HERE / f"qini_{dataset}.png", dpi=150)
    plt.close(fig)


def _plot_ate_comparison(dataset: str, direct_effect: float, ope_results: dict) -> None:
    """Bar chart of each estimator's implied ATE (always-treat point minus
    never-treat point), against the trivial direct arm-mean difference. No
    error bars here — combining two independent bootstrap CIs into a single
    CI for their difference needs proper propagation, not simple subtraction,
    and that's not done here, so it's left out rather than shown wrong."""
    methods = ["direct", "ips", "snips", "dr"]
    points = [direct_effect] + [ope_results[m]["implied_ate"] for m in methods[1:]]
    fig, ax = plt.subplots(figsize=(6, 5))
    ax.bar(methods, points, color=["#888"] + ["#2b6cb0"] * 3)
    ax.axhline(direct_effect, color="#888", linestyle="--", alpha=0.5, label="direct arm-mean ATE")
    ax.set_ylabel("Implied average treatment effect")
    ax.set_title(f"OPE estimators vs. direct arm-mean ATE — {dataset}")
    ax.legend()
    fig.tight_layout()
    fig.savefig(HERE / f"ope_ate_comparison_{dataset}.png", dpi=150)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=["hillstrom", "criteo"], required=True)
    parser.add_argument("--sample-frac", type=float, default=0.05, help="criteo only")
    parser.add_argument("--target-col", default="visit")
    args = parser.parse_args()

    results = run(args.dataset, args.sample_frac, args.target_col)

    out_path = HERE / f"results_{args.dataset}.json"
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
