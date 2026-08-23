"""Simulated channel adapters (spec section 5.5 / non-goals section 2: no
real WhatsApp/SMS/voice integration — simulated adapters behind an
interface, one may be wired to a real sandbox later if time permits). Every
adapter here just records what *would* have been sent; nothing leaves the
process.
"""

from __future__ import annotations

from pydantic import BaseModel

from recovery_ledger.events.actions import ActionType
from recovery_ledger.events.schemas import Channel
from recovery_ledger.kernel.certificate import Certificate, Decision


class ActionResult(BaseModel):
    executed: bool
    action_type: ActionType
    channel: Channel | None
    detail: str


class SimulatedExecutor:
    def execute(self, certificate: Certificate) -> ActionResult:
        if certificate.decision != Decision.ALLOW:
            return ActionResult(
                executed=False, action_type=certificate.action_type, channel=certificate.channel,
                detail=f"not executed: certificate denied ({certificate.denied_rules})",
            )
        return ActionResult(
            executed=True, action_type=certificate.action_type, channel=certificate.channel,
            detail=f"simulated {certificate.action_type.value} via {certificate.channel.value if certificate.channel else 'n/a'}",
        )
