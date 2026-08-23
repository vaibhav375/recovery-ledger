from datetime import datetime, timezone

from recovery_ledger.agent.loop import RecoveryAgent
from recovery_ledger.detector.detector import CaseDetector
from recovery_ledger.diagnoser.diagnoser import CaseDiagnoser
from recovery_ledger.events.actions import StopReason
from recovery_ledger.events.schemas import CustomerProfile, FailedPaymentCase
from recovery_ledger.executor.executor import SimulatedExecutor
from recovery_ledger.kernel.engine import KernelEngine
from recovery_ledger.kernel.rules.budget import ContactBudgetRule
from recovery_ledger.kernel.rules.opt_out import OptOutRule
from recovery_ledger.kernel.rules.timing import ContactHoursRule
from recovery_ledger.ledger.ledger import Ledger
from recovery_ledger.listener.listener import Listener
from recovery_ledger.policy.decision import DecisionPolicy

DAYTIME = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)
NIGHTTIME = datetime(2026, 8, 23, 22, 0, tzinfo=timezone.utc)


def _case(**overrides) -> FailedPaymentCase:
    defaults = dict(
        case_id="case_1",
        customer=CustomerProfile(customer_id="cust_1"),
        amount_at_risk=500.0,
        detected_at=DAYTIME,
        failure_code="insufficient_funds",
        is_hard_decline=False,
        payment_method="upi",
    )
    defaults.update(overrides)
    return FailedPaymentCase(**defaults)


def _build_agent(*, clock, rules=None) -> tuple[RecoveryAgent, Ledger]:
    ledger = Ledger()
    if rules is None:
        rules = [ContactHoursRule(), OptOutRule(), ContactBudgetRule()]
    agent = RecoveryAgent(
        detector=CaseDetector(),
        diagnoser=CaseDiagnoser(),
        policy=DecisionPolicy(),
        kernel=KernelEngine(rules=rules),
        executor=SimulatedExecutor(),
        listener=Listener(),
        ledger=ledger,
        clock=clock,
    )
    return agent, ledger


def test_full_run_produces_valid_hash_chain():
    agent, ledger = _build_agent(clock=lambda: DAYTIME)
    outcome = agent.run_case(_case())
    assert ledger.verify_chain() is True
    assert len(ledger) > 0
    assert outcome.is_terminated
    assert isinstance(outcome.stop_reason, StopReason)


def test_stub_policy_terminates_with_budget_exhausted():
    """The stub policy (Listener always returns NO_REPLY, so nothing ever
    resolves) must still provably terminate — this is B3, not a detail.

    It stops because it runs out of attempts, so the ledger must say
    BUDGET_EXHAUSTED. Until 2026-08-24 every policy STOP was recorded as
    NEGATIVE_EV regardless of cause, which hid budget exhaustion entirely."""
    agent, ledger = _build_agent(clock=lambda: DAYTIME)
    outcome = agent.run_case(_case())
    assert outcome.stop_reason == StopReason.BUDGET_EXHAUSTED


def test_kernel_deny_outside_contact_hours_blocks_the_contact_but_does_not_kill_the_case():
    """Spec section 10, stopping rule 10 is "the kernel denies ALL remaining
    actions", not "one proposed action was denied". A nudge outside contact
    hours must be blocked, but the case should fall back to WAIT and stay
    alive rather than being abandoned (changed 2026-08-24 — see
    ENGINEERING_LOG.md)."""
    agent, ledger = _build_agent(clock=lambda: NIGHTTIME)
    reason = agent.run_case(_case())

    certs = [e for e in ledger.entries_for_case("case_1") if e.entry_type == "certificate"]
    assert certs, "expected at least one certificate entry"
    assert certs[0].payload["decision"] == "DENY", "the out-of-hours nudge must be denied"
    assert reason != StopReason.REGULATORY_CEILING, (
        "a single denied action must not terminate the case while WAIT is still admissible"
    )
    # and the denied nudge must never have actually gone out
    executed_contacts = [
        e for e in ledger.entries_for_case("case_1")
        if e.entry_type == "action_result"
        and e.payload["executed"]
        and e.payload["action_type"] not in ("wait", "retry")
    ]
    assert not executed_contacts, "no customer contact may be executed outside contact hours"


def test_opted_out_customer_is_never_contacted():
    """The safety property that must hold regardless of how the loop's
    fallback behaviour changes: an opted-out customer receives no
    customer-facing contact, ever."""
    case = _case(customer=CustomerProfile(
        customer_id="cust_1", opted_out=True, opted_out_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
    ))
    agent, ledger = _build_agent(clock=lambda: DAYTIME)
    agent.run_case(case)

    executed_contacts = [
        e for e in ledger.entries_for_case("case_1")
        if e.entry_type == "action_result"
        and e.payload["executed"]
        and e.payload["action_type"] not in ("wait", "retry")
    ]
    assert not executed_contacts, "an opted-out customer must never be contacted"

    # every contact-type certificate issued for this case must have been denied
    contact_certs = [
        e for e in ledger.entries_for_case("case_1")
        if e.entry_type == "certificate" and e.payload["action_type"] not in ("wait", "retry")
    ]
    assert contact_certs, "expected the policy to have proposed at least one contact"
    assert all(c.payload["decision"] == "DENY" for c in contact_certs)


def test_every_case_has_a_terminal_ledger_entry():
    """Every stop must write a terminal ledger entry with the reason code
    (spec section 10, closing line)."""
    agent, ledger = _build_agent(clock=lambda: DAYTIME)
    agent.run_case(_case())
    stop_entries = [e for e in ledger.entries_for_case("case_1") if e.entry_type == "stop"]
    assert len(stop_entries) == 1
    assert stop_entries[0].payload["reason"] in {r.value for r in StopReason}


def test_deterministic_given_same_clock_and_case():
    agent_a, ledger_a = _build_agent(clock=lambda: DAYTIME)
    agent_b, ledger_b = _build_agent(clock=lambda: DAYTIME)
    outcome_a = agent_a.run_case(_case())
    outcome_b = agent_b.run_case(_case())
    assert outcome_a.stop_reason == outcome_b.stop_reason
    # entry_type sequence should match exactly, even though timestamps/hashes differ
    types_a = [e.entry_type for e in ledger_a.entries_for_case("case_1")]
    types_b = [e.entry_type for e in ledger_b.entries_for_case("case_1")]
    assert types_a == types_b


def test_loop_terminates_within_hard_max_steps():
    """Safety net: even a hypothetically buggy policy that never proposes
    STOP must not loop forever."""
    from recovery_ledger.agent.loop import HARD_MAX_STEPS
    agent, ledger = _build_agent(clock=lambda: DAYTIME)
    agent.run_case(_case())
    diagnosis_entries = [e for e in ledger.entries_for_case("case_1") if e.entry_type == "diagnosis"]
    assert len(diagnosis_entries) <= HARD_MAX_STEPS
