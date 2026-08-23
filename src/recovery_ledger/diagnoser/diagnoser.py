"""Failure taxonomy + root cause attribution (spec section 5.2). Rule-based
taxonomy assignment for now — deterministic, no LLM. LLM narration of "the
why" for the operator dashboard is a documented, separate later addition
(spec section 8.5 table: narration is generation, not decision, so it's
allowed to use an LLM — but nothing here depends on one yet).
"""

from __future__ import annotations

from pydantic import BaseModel

from recovery_ledger.events.schemas import (
    CheckoutAbandonmentCase,
    FailedPaymentCase,
    FailedSubscriptionCase,
    OverdueReceivableCase,
    RecoveryCase,
)


class Diagnosis(BaseModel):
    case_id: str
    taxonomy: str
    root_cause: str
    narration: str


class CaseDiagnoser:
    def diagnose(self, case: RecoveryCase) -> Diagnosis:
        if isinstance(case, FailedPaymentCase):
            taxonomy = "hard_decline" if case.is_hard_decline else "soft_decline"
            root_cause = case.failure_code
        elif isinstance(case, CheckoutAbandonmentCase):
            taxonomy = "abandonment"
            root_cause = "checkout_not_completed"
        elif isinstance(case, FailedSubscriptionCase):
            taxonomy = "involuntary_churn"
            root_cause = f"mandate_retry_{case.retry_count}_status_{case.razorpay_status}"
        elif isinstance(case, OverdueReceivableCase):
            taxonomy = "liquidity_delay"
            root_cause = f"overdue_{case.days_overdue}_days"
        else:  # pragma: no cover - exhaustive over RecoveryCase's Union
            raise TypeError(f"unhandled case type: {type(case)!r}")

        return Diagnosis(
            case_id=case.case_id,
            taxonomy=taxonomy,
            root_cause=root_cause,
            narration=f"{taxonomy}: {root_cause} (rule-based; LLM narration not yet wired)",
        )
