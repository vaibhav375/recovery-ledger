"""Contact-free recovery — novelty claim N6 (spec section 8.4).

Every other lever in this project works by deciding whether to *contact*
someone. This one recovers revenue by noticing the payment rail is broken
and declining to retry into it — no customer is messaged at all.

Two agents, identical case batch, identical outage:

- **blind** — retries by expected value alone, with no idea an issuer is down
- **fleet-aware** — same policy, plus a detector that has observed the
  attempt stream and flagged the degraded issuer

The detector is never told which issuer is out. It sees only observed
attempts and has to find it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tier2_simulation"))

from run_batch import NOW, SEED, build_kernel, train_models  # noqa: E402

from recovery_ledger.agent.loop import RecoveryAgent  # noqa: E402
from recovery_ledger.detector.detector import CaseDetector  # noqa: E402
from recovery_ledger.detector.fleet import (  # noqa: E402
    DegradedIssuerRegistry,
    FleetDegradationDetector,
)
from recovery_ledger.diagnoser.diagnoser import CaseDiagnoser  # noqa: E402
from recovery_ledger.events.schemas import FailedPaymentCase  # noqa: E402
from recovery_ledger.executor.executor import SimulatedExecutor  # noqa: E402
from recovery_ledger.ledger.ledger import Ledger  # noqa: E402
from recovery_ledger.policy.decision import EVDecisionPolicy  # noqa: E402
from recovery_ledger.sim.environment import (  # noqa: E402
    EnvironmentListener,
    SimulationEnvironment,
    generate_population,
)
from recovery_ledger.sim.fleet_health import generate_fleet_health, synth_history  # noqa: E402
from recovery_ledger.sim.generator import ISSUERS, generate_cases  # noqa: E402

HERE = Path(__file__).parent


def run_arm(name, cases, traits, health, uplift, churn, registry, *, seed):
    env = SimulationEnvironment(traits, seed=seed, fleet_health=health, now=NOW)
    listener = EnvironmentListener(env)
    ledger = Ledger()
    agent = RecoveryAgent(
        detector=CaseDetector(), diagnoser=CaseDiagnoser(),
        policy=EVDecisionPolicy(uplift_model=uplift, churn_model=churn,
                                degraded_issuers=registry),
        kernel=build_kernel(), executor=SimulatedExecutor(), listener=listener,
        ledger=ledger, clock=lambda: NOW,
    )
    for c in cases:
        agent.run_case(c)

    decisions = [e for e in ledger._entries if e.entry_type == "decision"]
    retries = [e for e in decisions if e.payload.get("action_type") == "retry"]
    nudges = [e for e in decisions if e.payload.get("action_type") == "nudge"]

    out_issuers = {o.issuer for o in health.outages}
    by_id = {c.case_id: c for c in cases}
    wasted = sum(
        1 for e in retries
        if isinstance(by_id.get(e.case_id), FailedPaymentCase)
        and by_id[e.case_id].issuer in out_issuers
    )
    affected = [c for c in cases
                if isinstance(c, FailedPaymentCase) and c.issuer in out_issuers]
    recovered_affected = sum(c.amount_at_risk for c in affected
                             if c.case_id in listener.paid_cases)

    return {
        "arm": name,
        "gross_recovered": float(sum(c.amount_at_risk for c in cases
                                     if c.case_id in listener.paid_cases)),
        "retries": len(retries),
        "retries_into_degraded_issuer": wasted,
        "contacts": len(nudges),
        "cases_on_degraded_issuer": len(affected),
        "recovered_on_degraded_issuer": float(recovered_affected),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n-train", type=int, default=5000)
    ap.add_argument("--n-eval", type=int, default=2000)
    args = ap.parse_args()

    uplift, churn = train_models(args.n_train, seed=SEED)

    eval_seed = SEED + 3000
    cases = generate_cases(args.n_eval, seed=eval_seed, now=NOW)
    traits = generate_population(cases, seed=eval_seed)
    health = generate_fleet_health(ISSUERS, now=NOW, seed=11)
    truth = sorted(o.issuer for o in health.outages)

    detector = FleetDegradationDetector()
    # 25 attempts/hour/issuer -> 150 recent observations, comfortably above the
    # detector's minimum. See MIN_RECENT_ATTEMPTS for why that floor exists.
    detector.observe_many(synth_history(ISSUERS, health, now=NOW, seed=11, attempts_per_hour=25))
    found = detector.detect(NOW)
    registry = DegradedIssuerRegistry().update_from(found)
    attributed = detector.attribute(NOW)

    print(f"Ground-truth outage: {truth}")
    print(f"Detector flagged   : {sorted(registry.degraded)}   "
          f"{'CORRECT' if sorted(registry.degraded) == truth else 'MISMATCH'}")
    if attributed:
        print(f"Attribution: {attributed.narrate()}")

    blind = run_arm("blind", cases, traits, health, uplift, churn, None, seed=eval_seed + 1)
    aware = run_arm("fleet_aware", cases, traits, health, uplift, churn, registry, seed=eval_seed + 1)

    print(f"\n{'':16s} {'gross Rs':>12s} {'retries':>8s} {'wasted':>7s} {'contacts':>9s} {'Rs on outage':>13s}")
    for r in (blind, aware):
        print(f"  {r['arm']:14s} {r['gross_recovered']:>12,.0f} {r['retries']:>8d} "
              f"{r['retries_into_degraded_issuer']:>7d} {r['contacts']:>9d} "
              f"{r['recovered_on_degraded_issuer']:>13,.0f}")

    saved = blind["retries_into_degraded_issuer"] - aware["retries_into_degraded_issuer"]
    delta = aware["gross_recovered"] - blind["gross_recovered"]
    on_outage = aware["recovered_on_degraded_issuer"] - blind["recovered_on_degraded_issuer"]
    print(f"\nFutile retries avoided        : {saved}")
    print(f"Gross recovery change         : {delta:+,.0f}")
    print(f"  of which on outage-hit cases: {on_outage:+,.0f}")
    print(f"Extra contacts used           : {aware['contacts'] - blind['contacts']:+d}")

    report = {"ground_truth_outage": truth, "detected": sorted(registry.degraded),
              "detection_correct": sorted(registry.degraded) == truth,
              "attribution": attributed.narrate() if attributed else None,
              "blind": blind, "fleet_aware": aware,
              "futile_retries_avoided": saved, "gross_recovery_change": delta,
              "recovery_change_on_outage_cases": on_outage}
    (HERE / "results_fleet.json").write_text(json.dumps(report, indent=2))
    print(f"\nWrote {HERE / 'results_fleet.json'}")


if __name__ == "__main__":
    main()
