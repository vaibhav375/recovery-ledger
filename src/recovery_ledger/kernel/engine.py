"""Deny-by-default compliance evaluator (spec section 9.1).

DETERMINISTIC. NO LLM. This module and everything under `kernel/rules/` must
never import an LLM client — enforced mechanically by
`tests/test_kernel_no_llm_imports.py`, not just by convention.

An action is ALLOW only if every registered rule passes. With zero rules
registered, every action is DENY — "no certificate → no action" holds even
in a misconfigured kernel, rather than silently defaulting open.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, Protocol

from recovery_ledger.events.actions import ActionType
from recovery_ledger.events.schemas import Channel, RecoveryCase
from recovery_ledger.kernel.certificate import Certificate, Decision, RuleResult

MessageClass = Literal["promotional", "service", "transactional", "government"]


@dataclass
class ConsentInfo:
    """TCCCPR consent state (spec section 9.2). `basis="inferred"` means
    consent is implied by an active contract/transaction relationship and
    lapses when that relationship ends; `basis="explicit"` means the
    customer affirmatively opted in."""

    basis: Literal["explicit", "inferred"] = "explicit"
    captured_at: datetime | None = None
    contract_active: bool = True


@dataclass
class DLTInfo:
    """DLT (Distributed Ledger Technology — TRAI's telecom scrubbing
    registry) registration state for the template this action would send."""

    registered: bool = True
    header: str | None = None
    template_class: MessageClass = "service"


@dataclass
class MandateInfo:
    """RBI e-mandate 2026 framework state, relevant only when the action is
    a debit attempt (RETRY) against a FailedSubscriptionCase."""

    pre_debit_notice_sent_at: datetime | None = None
    afa_completed: bool = True


@dataclass
class RuleContext:
    """Everything a compliance rule might need to evaluate one candidate
    action. Deliberately a plain dataclass of primitives/enums/small nested
    dataclasses — rules must stay pure functions of structured state, per
    spec section 9.1. Field names deliberately mirror the certificate
    justification example in spec section 9.3."""

    case: RecoveryCase
    action_type: ActionType
    channel: Channel | None
    now_ist: datetime
    attempts_in_window: int
    attempt_cap: int
    window_days: int
    message_class: MessageClass = "service"
    consent: ConsentInfo = field(default_factory=ConsentInfo)
    dlt: DLTInfo = field(default_factory=DLTInfo)
    mandate: MandateInfo = field(default_factory=MandateInfo)
    includes_opt_out_option: bool = True
    sender_number_series: Literal["140", "160", "other"] = "160"
    tone_intensity: int = 0  # 0 (neutral) .. 3 (firm) — see rules/escalation.py


class ComplianceRule(Protocol):
    name: str

    def evaluate(self, context: RuleContext) -> RuleResult: ...


class KernelEngine:
    def __init__(self, rules: list[ComplianceRule]):
        self.rules = rules

    def issue_certificate(self, context: RuleContext) -> Certificate:
        results = [rule.evaluate(context) for rule in self.rules]
        decision = Decision.ALLOW if self.rules and all(r.passed for r in results) else Decision.DENY
        return Certificate(
            action_id=f"act_{uuid.uuid4().hex[:16]}",
            case_id=context.case.case_id,
            decision=decision,
            action_type=context.action_type,
            channel=context.channel,
            rule_results=results,
            created_at=datetime.now(timezone.utc),
        )
