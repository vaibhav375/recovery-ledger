"""Certificate format (spec section 9.3) — the receipt every kernel decision
produces. `hash`/`prev_hash` are filled in by the ledger when the certificate
is appended (see agent/loop.py); this module owns only the certificate's own
content and the ALLOW/DENY decision.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel

from recovery_ledger.events.actions import ActionType
from recovery_ledger.events.schemas import Channel


class Decision(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"


class RuleResult(BaseModel):
    rule_name: str
    passed: bool
    detail: dict


class Certificate(BaseModel):
    action_id: str
    case_id: str
    decision: Decision
    action_type: ActionType
    channel: Channel | None
    rule_results: list[RuleResult]
    created_at: datetime

    @property
    def rules_evaluated(self) -> list[str]:
        return [r.rule_name for r in self.rule_results]

    @property
    def denied_rules(self) -> list[str]:
        return [r.rule_name for r in self.rule_results if not r.passed]
