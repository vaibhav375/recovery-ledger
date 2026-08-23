"""Regression test for a real bug caught 2026-08-23: several rules exempted
RETRY from customer-contact checks but not WAIT, so a "do nothing" holdout
policy issuing WAIT would have been incorrectly gated. Every
customer-contact rule must treat WAIT the same as RETRY: not contact.
"""

from datetime import datetime

from recovery_ledger.events.actions import ActionType
from recovery_ledger.events.schemas import Channel, CustomerProfile, FailedPaymentCase
from recovery_ledger.kernel.engine import ConsentInfo, DLTInfo, RuleContext
from recovery_ledger.kernel.rules.budget import ContactBudgetRule
from recovery_ledger.kernel.rules.dpdp import ConsentRecordExistsRule
from recovery_ledger.kernel.rules.escalation import ToneIntensityCeilingRule
from recovery_ledger.kernel.rules.opt_out import OptOutRule
from recovery_ledger.kernel.rules.tcccpr import (
    ConsentValidityRule,
    DLTRegistrationRule,
    HeaderClassMatchRule,
    NumberSeriesRule,
    OptOutOptionPresentRule,
)
from recovery_ledger.kernel.rules.timing import ContactHoursRule

NOW = datetime(2026, 8, 23, 12, 0)

WORST_CASE_CONTEXT_KWARGS = dict(
    # Every field set to whatever WOULD deny a real contact action, so the
    # only way any of these rules can pass for WAIT is via the exemption.
    action_type=ActionType.WAIT,
    channel=None,
    now_ist=datetime(2026, 8, 23, 23, 0),  # outside contact hours
    attempts_in_window=99,
    attempt_cap=1,  # budget already blown
    window_days=7,
    message_class="promotional",
    consent=ConsentInfo(basis="explicit", captured_at=None),  # no consent record at all
    dlt=DLTInfo(registered=False, template_class="transactional"),  # wrong class, unregistered
    includes_opt_out_option=False,
    sender_number_series="other",
    tone_intensity=3,
)


def _case_with_opt_out() -> FailedPaymentCase:
    return FailedPaymentCase(
        case_id="case_1",
        customer=CustomerProfile(customer_id="cust_1", opted_out=True, opted_out_at=datetime(2026, 8, 20)),
        amount_at_risk=500.0, detected_at=NOW, failure_code="insufficient_funds",
        is_hard_decline=False, payment_method="upi",
    )


ALL_RULES = [
    ContactHoursRule(), OptOutRule(), ContactBudgetRule(),
    DLTRegistrationRule(), HeaderClassMatchRule(), ConsentValidityRule(),
    OptOutOptionPresentRule(), NumberSeriesRule(), ConsentRecordExistsRule(),
    ToneIntensityCeilingRule(),
]


def test_wait_action_passes_every_rule_even_under_worst_case_context():
    case = _case_with_opt_out()
    context = RuleContext(case=case, **WORST_CASE_CONTEXT_KWARGS)
    for rule in ALL_RULES:
        result = rule.evaluate(context)
        assert result.passed is True, f"{rule.name} incorrectly denied a WAIT action: {result.detail}"


def test_same_worst_case_context_denies_for_nudge():
    """Sanity check that WORST_CASE_CONTEXT_KWARGS actually IS a worst case
    — confirms the WAIT test above is testing the exemption, not a
    context that happens to pass everything regardless of action type."""
    case = _case_with_opt_out()
    kwargs = dict(WORST_CASE_CONTEXT_KWARGS)
    kwargs["action_type"] = ActionType.NUDGE
    kwargs["channel"] = Channel.SMS
    context = RuleContext(case=case, **kwargs)
    denied = [rule.name for rule in ALL_RULES if not rule.evaluate(context).passed]
    assert len(denied) >= 5, f"expected most rules to deny a NUDGE here, only denied: {denied}"
