"""The agent loop (spec section 5): detect → diagnose → decide → gate → act →
listen → stop. Every step is written to the ledger, so a full run is
reconstructible from the audit trail alone. This is deliberately the
component built early and kept working at every commit — the "the agent is
the product" rule (spec section 0) — even while the components it calls
(policy, listener, simulator) are still stubs.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from recovery_ledger.detector.detector import CaseDetector
from recovery_ledger.diagnoser.diagnoser import CaseDiagnoser
from recovery_ledger.events.actions import ActionType, StopReason
from recovery_ledger.events.outcomes import CaseOutcome
from recovery_ledger.events.schemas import Channel, RecoveryCase
from recovery_ledger.executor.executor import SimulatedExecutor
from recovery_ledger.kernel.certificate import Decision
from recovery_ledger.kernel.engine import ConsentInfo, DLTInfo, KernelEngine, MandateInfo, RuleContext
from recovery_ledger.ledger.ledger import Ledger
from recovery_ledger.listener.listener import Listener, ReplyIntent
from recovery_ledger.policy.decision import DecisionPolicy

REPLY_TO_STOP_REASON = {
    ReplyIntent.PAID: StopReason.RESOLVED,
    ReplyIntent.OPT_OUT: StopReason.OPT_OUT,
    ReplyIntent.DISPUTE: StopReason.DISPUTE_RAISED,
}

# How long after a promised payment date the agent waits before working the
# case again — the "+ grace" in spec section 10, rule 6.
PROMISE_GRACE = timedelta(days=2)


class KillSwitch:
    """Operator halt (spec section 10, rule 11). Shared across agents so a
    single operator action stops the whole fleet, not one case."""

    def __init__(self, engaged: bool = False):
        self._engaged = engaged

    def engage(self) -> None:
        self._engaged = True

    def release(self) -> None:
        self._engaged = False

    @property
    def engaged(self) -> bool:
        return self._engaged

DEFAULT_ATTEMPT_CAP = 3
DEFAULT_WINDOW_DAYS = 7
HARD_MAX_STEPS = 10  # safety net: the loop must provably terminate (B3) even if a
                      # future, non-stub policy has a bug that never proposes STOP


class RecoveryAgent:
    def __init__(
        self,
        *,
        detector: CaseDetector,
        diagnoser: CaseDiagnoser,
        policy: DecisionPolicy,
        kernel: KernelEngine,
        executor: SimulatedExecutor,
        listener: Listener,
        ledger: Ledger,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        kill_switch: "KillSwitch | None" = None,
        respect_promise_windows: bool = True,
    ):
        self.detector = detector
        self.diagnoser = diagnoser
        self.policy = policy
        self.kernel = kernel
        self.executor = executor
        self.listener = listener
        self.ledger = ledger
        self.clock = clock
        self.kill_switch = kill_switch or KillSwitch()
        self.respect_promise_windows = respect_promise_windows
        # case_id -> datetime the customer promised to pay by (+ grace).
        # Survives across resumptions so the kernel can enforce silence.
        self.promises: dict[str, datetime] = {}

    def _stop(self, case: RecoveryCase, reason: StopReason) -> CaseOutcome:
        self.ledger.append(case.case_id, "stop", {"reason": reason.value})
        return CaseOutcome.terminated(case.case_id, reason)

    def _pause(self, case: RecoveryCase, resume_at: datetime, reason: StopReason) -> CaseOutcome:
        self.ledger.append(
            case.case_id, "pause", {"reason": reason.value, "resume_at": resume_at.isoformat()},
        )
        return CaseOutcome.paused(case.case_id, resume_at, reason)

    def _rule_context(
        self,
        case: RecoveryCase,
        action_type: ActionType,
        channel: Channel | None,
        attempts_so_far: int,
    ) -> RuleContext:
        return RuleContext(
            case=case,
            action_type=action_type,
            channel=channel,
            now_ist=self.clock(),
            attempts_in_window=attempts_so_far,
            attempt_cap=DEFAULT_ATTEMPT_CAP,
            window_days=DEFAULT_WINDOW_DAYS,
            message_class="service",
            # Consent inferred from the existing transaction/subscription/
            # invoice relationship the case arose from, captured at
            # detection time — not marketing outreach to a stranger.
            consent=ConsentInfo(basis="inferred", captured_at=case.detected_at, contract_active=True),
            dlt=DLTInfo(registered=True, header="RZPRCV-S", template_class="service"),
            # Modelling choice: the case's detection is treated as when the
            # pre-debit notice would have gone out, so a mandate RETRY
            # genuinely can get denied here if it's attempted too soon —
            # this isn't forced to always pass.
            mandate=MandateInfo(pre_debit_notice_sent_at=case.detected_at),
            includes_opt_out_option=True,
            sender_number_series="160",
            tone_intensity=min(attempts_so_far, 3),
            promise_to_pay_until=(
                self.promises.get(case.case_id) if self.respect_promise_windows else None
            ),
        )

    def run_case(self, case: RecoveryCase, *, start_attempt: int = 0) -> CaseOutcome:
        """Work a case until it terminates or must pause.

        `start_attempt` lets a resumed case continue spending the attempt
        budget it had already partly used, rather than getting a fresh
        allowance every time it wakes up — otherwise a customer could be
        contacted indefinitely by promising to pay each time.
        """
        if start_attempt == 0:
            self.ledger.append(case.case_id, "case_ingested", case.model_dump(mode="json"))

        resolved = False
        for attempts_so_far in range(start_attempt, HARD_MAX_STEPS):
            # Rule 11 — operator halt. Checked first and every iteration, so
            # engaging it stops in-flight work rather than only new work.
            if self.kill_switch.engaged:
                return self._stop(case, StopReason.GLOBAL_KILL_SWITCH)

            if not self.detector.is_at_risk(case, resolved=resolved):
                return self._stop(case, StopReason.RESOLVED)

            diagnosis = self.diagnoser.diagnose(case)
            self.ledger.append(case.case_id, "diagnosis", diagnosis.model_dump())

            decision = self.policy.decide(case, diagnosis, attempts_so_far)
            self.ledger.append(case.case_id, "decision", decision.model_dump())

            if decision.action_type == ActionType.STOP:
                # Attribute what the policy actually said, rather than
                # assuming NEGATIVE_EV for every stop — that conflation hid
                # budget exhaustion entirely (see ENGINEERING_LOG.md).
                return self._stop(case, decision.stop_reason or StopReason.NEGATIVE_EV)

            if decision.action_type == ActionType.ESCALATE_HUMAN:
                return self._stop(
                    case, decision.stop_reason or StopReason.HUMAN_ESCALATION_THRESHOLD
                )

            certificate = self.kernel.issue_certificate(
                self._rule_context(case, decision.action_type, decision.channel, attempts_so_far)
            )
            self.ledger.append(case.case_id, "certificate", certificate.model_dump(mode="json"))

            executed_action = decision.action_type
            if certificate.decision == Decision.DENY:
                # Spec section 10, stopping rule 10 is "the kernel denies ALL
                # remaining actions" — NOT "the kernel denied the one action
                # the policy happened to propose first". Falling back to WAIT
                # (which is never customer contact, and is exempt from every
                # rule in the kernel) keeps the case alive for organic
                # resolution instead of abandoning it over a single
                # inadmissible action.
                #
                # This matters more than it sounds: before this fix, the EV
                # policy's preference for RETRY on mandate cases meant ~12%
                # of its cases were killed outright by the 24-hour pre-debit
                # notice rule, while a policy that only ever nudged never
                # tripped that rule at all — an artificial penalty for using
                # more of the action space (measured 2026-08-24, see
                # ENGINEERING_LOG.md).
                fallback_certificate = self.kernel.issue_certificate(
                    self._rule_context(case, ActionType.WAIT, None, attempts_so_far)
                )
                self.ledger.append(
                    case.case_id, "certificate", fallback_certificate.model_dump(mode="json")
                )
                if fallback_certificate.decision == Decision.DENY:
                    return self._stop(case, StopReason.REGULATORY_CEILING)
                certificate = fallback_certificate
                executed_action = ActionType.WAIT

            result = self.executor.execute(certificate)
            self.ledger.append(case.case_id, "action_result", result.model_dump())

            reply = self.listener.listen(case, executed_action, attempts_so_far)
            self.ledger.append(case.case_id, "reply", {"intent": reply.value})

            if reply == ReplyIntent.PROMISE_TO_PAY:
                # Rule 6 — a promise is a PAUSE, not an ending. Record when
                # the agent may speak again and hand the case back to the
                # runner; the kernel enforces silence until then.
                promised_by = self.clock() + PROMISE_GRACE
                self.promises[case.case_id] = promised_by
                if self.respect_promise_windows:
                    return self._pause(case, promised_by, StopReason.PROMISE_TO_PAY_ACTIVE)

            if reply in REPLY_TO_STOP_REASON:
                if reply == ReplyIntent.PAID:
                    resolved = True
                    continue  # let the next loop iteration's detector check record RESOLVED
                return self._stop(case, REPLY_TO_STOP_REASON[reply])

        return self._stop(case, StopReason.BUDGET_EXHAUSTED)
