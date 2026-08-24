"""Reply-intent classification: strict parsing, safe failure, and the
deterministic opt-out floor.

None of these need Ollama — the LLM is mocked. What is being tested is the
logic around the model, which is where the safety properties live.
"""

from __future__ import annotations

import pytest

from recovery_ledger.events.actions import ActionType
from recovery_ledger.events.schemas import Channel, CustomerProfile, FailedPaymentCase
from recovery_ledger.listener.listener import ReplyIntent
from recovery_ledger.listener.llm_listener import LLMListener, parse_label
from recovery_ledger.listener.opt_out_detector import is_opt_out, matched_patterns
from recovery_ledger.llm.client import MockLLMClient, OllamaClient

from datetime import datetime, timezone

NOW = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)


def _case():
    return FailedPaymentCase(
        case_id="c1", customer=CustomerProfile(customer_id="u1", channel_pref=Channel.SMS),
        amount_at_risk=500.0, detected_at=NOW, failure_code="insufficient_funds",
        is_hard_decline=False, payment_method="upi",
    )


@pytest.mark.parametrize("raw,expected", [
    ("paid", ReplyIntent.PAID),
    ("  OPT_OUT  ", ReplyIntent.OPT_OUT),
    ("label: promise_to_pay", ReplyIntent.PROMISE_TO_PAY),
])
def test_valid_labels_parse(raw, expected):
    assert parse_label(raw) == expected


@pytest.mark.parametrize("raw", ["banana", "", "paid or dispute", "I think maybe negotiate or paid"])
def test_unparseable_output_becomes_no_reply(raw):
    """An unreadable classification must never become an action. NO_REPLY is
    the safe default: it makes the agent wait rather than contact anyone."""
    assert parse_label(raw) == ReplyIntent.NO_REPLY


def test_unreachable_model_degrades_to_no_reply_not_a_guess():
    listener = LLMListener(client=OllamaClient(host="http://localhost:1", timeout_seconds=0.5),
                           reply_source=lambda *a: "anything")
    assert listener.classify("I will pay tomorrow") == ReplyIntent.NO_REPLY


def test_silent_actions_never_produce_a_reply():
    """Nothing was sent, so nothing can have come back."""
    listener = LLMListener(client=MockLLMClient(default_response="paid"),
                           reply_source=lambda *a: "I already paid")
    for action in (ActionType.WAIT, ActionType.RETRY):
        assert listener.listen(_case(), action, 0) == ReplyIntent.NO_REPLY


def test_opt_out_is_detected_deterministically_across_languages():
    for text in [
        "Stop messaging me, remove my number",
        "please unsubscribe me",
        "mujhe aur message mat bhejo",
        "bas karo, ab koi message nahi chahiye",
        "मुझे और संदेश मत भेजिए",
        "कृपया मुझसे दोबारा संपर्क न करें",
    ]:
        assert is_opt_out(text), text


def test_opt_out_detector_does_not_fire_on_other_intents():
    """False positives cost revenue; the detector still must not fire on a
    dispute. 'band kar diya' (I cancelled it) is a dispute, not 'band karo'
    (stop it) — a real false positive this pattern once produced."""
    for text in [
        "maine to subscription band kar diya tha, phir charge kyun hua",
        "I will pay on the 5th when my salary comes",
        "ye amount galat hai",
        "can I pay in instalments",
    ]:
        assert not is_opt_out(text), text


def test_opt_out_overrides_a_wrong_model_answer():
    """The compliance-critical property. Measured recall for opt-out from the
    LLM alone was 0.57 on the gold set; this override is why the combined
    system reaches 1.00. Missing an opt-out is a TCCCPR violation, so it must
    not depend on the model being right."""
    listener = LLMListener(
        client=MockLLMClient(default_response="wrong_person"),   # model is wrong
        reply_source=lambda *a: None,
    )
    assert listener.classify("कृपया मुझसे दोबारा संपर्क न करें") == ReplyIntent.OPT_OUT


def test_matched_patterns_are_reportable_for_the_audit_trail():
    hits = matched_patterns("mujhe aur message mat bhejo, number hata do")
    assert hits, "a deterministic denial must be able to say which rule fired"
