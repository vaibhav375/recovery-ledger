"""5-baseline comparison (spec section 11.3) — "a chart of these five on
incremental-₹-and-cost axes is the single most persuasive frame in the
video."

All 5 policies run against the SAME eval batch of cases (same population,
same hidden traits), each through its own freshly-seeded
`SimulationEnvironment` and the same `RecoveryAgent`/kernel/ledger
machinery used everywhere else in this project. Incremental ₹ for each
active policy is computed against the do-nothing policy's outcomes on that
same case batch — not a random per-policy holdout split like
`run_batch.py`'s headline number (that remains the authoritative B1 figure;
this script answers a different, complementary question: "how does this
policy rank against 4 named alternatives on the same cases").

CLAIM SCOPE: same as run_batch.py — policy dominance under stated
assumptions, in simulation. See that script's docstring and
experiments/tier2_simulation/REPORT.md before trusting any number here for
anything beyond a relative ranking.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from recovery_ledger.agent.loop import RecoveryAgent
from recovery_ledger.detector.detector import CaseDetector
from recovery_ledger.diagnoser.diagnoser import CaseDiagnoser
from recovery_ledger.executor.executor import SimulatedExecutor
from recovery_ledger.ledger.ledger import Ledger
from recovery_ledger.policy.decision import (
    CHANNEL_COST,
    BlastEveryonePolicy,
    DoNothingPolicy,
    EVDecisionPolicy,
    LookaheadEVDecisionPolicy,
    RandomTargetingPolicy,
    RazorpayCurrentPolicy,
    RulesBasedDunningPolicy,
)
from recovery_ledger.sim.environment import EnvironmentListener, SimulationEnvironment, generate_population, persuadability
from recovery_ledger.sim.generator import generate_cases
from run_batch import NOW, SEED, build_kernel, train_uplift_model

HERE = Path(__file__).parent


def _paired_bootstrap_ci(
    treated_values: np.ndarray, control_values: np.ndarray, *, n_boot: int, seed: int
) -> tuple[float, float, float]:
    """PAIRED bootstrap: both arms here are measured on the SAME cases in the
    same order, so case indices must be resampled ONCE and applied to both
    arms together.

    Using an unpaired bootstrap (resampling each arm independently) on paired
    data throws away the correlation between arms and mis-sizes the interval —
    it was doing exactly that until 2026-08-24. `run_batch.py` keeps the
    unpaired version, which is correct there because its treatment and holdout
    arms are disjoint random splits of different cases.
    """
    assert len(treated_values) == len(control_values), "paired bootstrap needs equal-length arms"
    rng = np.random.default_rng(seed)
    n = len(treated_values)
    point = float(treated_values.mean() - control_values.mean())
    boot = np.empty(n_boot)
    for b in range(n_boot):
        idx = rng.integers(0, n, size=n)
        boot[b] = treated_values[idx].mean() - control_values[idx].mean()
    lo, hi = np.quantile(boot, [0.025, 0.975])
    return point, float(lo), float(hi)


def run_one_policy(policy_name: str, policy, cases, traits, *, seed: int, params=None) -> dict:
    from recovery_ledger.sim.environment import DEFAULT_PARAMS
    env = SimulationEnvironment(traits, seed=seed, params=params or DEFAULT_PARAMS)
    listener = EnvironmentListener(env)
    ledger = Ledger()
    agent = RecoveryAgent(
        detector=CaseDetector(), diagnoser=CaseDiagnoser(), policy=policy,
        kernel=build_kernel(), executor=SimulatedExecutor(), listener=listener,
        ledger=ledger, clock=lambda: NOW,
    )
    for case in cases:
        agent.run_case(case)

    recovered = np.array([
        case.amount_at_risk if case.case_id in listener.paid_cases else 0.0 for case in cases
    ])
    nudge_entries = [
        e for e in ledger._entries
        if e.entry_type == "decision" and e.payload.get("action_type") == "nudge"
    ]
    n_contacts = len(nudge_entries)
    do_not_disturb_contacts = sum(1 for e in nudge_entries if persuadability(traits[e.case_id]) < 0)
    approx_channel_cost = sum(
        CHANNEL_COST.get(_channel_from_decision_payload(e.payload), 0.0) for e in nudge_entries
    )

    return {
        "policy": policy_name,
        "n_cases": len(cases),
        "gross_recovered": float(recovered.sum()),
        "recovery_rate": float((recovered > 0).mean()),
        "mean_recovered_per_case": float(recovered.mean()),
        "contacts_sent": n_contacts,
        "contacts_sent_to_do_not_disturbs": do_not_disturb_contacts,
        "pct_contacts_to_do_not_disturbs": (do_not_disturb_contacts / n_contacts) if n_contacts else None,
        "approx_channel_cost": approx_channel_cost,
        "_recovered": recovered,  # kept for incremental/CI computation, stripped before writing to disk
    }


def _channel_from_decision_payload(payload: dict):
    from recovery_ledger.events.schemas import Channel
    channel_value = payload.get("channel")
    return Channel(channel_value) if channel_value else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-train", type=int, default=5000)
    parser.add_argument("--n-eval", type=int, default=2000)
    args = parser.parse_args()

    print(f"Training uplift model on {args.n_train} randomised-contact cases...")
    uplift_model = train_uplift_model(args.n_train, seed=SEED)

    eval_seed = SEED + 2000  # disjoint from run_batch.py's own eval seed (SEED+1000)
    cases = generate_cases(args.n_eval, seed=eval_seed, now=NOW)
    traits = generate_population(cases, seed=eval_seed)

    policies = {
        "do_nothing": DoNothingPolicy(max_attempts=3),
        "blast_everyone": BlastEveryonePolicy(max_attempts=3),
        "razorpay_current": RazorpayCurrentPolicy(),
        "rules_based_dunning": RulesBasedDunningPolicy(max_attempts=3),
        # Matched-volume control: contacts a random ~45% of cases, landing in
        # the same contact-volume ballpark as the EV policy. This is what makes
        # the efficiency claim falsifiable rather than rhetorical — see
        # REPORT.md, "Does the targeting actually work?".
        "random_targeting": RandomTargetingPolicy(contact_rate=0.45, seed=7),
        "ev_policy_greedy": EVDecisionPolicy(uplift_model=uplift_model),
        "ev_policy_lookahead": LookaheadEVDecisionPolicy(uplift_model=uplift_model),
    }

    print(f"Running {len(policies)} policies against the same {args.n_eval}-case batch...")
    raw_results = {}
    for name, policy in policies.items():
        raw_results[name] = run_one_policy(name, policy, cases, traits, seed=eval_seed + 1)
        r = raw_results[name]
        dnd_pct = f"{r['pct_contacts_to_do_not_disturbs']:.2%}" if r["pct_contacts_to_do_not_disturbs"] is not None else "n/a"
        print(
            f"  {name:20s} recovery_rate={r['recovery_rate']:.4f}  "
            f"gross={r['gross_recovered']:10.2f}  "
            f"contacts={r['contacts_sent']:4d}  "
            f"dnd_contact_rate={dnd_pct}"
        )

    baseline = raw_results["do_nothing"]["_recovered"]
    comparison = []
    for name, r in raw_results.items():
        if name == "do_nothing":
            incremental = {"point": 0.0, "ci_low": 0.0, "ci_high": 0.0}
        else:
            point, ci_low, ci_high = _paired_bootstrap_ci(r["_recovered"], baseline, n_boot=2000, seed=eval_seed)
            incremental = {"point": point * 1000, "ci_low": ci_low * 1000, "ci_high": ci_high * 1000}
        comparison.append({
            "policy": name,
            "gross_recovered": r["gross_recovered"],
            "recovery_rate": r["recovery_rate"],
            "contacts_sent": r["contacts_sent"],
            "contacts_sent_to_do_not_disturbs": r["contacts_sent_to_do_not_disturbs"],
            "pct_contacts_to_do_not_disturbs": r["pct_contacts_to_do_not_disturbs"],
            "approx_channel_cost": r["approx_channel_cost"],
            "incremental_per_1000_cases": incremental,
            "cost_per_incremental_rupee": (
                r["approx_channel_cost"] / incremental["point"] if incremental["point"] > 0 else None
            ),
            # The efficiency metric that actually separates targeting from
            # sheer volume: incremental rupees earned per contact spent.
            "incremental_rupees_per_contact": (
                (r["gross_recovered"] - raw_results["do_nothing"]["gross_recovered"]) / r["contacts_sent"]
                if r["contacts_sent"] else None
            ),
        })

    out = {"n_train": args.n_train, "n_eval": args.n_eval, "eval_seed": eval_seed, "policies": comparison}
    (HERE / "results_baselines.json").write_text(json.dumps(out, indent=2))
    print(f"\nWrote {HERE / 'results_baselines.json'}")

    _plot_comparison(comparison)


def _plot_comparison(comparison: list[dict]) -> None:
    names = [c["policy"] for c in comparison]
    points = [c["incremental_per_1000_cases"]["point"] for c in comparison]
    err_low = [c["incremental_per_1000_cases"]["point"] - c["incremental_per_1000_cases"]["ci_low"] for c in comparison]
    err_high = [c["incremental_per_1000_cases"]["ci_high"] - c["incremental_per_1000_cases"]["point"] for c in comparison]

    fig, ax = plt.subplots(figsize=(9, 6))
    colors = ["#888" if n == "do_nothing" else "#2b6cb0" for n in names]
    colors = ["#2f855a" if n.startswith("ev_policy") else c for n, c in zip(names, colors)]
    ax.bar(names, points, yerr=[err_low, err_high], capsize=5, color=colors)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_ylabel("Incremental ₹ recovered per 1,000 cases\n(vs. do-nothing, same eval batch)")
    ax.set_title("5-baseline comparison — simulation result, not a real-world claim")
    plt.xticks(rotation=20, ha="right")
    fig.tight_layout()
    fig.savefig(HERE / "baselines_comparison.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()
