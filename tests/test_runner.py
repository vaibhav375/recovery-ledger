"""The resumption queue (agent/runner.py): paused cases must actually wake
up, the clock must advance, and the whole thing must provably terminate."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np

from recovery_ledger.agent.loop import RecoveryAgent
from recovery_ledger.agent.runner import BatchRunner, exception_report
from recovery_ledger.detector.detector import CaseDetector
from recovery_ledger.diagnoser.diagnoser import CaseDiagnoser
from recovery_ledger.events.actions import StopReason
from recovery_ledger.events.schemas import Channel, CustomerProfile, FailedPaymentCase
from recovery_ledger.executor.executor import SimulatedExecutor
from recovery_ledger.kernel.engine import KernelEngine
from recovery_ledger.kernel.rules.promise import PromiseToPayWindowRule
from recovery_ledger.kernel.rules.timing import ContactHoursRule
from recovery_ledger.ledger.ledger import Ledger
from recovery_ledger.listener.listener import ReplyIntent
from recovery_ledger.policy.decision import EVDecisionPolicy

DAY = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)


class FixedUplift:
    def __init__(self, cate=0.4):
        self.cate = cate

    def predict_cate(self, X):
        return np.full(len(X), self.cate)


class Replies:
    def __init__(self, seq):
        self.seq, self.i = list(seq), 0

    def listen(self, case, action_type, attempt_index):
        r = self.seq[min(self.i, len(self.seq) - 1)]
        self.i += 1
        return r


def _case(cid="c", amount=1000.0):
    return FailedPaymentCase(
        case_id=cid, customer=CustomerProfile(customer_id=f"u{cid}", channel_pref=Channel.SMS),
        amount_at_risk=amount, detected_at=DAY - timedelta(days=3),
        failure_code="insufficient_funds", is_hard_decline=False, payment_method="upi",
    )


def _agent(listener):
    return RecoveryAgent(
        detector=CaseDetector(), diagnoser=CaseDiagnoser(),
        policy=EVDecisionPolicy(uplift_model=FixedUplift()),
        kernel=KernelEngine(rules=[ContactHoursRule(), PromiseToPayWindowRule()]),
        executor=SimulatedExecutor(), listener=listener, ledger=Ledger(), clock=lambda: DAY,
    )


def test_paused_case_resumes_and_clock_advances():
    """A promise pauses the case; the runner advances simulated time past the
    promise window and works it again."""
    agent = _agent(Replies([ReplyIntent.PROMISE_TO_PAY, ReplyIntent.PAID]))
    result = BatchRunner(agent).run([_case("c1")], now=DAY)

    assert result.rounds_run >= 2, "the case must be picked up again after pausing"
    assert result.clock_advances, "the runner must advance simulated time"
    assert result.clock_advances[0] > DAY
    assert result.outcomes["c1"].is_terminated


def test_all_cases_reach_a_terminal_outcome_or_are_reported_as_exceptions():
    agent = _agent(Replies([ReplyIntent.NO_REPLY]))
    cases = [_case(f"c{i}") for i in range(5)]
    result = BatchRunner(agent).run(cases, now=DAY)

    for c in cases:
        assert c.case_id in result.outcomes
    accounted = len(result.terminated) + len(result.exceptions)
    assert accounted >= len(cases), "no case may be silently dropped"


def test_runner_terminates_even_when_the_customer_promises_forever():
    """A customer who promises on every single contact must not keep the
    agent working the case indefinitely — the attempt budget carries across
    resumptions precisely to prevent that."""
    agent = _agent(Replies([ReplyIntent.PROMISE_TO_PAY]))
    result = BatchRunner(agent, max_rounds=6).run([_case("c1")], now=DAY)
    assert result.rounds_run <= 6


def test_exception_report_lists_unresolved_cases_with_reasons():
    agent = _agent(Replies([ReplyIntent.NO_REPLY]))
    result = BatchRunner(agent).run([_case("c1"), _case("c2")], now=DAY)
    rows = exception_report(result)
    assert rows, "cases that did not recover must appear in the exception list"
    assert all("reason" in r and "case_id" in r for r in rows)


def test_promise_window_suppresses_contact_in_the_kernel():
    """The silence window is enforced by the compliance kernel and visible in
    the audit trail — not hidden in the agent's control flow."""
    agent = _agent(Replies([ReplyIntent.PROMISE_TO_PAY, ReplyIntent.NO_REPLY]))
    agent.promises["c1"] = DAY + timedelta(days=30)   # promise far in the future
    agent.run_case(_case("c1"))

    denials = [
        e for e in agent.ledger.entries_for_case("c1")
        if e.entry_type == "certificate" and e.payload["decision"] == "DENY"
        and any(r["rule_name"] == "POLICY.PROMISE_TO_PAY_WINDOW" and not r["passed"]
                for r in e.payload["rule_results"])
    ]
    assert denials, "contact during an active promise window must be denied by the kernel"
