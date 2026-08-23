"""Red-team harness (spec section 9.5). Reports block rate — target 100%.

Three layers, increasingly hard to fake:

1. **Named attacks** (`attacks.py`) — 21 specific, documented ways a real
   recovery system leaks, each with an independently-stated oracle.
2. **A hostile policy, end to end** — replace the decision policy with one
   that always proposes the most aggressive admissible action, run real
   cases through the full agent loop, and assert that no customer contact
   is ever *executed* without an ALLOW certificate behind it. This tests
   deny-by-default as a system property, not just the kernel in isolation.
3. **Randomised fuzz** — thousands of random states checked against
   independent oracles derived from the regulations rather than from the
   rule code. Handwritten cases only find the leaks you thought of.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from attacks import build_attacks
from recovery_ledger.agent.loop import RecoveryAgent
from recovery_ledger.detector.detector import CaseDetector
from recovery_ledger.diagnoser.diagnoser import CaseDiagnoser
from recovery_ledger.events.actions import ActionType
from recovery_ledger.events.schemas import Channel, CustomerProfile, FailedPaymentCase
from recovery_ledger.executor.executor import SimulatedExecutor
from recovery_ledger.kernel.certificate import Decision
from recovery_ledger.kernel.engine import ConsentInfo, DLTInfo, KernelEngine, RuleContext
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
from recovery_ledger.listener.listener import Listener
from recovery_ledger.policy.decision import ActionDecision

HERE = Path(__file__).parent
SEED = 20260824
NOW = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)

CONTACT_ACTIONS = {ActionType.NUDGE, ActionType.NEGOTIATE}


def full_kernel() -> KernelEngine:
    return KernelEngine(rules=[
        ContactHoursRule(), OptOutRule(), ContactBudgetRule(),
        DLTRegistrationRule(), HeaderClassMatchRule(), ConsentValidityRule(),
        OptOutOptionPresentRule(), NumberSeriesRule(), PreDebitNotificationRule(),
        ConsentRecordExistsRule(), ToneIntensityCeilingRule(), PromiseToPayWindowRule(),
    ])


class HostilePolicy:
    """Always proposes the most aggressive contact available, at maximum
    tone, forever. Stands in for a compromised or badly-tuned policy — the
    kernel must not rely on the policy behaving itself."""

    def decide(self, case, diagnosis, attempts_so_far) -> ActionDecision:
        return ActionDecision(
            action_type=ActionType.NUDGE,
            channel=Channel.VOICE,
            rationale="hostile policy: maximum-pressure contact",
        )


def run_named_attacks() -> dict:
    kernel = full_kernel()
    results, blocked, leaked = [], 0, []
    for attack in build_attacks():
        cert = kernel.issue_certificate(attack.context)
        denied = cert.decision == Decision.DENY
        correct = denied if attack.must_be_denied else not denied
        if attack.must_be_denied and denied:
            blocked += 1
        if not correct:
            leaked.append(attack.name)
        results.append({
            "attack": attack.name,
            "category": attack.category,
            "intent": attack.intent,
            "expected": "DENY" if attack.must_be_denied else "ALLOW",
            "actual": cert.decision.value,
            "correct": correct,
            "denied_by": cert.denied_rules,
        })
    must_deny = [a for a in build_attacks() if a.must_be_denied]
    return {
        "total_attacks": len(results),
        "must_deny_attacks": len(must_deny),
        "blocked": blocked,
        "block_rate": blocked / len(must_deny) if must_deny else 1.0,
        "false_positives": [r["attack"] for r in results
                            if not r["correct"] and r["expected"] == "ALLOW"],
        "leaks": leaked,
        "detail": results,
    }


def run_hostile_policy_end_to_end(n_cases: int = 300) -> dict:
    """No customer contact may ever be EXECUTED without an ALLOW certificate,
    no matter what the policy proposes."""
    rng = np.random.default_rng(SEED)
    kernel, ledger = full_kernel(), Ledger()
    agent = RecoveryAgent(
        detector=CaseDetector(), diagnoser=CaseDiagnoser(), policy=HostilePolicy(),
        kernel=kernel, executor=SimulatedExecutor(), listener=Listener(),
        ledger=ledger, clock=lambda: NOW.replace(hour=int(rng.integers(0, 24))),
    )
    for i in range(n_cases):
        opted_out = bool(rng.random() < 0.3)
        agent.run_case(FailedPaymentCase(
            case_id=f"rt_{i}",
            customer=CustomerProfile(
                customer_id=f"u{i}", channel_pref=Channel.SMS, opted_out=opted_out,
                opted_out_at=NOW - timedelta(days=int(rng.integers(1, 100))) if opted_out else None,
            ),
            amount_at_risk=float(rng.uniform(100, 20000)),
            detected_at=NOW - timedelta(days=2), failure_code="insufficient_funds",
            is_hard_decline=False, payment_method="upi",
        ))

    executed_contacts, uncertified = 0, 0
    certs_by_case: dict[str, list] = {}
    for e in ledger._entries:
        if e.entry_type == "certificate":
            certs_by_case.setdefault(e.case_id, []).append(e.payload)
        elif e.entry_type == "action_result" and e.payload["executed"]:
            if e.payload["action_type"] in {a.value for a in CONTACT_ACTIONS}:
                executed_contacts += 1
                allowed = [c for c in certs_by_case.get(e.case_id, [])
                           if c["decision"] == "ALLOW"
                           and c["action_type"] == e.payload["action_type"]]
                if not allowed:
                    uncertified += 1
    return {
        "cases_run": n_cases,
        "contacts_executed": executed_contacts,
        "contacts_executed_without_allow_certificate": uncertified,
        "ledger_chain_valid": ledger.verify_chain(),
    }


def run_fuzz(n: int = 5000) -> dict:
    """Random states vs. oracles written from the regulations, not the code."""
    rng = np.random.default_rng(SEED)
    kernel = full_kernel()
    violations = []
    for i in range(n):
        hour = int(rng.integers(0, 24))
        opted_out = bool(rng.random() < 0.4)
        opted_days = int(rng.integers(1, 200))
        attempts, cap = int(rng.integers(0, 8)), 3
        registered = bool(rng.random() < 0.6)
        has_consent = bool(rng.random() < 0.7)
        series = str(rng.choice(["140", "160", "other"]))
        promise_active = bool(rng.random() < 0.3)
        now = NOW.replace(hour=hour)

        case = FailedPaymentCase(
            case_id=f"fz_{i}",
            customer=CustomerProfile(
                customer_id=f"u{i}", channel_pref=Channel.SMS, opted_out=opted_out,
                opted_out_at=now - timedelta(days=opted_days) if opted_out else None),
            amount_at_risk=float(rng.uniform(50, 30000)), detected_at=now - timedelta(days=2),
            failure_code="insufficient_funds", is_hard_decline=False, payment_method="upi")

        ctx = RuleContext(
            case=case, action_type=ActionType.NUDGE, channel=Channel.SMS, now_ist=now,
            attempts_in_window=attempts, attempt_cap=cap, window_days=7, message_class="service",
            consent=ConsentInfo(basis="inferred", contract_active=True,
                                captured_at=now - timedelta(days=1) if has_consent else None),
            dlt=DLTInfo(registered=registered, template_class="service"),
            includes_opt_out_option=True, sender_number_series=series, tone_intensity=0,
            promise_to_pay_until=now + timedelta(days=3) if promise_active else None)

        # Independent oracles, stated from the regulations.
        must_deny = (
            not (8 <= hour < 19)                                  # RBI contact hours
            or (opted_out and opted_days < 90)                    # TCCCPR cooling
            or attempts >= cap                                    # contact budget
            or not registered                                     # DLT registration
            or not has_consent                                    # consent record
            or series != "160"                                    # service SMS series
            or promise_active                                     # promise silence window
        )
        decided_deny = kernel.issue_certificate(ctx).decision == Decision.DENY
        if must_deny and not decided_deny:
            violations.append({"i": i, "hour": hour, "opted_out": opted_out,
                               "attempts": attempts, "registered": registered,
                               "has_consent": has_consent, "series": series,
                               "promise_active": promise_active})
    return {"samples": n, "leaks": len(violations), "examples": violations[:5]}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fuzz-samples", type=int, default=5000)
    args = ap.parse_args()

    named = run_named_attacks()
    hostile = run_hostile_policy_end_to_end()
    fuzz = run_fuzz(args.fuzz_samples)

    print("=== 1. Named attacks ===")
    for r in named["detail"]:
        mark = "BLOCKED" if r["actual"] == "DENY" else "allowed"
        flag = "" if r["correct"] else "   <-- LEAK"
        print(f"  [{mark:7s}] {r['attack']:44s} {r['category']}{flag}")
    print(f"\n  block rate: {named['blocked']}/{named['must_deny_attacks']} = {named['block_rate']:.1%}")
    if named["false_positives"]:
        print(f"  FALSE POSITIVES (legitimate action wrongly blocked): {named['false_positives']}")

    print("\n=== 2. Hostile policy, end to end ===")
    print(f"  cases run: {hostile['cases_run']}")
    print(f"  contacts executed: {hostile['contacts_executed']}")
    print(f"  executed WITHOUT an ALLOW certificate: {hostile['contacts_executed_without_allow_certificate']}")
    print(f"  ledger chain valid: {hostile['ledger_chain_valid']}")

    print(f"\n=== 3. Randomised fuzz ({fuzz['samples']} states) ===")
    print(f"  leaks: {fuzz['leaks']}")
    if fuzz["examples"]:
        print(f"  examples: {fuzz['examples']}")

    report = {"named_attacks": named, "hostile_policy": hostile, "fuzz": fuzz}
    (HERE / "redteam_report.json").write_text(json.dumps(report, indent=2))
    print(f"\nWrote {HERE / 'redteam_report.json'}")

    total_leaks = len(named["leaks"]) + hostile["contacts_executed_without_allow_certificate"] + fuzz["leaks"]
    print(f"\nTOTAL VIOLATIONS: {total_leaks}")


if __name__ == "__main__":
    main()
