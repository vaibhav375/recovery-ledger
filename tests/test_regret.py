"""Attribution and pricing of the cases the agent declined to contact.

Two of these tests exist to fail. A denied nudge must not count as contact
(`test_a_denied_nudge_is_not_contact`) — a kernel-blocked action falls back to
WAIT and never reaches the customer, so counting the decision rather than the
executed result would record a contact that did not happen. And a
`negative_ev` refusal of a customer with positive true uplift must be counted
as a model error, not filed as "saved"
(`test_a_negative_ev_refusal_of_a_persuadable_customer_is_a_model_error`) —
that would turn the system's own mistake into a success. Both are mutated in
Task 1 Step 6 to prove they bite.

This module has no test for holdout-arm exclusion, and cannot: `DeclinedCase`
has no field for arm membership, so there is nothing here to construct a
holdout case out of. A holdout-arm case entering the universe would roughly
double the reported regret, but that guard lives one layer up, in
`experiments/regret/run_regret.py`'s `treatment_arm()` (which reconstructs
`run_eval`'s own 50/50 assignment) and the arm-size assertion in its `main()`.
"""

from __future__ import annotations

import pytest

from recovery_ledger.events.actions import ActionType, StopReason
from recovery_ledger.policy.regret import (
    Bucket,
    DeclinedCase,
    classify,
    regret_totals,
    totals_by_bucket,
    was_contacted,
)


class _Entry:
    """Minimal stand-in for LedgerEntry: the module only reads these two."""

    def __init__(self, entry_type: str, payload: dict):
        self.entry_type = entry_type
        self.payload = payload


def _executed(action: ActionType) -> _Entry:
    return _Entry("action_result", {"executed": True, "action_type": action.value})


def _blocked(action: ActionType) -> _Entry:
    return _Entry("action_result", {"executed": False, "action_type": action.value})


def _case(tau: float, bucket: Bucket, *, amount: float = 1000.0) -> DeclinedCase:
    return DeclinedCase(
        case_id="c1", amount_at_risk=amount, tau_true=tau,
        bucket=bucket, stop_reason="negative_ev",
    )


def test_an_executed_nudge_counts_as_contact():
    assert was_contacted([_executed(ActionType.NUDGE)]) is True


def test_a_denied_nudge_is_not_contact():
    assert was_contacted([_blocked(ActionType.NUDGE)]) is False


def test_a_payment_retry_is_not_customer_contact():
    """N6's whole claim: recovering without messaging anyone."""
    assert was_contacted([_executed(ActionType.RETRY)]) is False
    assert was_contacted([_executed(ActionType.REROUTE)]) is False


def test_negotiation_is_customer_contact():
    assert was_contacted([_executed(ActionType.NEGOTIATE)]) is True


@pytest.mark.parametrize("reason,expected", [
    (StopReason.OPT_OUT, Bucket.MANDATORY),
    (StopReason.PROMISE_TO_PAY_ACTIVE, Bucket.MANDATORY),
    (StopReason.REGULATORY_CEILING, Bucket.MANDATORY),
    (StopReason.GLOBAL_KILL_SWITCH, Bucket.MANDATORY),
    (StopReason.NEGATIVE_EV, Bucket.MODEL_JUDGEMENT),
    (StopReason.DO_NOT_DISTURB, Bucket.MODEL_JUDGEMENT),
    (StopReason.BUDGET_EXHAUSTED, Bucket.ALLOCATION),
    (StopReason.DISPUTE_RAISED, Bucket.CASE_STATE),
    (StopReason.HARD_DECLINE, Bucket.CASE_STATE),
    (StopReason.HUMAN_ESCALATION_THRESHOLD, Bucket.DEFERRED),
])
def test_stop_reasons_map_to_their_bucket(reason, expected):
    assert classify(reason.value, kernel_denied_contact=False) == expected


def test_a_kernel_denial_outranks_the_stop_reason():
    """The agent tried to contact and the kernel refused, so the binding
    constraint was the rule, not the policy's judgement — however the case
    later happened to terminate."""
    assert classify(
        StopReason.BUDGET_EXHAUSTED.value, kernel_denied_contact=True
    ) == Bucket.MANDATORY


def test_positive_uplift_is_cost_and_negative_uplift_is_saved():
    declined = [
        _case(0.10, Bucket.MODEL_JUDGEMENT),   # refusing cost 100
        _case(-0.04, Bucket.MODEL_JUDGEMENT),  # refusing saved 40
    ]
    t = regret_totals(declined)
    assert t.cost == pytest.approx(100.0)
    assert t.saved == pytest.approx(40.0)
    assert t.net == pytest.approx(-60.0)


def test_a_negative_ev_refusal_of_a_persuadable_customer_is_a_model_error():
    """THE FAILURE DIRECTION. The agent said this customer was not worth
    contacting and the truth says otherwise. Filing it as `saved` would
    convert the system's own mistake into a success."""
    t = regret_totals([_case(0.10, Bucket.MODEL_JUDGEMENT)])
    assert t.model_errors == 1
    assert t.cost == pytest.approx(100.0)
    assert t.saved == pytest.approx(0.0)


def test_a_correct_do_not_disturb_refusal_is_not_a_model_error():
    t = regret_totals([_case(-0.10, Bucket.MODEL_JUDGEMENT)])
    assert t.model_errors == 0


def test_a_mandatory_refusal_of_a_persuadable_customer_is_not_a_model_error():
    """Compliance cost is not a model mistake."""
    t = regret_totals([_case(0.10, Bucket.MANDATORY)])
    assert t.model_errors == 0
    assert t.cost == pytest.approx(100.0)


def test_deferred_cases_are_excluded_from_the_totals():
    """A handoff to a human is not a refusal — the money is not forgone."""
    t = regret_totals([_case(0.10, Bucket.DEFERRED), _case(0.10, Bucket.MANDATORY)])
    assert t.n == 1
    assert t.cost == pytest.approx(100.0)


def test_totals_by_bucket_partitions_every_in_scope_case():
    declined = [
        _case(0.10, Bucket.MANDATORY),
        _case(0.10, Bucket.MODEL_JUDGEMENT),
        _case(-0.05, Bucket.ALLOCATION),
        _case(0.10, Bucket.DEFERRED),
    ]
    by = totals_by_bucket(declined)
    assert sum(t.n for t in by.values()) == regret_totals(declined).n == 3
    assert Bucket.DEFERRED not in by
