"""Synthetic case generator — skeleton of "the recovery gym" (spec section
7.3). This is deliberately the thin first slice: deterministic, seeded
generation of plausible cases across all four loss types, enough to drive
the end-to-end agent loop. The full gym — hidden latent payer traits
(liquidity, payday cycle, annoyance threshold, channel/language
preference), a response-to-intervention model including negative responses,
and calibration to the published marginals in spec section 3.2 — is a
separate, larger piece of work landing once Tier 1's validated causal
machinery is ready to transfer in (spec section 7.3 explicitly: the
simulator only needs to be *plausible*, not probative, because the method is
proven separately — but it isn't built yet, and this generator doesn't
pretend to be it).
"""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np

from recovery_ledger.events.schemas import (
    Channel,
    CheckoutAbandonmentCase,
    CustomerProfile,
    FailedPaymentCase,
    FailedSubscriptionCase,
    Language,
    LossType,
    OverdueReceivableCase,
    RecoveryCase,
)

FAILURE_CODES = ["insufficient_funds", "gateway_timeout", "expired_card", "wrong_pin", "issuer_decline"]
HARD_DECLINE_CODES = {"expired_card"}
PAYMENT_METHODS = ["upi", "card", "netbanking"]


def _choice_enum(rng: np.random.Generator, options: list) -> object:
    """np.random.Generator.choice on a list of str-subclassed Enum members
    silently mangles them (converts to a bogus numpy string dtype) — sample
    an index instead and index back into the plain Python list."""
    return options[int(rng.integers(0, len(options)))]


def _customer(rng: np.random.Generator, i: int) -> CustomerProfile:
    return CustomerProfile(
        customer_id=f"cust_{i:06d}",
        language_pref=_choice_enum(rng, list(Language)),
        channel_pref=_choice_enum(rng, [Channel.SMS, Channel.WHATSAPP, Channel.EMAIL]),
        is_b2b=bool(rng.random() < 0.15),
    )


def generate_cases(n: int, *, seed: int, now: datetime) -> list[RecoveryCase]:
    rng = np.random.default_rng(seed)
    loss_type_options = list(LossType)
    loss_types = [_choice_enum(rng, loss_type_options) for _ in range(n)]
    cases: list[RecoveryCase] = []

    for i, loss_type in enumerate(loss_types):
        case_id = f"case_{i:06d}"
        customer = _customer(rng, i)
        amount = float(rng.gamma(shape=2.0, scale=800.0)) + 50.0  # right-skewed, plausible INR amounts
        detected_at = now - timedelta(hours=float(rng.uniform(0, 48)))

        if loss_type == LossType.FAILED_PAYMENT:
            code = str(rng.choice(FAILURE_CODES))
            cases.append(FailedPaymentCase(
                case_id=case_id, customer=customer, amount_at_risk=amount, detected_at=detected_at,
                failure_code=code, is_hard_decline=code in HARD_DECLINE_CODES,
                payment_method=str(rng.choice(PAYMENT_METHODS)),
            ))
        elif loss_type == LossType.CHECKOUT_ABANDONMENT:
            cases.append(CheckoutAbandonmentCase(
                case_id=case_id, customer=customer, amount_at_risk=amount, detected_at=detected_at,
                cart_id=f"cart_{i:06d}", items_count=int(rng.integers(1, 6)),
                checkout_started_at=detected_at - timedelta(minutes=float(rng.uniform(2, 30))),
            ))
        elif loss_type == LossType.FAILED_SUBSCRIPTION:
            cases.append(FailedSubscriptionCase(
                case_id=case_id, customer=customer, amount_at_risk=amount, detected_at=detected_at,
                subscription_id=f"sub_{i:06d}", mandate_id=f"mandate_{i:06d}",
                retry_count=int(rng.integers(1, 3)), razorpay_status="halted",
            ))
        else:  # OVERDUE_RECEIVABLE
            days_overdue = int(rng.integers(1, 60))
            cases.append(OverdueReceivableCase(
                case_id=case_id, customer=customer, amount_at_risk=amount * 5, detected_at=detected_at,
                invoice_id=f"inv_{i:06d}", due_date=detected_at - timedelta(days=days_overdue),
                days_overdue=days_overdue, is_msme_counterparty=bool(rng.random() < 0.4),
            ))

    return cases
