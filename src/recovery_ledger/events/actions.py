"""Shared vocabulary for what the agent can do, and why it stops doing it."""

from __future__ import annotations

from enum import Enum


class ActionType(str, Enum):
    WAIT = "wait"
    RETRY = "retry"
    REROUTE = "reroute"
    NUDGE = "nudge"
    NEGOTIATE = "negotiate"
    ESCALATE_HUMAN = "escalate_human"
    STOP = "stop"


class StopReason(str, Enum):
    """The 11 stopping rules, spec section 10. A case terminates the moment
    any one of these fires; the reason is always written to the ledger."""

    RESOLVED = "resolved"
    OPT_OUT = "opt_out"
    BUDGET_EXHAUSTED = "budget_exhausted"
    NEGATIVE_EV = "negative_ev"
    DO_NOT_DISTURB = "do_not_disturb"
    PROMISE_TO_PAY_ACTIVE = "promise_to_pay_active"
    DISPUTE_RAISED = "dispute_raised"
    HUMAN_ESCALATION_THRESHOLD = "human_escalation_threshold"
    HARD_DECLINE = "hard_decline"
    REGULATORY_CEILING = "regulatory_ceiling"
    GLOBAL_KILL_SWITCH = "global_kill_switch"
