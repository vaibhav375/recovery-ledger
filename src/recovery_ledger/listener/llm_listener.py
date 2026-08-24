"""LLM reply-intent classification (spec section 8.5).

Free-text customer reply → one of the structured intents the agent loop acts
on. This is a legitimate LLM use: the input is natural language in three
languages and the output is a small closed set, which is exactly what
language models are good at and what rules are bad at.

Two design decisions worth stating:

**The output is constrained and validated, never trusted raw.** The model is
asked for a single token from a fixed set; anything it returns that is not
in that set becomes `NO_REPLY`. An unparseable classification must never
become an action, and `NO_REPLY` is the safe default because it causes the
agent to keep waiting rather than to contact anyone.

**Nothing here can authorise an action on its own.** A classification only
ever *narrows* what the agent may do — it can stop a case (opt-out, dispute,
paid) or pause it (promise to pay). Every outbound action still has to clear
the deterministic compliance kernel, which cannot see this module and cannot
import it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from recovery_ledger.events.actions import ActionType
from recovery_ledger.events.schemas import RecoveryCase
from recovery_ledger.listener.listener import ReplyIntent
from recovery_ledger.listener.opt_out_detector import is_opt_out
from recovery_ledger.llm.client import LLMClient, OllamaUnavailableError

CLASSIFIABLE = [
    ReplyIntent.PAID,
    ReplyIntent.PROMISE_TO_PAY,
    ReplyIntent.DISPUTE,
    ReplyIntent.OPT_OUT,
    ReplyIntent.WRONG_PERSON,
    ReplyIntent.NEGOTIATE,
]

SYSTEM = (
    "You classify replies from Indian customers to payment-recovery messages. "
    "Replies may be in English, Hindi, or Hinglish. "
    "Answer with exactly one label and nothing else."
)

_DEFINITIONS = """paid = they say the payment is already made
promise_to_pay = they cannot pay now but commit to paying by some near date
dispute = they contest the amount or say the charge is wrong
opt_out = they want all contact to stop
wrong_person = they say it is not their account or wrong number
negotiate = they want to pay less, in instalments, or are bargaining for terms"""


def _prompt(reply_text: str) -> str:
    return (
        f"Labels:\n{_DEFINITIONS}\n\n"
        f"Customer reply:\n{reply_text}\n\n"
        f"Which single label fits best? Answer with the label only."
    )


def parse_label(raw: str) -> ReplyIntent:
    """Strictly map model output to an intent. Anything unrecognised becomes
    NO_REPLY — the conservative outcome, since it makes the agent wait rather
    than act on a classification it could not read."""
    text = raw.strip().lower()
    for intent in CLASSIFIABLE:                      # exact match first
        if text == intent.value:
            return intent
    hits = [i for i in CLASSIFIABLE if i.value in text]
    if len(hits) == 1:                                # unambiguous substring
        return hits[0]
    return ReplyIntent.NO_REPLY


@dataclass
class LLMListener:
    """Classifies a supplied reply text. `reply_source` provides the text for
    a given case — in simulation that is the persona generator; in a real
    deployment it would be the inbound message webhook."""

    client: LLMClient
    reply_source: "callable[[RecoveryCase, ActionType, int], str | None]"
    fallback: ReplyIntent = ReplyIntent.NO_REPLY
    classified: list[tuple[str, ReplyIntent]] = field(default_factory=list)

    def classify(self, reply_text: str) -> ReplyIntent:
        # Deterministic opt-out check FIRST, overriding the model. Missing an
        # opt-out is a TCCCPR violation, not a missed sale, so it does not get
        # to depend on a language model — see opt_out_detector.py for the
        # measurement that motivated this.
        if is_opt_out(reply_text):
            self.classified.append((reply_text, ReplyIntent.OPT_OUT))
            return ReplyIntent.OPT_OUT
        try:
            raw = self.client.complete(_prompt(reply_text), system=SYSTEM, temperature=0.0)
        except OllamaUnavailableError:
            # A local model being unreachable must degrade to "heard nothing",
            # never to a guessed intent that could terminate a live case.
            return self.fallback
        intent = parse_label(raw)
        self.classified.append((reply_text, intent))
        return intent

    def listen(self, case: RecoveryCase, action_type: ActionType, attempt_index: int) -> ReplyIntent:
        if action_type in (ActionType.WAIT, ActionType.RETRY):
            return ReplyIntent.NO_REPLY          # nothing was sent, so nothing came back
        text = self.reply_source(case, action_type, attempt_index)
        if not text:
            return ReplyIntent.NO_REPLY
        return self.classify(text)
