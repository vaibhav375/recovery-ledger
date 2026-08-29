"""When does planning ahead actually pay?

Novelty claim N4 says contact should be treated as a budget-constrained
*sequential* decision rather than one-shot classification. The repo has both:
a greedy EV policy and a finite-horizon lookahead that solves the same problem
by backward induction. And the README marks N4 "partial", because in the
headline batch the lookahead earns Rs 300,677 against greedy's Rs 301,018 —
very slightly *worse*, on 21 fewer contacts.

Reporting that as "the lookahead adds nothing measurable" is honest but
incurious. It leaves the important question unasked: is the solver broken, or
is greedy genuinely near-optimal in this regime? Those have opposite
implications for the claim, and the outcome number cannot distinguish them.

So this measures the thing that can. Two knobs should control whether the
horizon matters at all:

  max_attempts      how far there is to look. At 1 the two policies are the
                    same algorithm and must agree exactly — which is also a
                    test that the comparison is wired up correctly.
  lambda_annoyance  the per-attempt penalty. It enters the immediate value as
                    -lambda * attempt_index, so a large value makes every
                    future attempt worthless and collapses the horizon no
                    matter how long it is.

At each setting both policies run on the same cases under common random
numbers, and the report includes **decision agreement** — the share of cases
where they choose the same action — alongside the rupee outcome. Agreement is
far more sensitive: two policies can disagree on many cases and still land on
the same total, and a solver that is silently degenerate will agree 100% of
the time everywhere, which no outcome comparison would reveal.
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
from recovery_ledger.policy.decision import (
    CHANNEL_COST,
    EVDecisionPolicy,
    LookaheadEVDecisionPolicy,
)
from recovery_ledger.policy.features import cases_to_feature_matrix
from recovery_ledger.policy.uplift.learners import TLearnerModel
from recovery_ledger.sim.environment import (
    SimulationEnvironment,
    generate_population,
    persuadability,
)
from recovery_ledger.sim.generator import generate_cases

HERE = Path(__file__).parent
NOW = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)
SEED = 20260823
EVAL_SEED = SEED + 9000  # disjoint; see tests/test_experiment_seeds.py
LAMBDA_CHURN = 4.0
CONTACT_ACTIONS = {ActionType.NUDGE, ActionType.NEGOTIATE}


def train(n_train: int, seed: int):
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
    return (
        TLearnerModel(random_state=seed).fit(X, treatment, paid),
        ChurnRiskModel().fit(X, treatment, churned, random_state=seed),
    )


def decisions(policy, cases, diagnoser, attempt: int) -> list[ActionType]:
    return [policy.decide(c, diagnoser.diagnose(c), attempt).action_type for c in cases]


def realised(cases, traits, actions, *, seed: int) -> dict:
    """One step of the world under these actions, valued the way the policy is
    optimising: rupees, net of channel cost and the churn it causes."""
    env = SimulationEnvironment(traits, seed=seed)
    total, contacts = 0.0, 0
    for i, c in enumerate(cases):
        contact = actions[i] in CONTACT_ACTIONS
        contacts += int(contact)
        r = env.step(c, ActionType.NUDGE if contact else ActionType.WAIT, 0)
        cost = CHANNEL_COST[c.customer.channel_pref or Channel.SMS] if contact else 0.0
        churn = LAMBDA_CHURN * estimated_ltv(c) if r.reply == ReplyIntent.OPT_OUT else 0.0
        total += float(r.paid) * c.amount_at_risk - cost - churn
    return {"net_value_per_case": total / len(cases), "contacts": contacts}


def rollout(cases, traits, policy, *, horizon: int, seed: int) -> dict:
    """Play the whole episode, not one step of it.

    THIS IS THE MEASUREMENT THAT CAN ANSWER THE QUESTION, and the single-step
    one is not. A lookahead policy's entire advantage is deferral: it declines
    to spend an attempt now because it expects a better moment later, or it
    spends one now because it can see there will be no later. Evaluating that
    with one env.step charges it for every wait and lets it collect on none of
    them, so the sequential policy is guaranteed to look equal-or-worse no
    matter how good it is. The first version of this experiment did exactly
    that and produced a clean, confident, meaningless negative.

    Here each case runs until it pays, opts out, or exhausts the attempt
    budget, with the environment carrying contact count and accumulated
    annoyance across attempts the way it does in the batch runner.
    """
    env = SimulationEnvironment(traits, seed=seed)
    diagnoser = CaseDiagnoser()
    diagnoses = {c.case_id: diagnoser.diagnose(c) for c in cases}
    active = list(cases)
    total, contacts = 0.0, 0

    for attempt in range(horizon):
        if not active:
            break
        survivors = []
        for c in active:
            action = policy.decide(c, diagnoses[c.case_id], attempt).action_type
            contact = action in CONTACT_ACTIONS
            contacts += int(contact)
            r = env.step(c, ActionType.NUDGE if contact else ActionType.WAIT, attempt)
            if contact:
                total -= CHANNEL_COST[c.customer.channel_pref or Channel.SMS]
            if r.reply == ReplyIntent.OPT_OUT:
                total -= LAMBDA_CHURN * estimated_ltv(c)
                continue  # gone: no further attempts on this customer
            if r.paid:
                total += c.amount_at_risk
                continue  # resolved
            survivors.append(c)
        active = survivors

    return {
        "net_value_per_case": total / len(cases),
        "contacts": contacts,
        "unresolved": len(active),
    }


def compare(cases, traits, uplift, churn, *, horizon: int, annoyance: float,
            eval_seed: int = EVAL_SEED, mode: str = "rollout") -> dict:
    diagnoser = CaseDiagnoser()
    common = dict(uplift_model=uplift, churn_model=churn,
                  max_attempts=horizon, lambda_annoyance=annoyance)
    greedy_policy = EVDecisionPolicy(**common)
    look_policy = LookaheadEVDecisionPolicy(**common)

    # Agreement is still measured at attempt 0, where the two policies face an
    # identical state, so it stays a clean read on whether the solver differs.
    g = decisions(greedy_policy, cases, diagnoser, 0)
    la = decisions(look_policy, cases, diagnoser, 0)
    agree = float(np.mean([a == b for a, b in zip(g, la)]))

    if mode == "rollout":
        gr = rollout(cases, traits, greedy_policy, horizon=horizon, seed=eval_seed)
        lr = rollout(cases, traits, look_policy, horizon=horizon, seed=eval_seed)
    else:
        gr = realised(cases, traits, g, seed=eval_seed)
        lr = realised(cases, traits, la, seed=eval_seed)
    return {
        "max_attempts": horizon,
        "lambda_annoyance": annoyance,
        "decision_agreement": round(agree, 4),
        "disagreements": int(round((1 - agree) * len(cases))),
        "greedy": {k: round(v, 2) for k, v in gr.items()},
        "lookahead": {k: round(v, 2) for k, v in lr.items()},
        "value_delta_per_case": round(
            lr["net_value_per_case"] - gr["net_value_per_case"], 2
        ),
        "contact_delta": lr["contacts"] - gr["contacts"],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n-train", type=int, default=5000)
    ap.add_argument("--n-eval", type=int, default=3000)
    ap.add_argument("--horizons", type=int, nargs="+", default=[1, 2, 3, 5, 8])
    ap.add_argument("--annoyance", type=float, nargs="+", default=[0.0, 15.0, 30.0, 60.0, 120.0])
    ap.add_argument("--mode", choices=["rollout", "single"], default="rollout",
                    help="rollout plays the full episode; single plays one attempt "
                         "and cannot detect a deferral advantage (see rollout docstring)")
    ap.add_argument("--eval-draws", type=int, default=3,
                    help="independent evaluation populations; one draw is not a result")
    args = ap.parse_args()

    print(f"Training on {args.n_train} randomised cases...")
    uplift, churn = train(args.n_train, SEED)
    draws = [EVAL_SEED + 100 * d for d in range(args.eval_draws)]
    corr = None
    per_draw: dict[int, list[dict]] = {}
    for eval_seed in draws:
        cs = generate_cases(args.n_eval, seed=eval_seed, now=NOW)
        tr = generate_population(cs, seed=eval_seed)
        if corr is None:
            corr = float(np.corrcoef(
                uplift.predict_cate(cases_to_feature_matrix(cs)),
                np.array([persuadability(tr[c.case_id]) for c in cs]),
            )[0, 1])
            print(f"  corr(tau_hat, tau_true) = {corr:.3f} on {args.n_eval} eval cases\n")
        per_draw[eval_seed] = [
            compare(cs, tr, uplift, churn, horizon=h, annoyance=a,
                    eval_seed=eval_seed, mode=args.mode)
            for h in args.horizons for a in args.annoyance
        ]
        print(f"  draw at seed {eval_seed} done")

    # Averaged over draws. The single-draw version of this grid reported a
    # +Rs 61/case advantage at horizon 8; that is exactly the kind of number
    # this project has watched evaporate three times, so it is not quoted
    # until several populations agree.
    rows = []
    print(f"\n{'horizon':>8}{'lambda':>9}{'agreement':>11}{'disagree':>10}"
          f"{'greedy Rs':>11}{'lookahead':>11}{'delta':>8}{'delta range':>16}")
    for i in range(len(per_draw[draws[0]])):
        cells = [per_draw[s][i] for s in draws]
        deltas = [c["value_delta_per_case"] for c in cells]
        base = cells[0]
        row = {
            "max_attempts": base["max_attempts"],
            "lambda_annoyance": base["lambda_annoyance"],
            "decision_agreement": round(float(np.mean([c["decision_agreement"] for c in cells])), 4),
            "disagreements": int(round(float(np.mean([c["disagreements"] for c in cells])))),
            "greedy_value": round(float(np.mean([c["greedy"]["net_value_per_case"] for c in cells])), 2),
            "lookahead_value": round(float(np.mean([c["lookahead"]["net_value_per_case"] for c in cells])), 2),
            "value_delta_per_case": round(float(np.mean(deltas)), 2),
            "value_delta_min": round(min(deltas), 2),
            "value_delta_max": round(max(deltas), 2),
            # Only claimable if every draw agrees on the sign.
            "advantage_consistent": bool(all(d > 0 for d in deltas) or all(d < 0 for d in deltas)),
            "per_draw_delta": deltas,
        }
        rows.append(row)
        print(f"{row['max_attempts']:>8}{row['lambda_annoyance']:>9.0f}"
              f"{row['decision_agreement']:>11.3f}{row['disagreements']:>10}"
              f"{row['greedy_value']:>11.0f}{row['lookahead_value']:>11.0f}"
              f"{row['value_delta_per_case']:>+8.0f}"
              f"{f'[{row["value_delta_min"]:+.0f}, {row["value_delta_max"]:+.0f}]':>16}")

    # Horizon 1 is the control: with one attempt left there is no future to
    # look into, so the two policies are the same algorithm and must agree on
    # every case. If they do not, the comparison is measuring a wiring bug
    # rather than a difference in planning.
    control = [r for r in rows if r["max_attempts"] == 1]
    control_ok = all(r["decision_agreement"] == 1.0 for r in control)

    best = max(rows, key=lambda r: r["value_delta_per_case"])
    ever_differs = [r for r in rows if r["decision_agreement"] < 1.0]
    consistent = [r for r in rows if r["advantage_consistent"] and r["value_delta_per_case"] > 0]

    print(f"\ncontrol (horizon 1, must agree everywhere): "
          f"{'PASS' if control_ok else 'FAIL - the comparison is broken'}")
    print(f"settings where the policies ever disagree: {len(ever_differs)} of {len(rows)}")
    if ever_differs:
        worst = min(ever_differs, key=lambda r: r["decision_agreement"])
        print(f"  lowest agreement: {worst['decision_agreement']:.3f} "
              f"at horizon {worst['max_attempts']}, lambda {worst['lambda_annoyance']:.0f}")
    print(f"best lookahead advantage: {best['value_delta_per_case']:+.0f}/case "
          f"at horizon {best['max_attempts']}, lambda {best['lambda_annoyance']:.0f} "
          f"(per draw {best['per_draw_delta']})")
    print(f"settings where every draw agrees the lookahead wins: {len(consistent)} of {len(rows)}")
    if consistent:
        for r in sorted(consistent, key=lambda r: -r["value_delta_per_case"])[:3]:
            print(f"  horizon {r['max_attempts']}, lambda {r['lambda_annoyance']:.0f}: "
                  f"{r['value_delta_per_case']:+.0f}/case "
                  f"[{r['value_delta_min']:+.0f}, {r['value_delta_max']:+.0f}]")

    out = {
        "n_train": args.n_train, "n_eval": args.n_eval, "mode": args.mode,
        "seed": SEED, "eval_seed": EVAL_SEED,
        "uplift_correlation": round(corr, 4),
        "control_horizon1_agrees_everywhere": control_ok,
        "settings_where_policies_differ": len(ever_differs),
        "settings_tested": len(rows),
        "eval_draws": args.eval_draws,
        "settings_with_consistent_lookahead_advantage": len(consistent),
        "best_lookahead_advantage_per_case": best["value_delta_per_case"],
        "best_advantage_consistent_across_draws": best["advantage_consistent"],
        "best_setting": {"max_attempts": best["max_attempts"],
                         "lambda_annoyance": best["lambda_annoyance"]},
        "grid": rows,
    }
    (HERE / f"results_horizon_{args.mode}.json").write_text(json.dumps(out, indent=2))
    print(f"\nWrote {HERE / f'results_horizon_{args.mode}.json'}")


if __name__ == "__main__":
    main()
