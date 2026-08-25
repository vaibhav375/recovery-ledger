"""Runs the real agent, live, and reports what it did as it does it.

Nothing here re-implements the agent. It builds exactly the wiring
`experiments/tier2_simulation/run_batch.py` builds — the same trained
T-learner, the same churn model, the same 13-rule kernel, the same
`LookaheadEVDecisionPolicy` — subscribes to the ledger, and forwards entries
to whoever is watching. If the live console showed something the batch
experiment would not have done, this module would be a lie, so it is written
to make that impossible: the only thing it adds to a normal run is a
listener on the ledger.

Two honesty rules the console depends on:

* Timings are real. Every event carries `t_ms`, the elapsed wall-clock time
  since the run started. A full case resolves in single-digit milliseconds;
  the console replays that at reading speed and says so on screen rather than
  pretending a human could watch it live.

* The kill switch is the real `KillSwitch` from `agent/loop.py`, the same
  object stopping rule 11 checks. Engaging it from the browser is not a UI
  affordance that fakes a halt — the next case the loop starts finds the
  switch engaged and stops for `GLOBAL_KILL_SWITCH`, in the ledger, where you
  can read it back.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from queue import Empty, Queue
from typing import Any

import numpy as np

from recovery_ledger.agent.loop import KillSwitch, RecoveryAgent
from recovery_ledger.agent.runner import BatchRunner
from recovery_ledger.detector.detector import CaseDetector
from recovery_ledger.diagnoser.diagnoser import CaseDiagnoser
from recovery_ledger.events.actions import ActionType
from recovery_ledger.executor.executor import SimulatedExecutor
from recovery_ledger.kernel.engine import KernelEngine
from recovery_ledger.kernel.rules.budget import ContactBudgetRule
from recovery_ledger.kernel.rules.dpdp import ConsentRecordExistsRule
from recovery_ledger.kernel.rules.emandate_2026 import PreDebitNotificationRule
from recovery_ledger.kernel.rules.escalation import ToneIntensityCeilingRule
from recovery_ledger.kernel.rules.negotiation import NegotiationEnvelopeRule
from recovery_ledger.kernel.rules.opt_out import OptOutRule
from recovery_ledger.kernel.rules.promise import PromiseToPayWindowRule
from recovery_ledger.kernel.rules.tcccpr import (
    ConsentValidityRule,
    DLTRegistrationRule,
    HeaderClassMatchRule,
    NumberSeriesRule,
    OptOutOptionPresentRule,
)
from recovery_ledger.kernel.rules.timing import ContactHoursRule
from recovery_ledger.ledger.ledger import Ledger, LedgerEntry
from recovery_ledger.listener.listener import ReplyIntent
from recovery_ledger.policy.churn import ChurnRiskModel
from recovery_ledger.policy.decision import LookaheadEVDecisionPolicy
from recovery_ledger.policy.features import cases_to_feature_matrix
from recovery_ledger.policy.uplift.learners import TLearnerModel
from recovery_ledger.sim.environment import (
    EnvironmentListener,
    SimulationEnvironment,
    generate_population,
    persuadability,
)
from recovery_ledger.sim.generator import generate_cases

# Same fixed reference time the batch experiment uses. Case generation must be
# reproducible from the seed alone.
NOW = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)
DEFAULT_SEED = 20260823
# Matches `make eval`'s --n-train, so the console's models are the models the
# published results describe rather than a cheaper approximation of them.
TRAIN_N = 5000

# Cases the agent actually works are drawn from a seed disjoint from the one
# the models were fitted on — the same separation experiments/tier2_simulation
# uses (SEED for training, SEED + 1000 for evaluation). Sharing a seed would
# have the console demonstrating the agent on its own training distribution.
EVAL_SEED = DEFAULT_SEED + 1000
EVAL_N = 2000


def build_kernel() -> KernelEngine:
    """The same 13 rules the batch experiment and `make demo` register."""
    return KernelEngine(rules=[
        ContactHoursRule(), OptOutRule(), ContactBudgetRule(),
        DLTRegistrationRule(), HeaderClassMatchRule(), ConsentValidityRule(),
        OptOutOptionPresentRule(), NumberSeriesRule(),
        PreDebitNotificationRule(), ConsentRecordExistsRule(), ToneIntensityCeilingRule(),
        PromiseToPayWindowRule(), NegotiationEnvelopeRule(),
    ])


# ── model cache ──────────────────────────────────────────────────────────

@dataclass
class TrainedModels:
    uplift: TLearnerModel
    churn: ChurnRiskModel
    seed: int
    n_train: int
    train_seconds: float
    # Correlation between predicted CATE and the simulator's hidden
    # persuadability trait, measured on HELD-OUT cases (EVAL_SEED), never on
    # the training cases. A live console that shows tau_hat driving decisions
    # has to be honest about how good tau_hat is, and a train-set correlation
    # would flatter it. This is the same quantity RESULTS.md reports.
    uplift_correlation: float


_MODEL_LOCK = threading.Lock()
_MODELS: TrainedModels | None = None


def get_models(seed: int = DEFAULT_SEED, n_train: int = TRAIN_N) -> TrainedModels:
    """Train once per process, then reuse. Fitting takes a few seconds; doing
    it per request would make the console feel like the agent is slow when it
    is the training that is slow."""
    global _MODELS
    with _MODEL_LOCK:
        if _MODELS is not None and _MODELS.seed == seed and _MODELS.n_train == n_train:
            return _MODELS
        started = time.perf_counter()

        cases = generate_cases(n_train, seed=seed, now=NOW)
        traits = generate_population(cases, seed=seed)
        env = SimulationEnvironment(traits, seed=seed)
        rng = np.random.default_rng(seed)
        treatment = rng.integers(0, 2, size=n_train)

        paid = np.zeros(n_train)
        churned = np.zeros(n_train)
        for i, case in enumerate(cases):
            action = ActionType.NUDGE if treatment[i] == 1 else ActionType.WAIT
            result = env.step(case, action, attempt_index=0)
            paid[i] = float(result.paid)
            churned[i] = float(result.reply == ReplyIntent.OPT_OUT)

        X = cases_to_feature_matrix(cases)
        uplift = TLearnerModel(random_state=seed)
        uplift.fit(X, treatment, paid)
        churn = ChurnRiskModel().fit(X, treatment, churned, random_state=seed)

        # Held-out, and computed exactly the way run_batch.py computes the
        # figure in RESULTS.md: a fresh EVAL_N draw on EVAL_SEED, the model's
        # predicted CATE against the simulator's hidden persuadability trait.
        eval_cases = generate_cases(EVAL_N, seed=EVAL_SEED, now=NOW)
        eval_traits = generate_population(eval_cases, seed=EVAL_SEED)
        X_eval = cases_to_feature_matrix(eval_cases)
        corr = float(np.corrcoef(
            uplift.predict_cate(X_eval),
            np.array([persuadability(eval_traits[c.case_id]) for c in eval_cases]),
        )[0, 1])

        _MODELS = TrainedModels(
            uplift=uplift, churn=churn, seed=seed, n_train=n_train,
            train_seconds=time.perf_counter() - started,
            uplift_correlation=corr,
        )
        return _MODELS


# ── a run ────────────────────────────────────────────────────────────────

@dataclass
class RunSession:
    """One live run. Events are pushed to a queue as the agent produces them;
    every listener drains its own copy."""

    run_id: str
    seed: int
    n_cases: int
    # Deliberate delay between ledger entries, so a run is watchable and the
    # kill switch is reachable by a human hand. It does NOT contaminate the
    # reported timings: `_paced_ms` is accumulated and subtracted, so `t_ms`
    # on every event remains true agent time and `wall_ms` reports the clock.
    pace_ms: int = 0
    kill: KillSwitch = field(default_factory=KillSwitch)
    ledger: Ledger = field(default_factory=Ledger)
    _events: list[dict] = field(default_factory=list)
    _subscribers: list[Queue] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    started_at: float = field(default_factory=time.perf_counter)
    finished: bool = False
    summary: dict[str, Any] | None = None
    error: str | None = None
    _paced_ms: float = 0.0

    # ---- fan-out ----
    def _emit(self, event: dict) -> None:
        with self._lock:
            self._events.append(event)
            subs = tuple(self._subscribers)
        for q in subs:
            q.put(event)

    def subscribe(self) -> tuple[Queue, list[dict]]:
        """Returns a queue for future events and the backlog so far, so a
        browser that connects late still sees the whole run."""
        q: Queue = Queue()
        with self._lock:
            backlog = list(self._events)
            self._subscribers.append(q)
        return q, backlog

    def unsubscribe(self, q: Queue) -> None:
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def stream(self, timeout: float = 30.0) -> Iterator[dict]:
        q, backlog = self.subscribe()
        try:
            for event in backlog:
                yield event
                if event.get("type") == "run_finished":
                    return
            if self.finished:
                return
            while True:
                try:
                    event = q.get(timeout=timeout)
                except Empty:
                    yield {"type": "heartbeat", "t_ms": self._elapsed_ms()}
                    continue
                yield event
                if event.get("type") == "run_finished":
                    return
        finally:
            self.unsubscribe(q)

    def _wall_ms(self) -> float:
        return round((time.perf_counter() - self.started_at) * 1000, 2)

    def _elapsed_ms(self) -> float:
        """Agent time: wall clock minus any delay we introduced for viewing."""
        return round(self._wall_ms() - self._paced_ms, 2)

    def _pace(self) -> None:
        if self.pace_ms > 0:
            time.sleep(self.pace_ms / 1000.0)
            self._paced_ms += self.pace_ms


def _entry_event(entry: LedgerEntry, elapsed_ms: float) -> dict:
    return {
        "type": "ledger",
        "t_ms": elapsed_ms,
        "seq": entry.seq,
        "case_id": entry.case_id,
        "entry_type": entry.entry_type,
        "payload": entry.payload,
        "hash": entry.hash,
        "prev_hash": entry.prev_hash,
    }


def run_session(
    session: RunSession,
    *,
    on_done: Callable[[RunSession], None] | None = None,
) -> None:
    """Execute the run. Blocking; the server calls this on a worker thread."""
    try:
        models = get_models()
        # Model fitting is a one-off process cost, not agent time, and it
        # happens before the run. Start the clock after it so `t_ms` measures
        # what it claims to measure; training is reported separately on the
        # run_started event.
        session.started_at = time.perf_counter()
        cases = generate_cases(session.n_cases, seed=session.seed, now=NOW)
        traits = generate_population(cases, seed=session.seed)
        env = SimulationEnvironment(traits, seed=session.seed + 2)
        listener = EnvironmentListener(env)

        agent = RecoveryAgent(
            detector=CaseDetector(),
            diagnoser=CaseDiagnoser(),
            policy=LookaheadEVDecisionPolicy(
                uplift_model=models.uplift, churn_model=models.churn
            ),
            kernel=build_kernel(),
            executor=SimulatedExecutor(),
            listener=listener,
            ledger=session.ledger,
            clock=lambda: NOW,
            kill_switch=session.kill,
        )

        def _on_entry(entry: LedgerEntry) -> None:
            session._emit(_entry_event(entry, session._elapsed_ms()))
            session._pace()

        session.ledger.subscribe(_on_entry)

        X = cases_to_feature_matrix(cases)
        tau_hat = models.uplift.predict_cate(X)

        # The roster goes out before anything runs, so the console can show
        # what the agent is about to work on — including the model's own
        # estimate for each case, so a viewer sees the number the policy is
        # about to act on rather than taking the decision on faith.
        session._emit({
            "type": "run_started",
            "t_ms": session._elapsed_ms(),
            "run_id": session.run_id,
            "seed": session.seed,
            "n_cases": session.n_cases,
            "policy": "LookaheadEVDecisionPolicy",
            "rules": [r.name for r in agent.kernel.rules],
            "uplift_correlation": round(models.uplift_correlation, 3),
            "train_seconds": round(models.train_seconds, 2),
            "roster": [
                {
                    "index": i,
                    "case_id": case.case_id,
                    "loss_type": type(case).__name__,
                    "amount": float(case.amount_at_risk),
                    "language": case.customer.language_pref.value,
                    "is_b2b": bool(getattr(case.customer, "is_b2b", False)),
                    "tau_hat": round(float(tau_hat[i]), 4),
                }
                for i, case in enumerate(cases)
            ],
        })

        # BatchRunner, not a bare loop over run_case: a promise to pay is a
        # pause, and the runner is what advances simulated time and brings
        # those cases back. Using anything else here would make the console
        # show a different agent from the one the results come from.
        result = BatchRunner(agent).run(cases, now=NOW)

        recovered = sum(
            float(c.amount_at_risk) for c in cases if c.case_id in listener.paid_cases
        )
        chain = session.ledger.verify_chain_detail()
        session.summary = {
            "cases": len(cases),
            "entries": len(session.ledger),
            "recovered_rupees": round(recovered, 2),
            "resolved": sum(
                1 for o in result.outcomes.values()
                if o.stop_reason is not None and o.stop_reason.value == "resolved"
            ),
            "stop_reasons": result.stop_reason_counts(),
            # Cases still paused when the horizon was reached. Reported, not
            # dropped and not counted as failures — the honest exception list.
            "still_open": [
                {"case_id": p.case.case_id, "resume_at": p.resume_at.isoformat()}
                for p in result.exceptions
            ],
            "rounds_run": result.rounds_run,
            "chain": chain,
            "killed": session.kill.engaged,
            "agent_ms": session._elapsed_ms(),
            "wall_ms": session._wall_ms(),
            "paced_ms": round(session._paced_ms, 2),
        }
    except Exception as exc:  # noqa: BLE001 — surfaced to the client, not swallowed
        session.error = f"{type(exc).__name__}: {exc}"
    finally:
        session.finished = True
        session._emit({
            "type": "run_finished",
            "t_ms": session._elapsed_ms(),
            "summary": session.summary,
            "error": session.error,
        })
        if on_done is not None:
            on_done(session)


def new_session(seed: int, n_cases: int, pace_ms: int = 0) -> RunSession:
    return RunSession(
        run_id=uuid.uuid4().hex[:12], seed=seed, n_cases=n_cases, pace_ms=pace_ms
    )
