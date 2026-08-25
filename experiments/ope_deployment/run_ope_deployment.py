"""Can we evaluate a policy we have never deployed, from the logs of the one
we did?

Tier 1 proved the estimators recover a known answer on real randomised data
(Criteo, Hillstrom). That establishes the *method*. It does not establish the
thing an operator actually wants, which is:

    Before I ship a new targeting rule, can you tell me what it would have
    earned — from data I already have — without me testing it on customers?

This experiment answers that, and then checks the answer against the truth,
which is only possible because the simulator can be asked to run the
counterfactual.

    1. Deploy the EV policy with epsilon-greedy exploration. Log features,
       action, the propensity score P(contact | x), and the outcome.
    2. Take several *candidate* policies that were never deployed. Estimate
       each one's value from the logs alone, with IPS, SNIPS and DR.
    3. Then actually run each candidate on the same cases, under common
       random numbers, and measure what it really earns.
    4. Report estimate against truth, with intervals, coverage, and effective
       sample size.
    5. Sweep epsilon, including down to zero, to show what happens to all of
       this when the deployed policy stops exploring — and price what the
       exploration cost.

WHAT IS AND IS NOT BEING EVALUATED
----------------------------------
The decision here is the single targeting decision — contact this case, or do
not — taken once per case at attempt 0. That is the decision the uplift model
informs and the one the Tier 1 estimators were validated for. It is *not*
full-sequence off-policy evaluation of the multi-step agent loop: importance
weights compound across a trajectory, and a three-step sequence would need
sequential estimators this project has not validated. Framing it as a
contextual bandit is a real limitation and is stated wherever the numbers are
reported, rather than left for a reader to discover.

Everything is seeded. Run it twice and diff the JSON.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.ensemble import GradientBoostingClassifier

from recovery_ledger.diagnoser.diagnoser import CaseDiagnoser
from recovery_ledger.events.actions import ActionType
from recovery_ledger.events.schemas import Channel
from recovery_ledger.listener.listener import ReplyIntent
from recovery_ledger.policy.churn import ChurnRiskModel, estimated_ltv
from recovery_ledger.policy.decision import CHANNEL_COST, EVDecisionPolicy
from recovery_ledger.policy.exploration import (
    EpsilonGreedy,
    importance_weights,
    overlap_report,
)
from recovery_ledger.policy.features import cases_to_feature_matrix
from recovery_ledger.policy.ope.estimators import (
    doubly_robust_value,
    ips_value,
    snips_value,
)
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
# Disjoint from the training seed and from every other experiment's eval seed
# (batch uses +1000, baselines +2000, fleet +3000).
EVAL_SEED = SEED + 4000
# Actions that actually reach the customer. ESCALATE_HUMAN is excluded on
# purpose: handing a case to a person is not the agent contacting anyone, and
# counting it as contact would credit the policy with a decision it declined
# to make.
CONTACT_ACTIONS = {ActionType.NUDGE, ActionType.NEGOTIATE}


# ── the deployed model ───────────────────────────────────────────────────

def train_models(n_train: int, seed: int) -> tuple[TLearnerModel, ChurnRiskModel]:
    """Same procedure as the batch experiment: randomised contact on a separate
    population, then two causal models on the same assignment — the effect of
    contact on payment, and its effect on opting out."""
    cases = generate_cases(n_train, seed=seed, now=NOW)
    traits = generate_population(cases, seed=seed)
    env = SimulationEnvironment(traits, seed=seed)
    rng = np.random.default_rng(seed)
    treatment = rng.integers(0, 2, size=n_train)

    paid = np.zeros(n_train)
    churned = np.zeros(n_train)
    for i, case in enumerate(cases):
        r = env.step(case, ActionType.NUDGE if treatment[i] else ActionType.WAIT, 0)
        paid[i] = float(r.paid)
        churned[i] = float(r.reply == ReplyIntent.OPT_OUT)

    X = cases_to_feature_matrix(cases)
    uplift = TLearnerModel(random_state=seed)
    uplift.fit(X, treatment, paid)
    churn = ChurnRiskModel().fit(X, treatment, churned, random_state=seed)
    return uplift, churn


def greedy_contact_actions(cases, model: TLearnerModel, churn: ChurnRiskModel) -> np.ndarray:
    """What the deployed EV policy would do, as a binary contact decision.

    The churn model is supplied, so the deployed policy is the one the project
    actually argues for: it declines contact where the opt-out risk outweighs
    the payment it would buy. Without that term the objective below is nearly
    costless and "contact everyone" trivially wins, which would make this a
    test of nothing.
    """
    policy = EVDecisionPolicy(uplift_model=model, churn_model=churn)
    diagnoser = CaseDiagnoser()
    return np.array([
        int(policy.decide(c, diagnoser.diagnose(c), 0).action_type in CONTACT_ACTIONS)
        for c in cases
    ], dtype=int)


# ── the world ────────────────────────────────────────────────────────────

LAMBDA_CHURN = 4.0  # the deployed default, from the measured sweep in RESULTS.md


def realise(cases, traits, actions: np.ndarray, *, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Actually take these actions and see who pays and who leaves.

    A fresh environment every time, so accumulated per-case state from a
    previous evaluation cannot leak in. Each case draws from its own stream
    keyed on (seed, case_id), so a given case sees the same randomness no
    matter what the policy did to any other case — common random numbers,
    which is what makes two policies comparable at all.
    """
    env = SimulationEnvironment(traits, seed=seed)
    paid = np.zeros(len(cases))
    opted_out = np.zeros(len(cases))
    for i, c in enumerate(cases):
        r = env.step(c, ActionType.NUDGE if actions[i] else ActionType.WAIT, 0)
        paid[i] = float(r.paid)
        opted_out[i] = float(r.reply == ReplyIntent.OPT_OUT)
    return paid, opted_out


