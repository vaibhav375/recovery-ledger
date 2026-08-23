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
    reason = agent.run_case(_case())
    assert ledger.verify_chain() is True
    assert len(ledger) > 0
    assert isinstance(reason, StopReason)


def test_stub_policy_eventually_stops_with_negative_ev():
    """The stub policy (Listener always returns NO_REPLY, so nothing ever
    resolves) must still provably terminate — this is B3, not a detail."""
    agent, ledger = _build_agent(clock=lambda: DAYTIME)
    reason = agent.run_case(_case())
    assert reason == StopReason.NEGATIVE_EV


def test_kernel_deny_outside_contact_hours_stops_case():
    agent, ledger = _build_agent(clock=lambda: NIGHTTIME)
    reason = agent.run_case(_case())
    assert reason == StopReason.REGULATORY_CEILING
    certs = [e for e in ledger.entries_for_case("case_1") if e.entry_type == "certificate"]
    assert certs, "expected at least one certificate entry before stopping"
    assert certs[0].payload["decision"] == "DENY"


def test_opted_out_customer_is_never_contacted():
    case = _case(customer=CustomerProfile(
        customer_id="cust_1", opted_out=True, opted_out_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
    ))
    agent, ledger = _build_agent(clock=lambda: DAYTIME)
    reason = agent.run_case(case)
    assert reason == StopReason.REGULATORY_CEILING
    action_results = [e for e in ledger.entries_for_case("case_1") if e.entry_type == "action_result"]
    assert all(not e.payload["executed"] for e in action_results)


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
    reason_a = agent_a.run_case(_case())
    reason_b = agent_b.run_case(_case())
    assert reason_a == reason_b
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
