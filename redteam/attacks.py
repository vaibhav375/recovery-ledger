"""Adversarial attack suite against the compliance kernel (spec section 9.5).

An honest note on what this can and cannot be. The spec describes "an
adversarial LLM attempts to induce non-compliant sends (jailbreak the
drafter...)". The compliance kernel is deliberately **not** an LLM — it is a
deterministic predicate over structured state — so there is no prompt to
jailbreak and no persuasion to resist. Claiming to have "jailbroken" it
would be theatre.

The real attack surface, and what this suite actually attacks:

1. **Crafted state** — can some combination of case, consent, timing, and
   budget produce an ALLOW that a regulation says must be a DENY?
2. **Deny-by-default integrity** — can a contact be *executed* without a
   valid ALLOW certificate backing it?
3. **A hostile policy** — if the decision policy is replaced by one that
   always proposes the most aggressive possible action, does the kernel
   still hold the line?

Each attack states an **independent oracle**: the condition under which the
action must be denied, written from the regulation rather than from the
rule implementation. That independence is the point — checking the kernel
against a restatement of its own code would prove nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from recovery_ledger.events.actions import ActionType
from recovery_ledger.events.schemas import (
    Channel,
    CustomerProfile,
    FailedPaymentCase,
    FailedSubscriptionCase,
    RecoveryCase,
)
from recovery_ledger.kernel.engine import ConsentInfo, DLTInfo, MandateInfo, RuleContext

IST_DAY = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)


def _customer(**kw) -> CustomerProfile:
    base = dict(customer_id="victim", channel_pref=Channel.SMS)
    base.update(kw)
    return CustomerProfile(**base)


def _payment(**kw) -> FailedPaymentCase:
    base = dict(
        case_id="target", customer=_customer(), amount_at_risk=5000.0,
        detected_at=IST_DAY - timedelta(days=2), failure_code="insufficient_funds",
        is_hard_decline=False, payment_method="upi",
    )
    base.update(kw)
    return FailedPaymentCase(**base)


def _subscription(**kw) -> FailedSubscriptionCase:
    base = dict(
        case_id="target", customer=_customer(), amount_at_risk=5000.0,
        detected_at=IST_DAY - timedelta(hours=2), subscription_id="sub",
        mandate_id="mandate", retry_count=1, razorpay_status="halted",
    )
    base.update(kw)
    return FailedSubscriptionCase(**base)


@dataclass
class Attack:
    name: str
    category: str
    intent: str
    context: RuleContext
    # Independent oracle: True means "a compliant system MUST refuse this".
    must_be_denied: bool = True


def _ctx(case: RecoveryCase, **overrides) -> RuleContext:
    base = dict(
        case=case, action_type=ActionType.NUDGE, channel=Channel.SMS,
        now_ist=IST_DAY, attempts_in_window=0, attempt_cap=3, window_days=7,
        message_class="service",
        consent=ConsentInfo(basis="inferred", captured_at=IST_DAY - timedelta(days=1)),
        dlt=DLTInfo(registered=True, header="RZPRCV-S", template_class="service"),
        mandate=MandateInfo(pre_debit_notice_sent_at=IST_DAY - timedelta(days=2)),
        includes_opt_out_option=True, sender_number_series="160", tone_intensity=0,
    )
    base.update(overrides)
    return RuleContext(**base)


def build_attacks() -> list[Attack]:
    """Every attack below is a specific, named way a real system leaks."""
    attacks: list[Attack] = []

    # --- timing -------------------------------------------------------------
    for hour, label in [(2, "02:00 pre-dawn"), (21, "21:00 late evening"), (23, "23:00 midnight-adjacent")]:
        attacks.append(Attack(
            name=f"contact_outside_hours_{hour:02d}",
            category="RBI recovery hours",
            intent=f"Send a nudge at {label}, outside the 08:00-19:00 window.",
            context=_ctx(_payment(), now_ist=IST_DAY.replace(hour=hour)),
        ))
    attacks.append(Attack(
        name="silent_retry_outside_hours_is_legitimate",
        category="RBI recovery hours",
        intent="Silent retry at 03:00 — NOT customer contact, must be permitted.",
        context=_ctx(_payment(), action_type=ActionType.RETRY, channel=None,
                     now_ist=IST_DAY.replace(hour=3)),
        must_be_denied=False,
    ))

    # --- consent forgery ----------------------------------------------------
    attacks.append(Attack(
        name="forge_consent_absent_record",
        category="DPDPA / TCCCPR consent",
        intent="Contact with no consent record on file at all.",
        context=_ctx(_payment(), consent=ConsentInfo(basis="explicit", captured_at=None)),
    ))
    attacks.append(Attack(
        name="forge_consent_expired_explicit",
        category="TCCCPR consent",
        intent="Reuse explicit service consent captured 30 days ago (7-day validity).",
        context=_ctx(_payment(), message_class="service",
                     consent=ConsentInfo(basis="explicit", captured_at=IST_DAY - timedelta(days=30))),
    ))
    attacks.append(Attack(
        name="forge_consent_discharged_contract",
        category="TCCCPR consent",
        intent="Rely on inferred consent after the underlying contract ended.",
        context=_ctx(_payment(), consent=ConsentInfo(basis="inferred", contract_active=False,
                                                     captured_at=IST_DAY - timedelta(days=1))),
    ))

    # --- opt-out ------------------------------------------------------------
    attacks.append(Attack(
        name="message_opted_out_customer",
        category="TCCCPR opt-out",
        intent="Message a customer who opted out two days ago.",
        context=_ctx(_payment(customer=_customer(opted_out=True,
                                                 opted_out_at=IST_DAY - timedelta(days=2)))),
    ))
    attacks.append(Attack(
        name="message_opted_out_customer_late_in_cooling",
        category="TCCCPR opt-out",
        intent="Message on day 89 of the 90-day cooling period.",
        context=_ctx(_payment(customer=_customer(opted_out=True,
                                                 opted_out_at=IST_DAY - timedelta(days=89)))),
    ))

    # --- budget -------------------------------------------------------------
    for attempts in [3, 7, 99]:
        attacks.append(Attack(
            name=f"exceed_contact_budget_{attempts}",
            category="Contact budget",
            intent=f"Send contact number {attempts + 1} against a cap of 3.",
            context=_ctx(_payment(), attempts_in_window=attempts, attempt_cap=3),
        ))

    # --- DLT ----------------------------------------------------------------
    attacks.append(Attack(
        name="send_unregistered_template",
        category="TCCCPR DLT",
        intent="Transmit a commercial message on an unregistered DLT template.",
        context=_ctx(_payment(), dlt=DLTInfo(registered=False, template_class="service")),
    ))
    attacks.append(Attack(
        name="promotional_content_on_service_header",
        category="TCCCPR DLT",
        intent="Send promotional content through a service-class registered header.",
        context=_ctx(_payment(), message_class="promotional",
                     dlt=DLTInfo(registered=True, template_class="service")),
    ))
    attacks.append(Attack(
        name="promotional_without_opt_out_option",
        category="TCCCPR",
        intent="Send a promotional message carrying no opt-out option.",
        context=_ctx(_payment(), message_class="promotional",
                     dlt=DLTInfo(registered=True, template_class="promotional"),
                     includes_opt_out_option=False, sender_number_series="140"),
    ))
    attacks.append(Attack(
        name="service_sms_from_unapproved_number_series",
        category="TCCCPR number series",
        intent="Send service SMS from an ordinary 10-digit number.",
        context=_ctx(_payment(), sender_number_series="other"),
    ))

    # --- e-mandate ----------------------------------------------------------
    attacks.append(Attack(
        name="debit_without_pre_debit_notice",
        category="RBI e-mandate 2026",
        intent="Attempt a mandate debit with no pre-debit notification sent.",
        context=_ctx(_subscription(), action_type=ActionType.RETRY, channel=None,
                     mandate=MandateInfo(pre_debit_notice_sent_at=None)),
    ))
    attacks.append(Attack(
        name="debit_inside_24h_notice_window",
        category="RBI e-mandate 2026",
        intent="Debit 23 hours after notice, inside the 24-hour minimum.",
        context=_ctx(_subscription(), action_type=ActionType.RETRY, channel=None,
                     mandate=MandateInfo(pre_debit_notice_sent_at=IST_DAY - timedelta(hours=23))),
    ))

    # --- promise-to-pay -----------------------------------------------------
    attacks.append(Attack(
        name="contact_during_promise_window",
        category="Promise-to-pay",
        intent="Chase a customer who promised payment next week.",
        context=_ctx(_payment(), promise_to_pay_until=IST_DAY + timedelta(days=7)),
    ))

    # --- harassment / tone --------------------------------------------------
    attacks.append(Attack(
        name="max_intensity_on_first_contact",
        category="RBI harassment",
        intent="Open with the firmest possible tone on the very first contact.",
        context=_ctx(_payment(), attempts_in_window=0, tone_intensity=3),
    ))

    # --- combined -----------------------------------------------------------
    attacks.append(Attack(
        name="everything_at_once",
        category="Combined",
        intent="Every violation simultaneously — the kernel must deny, not average.",
        context=_ctx(
            _payment(customer=_customer(opted_out=True, opted_out_at=IST_DAY - timedelta(days=1))),
            now_ist=IST_DAY.replace(hour=3), attempts_in_window=50, message_class="promotional",
            consent=ConsentInfo(basis="explicit", captured_at=None),
            dlt=DLTInfo(registered=False, template_class="transactional"),
            includes_opt_out_option=False, sender_number_series="other", tone_intensity=3,
            promise_to_pay_until=IST_DAY + timedelta(days=5),
        ),
    ))

    return attacks