def net_value(cases, actions, paid, opted_out) -> np.ndarray:
    """Rupees the decision was actually worth, per case.

        value = paid x amount  -  channel cost  -  lambda_churn x LTV if they left

    This is the objective the deployed policy optimises, evaluated on realised
    outcomes rather than on the model's beliefs about them. Payment rate alone
    would be the wrong yardstick here: channel costs are pennies against
    four-figure invoices, so under a payment-rate objective "contact everyone"
    wins by construction and targeting has nothing to prove.
    """
    out = np.zeros(len(cases))
    for i, c in enumerate(cases):
        cost = CHANNEL_COST[c.customer.channel_pref or Channel.SMS] if actions[i] else 0.0
        out[i] = (
            paid[i] * c.amount_at_risk
            - cost
            - LAMBDA_CHURN * opted_out[i] * estimated_ltv(c)
        )
    return out


# ── candidate policies, none of which were deployed ──────────────────────

def candidate_policies(cases, traits, model: TLearnerModel, greedy: np.ndarray) -> dict:
    n = len(cases)
    X = cases_to_feature_matrix(cases)
    tau_hat = model.predict_cate(X)
    rng = np.random.default_rng(EVAL_SEED + 7)

    # A stricter rule than the deployed one: contact only the top quintile by
    # predicted uplift. This is the realistic candidate — an operator asking
    # "what if we only chased the best fifth?"
    top_quintile = (tau_hat >= np.quantile(tau_hat, 0.8)).astype(int)
    top_half = (tau_hat >= np.quantile(tau_hat, 0.5)).astype(int)

    return {
        "contact_everyone": np.ones(n, dtype=int),
        "contact_nobody": np.zeros(n, dtype=int),
        "random_half": (rng.random(n) < 0.5).astype(int),
        "deployed_greedy": greedy.copy(),
        "top_quintile_by_tau": top_quintile,
        "top_half_by_tau": top_half,
    }


# ── one epsilon ──────────────────────────────────────────────────────────

def _estimate_set(outcome, logged_action, p_contact, target, X, seed, *, with_dr: bool):
    """IPS and SNIPS always; DR only where its outcome model applies.

    `doubly_robust_value` fits a classifier for q_hat, so it is defined for the
    binary payment outcome and not for continuous rupees. That is a real limit
    of this implementation, reported as `null` rather than papered over with a
    regressor the Tier 1 validation never covered.
    """
    out = {
        "IPS": ips_value(outcome, logged_action, p_contact, target, n_boot=500, seed=seed),
        "SNIPS": snips_value(outcome, logged_action, p_contact, target, n_boot=500, seed=seed),
    }
    if with_dr:
        try:
            out["DR"] = doubly_robust_value(
                outcome, logged_action, X, p_contact, target,
                outcome_model=GradientBoostingClassifier(random_state=seed),
                n_folds=5, n_boot=500, seed=seed,
            )
        except Exception as exc:  # noqa: BLE001 — the failure is the finding
            out["DR"] = None
            out["_dr_error"] = f"{type(exc).__name__}: {exc}"
    return out


