from datetime import datetime, timezone

from recovery_ledger.events.schemas import (
    CustomerProfile,
    FailedPaymentCase,
    LossType,
)
from recovery_ledger.sim.generator import generate_cases

NOW = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)


def test_failed_payment_case_round_trips_through_json():
    case = FailedPaymentCase(
        case_id="case_1",
        customer=CustomerProfile(customer_id="cust_1"),
        amount_at_risk=500.0,
        detected_at=NOW,
        failure_code="insufficient_funds",
        is_hard_decline=False,
        payment_method="upi",
    )
    dumped = case.model_dump(mode="json")
    assert dumped["loss_type"] == "failed_payment"
    restored = FailedPaymentCase.model_validate(dumped)
    assert restored == case


def test_generate_cases_is_deterministic():
    a = generate_cases(200, seed=42, now=NOW)
    b = generate_cases(200, seed=42, now=NOW)
    assert [c.case_id for c in a] == [c.case_id for c in b]
    assert [c.loss_type for c in a] == [c.loss_type for c in b]
    assert [c.amount_at_risk for c in a] == [c.amount_at_risk for c in b]


def test_generate_cases_covers_all_four_loss_types():
    cases = generate_cases(500, seed=42, now=NOW)
    seen = {c.loss_type for c in cases}
    assert seen == set(LossType)


def test_generate_cases_amounts_are_positive():
    cases = generate_cases(200, seed=1, now=NOW)
    assert all(c.amount_at_risk > 0 for c in cases)


def test_generate_cases_different_seeds_differ():
    a = generate_cases(50, seed=1, now=NOW)
    b = generate_cases(50, seed=2, now=NOW)
    assert [c.amount_at_risk for c in a] != [c.amount_at_risk for c in b]
