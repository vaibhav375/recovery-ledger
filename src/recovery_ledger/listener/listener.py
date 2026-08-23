"""Reply-intent listener (spec section 5.6 / 8.5). STUB: no reply channel is
wired yet, so this always reports NO_REPLY. Real LLM-based free-text intent
parsing (paid / promise_to_pay / dispute / opt_out / wrong_person /
negotiate) is a dedicated later phase, validated against a labelled accuracy
set per spec section 11.2. Kept behind this interface now so that swapping
in the real implementation later doesn't require touching the agent loop.
"""

from __future__ import annotations

from enum import Enum


class ReplyIntent(str, Enum):
    PAID = "paid"
    PROMISE_TO_PAY = "promise_to_pay"
    DISPUTE = "dispute"
    OPT_OUT = "opt_out"
    WRONG_PERSON = "wrong_person"
    NEGOTIATE = "negotiate"
    NO_REPLY = "no_reply"


class Listener:
    def listen(self, case_id: str) -> ReplyIntent:
        return ReplyIntent.NO_REPLY
