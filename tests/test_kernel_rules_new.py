from datetime import datetime, timedelta

from recovery_ledger.events.actions import ActionType
from recovery_ledger.events.schemas import (
    Channel,
    CustomerProfile,
    FailedPaymentCase,
    FailedSubscriptionCase,
)
from recovery_ledger.kernel.engine import ConsentInfo, DLTInfo, MandateInfo, RuleContext
from recovery_ledger.kernel.rules.dpdp import ConsentRecordExistsRule
from recovery_ledger.kernel.rules.emandate_2026 import PreDebitNotificationRule
from recovery_ledger.kernel.rules.escalation import ToneIntensityCeilingRule
from recovery_ledger.kernel.rules.tcccpr import (
    ConsentValidityRule,
    DLTRegistrationRule,
    HeaderClassMatchRule,
    NumberSeriesRule,
    OptOutOptionPresentRule,
)

NOW = datetime(2026, 8, 23, 12, 0)


def _payment_case(**overrides) -> FailedPaymentCase:
    defaults = dict(
        case_id="case_1",
        customer=CustomerProfile(customer_id="cust_1"),
        amount_at_risk=500.0,
        detected_at=NOW,
        failure_code="insufficient_funds",
        is_hard_decline=False,
        payment_method="upi",
    )
    defaults.update(overrides)
    return FailedPaymentCase(**defaults)


def _subscription_case(**overrides) -> FailedSubscriptionCase:
    defaults = dict(
        case_id="case_2",
        customer=CustomerProfile(customer_id="cust_2"),
        amount_at_risk=500.0,
        detected_at=NOW,
        subscription_id="sub_1",
        mandate_id="mandate_1",
        retry_count=1,
        razorpay_status="halted",
    )
    defaults.update(overrides)
    return FailedSubscriptionCase(**defaults)


def _context(**overrides) -> RuleContext:
    defaults = dict(
        case=_payment_case(),
        action_type=ActionType.NUDGE,
        channel=Channel.SMS,
        now_ist=NOW,
        attempts_in_window=0,
        attempt_cap=3,
        window_days=7,
    )
    defaults.update(overrides)
    return RuleContext(**defaults)


# --- DLTRegistrationRule ---------------------------------------------------

def test_dlt_unregistered_denies():
    result = DLTRegistrationRule().evaluate(_context(dlt=DLTInfo(registered=False)))
    assert result.passed is False


def test_dlt_registered_allows():
    result = DLTRegistrationRule().evaluate(_context(dlt=DLTInfo(registered=True)))
    assert result.passed is True


def test_dlt_retry_is_exempt():
    result = DLTRegistrationRule().evaluate(
        _context(action_type=ActionType.RETRY, channel=None, dlt=DLTInfo(registered=False))
    )
    assert result.passed is True


# --- HeaderClassMatchRule ---------------------------------------------------

def test_header_class_mismatch_denies():
    result = HeaderClassMatchRule().evaluate(
        _context(message_class="service", dlt=DLTInfo(template_class="promotional"))
    )
    assert result.passed is False


def test_header_class_match_allows():
    result = HeaderClassMatchRule().evaluate(
        _context(message_class="service", dlt=DLTInfo(template_class="service"))
    )
    assert result.passed is True


# --- ConsentValidityRule ----------------------------------------------------

def test_explicit_service_consent_within_7_days_allows():
    result = ConsentValidityRule().evaluate(_context(
        message_class="service",
        consent=ConsentInfo(basis="explicit", captured_at=NOW - timedelta(days=3)),
    ))
    assert result.passed is True


def test_explicit_service_consent_older_than_7_days_denies():
    result = ConsentValidityRule().evaluate(_context(
        message_class="service",
        consent=ConsentInfo(basis="explicit", captured_at=NOW - timedelta(days=10)),
    ))
    assert result.passed is False


def test_inferred_consent_with_discharged_contract_denies():
    result = ConsentValidityRule().evaluate(_context(
        consent=ConsentInfo(basis="inferred", contract_active=False),
    ))
    assert result.passed is False


