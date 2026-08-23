"""Typed event schemas for the four loss types the spec names (section 6):
failed payment, checkout abandonment, failed subscription/mandate, and
overdue B2B receivable. Every case in the system is one of these four —
detector, diagnoser, policy, kernel, and ledger all operate on this common
shape rather than loss-type-specific ad hoc dicts.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


class LossType(str, Enum):
    FAILED_PAYMENT = "failed_payment"
    CHECKOUT_ABANDONMENT = "checkout_abandonment"
    FAILED_SUBSCRIPTION = "failed_subscription"
    OVERDUE_RECEIVABLE = "overdue_receivable"


class Channel(str, Enum):
    SMS = "sms"
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    VOICE = "voice"
    RETRY = "retry"  # silent — no customer contact, just a payment retry


class Language(str, Enum):
    EN = "en"
    HI = "hi"
    HINGLISH = "hinglish"
    REGIONAL = "regional"


class CustomerProfile(BaseModel):
    customer_id: str
    language_pref: Language = Language.EN
    channel_pref: Channel | None = None
    is_b2b: bool = False
    opted_out: bool = False
    opted_out_at: datetime | None = None


class _BaseCase(BaseModel):
    case_id: str
    customer: CustomerProfile
    amount_at_risk: float
    currency: Literal["INR"] = "INR"
    detected_at: datetime

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return f"{self.case_id} [{self.loss_type.value}] ₹{self.amount_at_risk:.2f}"  # type: ignore[attr-defined]


class FailedPaymentCase(_BaseCase):
    loss_type: Literal[LossType.FAILED_PAYMENT] = LossType.FAILED_PAYMENT
    failure_code: str
    is_hard_decline: bool
    payment_method: str
    issuer: str | None = None


class CheckoutAbandonmentCase(_BaseCase):
    loss_type: Literal[LossType.CHECKOUT_ABANDONMENT] = LossType.CHECKOUT_ABANDONMENT
    cart_id: str
    items_count: int
    checkout_started_at: datetime


class FailedSubscriptionCase(_BaseCase):
    loss_type: Literal[LossType.FAILED_SUBSCRIPTION] = LossType.FAILED_SUBSCRIPTION
    subscription_id: str
    mandate_id: str
    retry_count: int
    razorpay_status: str  # e.g. "halted" — see spec section 3.3


class OverdueReceivableCase(_BaseCase):
    loss_type: Literal[LossType.OVERDUE_RECEIVABLE] = LossType.OVERDUE_RECEIVABLE
    invoice_id: str
    due_date: datetime
    days_overdue: int
    is_msme_counterparty: bool  # drives the Section 43B(h) 45-day clock


RecoveryCase = Annotated[
    Union[
        FailedPaymentCase,
        CheckoutAbandonmentCase,
        FailedSubscriptionCase,
        OverdueReceivableCase,
    ],
    Field(discriminator="loss_type"),
]