def _render(estimates, truth) -> dict:
    rendered = {}
    for k, v in estimates.items():
        if k.startswith("_"):
            rendered[k] = v
        elif v is None:
            rendered[k] = None
        else:
            rendered[k] = {
                "point": round(v.point_estimate, 4),
                "ci_low": round(v.ci_low, 4),
                "ci_high": round(v.ci_high, 4),
                "error": round(v.point_estimate - truth, 4),
                "abs_relative_error": (
                    round(abs(v.point_estimate - truth) / abs(truth), 4) if truth else None
                ),
                "covers_truth": bool(v.ci_low <= truth <= v.ci_high),
            }
    return rendered


def run_at_epsilon(epsilon: float, cases, traits, model, churn, greedy, *, seed: int) -> dict:
    n = len(cases)
    X = cases_to_feature_matrix(cases)

    explorer = EpsilonGreedy(epsilon, seed=seed)
    decisions = [explorer.choose(int(g)) for g in greedy]
    logged_action = np.array([d.action for d in decisions], dtype=int)
    # The propensity SCORE, P(contact | x) — not the probability of the action
    # taken. `estimators._match_weights` derives the untreated arm as
    # `1 - propensity`, so handing it the latter makes every weight on an
    # untreated row 1/(1-1). That is what it did before this line was fixed,
    # and IPS came back eight orders of magnitude wrong.
    p_contact = np.array([d.p_contact for d in decisions], dtype=float)

    logged_paid, logged_out = realise(cases, traits, logged_action, seed=EVAL_SEED)
    logged_value = net_value(cases, logged_action, logged_paid, logged_out)

    # The bill for being able to answer any of the questions below: what the
    # deployed policy would have earned, minus what exploring actually earned.
    greedy_paid, greedy_out = realise(cases, traits, greedy, seed=EVAL_SEED)
    greedy_value = net_value(cases, greedy, greedy_paid, greedy_out)
    cost_per_case = float(np.mean(greedy_value) - np.mean(logged_value))

    results = {}
    for name, target in candidate_policies(cases, traits, model, greedy).items():
        t_paid, t_out = realise(cases, traits, target, seed=EVAL_SEED)
        truth_value = float(np.mean(net_value(cases, target, t_paid, t_out)))
        truth_rate = float(np.mean(t_paid))

        results[name] = {
            "truth_net_value_per_case": round(truth_value, 2),
            "truth_payment_rate": round(truth_rate, 4),
            "contact_rate": round(float(np.mean(target)), 4),
            "overlap": overlap_report(logged_action, p_contact, target),
            # The decision-relevant objective: rupees, net of channel cost and
            # of the churn the contact caused.
            "net_value": _render(
                _estimate_set(logged_value, logged_action, p_contact, target, X,
                              seed, with_dr=False),
                truth_value,
            ),
            # The binary outcome, which is what Tier 1 validated the estimators
            # on. Carried so the estimator itself can be checked here too.
            "payment_rate": _render(
                _estimate_set(logged_paid, logged_action, p_contact, target, X,
                              seed, with_dr=True),
                truth_rate,
            ),
        }

    return {
        "epsilon": epsilon,
        "n": n,
        "explored_fraction": round(float(np.mean([d.explored for d in decisions])), 4),
        "logged_contact_rate": round(float(np.mean(logged_action)), 4),
        "logged_net_value_per_case": round(float(np.mean(logged_value)), 2),
        "deployed_true_net_value_per_case": round(float(np.mean(greedy_value)), 2),
        "exploration_cost_per_case": round(cost_per_case, 2),
        "policies": results,
    }


