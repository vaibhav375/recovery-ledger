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
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from recovery_ledger.events.actions import ActionType
from recovery_ledger.events.schemas import Channel, RecoveryCase
from recovery_ledger.kernel.certificate import Certificate, Decision, RuleResult


@dataclass
class RuleContext:
    """Everything a compliance rule might need to evaluate one candidate
    action. Deliberately a plain dataclass of primitives/enums — rules must
    stay pure functions of structured state, per spec section 9.1."""

    case: RecoveryCase
    action_type: ActionType
    channel: Channel | None
    now_ist: datetime
    attempts_in_window: int
    attempt_cap: int
    window_days: int


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
