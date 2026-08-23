from datetime import datetime, timedelta

from recovery_ledger.events.actions import ActionType
from recovery_ledger.events.schemas import (
    Channel,
    CustomerProfile,
    FailedPaymentCase,
    LossType,
)
from recovery_ledger.kernel.certificate import Decision
from recovery_ledger.kernel.engine import KernelEngine, RuleContext
from recovery_ledger.kernel.rules.budget import ContactBudgetRule
from recovery_ledger.kernel.rules.opt_out import OptOutRule
from recovery_ledger.kernel.rules.timing import ContactHoursRule


def _case(**overrides) -> FailedPaymentCase:
    defaults = dict(
        case_id="case_1",
        customer=CustomerProfile(customer_id="cust_1"),
        amount_at_risk=500.0,
        detected_at=datetime(2026, 8, 23, 10, 0),
        failure_code="insufficient_funds",
        is_hard_decline=False,
        payment_method="upi",
    )
    defaults.update(overrides)
    return FailedPaymentCase(**defaults)


def _context(**overrides) -> RuleContext:
    defaults = dict(
        case=_case(),
        action_type=ActionType.NUDGE,
        channel=Channel.SMS,
        now_ist=datetime(2026, 8, 23, 12, 0),
        attempts_in_window=0,
        attempt_cap=3,
        window_days=7,
    )
    defaults.update(overrides)
    return RuleContext(**defaults)


def test_zero_rules_denies_by_default():
    engine = KernelEngine(rules=[])
    cert = engine.issue_certificate(_context())
    assert cert.decision == Decision.DENY


def test_all_rules_pass_allows():
    engine = KernelEngine(rules=[ContactHoursRule(), OptOutRule(), ContactBudgetRule()])
    cert = engine.issue_certificate(_context())
    assert cert.decision == Decision.ALLOW
    assert cert.denied_rules == []
    assert set(cert.rules_evaluated) == {
        "RBI.RECOVERY.HOURS", "TCCCPR.OPT_OUT.COOLING", "POLICY.CONTACT_BUDGET",
    }


def test_outside_contact_hours_denies():
    engine = KernelEngine(rules=[ContactHoursRule()])
    cert = engine.issue_certificate(_context(now_ist=datetime(2026, 8, 23, 21, 30)))
    assert cert.decision == Decision.DENY
    assert "RBI.RECOVERY.HOURS" in cert.denied_rules


def test_retry_exempt_from_contact_hours():
    engine = KernelEngine(rules=[ContactHoursRule()])
    cert = engine.issue_certificate(
        _context(action_type=ActionType.RETRY, channel=None, now_ist=datetime(2026, 8, 23, 3, 0))
    )
    assert cert.decision == Decision.ALLOW


def test_opted_out_customer_within_cooling_denies():
    case = _case(customer=CustomerProfile(
        customer_id="cust_1", opted_out=True, opted_out_at=datetime(2026, 8, 1),
    ))
    engine = KernelEngine(rules=[OptOutRule()])
    cert = engine.issue_certificate(_context(case=case, now_ist=datetime(2026, 8, 23)))
    assert cert.decision == Decision.DENY


def test_opted_out_customer_after_cooling_allows():
    case = _case(customer=CustomerProfile(
        customer_id="cust_1", opted_out=True, opted_out_at=datetime(2026, 1, 1),
    ))
    engine = KernelEngine(rules=[OptOutRule()])
    cert = engine.issue_certificate(_context(case=case, now_ist=datetime(2026, 8, 23)))
    assert cert.decision == Decision.ALLOW


def test_budget_exhausted_denies():
    engine = KernelEngine(rules=[ContactBudgetRule()])
    cert = engine.issue_certificate(_context(attempts_in_window=3, attempt_cap=3))
    assert cert.decision == Decision.DENY
    assert "POLICY.CONTACT_BUDGET" in cert.denied_rules


def test_one_failing_rule_among_several_denies():
    engine = KernelEngine(rules=[ContactHoursRule(), ContactBudgetRule()])
    cert = engine.issue_certificate(_context(attempts_in_window=5, attempt_cap=3))
    assert cert.decision == Decision.DENY
    assert cert.denied_rules == ["POLICY.CONTACT_BUDGET"]
