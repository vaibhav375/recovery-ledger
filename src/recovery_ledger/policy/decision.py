"""Decision policy (spec section 5.3 / 8.3). STUB: proposes a fixed, small
action sequence per case rather than real EV = Δp_pay × ₹amount − cost −
annoyance decisioning. The real version lands once the Tier 1 uplift
learners are transferred to the domain simulator (spec section 7.3) — this
stub exists so the end-to-end loop is real and runnable before that
transfer happens, per the project's rule 2 (the agent loop must work at
every commit, even with stub components inside it).
"""

from __future__ import annotations

from pydantic import BaseModel

from recovery_ledger.diagnoser.diagnoser import Diagnosis
from recovery_ledger.events.actions import ActionType
from recovery_ledger.events.schemas import Channel, RecoveryCase


class ActionDecision(BaseModel):
    action_type: ActionType
    channel: Channel | None
    rationale: str


class DecisionPolicy:
    """Fixed sequence: nudge once on the customer's preferred channel (SMS if
    unset), then a silent retry, then stop. Every real EV/budget/stopping
    constraint still runs downstream (the kernel and the loop's own stopping
    rules) — this only decides which action gets *proposed*."""

    max_attempts: int = 2

    def decide(self, case: RecoveryCase, diagnosis: Diagnosis, attempts_so_far: int) -> ActionDecision:
        if attempts_so_far >= self.max_attempts:
            return ActionDecision(
                action_type=ActionType.STOP, channel=None,
                rationale=f"stub policy: reached max_attempts={self.max_attempts}",
            )
        if attempts_so_far == 0:
            channel = case.customer.channel_pref or Channel.SMS
            return ActionDecision(
                action_type=ActionType.NUDGE, channel=channel,
                rationale=f"stub policy: first contact via {channel.value} ({diagnosis.taxonomy})",
            )
        return ActionDecision(
            action_type=ActionType.RETRY, channel=None,
            rationale="stub policy: second attempt, silent retry",
        )
