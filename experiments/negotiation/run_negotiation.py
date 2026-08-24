"""The negotiation showpiece (spec section 9.4), as a runnable scenario walk.

Shows the division of labour on real cases:

    Section 43B(h) clock  ->  what leverage exists
    NPV solver            ->  what may be conceded, and whether to bother
    compliance kernel     ->  whether that concession is permitted
    LLM                   ->  the sentence, using only supplied figures

Scenarios are chosen to make the boundaries visible: one where leverage
replaces margin, one where the envelope is tested, one above the autonomy
limit, and one non-MSME counterparty where 43B(h) simply does not apply.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from recovery_ledger.events.actions import ActionType
from recovery_ledger.events.schemas import CustomerProfile, OverdueReceivableCase
from recovery_ledger.kernel.certificate import Decision
from recovery_ledger.kernel.engine import KernelEngine, RuleContext
from recovery_ledger.kernel.rules.negotiation import NegotiationEnvelopeRule
from recovery_ledger.llm.client import build_default_client
from recovery_ledger.negotiation.clock import evaluate_43bh
from recovery_ledger.negotiation.drafter import NegotiationDrafter
from recovery_ledger.negotiation.solver import NegotiationSolver, PolicyEnvelope

HERE = Path(__file__).parent
NOW = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)

SCENARIOS = [
    ("Leverage instead of margin",
     dict(amount=340_000, days_since_due=32, msme=True, delay=75),
     "Inside the counterparty's own 45-day window: they already have a tax reason to settle."),
    ("Window breached, economics justify a discount",
     dict(amount=180_000, days_since_due=80, msme=True, delay=120),
     "Leverage is gone, so a real concession is now on the table."),
    ("Above the agent's autonomy limit",
     dict(amount=900_000, days_since_due=50, msme=True, delay=90),
     "Too large to settle autonomously - must go to a human."),
    ("Non-MSME counterparty",
     dict(amount=250_000, days_since_due=70, msme=False, delay=90),
     "Section 43B(h) does not apply; ordinary commercial negotiation only."),
]


def build():
    return (
        NegotiationSolver(envelope=PolicyEnvelope()),
        KernelEngine(rules=[NegotiationEnvelopeRule()]),
        NegotiationDrafter(client=build_default_client()),
    )


def run_scenario(name, cfg, note, solver, kernel, drafter) -> dict:
    case = OverdueReceivableCase(
        case_id=name.lower().replace(" ", "_")[:40],
        customer=CustomerProfile(customer_id="buyer", is_b2b=True),
        amount_at_risk=cfg["amount"], detected_at=NOW,
        invoice_id="INV-1", due_date=NOW - timedelta(days=cfg["days_since_due"]),
        days_overdue=cfg["days_since_due"], is_msme_counterparty=cfg["msme"],
    )
    status = evaluate_43bh(invoice_due_date=case.due_date, now=NOW,
                           is_msme_counterparty=case.is_msme_counterparty,
                           amount=case.amount_at_risk)
    offer = solver.best_offer(
        amount=case.amount_at_risk, expected_delay_days=cfg["delay"],
        days_until_43bh_deadline=(status.days_until_deadline
                                  if status.applies and not status.breached else None),
    )
    certificate = kernel.issue_certificate(RuleContext(
        case=case, action_type=ActionType.NEGOTIATE, channel=None, now_ist=NOW,
        attempts_in_window=0, attempt_cap=3, window_days=7,
        offer_discount_pct=offer.discount_pct,
        offer_extension_days=offer.extension_days,
        offer_instalments=offer.instalments,
    ))
    # Only draft if the kernel permitted the action. A denied action must not
    # produce an outbound message -- an earlier version of this script drafted
    # and displayed one anyway, which read as though the agent would send it.
    if certificate.decision == Decision.DENY:
        message = None
    else:
        message = drafter.draft(amount=case.amount_at_risk, offer=offer, status=status)

    print(f"\n=== {name} ===")
    print(f"  {note}")
    print(f"  Rs {case.amount_at_risk:,.0f} | {cfg['days_since_due']}d past due | MSME={case.is_msme_counterparty}")
    print(f"  43B(h)  : {status.urgency}"
          + (f"  ({status.days_until_deadline}d left)" if status.applies else ""))
    print(f"  solver  : {offer.offer_type.value}  {offer.discount_pct:.2%}")
    print(f"            {offer.rationale}")
    print(f"  kernel  : {certificate.decision.value}"
          + (f"   <- {certificate.denied_rules}" if certificate.decision == Decision.DENY else ""))
    if message is None:
        print("  message : NOT DRAFTED - kernel denied the action, so nothing is sent")
    else:
        print(f"  message : ({'LLM' if message.used_llm else 'template'}) {message.text}")

    return {
        "scenario": name, "amount": case.amount_at_risk,
        "43bh_urgency": status.urgency,
        "43bh_days_left": status.days_until_deadline if status.applies else None,
        "offer_type": offer.offer_type.value, "discount_pct": offer.discount_pct,
        "solver_rationale": offer.rationale,
        "kernel_decision": certificate.decision.value,
        "kernel_denied_rules": certificate.denied_rules,
        "message": message.text if message else None,
        "message_from_llm": message.used_llm if message else False,
        "message_suppressed_by_kernel": message is None,
    }


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    solver, kernel, drafter = build()
    results = [run_scenario(n, c, note, solver, kernel, drafter) for n, c, note in SCENARIOS]
    (HERE / "results_negotiation.json").write_text(json.dumps(results, indent=2))
    print(f"\nWrote {HERE / 'results_negotiation.json'}")


if __name__ == "__main__":
    main()