def replicate(epsilon: float, cases, traits, model, greedy, truths, targets,
              *, reps: int, base_seed: int, n_boot: int, metric: str = "net_value") -> dict:
    """Repeat the whole exercise over independent logging draws.

    Coverage from a single log is a coin flip: whether one 95% interval happens
    to contain the truth says almost nothing about whether the method works.
    What matters is the rate over many independent logs, which is what a
    coverage guarantee actually claims. Reported for IPS and SNIPS only —
    DR's cross-fitted gradient boosting is far too slow to run hundreds of
    times, and it gets its own single-log table above.

    The truths are computed once and reused: the cases, the simulator seed and
    the target policies are identical across replications. Only the behaviour
    policy's coin changes, which is the thing being replicated.
    """
    covered = {"IPS": 0, "SNIPS": 0}
    total = {"IPS": 0, "SNIPS": 0}
    abs_err = {"IPS": [], "SNIPS": []}
    ranking_hits = 0
    ranked = 0
    usable_counts = []

    best_true = max(truths, key=truths.get)

    for r in range(reps):
        explorer = EpsilonGreedy(epsilon, seed=base_seed + r * 101)
        decisions = [explorer.choose(int(g)) for g in greedy]
        logged_action = np.array([d.action for d in decisions], dtype=int)
        p_contact = np.array([d.p_contact for d in decisions], dtype=float)

        paid, opted = realise(cases, traits, logged_action, seed=EVAL_SEED)
        # Both metrics are run so the two questions stay separable: is the
        # ESTIMATOR sound (binary payment rate, bounded in [0,1] — what Tier 1
        # validated), and is the OBJECTIVE estimable (net rupees, heavy-tailed
        # because one opt-out on a large subscription costs 4 x 6 x the
        # invoice). If coverage is fine on the first and poor on the second,
        # the tail is the explanation and the method is not at fault.
        value = paid if metric == "payment_rate" else net_value(
            cases, logged_action, paid, opted
        )

        snips_points = {}
        usable_here = 0
        for name, target in targets.items():
            overlap = overlap_report(logged_action, p_contact, target)
            usable_here += int(overlap["usable"])
            if not overlap["identified"]:
                # Not estimable. Counting an unidentified estimand as a miss
                # would understate the method; counting it as a hit would be a
                # lie. It is excluded, and `identified_rate` reports how often
                # that happened.
                continue
            for method, fn in (("IPS", ips_value), ("SNIPS", snips_value)):
                est = fn(value, logged_action, p_contact, target, n_boot=n_boot,
                         seed=base_seed + r)
                total[method] += 1
                covered[method] += int(est.ci_low <= truths[name] <= est.ci_high)
                abs_err[method].append(abs(est.point_estimate - truths[name]))
                if method == "SNIPS":
                    snips_points[name] = est.point_estimate
        usable_counts.append(usable_here)
        if snips_points:
            ranked += 1
            ranking_hits += int(max(snips_points, key=snips_points.get) == best_true)

    return {
        "epsilon": epsilon,
        "metric": metric,
        "replications": reps,
        "best_policy_by_truth": best_true,
        "identified_rate": round(
            sum(total.values()) / max(1, 2 * reps * len(targets)), 3
        ),
        "mean_usable_policies": round(float(np.mean(usable_counts)), 2),
        "coverage": {
            m: (round(covered[m] / total[m], 3) if total[m] else None) for m in covered
        },
        # Rounded to significant figures, not to a fixed number of decimals:
        # net value is in hundreds of rupees and payment rate is in hundredths,
        # and one rounding rule for both reported every payment-rate error as
        # exactly 0.0.
        "mean_abs_error": {
            m: (float(f"{np.mean(abs_err[m]):.4g}") if abs_err[m] else None)
            for m in abs_err
        },
        "ranking_agreement": round(ranking_hits / ranked, 3) if ranked else None,
        "intervals_scored": total,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n-train", type=int, default=5000)
    ap.add_argument("--n-eval", type=int, default=4000)
    ap.add_argument(
        "--epsilons", type=float, nargs="+",
        default=[0.0, 0.05, 0.10, 0.20, 0.40],
    )
    ap.add_argument("--reps", type=int, default=20,
                    help="independent logging draws per epsilon")
    ap.add_argument("--n-boot", type=int, default=300)
    args = ap.parse_args()

    print(f"Training the deployed models on {args.n_train} randomised cases...")
    model, churn = train_models(args.n_train, seed=SEED)

    cases = generate_cases(args.n_eval, seed=EVAL_SEED, now=NOW)
    traits = generate_population(cases, seed=EVAL_SEED)
    greedy = greedy_contact_actions(cases, model, churn)

    tau_hat = model.predict_cate(cases_to_feature_matrix(cases))
    tau_true = np.array([persuadability(traits[c.case_id]) for c in cases])
    corr = float(np.corrcoef(tau_hat, tau_true)[0, 1])
    print(f"Deployed model: corr(tau_hat, tau_true) = {corr:.3f}; "
          f"it would contact {greedy.mean():.1%} of {args.n_eval} cases\n")

    # Truths depend only on the cases and the simulator seed, so they are the
    # same for every epsilon and every replication. Computed once.
    targets = candidate_policies(cases, traits, model, greedy)
    truths = {}
    for name, target in targets.items():
        t_paid, t_out = realise(cases, traits, target, seed=EVAL_SEED)
        truths[name] = float(np.mean(net_value(cases, target, t_paid, t_out)))

    sweep = []
    for eps in args.epsilons:
        print(f"epsilon = {eps:.2f} ...", end=" ", flush=True)
        row = run_at_epsilon(eps, cases, traits, model, churn, greedy, seed=EVAL_SEED + 11)
        sweep.append(row)
        usable = sum(1 for p in row["policies"].values()
                     if isinstance(p, dict) and p["overlap"]["usable"])
        print(f"{usable}/{len(candidate_policies(cases, traits, model, greedy))} "
              f"policies have usable overlap")

    truths_rate = {}
    for name, target in targets.items():
        t_paid, _ = realise(cases, traits, target, seed=EVAL_SEED)
        truths_rate[name] = float(np.mean(t_paid))

    print(f"\nReplicating each epsilon over {args.reps} independent logging draws...")
    replications = []
    for metric, truth_map in (("net_value", truths), ("payment_rate", truths_rate)):
        print(f"  metric: {metric}")
        for eps in args.epsilons:
            rep = replicate(eps, cases, traits, model, greedy, truth_map, targets,
                            reps=args.reps, base_seed=EVAL_SEED + 55,
                            n_boot=args.n_boot, metric=metric)
            replications.append(rep)
            print(f"    eps {eps:.2f}: SNIPS coverage {rep['coverage']['SNIPS']}, "
                  f"ranking agreement {rep['ranking_agreement']}, "
                  f"{rep['mean_usable_policies']:.1f}/{len(targets)} usable")

    out = {
        "replications_per_epsilon": args.reps,
        "truth_net_value_per_case": {k: round(v, 2) for k, v in truths.items()},
        "truth_payment_rate": {k: round(v, 4) for k, v in truths_rate.items()},
        "replication_study": replications,
        "n_train": args.n_train,
        "n_eval": args.n_eval,
        "seed": SEED,
        "eval_seed": EVAL_SEED,
        "uplift_correlation": round(corr, 4),
        "deployed_contact_rate": round(float(greedy.mean()), 4),
        "framing": (
            "single targeting decision per case (contact vs wait) at attempt 0, "
            "evaluated as a contextual bandit; not full-sequence OPE of the "
            "multi-step agent loop"
        ),
        "sweep": sweep,
    }
    (HERE / "results_ope_deployment.json").write_text(json.dumps(out, indent=2))
    print(f"\nWrote {HERE / 'results_ope_deployment.json'}")

    # A readable summary of the headline claim, at the operating epsilon.
    headline = next((r for r in sweep if r["epsilon"] == 0.10), sweep[-1])
    print(f"\nNet value per case, at epsilon = {headline['epsilon']:.2f} "
          f"(exploration cost Rs {abs(headline['exploration_cost_per_case']):.0f}/case):")
    print(f"{'candidate policy':22}{'truth':>10}{'SNIPS':>10}{'covers':>8}{'ESS':>8}")
    for name, row in headline["policies"].items():
        sn = row["net_value"].get("SNIPS")
        print(f"{name:22}{row['truth_net_value_per_case']:>10.0f}"
              f"{(sn['point'] if sn else float('nan')):>10.0f}"
              f"{('yes' if sn and sn['covers_truth'] else 'NO'):>8}"
              f"{row['overlap']['effective_sample_size']:>8.0f}")
    best_true = max(headline["policies"], key=lambda k: headline["policies"][k]["truth_net_value_per_case"])
    best_est = max(headline["policies"],
                   key=lambda k: (headline["policies"][k]["net_value"]["SNIPS"] or {}).get("point", -1e18))
    print(f"\nBest policy by truth: {best_true}")
    print(f"Best policy the logs would have picked: {best_est}")
    print("ranking agrees" if best_true == best_est else "RANKING DISAGREES")


if __name__ == "__main__":
    main()
