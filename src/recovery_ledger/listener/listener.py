"""Reply-intent listener (spec section 5.6 / 8.5). STUB: no reply channel is
wired yet, so this always reports NO_REPLY. Real LLM-based free-text intent
parsing (paid / promise_to_pay / dispute / opt_out / wrong_person /
negotiate) is a dedicated later phase, validated against a labelled accuracy
set per spec section 11.2. Kept behind this interface now so that swapping
in the real implementation later doesn't require touching the agent loop.
"""

from __future__ import annotations

from enum import Enum
from typing import Protocol

from recovery_ledger.events.actions import ActionType
from recovery_ledger.events.schemas import RecoveryCase


class ReplyIntent(str, Enum):
    PAID = "paid"
    PROMISE_TO_PAY = "promise_to_pay"
    DISPUTE = "dispute"
    OPT_OUT = "opt_out"
    WRONG_PERSON = "wrong_person"
    NEGOTIATE = "negotiate"
    NO_REPLY = "no_reply"


class ListenerProtocol(Protocol):
    def listen(self, case: RecoveryCase, action_type: ActionType, attempt_index: int) -> ReplyIntent: ...


class Listener:
    """Stub: ignores everything it's given and always reports NO_REPLY.
    Kept as the default for `make demo` — no reply channel, real or
    simulated, is wired into the base demo path."""

    def listen(self, case: RecoveryCase, action_type: ActionType, attempt_index: int) -> ReplyIntent:
        return ReplyIntent.NO_REPLY
