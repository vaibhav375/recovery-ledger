"""Tier 2 batch experiment — the B1 headline deliverable.

Two phases:

1. TRAIN: generate a batch of cases, randomly assign contact/no-contact
   50/50 (a mini RCT, same logic Tier 1 validated on real data), run them
   through the simulator's response model, and fit a T-learner (the same
   class from policy/uplift/learners.py that Tier 1 validated) on the
   result. This is the "transfer" spec section 7.3 describes: the causal
   *method* was proven on Criteo/Hillstrom; only the *simulator* is new
   here, and it only needs to be plausible, not probative.

2. EVAL: generate a FRESH, disjoint batch of cases (different seed — no
   overlap with training), split it 50/50 into a treatment arm (runs the
   full agent loop with the fitted EVDecisionPolicy) and a randomised
   no-contact holdout arm (DoNothingPolicy). Both arms go through the same
   RecoveryAgent machinery — same kernel, same ledger, same detector — so
   the only difference between arms is the policy.

Headline metric: incremental rupees recovered per 1,000 at-risk cases,
treatment arm minus holdout arm, with a bootstrap 95% CI (spec section
11.1). Never report gross alone — both are printed, with the gap between
them being the actual point (a nontrivial holdout recovery rate is direct
evidence that gross reporting overstates what any intervention added).

CLAIM SCOPE (spec sections 0, 2, 7 — read this before trusting a number
here): this experiment demonstrates POLICY DOMINANCE UNDER STATED
ASSUMPTIONS, IN SIMULATION. It does not and cannot claim a real-world
effect size — the response model's specific numbers are invented (see
sim/environment.py's module docstring). What's being tested here is
whether the causal-inference-driven policy beats a no-contact baseline
*given this simulator's assumptions*, not what it would recover in
production.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from recovery_ledger.agent.loop import RecoveryAgent
from recovery_ledger.agent.runner import BatchRunner, exception_report
from recovery_ledger.detector.detector import CaseDetector
from recovery_ledger.diagnoser.diagnoser import CaseDiagnoser
from recovery_ledger.events.actions import ActionType
from recovery_ledger.executor.executor import SimulatedExecutor
from recovery_ledger.kernel.engine import KernelEngine
from recovery_ledger.kernel.rules.budget import ContactBudgetRule
from recovery_ledger.kernel.rules.dpdp import ConsentRecordExistsRule
from recovery_ledger.kernel.rules.emandate_2026 import PreDebitNotificationRule
from recovery_ledger.kernel.rules.escalation import ToneIntensityCeilingRule
from recovery_ledger.kernel.rules.opt_out import OptOutRule
from recovery_ledger.kernel.rules.promise import PromiseToPayWindowRule
from recovery_ledger.kernel.rules.tcccpr import (
    ConsentValidityRule,
    DLTRegistrationRule,
    HeaderClassMatchRule,
    NumberSeriesRule,
    OptOutOptionPresentRule,
)
from recovery_ledger.kernel.rules.timing import ContactHoursRule
from recovery_ledger.ledger.ledger import Ledger
from recovery_ledger.policy.decision import DoNothingPolicy, LookaheadEVDecisionPolicy
from recovery_ledger.policy.features import cases_to_feature_matrix
from recovery_ledger.policy.uplift.learners import TLearnerModel
from recovery_ledger.sim.environment import EnvironmentListener, SimulationEnvironment, generate_population, persuadability
from recovery_ledger.sim.generator import generate_cases

SEED = 20260823
NOW = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)
HERE = Path(__file__).parent


def build_kernel() -> KernelEngine:
    return KernelEngine(rules=[
        ContactHoursRule(), OptOutRule(), ContactBudgetRule(),
        DLTRegistrationRule(), HeaderClassMatchRule(), ConsentValidityRule(),
        OptOutOptionPresentRule(), NumberSeriesRule(),
        PreDebitNotificationRule(), ConsentRecordExistsRule(), ToneIntensityCeilingRule(),
        PromiseToPayWindowRule(),
    ])


def train_uplift_model(n_train: int, seed: int) -> TLearnerModel:
    cases = generate_cases(n_train, seed=seed, now=NOW)
    traits = generate_population(cases, seed=seed)
    env = SimulationEnvironment(traits, seed=seed)

    rng = np.random.default_rng(seed)
    treatment = rng.integers(0, 2, size=n_train)  # 0=no contact, 1=one nudge

    outcomes = np.zeros(n_train)
    for i, case in enumerate(cases):
        action = ActionType.NUDGE if treatment[i] == 1 else ActionType.WAIT
        result = env.step(case, action, attempt_index=0)
        outcomes[i] = float(result.paid)

    X = cases_to_feature_matrix(cases)
    model = TLearnerModel(random_state=seed)
    model.fit(X, treatment, outcomes)
    return model


def _bootstrap_ci(treated_values: np.ndarray, control_values: np.ndarray, *, n_boot: int, seed: int) -> tuple[float, float, float]:
    rng = np.random.default_rng(seed)
    point = float(treated_values.mean() - control_values.mean())
    boot = np.empty(n_boot)
    for b in range(n_boot):
        t_sample = rng.choice(treated_values, size=len(treated_values), replace=True)
        c_sample = rng.choice(control_values, size=len(control_values), replace=True)
        boot[b] = t_sample.mean() - c_sample.mean()
    lo, hi = np.quantile(boot, [0.025, 0.975])
    return point, float(lo), float(hi)


def run_eval(n_eval: int, uplift_model: TLearnerModel, *, seed: int) -> dict:
    cases = generate_cases(n_eval, seed=seed, now=NOW)
    traits = generate_population(cases, seed=seed)

    rng = np.random.default_rng(seed + 1)
    is_treatment = rng.integers(0, 2, size=n_eval).astype(bool)
    treatment_cases = [c for c, t in zip(cases, is_treatment) if t]
    holdout_cases = [c for c, t in zip(cases, is_treatment) if not t]

    env = SimulationEnvironment(traits, seed=seed + 2)
    listener = EnvironmentListener(env)
    ledger = Ledger()
    kernel = build_kernel()
    detector, diagnoser, executor = CaseDetector(), CaseDiagnoser(), SimulatedExecutor()

    treatment_agent = RecoveryAgent(
        detector=detector, diagnoser=diagnoser, policy=LookaheadEVDecisionPolicy(uplift_model=uplift_model),
        kernel=kernel, executor=executor, listener=listener, ledger=ledger, clock=lambda: NOW,
    )
    holdout_agent = RecoveryAgent(
        detector=detector, diagnoser=diagnoser, policy=DoNothingPolicy(),
        kernel=kernel, executor=executor, listener=listener, ledger=ledger, clock=lambda: NOW,
    )

    # Run through the resumption queue rather than a single pass, so a case
    # that pauses on a promise-to-pay actually gets picked up again after the
    # promised date rather than being abandoned mid-negotiation.
    treatment_result = BatchRunner(treatment_agent).run(treatment_cases, now=NOW)
    holdout_result = BatchRunner(holdout_agent).run(holdout_cases, now=NOW)

    treatment_recovered = np.array([
        case.amount_at_risk if case.case_id in listener.paid_cases else 0.0 for case in treatment_cases
    ])
    holdout_recovered = np.array([
        case.amount_at_risk if case.case_id in listener.paid_cases else 0.0 for case in holdout_cases
    ])

    point, ci_low, ci_high = _bootstrap_ci(treatment_recovered, holdout_recovered, n_boot=2000, seed=seed)
    scale = 1000.0

    # Sanity check kept as a permanent, printed part of every run, not a
    # one-off manual check: is the uplift model's prediction actually
    # correlated with the true (hidden, never-seen-by-the-model)
    # persuadability? Near-zero here means the model isn't learning real
    # heterogeneity and every downstream targeting claim is unsupported —
    # this is exactly the failure mode found and fixed 2026-08-24.
    X_eval = cases_to_feature_matrix(cases)
    tau_hat_eval = uplift_model.predict_cate(X_eval)
    tau_true_eval = np.array([persuadability(traits[c.case_id]) for c in cases])
    uplift_model_correlation = float(np.corrcoef(tau_hat_eval, tau_true_eval)[0, 1])

    stop_reason_counts = treatment_result.stop_reason_counts()
    exceptions = exception_report(treatment_result)

    n_contacts = sum(
        1 for e in ledger._entries
        if e.entry_type == "decision" and e.payload.get("action_type") == "nudge"
    )
    do_not_disturb_contacts = sum(
        1 for e in ledger._entries
        if e.entry_type == "decision" and e.payload.get("action_type") == "nudge"
        and persuadability(traits[e.case_id]) < 0
    )

    return {
        "n_eval": n_eval,
        "n_treatment": len(treatment_cases),
        "n_holdout": len(holdout_cases),
        "uplift_model_correlation_with_true_persuadability": uplift_model_correlation,
        "gross_treatment_recovered": float(treatment_recovered.sum()),
        "gross_holdout_recovered": float(holdout_recovered.sum()),
        "treatment_recovery_rate": float((treatment_recovered > 0).mean()),
        "holdout_recovery_rate": float((holdout_recovered > 0).mean()),
        "incremental_per_1000_cases": {
            "point": point * scale, "ci_low": ci_low * scale, "ci_high": ci_high * scale,
        },
        "contacts_sent": n_contacts,
        "contacts_sent_to_do_not_disturbs": do_not_disturb_contacts,
        "pct_contacts_to_do_not_disturbs": (do_not_disturb_contacts / n_contacts) if n_contacts else None,
        "stop_reason_counts": stop_reason_counts,
        "distinct_stop_reasons_fired": len(stop_reason_counts),
        "unresolved_exceptions": len(exceptions),
        "ledger_entries": len(ledger),
        "ledger_chain_valid": ledger.verify_chain(),
    }, ledger


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-train", type=int, default=5000)
    parser.add_argument("--n-eval", type=int, default=1000)
    args = parser.parse_args()

    print(f"Training uplift model on {args.n_train} randomised-contact cases...")
    model = train_uplift_model(args.n_train, seed=SEED)

    print(f"Running eval batch: {args.n_eval} cases split into treatment/holdout arms...")
    results, ledger = run_eval(args.n_eval, model, seed=SEED + 1000)

    print(json.dumps(results, indent=2))

    (HERE / "results.json").write_text(json.dumps(results, indent=2))
    ledger.write(HERE / "batch_ledger.json")
    print(f"\nWrote {HERE / 'results.json'} and {HERE / 'batch_ledger.json'}")


if __name__ == "__main__":
    main()
