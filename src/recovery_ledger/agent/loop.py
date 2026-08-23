"""The agent loop (spec section 5): detect → diagnose → decide → gate → act →
listen → stop. Every step is written to the ledger, so a full run is
reconstructible from the audit trail alone. This is deliberately the
component built early and kept working at every commit — the "the agent is
the product" rule (spec section 0) — even while the components it calls
(policy, listener, simulator) are still stubs.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from recovery_ledger.detector.detector import CaseDetector
from recovery_ledger.diagnoser.diagnoser import CaseDiagnoser
from recovery_ledger.events.actions import ActionType, StopReason
from recovery_ledger.events.schemas import RecoveryCase
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
    ReplyIntent.PROMISE_TO_PAY: StopReason.PROMISE_TO_PAY_ACTIVE,
}

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
    ):
        self.detector = detector
        self.diagnoser = diagnoser
        self.policy = policy
        self.kernel = kernel
        self.executor = executor
        self.listener = listener
        self.ledger = ledger
        self.clock = clock

    def _stop(self, case: RecoveryCase, reason: StopReason) -> StopReason:
        self.ledger.append(case.case_id, "stop", {"reason": reason.value})
        return reason

    def run_case(self, case: RecoveryCase) -> StopReason:
        self.ledger.append(case.case_id, "case_ingested", case.model_dump(mode="json"))

        resolved = False
        for attempts_so_far in range(HARD_MAX_STEPS):
            if not self.detector.is_at_risk(case, resolved=resolved):
                return self._stop(case, StopReason.RESOLVED)

            diagnosis = self.diagnoser.diagnose(case)
            self.ledger.append(case.case_id, "diagnosis", diagnosis.model_dump())

            decision = self.policy.decide(case, diagnosis, attempts_so_far)
            self.ledger.append(case.case_id, "decision", decision.model_dump())

            if decision.action_type == ActionType.STOP:
                return self._stop(case, StopReason.NEGATIVE_EV)

            context = RuleContext(
                case=case,
                action_type=decision.action_type,
                channel=decision.channel,
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
            )
            certificate = self.kernel.issue_certificate(context)
            self.ledger.append(case.case_id, "certificate", certificate.model_dump(mode="json"))

            if certificate.decision == Decision.DENY:
                return self._stop(case, StopReason.REGULATORY_CEILING)

            result = self.executor.execute(certificate)
            self.ledger.append(case.case_id, "action_result", result.model_dump())

            reply = self.listener.listen(case, decision.action_type, attempts_so_far)
            self.ledger.append(case.case_id, "reply", {"intent": reply.value})

            if reply in REPLY_TO_STOP_REASON:
                if reply == ReplyIntent.PAID:
                    resolved = True
                    continue  # let the next loop iteration's detector check record RESOLVED
                return self._stop(case, REPLY_TO_STOP_REASON[reply])

        return self._stop(case, StopReason.BUDGET_EXHAUSTED)