def test_no_consent_captured_at_all_denies():
    result = ConsentValidityRule().evaluate(_context(
        consent=ConsentInfo(basis="explicit", captured_at=None),
    ))
    assert result.passed is False


# --- OptOutOptionPresentRule -------------------------------------------------

def test_promotional_message_without_opt_out_denies():
    result = OptOutOptionPresentRule().evaluate(
        _context(message_class="promotional", includes_opt_out_option=False)
    )
    assert result.passed is False


def test_promotional_message_with_opt_out_allows():
    result = OptOutOptionPresentRule().evaluate(
        _context(message_class="promotional", includes_opt_out_option=True)
    )
    assert result.passed is True


def test_service_message_exempt_from_opt_out_requirement():
    result = OptOutOptionPresentRule().evaluate(
        _context(message_class="service", includes_opt_out_option=False)
    )
    assert result.passed is True


# --- NumberSeriesRule --------------------------------------------------------

def test_promotional_voice_requires_140_series():
    denied = NumberSeriesRule().evaluate(_context(
        channel=Channel.VOICE, message_class="promotional", sender_number_series="160",
    ))
    allowed = NumberSeriesRule().evaluate(_context(
        channel=Channel.VOICE, message_class="promotional", sender_number_series="140",
    ))
    assert denied.passed is False
    assert allowed.passed is True


def test_service_sms_requires_160_series():
    denied = NumberSeriesRule().evaluate(_context(
        channel=Channel.SMS, message_class="service", sender_number_series="140",
    ))
    allowed = NumberSeriesRule().evaluate(_context(
        channel=Channel.SMS, message_class="service", sender_number_series="160",
    ))
    assert denied.passed is False
    assert allowed.passed is True


# --- PreDebitNotificationRule ------------------------------------------------

def test_mandate_debit_without_notice_denies():
    result = PreDebitNotificationRule().evaluate(_context(
        case=_subscription_case(), action_type=ActionType.RETRY, channel=None,
        mandate=MandateInfo(pre_debit_notice_sent_at=None),
    ))
    assert result.passed is False


def test_mandate_debit_with_notice_under_24h_denies():
    result = PreDebitNotificationRule().evaluate(_context(
        case=_subscription_case(), action_type=ActionType.RETRY, channel=None, now_ist=NOW,
        mandate=MandateInfo(pre_debit_notice_sent_at=NOW - timedelta(hours=5)),
    ))
    assert result.passed is False


def test_mandate_debit_with_notice_over_24h_allows():
    result = PreDebitNotificationRule().evaluate(_context(
        case=_subscription_case(), action_type=ActionType.RETRY, channel=None, now_ist=NOW,
        mandate=MandateInfo(pre_debit_notice_sent_at=NOW - timedelta(hours=25)),
    ))
    assert result.passed is True


def test_non_mandate_retry_is_exempt():
    result = PreDebitNotificationRule().evaluate(_context(
        case=_payment_case(), action_type=ActionType.RETRY, channel=None,
        mandate=MandateInfo(pre_debit_notice_sent_at=None),
    ))
    assert result.passed is True


# --- ConsentRecordExistsRule --------------------------------------------------

def test_no_consent_record_denies():
    result = ConsentRecordExistsRule().evaluate(_context(consent=ConsentInfo(captured_at=None)))
    assert result.passed is False


def test_consent_record_present_allows():
    result = ConsentRecordExistsRule().evaluate(_context(consent=ConsentInfo(captured_at=NOW)))
    assert result.passed is True


# --- ToneIntensityCeilingRule -------------------------------------------------

def test_first_attempt_tone_ceiling_is_low():
    denied = ToneIntensityCeilingRule().evaluate(_context(attempts_in_window=0, tone_intensity=2))
    allowed = ToneIntensityCeilingRule().evaluate(_context(attempts_in_window=0, tone_intensity=1))
    assert denied.passed is False
    assert allowed.passed is True


def test_tone_ceiling_loosens_with_more_attempts():
    result = ToneIntensityCeilingRule().evaluate(_context(attempts_in_window=2, tone_intensity=3))
    assert result.passed is True
