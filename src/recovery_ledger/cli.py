"""`make demo` entry point. Generates synthetic cases, runs each through the
full agent loop (detect → diagnose → decide → gate → act → listen → stop),
and prints a summary plus the ledger's own chain-integrity check — so
running this command is itself a demonstration of B4 (audit trail), not just
a claim about it.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from recovery_ledger.agent.loop import RecoveryAgent
from recovery_ledger.detector.detector import CaseDetector
from recovery_ledger.diagnoser.diagnoser import CaseDiagnoser
from recovery_ledger.executor.executor import SimulatedExecutor
from recovery_ledger.kernel.engine import KernelEngine
from recovery_ledger.kernel.rules.budget import ContactBudgetRule
from recovery_ledger.kernel.rules.opt_out import OptOutRule
from recovery_ledger.kernel.rules.timing import ContactHoursRule
from recovery_ledger.ledger.ledger import Ledger
from recovery_ledger.listener.listener import Listener
from recovery_ledger.policy.decision import DecisionPolicy
from recovery_ledger.sim.generator import generate_cases


def build_default_agent(ledger: Ledger, *, clock) -> RecoveryAgent:
    return RecoveryAgent(
        detector=CaseDetector(),
        diagnoser=CaseDiagnoser(),
        policy=DecisionPolicy(),
        kernel=KernelEngine(rules=[ContactHoursRule(), OptOutRule(), ContactBudgetRule()]),
        executor=SimulatedExecutor(),
        listener=Listener(),
        ledger=ledger,
        clock=clock,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-cases", type=int, default=20)
    parser.add_argument("--seed", type=int, default=20260823)
    parser.add_argument("--out", default="demo_ledger.json")
    args = parser.parse_args()

    # Fixed reference time, not wall-clock: case generation must be fully
    # reproducible from --seed alone, per the project's "deterministic seeds
    # everywhere" rule. Ledger entry *timestamps* still use real wall-clock
    # time (Ledger.append) — that's a true record of when the run happened,
    # which is correct for an audit trail; only the simulated world's clock
    # is pinned.
    now = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)
    cases = generate_cases(args.n_cases, seed=args.seed, now=now)

    ledger = Ledger()
    agent = build_default_agent(ledger, clock=lambda: now)

    print(f"Running {len(cases)} synthetic cases through the agent loop (seed={args.seed})\n")
    stop_reasons: Counter[str] = Counter()
    for case in cases:
        reason = agent.run_case(case)
        stop_reasons[reason.value] += 1
        print(f"  {case.case_id:12s} [{case.loss_type.value:22s}] ₹{case.amount_at_risk:9.2f} -> {reason.value}")

    print(f"\nStop reasons: {dict(stop_reasons)}")
    print(f"Ledger entries: {len(ledger)}")
    print(f"Ledger chain valid: {ledger.verify_chain()}")

    out_path = Path(args.out)
    ledger.write(out_path)
    print(f"Wrote full audit trail to {out_path}")


if __name__ == "__main__":
    main()
