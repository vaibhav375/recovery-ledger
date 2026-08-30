"""What the agent's silences cost, and what they saved.

Every refusal to contact is a bet that contacting would not have paid. Some of
those bets are wrong. This module prices both sides of the account, because
reporting only the cost would be self-flagellation with the same dishonesty as
reporting only gross recovery, and reporting only the saving would be
marketing.

The module deliberately does not import the simulator. It attributes and prices
refusals given a true per-case uplift that someone else supplies, so it can be
tested against constructed cases where the answer is exact.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import Enum

from recovery_ledger.events.actions import ActionType, StopReason

# Actions that reach a customer. RETRY and REROUTE move money on the payment
# rails without messaging anyone, which is the entire content of claim N6.
CONTACT_ACTIONS = frozenset({ActionType.NUDGE.value, ActionType.NEGOTIATE.value})


class Bucket(str, Enum):
    """Why a case was never contacted."""

    MANDATORY = "mandatory"              # a rule forbade it
    MODEL_JUDGEMENT = "model_judgement"  # the agent chose
    ALLOCATION = "allocation"            # it ran out of attempts
    CASE_STATE = "case_state"            # it ended for unrelated reasons
    DEFERRED = "deferred"                # handed to a human; not a refusal


BUCKET_BY_STOP_REASON: dict[str, Bucket] = {
    StopReason.OPT_OUT.value: Bucket.MANDATORY,
    StopReason.PROMISE_TO_PAY_ACTIVE.value: Bucket.MANDATORY,
    StopReason.REGULATORY_CEILING.value: Bucket.MANDATORY,
    StopReason.GLOBAL_KILL_SWITCH.value: Bucket.MANDATORY,
    StopReason.NEGATIVE_EV.value: Bucket.MODEL_JUDGEMENT,
    StopReason.DO_NOT_DISTURB.value: Bucket.MODEL_JUDGEMENT,
    StopReason.BUDGET_EXHAUSTED.value: Bucket.ALLOCATION,
    StopReason.DISPUTE_RAISED.value: Bucket.CASE_STATE,
    StopReason.HARD_DECLINE.value: Bucket.CASE_STATE,
    StopReason.HUMAN_ESCALATION_THRESHOLD.value: Bucket.DEFERRED,
}


@dataclass(frozen=True)
class DeclinedCase:
    case_id: str
    amount_at_risk: float
    tau_true: float
    bucket: Bucket
    stop_reason: str

    @property
    def forgone(self) -> float:
        """Rupees refusing cost. Zero when contact would have done harm."""
        return self.amount_at_risk * self.tau_true if self.tau_true > 0 else 0.0

    @property
    def avoided(self) -> float:
        """Rupees refusing saved. Zero when contact would have helped."""
        return -self.amount_at_risk * self.tau_true if self.tau_true < 0 else 0.0

    @property
    def is_model_error(self) -> bool:
        """The agent judged this customer not worth contacting, and it was
        wrong. Only meaningful where the agent actually made the call."""
        return self.bucket is Bucket.MODEL_JUDGEMENT and self.tau_true > 0


@dataclass(frozen=True)
class RegretTotals:
    n: int
    cost: float
    saved: float
    net: float
    model_errors: int


def was_contacted(entries: Iterable) -> bool:
    """Did any customer-facing action actually execute for this case?

    Reads `action_result`, not `decision`: a nudge the policy proposed and the
    kernel denied falls back to WAIT and never reaches the customer, so
    counting decisions would record a contact that did not happen.
    """
    return any(
        e.entry_type == "action_result"
        and bool(e.payload.get("executed"))
        and e.payload.get("action_type") in CONTACT_ACTIONS
        for e in entries
    )


def classify(stop_reason: str | None, *, kernel_denied_contact: bool) -> Bucket:
    """Which bucket a refusal belongs to.

    A kernel denial outranks the stop reason. If the agent proposed contact and
    the compliance kernel refused it, the binding constraint was the rule, not
    the policy's judgement — whatever reason the case eventually terminated on.
    """
    if kernel_denied_contact:
        return Bucket.MANDATORY
    if stop_reason is None:
        return Bucket.CASE_STATE
    return BUCKET_BY_STOP_REASON.get(stop_reason, Bucket.CASE_STATE)


def _in_scope(declined: Iterable[DeclinedCase]) -> list[DeclinedCase]:
    return [d for d in declined if d.bucket is not Bucket.DEFERRED]


def regret_totals(declined: Sequence[DeclinedCase]) -> RegretTotals:
    rows = _in_scope(declined)
    cost = sum(d.forgone for d in rows)
    saved = sum(d.avoided for d in rows)
    return RegretTotals(
        n=len(rows), cost=cost, saved=saved, net=saved - cost,
        model_errors=sum(1 for d in rows if d.is_model_error),
    )


def totals_by_bucket(declined: Sequence[DeclinedCase]) -> dict[Bucket, RegretTotals]:
    grouped: dict[Bucket, list[DeclinedCase]] = {}
    for row in _in_scope(declined):
        grouped.setdefault(row.bucket, []).append(row)
    return {b: regret_totals(rows) for b, rows in grouped.items()}
