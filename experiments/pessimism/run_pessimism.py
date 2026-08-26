"""Acting on a lower bound instead of a point estimate.

`experiments/fairness/` audited the deployed policy and found two things it
does badly, neither of which is a fairness violation:

  * **Overdue receivables are worth -Rs 69 per contact** — contacting them
    destroys more through opt-outs than it recovers — and the policy contacts
    20.2% of them anyway. The model predicts a small *positive* uplift there
    (tau_hat 0.023).
  * **The smallest invoices get the model's highest predicted uplift** and its
    worst correlation with truth (0.09). It is most confident exactly where it
    knows least.

Both are the same failure: the EV rule treats a point estimate as a fact.
`tau_hat = 0.02` from a model that understands the segment and `tau_hat = 0.02`
from a model that is guessing produce identical decisions, because a point
estimate cannot tell them apart.

This measures the obvious remedy. `BootstrapEnsembleModel` fits the same
learner on bootstrap resamples and reports a per-case standard error, and the
policy acts on

    tau_lcb = tau_hat - k * se

k = 0 is exactly the current policy, so the sweep has today's behaviour as its
origin rather than as a separate branch. Larger k means the agent declines
whenever it is unsure, which costs recovery on cases it would have got right.
Somewhere there is a best k, or there is not — a flat or downward curve is a
real result and is reported as one.

Everything runs under common random numbers on one fixed evaluation
population, so differences between settings belong to k.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from recovery_ledger.diagnoser.diagnoser import CaseDiagnoser
from recovery_ledger.events.actions import ActionType
from recovery_ledger.events.schemas import Channel
from recovery_ledger.listener.listener import ReplyIntent
from recovery_ledger.policy.churn import ChurnRiskModel, estimated_ltv
from recovery_ledger.policy.decision import CHANNEL_COST, EVDecisionPolicy
from recovery_ledger.policy.features import cases_to_feature_matrix
from recovery_ledger.policy.uplift.learners import BootstrapEnsembleModel, TLearnerModel
from recovery_ledger.sim.environment import (
    SimulationEnvironment,
    generate_population,
    persuadability,
)
from recovery_ledger.sim.generator import generate_cases

HERE = Path(__file__).parent
NOW = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)
SEED = 20260823
EVAL_SEED = SEED + 7000  # disjoint from every other experiment (see tests/test_experiment_seeds.py)
LAMBDA_CHURN = 4.0
CONTACT_ACTIONS = {ActionType.NUDGE, ActionType.NEGOTIATE}


def train(n_train: int, n_models: int, seed: int):
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
    ensemble = BootstrapEnsembleModel(
        base=TLearnerModel, n_models=n_models, random_state=seed
    ).fit(X, treatment, paid)
    churn = ChurnRiskModel().fit(X, treatment, churned, random_state=seed)
    return ensemble, churn


def evaluate(k: float, cases, traits, ensemble, churn, *, eval_seed: int) -> dict:
    policy = EVDecisionPolicy(uplift_model=ensemble, churn_model=churn, uncertainty_k=k)
    diagnoser = CaseDiagnoser()
    actions = [policy.decide(c, diagnoser.diagnose(c), 0).action_type for c in cases]
    contacted = np.array([int(a in CONTACT_ACTIONS) for a in actions])

    env = SimulationEnvironment(traits, seed=eval_seed)
    paid = np.zeros(len(cases))
    opted = np.zeros(len(cases))
    for i, c in enumerate(cases):
        r = env.step(c, ActionType.NUDGE if contacted[i] else ActionType.WAIT, 0)
        paid[i] = float(r.paid)
        opted[i] = float(r.reply == ReplyIntent.OPT_OUT)

    value = np.array([
        paid[i] * cases[i].amount_at_risk
        - (CHANNEL_COST[cases[i].customer.channel_pref or Channel.SMS] if contacted[i] else 0.0)
        - LAMBDA_CHURN * opted[i] * estimated_ltv(cases[i])
        for i in range(len(cases))
    ])

    # The audit's specific complaint, measured directly: how many of the
    # contacts land on cases whose TRUE expected value of contact is negative?
    # Only a simulator can answer this, and it is the cleanest statement of
    # what a point estimate was costing.
    true_value_of_contact = np.array([
        persuadability(traits[c.case_id]) * c.amount_at_risk for c in cases
    ])
    harmful = (true_value_of_contact < 0)
    n_contacts = int(contacted.sum())

    return {
        "uncertainty_k": k,
        "contact_rate": round(float(contacted.mean()), 4),
        "contacts": n_contacts,
        "net_value_per_case": round(float(value.mean()), 2),
        "net_value_per_contact": round(float(value.sum() / n_contacts), 2) if n_contacts else None,
        "payment_rate": round(float(paid.mean()), 4),
        "opt_out_rate": round(float(opted.mean()), 4),
        "harmful_contacts": int((contacted & harmful).sum()),
        "pct_contacts_that_are_harmful": (
            round(float((contacted & harmful).sum() / n_contacts), 4) if n_contacts else None
        ),
        "value_destroyed_on_harmful_contacts": round(
            float(value[(contacted == 1) & harmful].sum()), 2
        ),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n-train", type=int, default=5000)
    ap.add_argument("--n-eval", type=int, default=4000)
    ap.add_argument("--n-models", type=int, default=20)
    ap.add_argument("--ks", type=float, nargs="+", default=[0.0, 0.25, 0.5, 1.0, 1.5, 2.0])
    ap.add_argument("--eval-draws", type=int, default=3,
                    help="independent evaluation populations; one draw is not a result")
    args = ap.parse_args()

    print(f"Fitting a {args.n_models}-member bootstrap ensemble on {args.n_train} cases...")
    ensemble, churn = train(args.n_train, args.n_models, SEED)

    # Is the ensemble's averaging alone improving the point estimate, before
    # any pessimism? Compared on the SAME evaluation population as the
    # ensemble, because correlations from different populations are not
    # comparable — this project has already been bitten by exactly that.
    single = TLearnerModel(random_state=SEED)
    tc = generate_cases(args.n_train, seed=SEED, now=NOW)
    tt = generate_population(tc, seed=SEED)
    tenv = SimulationEnvironment(tt, seed=SEED)
    trng = np.random.default_rng(SEED)
    ttreat = trng.integers(0, 2, size=args.n_train)
    tpaid = np.array([
        float(tenv.step(c, ActionType.NUDGE if ttreat[i] else ActionType.WAIT, 0).paid)
        for i, c in enumerate(tc)
    ])
    single.fit(cases_to_feature_matrix(tc), ttreat, tpaid)

    draws = [EVAL_SEED + 100 * d for d in range(args.eval_draws)]
    per_draw = []
    corr_single, corr_ens = [], []

    for i, eval_seed in enumerate(draws):
        cases = generate_cases(args.n_eval, seed=eval_seed, now=NOW)
        traits = generate_population(cases, seed=eval_seed)
        X = cases_to_feature_matrix(cases)
        tau_true = np.array([persuadability(traits[c.case_id]) for c in cases])
        se = ensemble.predict_cate_std(X)
        corr_ens.append(float(np.corrcoef(ensemble.predict_cate(X), tau_true)[0, 1]))
        corr_single.append(float(np.corrcoef(single.predict_cate(X), tau_true)[0, 1]))

        rows = [evaluate(k, cases, traits, ensemble, churn, eval_seed=eval_seed)
                for k in args.ks]
        best = max(rows, key=lambda r: r["net_value_per_case"])
        per_draw.append({
            "eval_seed": eval_seed,
            "se_median": round(float(np.median(se)), 5),
            "best_k": best["uncertainty_k"],
            "improvement_per_case": round(
                best["net_value_per_case"] - rows[0]["net_value_per_case"], 2
            ),
            "sweep": rows,
        })
        print(f"draw {i + 1} (seed {eval_seed}): best k={best['uncertainty_k']}, "
              f"Rs {rows[0]['net_value_per_case']:.0f} -> {best['net_value_per_case']:.0f}/case, "
              f"harmful {rows[0]['harmful_contacts']} -> {best['harmful_contacts']}")

    print(f"\ncorr(tau_hat, tau_true), same populations:")
    print(f"  single T-learner   {np.mean(corr_single):.3f}  {[round(c, 3) for c in corr_single]}")
    print(f"  20-model ensemble  {np.mean(corr_ens):.3f}  {[round(c, 3) for c in corr_ens]}")

    print(f"\n{'k':>6}{'contacts':>10}{'net Rs/case':>13}{'Rs/contact':>12}"
          f"{'harmful':>9}{'% harmful':>11}   (mean over draws)")
    for j, k in enumerate(args.ks):
        rs = [d["sweep"][j] for d in per_draw]
        print(f"{k:>6.2f}{np.mean([r['contacts'] for r in rs]):>10.0f}"
              f"{np.mean([r['net_value_per_case'] for r in rs]):>13.0f}"
              f"{np.mean([r['net_value_per_contact'] or 0 for r in rs]):>12.0f}"
              f"{np.mean([r['harmful_contacts'] for r in rs]):>9.0f}"
              f"{np.mean([r['pct_contacts_that_are_harmful'] or 0 for r in rs]) * 100:>10.1f}%")

    best_ks = [d["best_k"] for d in per_draw]
    gains = [d["improvement_per_case"] for d in per_draw]
    print(f"\nBest k per draw: {best_ks}   improvement per case: {gains}")
    if len(set(best_ks)) > 1:
        print("Best k is NOT stable across draws — reported as a range, not a tuned value.")

    out = {
        "n_train": args.n_train, "n_eval": args.n_eval, "n_models": args.n_models,
        "seed": SEED, "eval_seed": EVAL_SEED, "eval_draws": args.eval_draws,
        "uplift_correlation_single_tlearner": round(float(np.mean(corr_single)), 4),
        "uplift_correlation_ensemble": round(float(np.mean(corr_ens)), 4),
        "correlation_per_draw": {
            "single": [round(c, 4) for c in corr_single],
            "ensemble": [round(c, 4) for c in corr_ens],
        },
        "best_k_per_draw": best_ks,
        "best_k_is_stable": len(set(best_ks)) == 1,
        "improvement_per_case_per_draw": gains,
        "draws": per_draw,
    }
    (HERE / "results_pessimism.json").write_text(json.dumps(out, indent=2))
    print(f"\nWrote {HERE / 'results_pessimism.json'}")


if __name__ == "__main__":
    main()
