"""The Kernel Range: fire an attack at the compliance kernel and watch it land.

Two things happen here, and they are different.

**Attacks** replay the project's actual adversarial suite — the same
`redteam/attacks.py` that produces the 100% block rate in `make redteam` —
one at a time, against the real 13-rule kernel, returning the real
certificate. The point of doing it interactively is not decoration: a claimed
block rate is a number in a report, and a refusal you triggered yourself is
evidence. Same code, same oracle, one attack at a time.

**Mutation** is the other half, and the more important one. A test suite that
cannot fail proves nothing. `disabled_rules` removes rules from the kernel
before the attack runs, so you can switch off `RBI.RECOVERY.HOURS`, fire the
03:00 contact again, and watch the same attack sail through with an ALLOW.
That is the demonstration that the 100% is load-bearing rather than
tautological — and it is the same argument `make redteam`'s mutation testing
makes offline.

**Counterfactuals** are separate: not an attack, but the same real case run
twice with one fact of the world changed, so you can see which single fact
moved the decision. The agent, kernel, policy, and simulator are unchanged
between the two runs; only the stated fact differs.
"""

from __future__ import annotations

import copy
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from recovery_ledger.agent.loop import RecoveryAgent
from recovery_ledger.detector.detector import CaseDetector
from recovery_ledger.diagnoser.diagnoser import CaseDiagnoser
from recovery_ledger.executor.executor import SimulatedExecutor
from recovery_ledger.kernel.engine import KernelEngine
from recovery_ledger.kernel.provenance import citation_for
from recovery_ledger.ledger.ledger import Ledger
from recovery_ledger.live.session import EVAL_SEED, NOW, build_kernel, get_models
from recovery_ledger.policy.decision import LookaheadEVDecisionPolicy
from recovery_ledger.sim.environment import (
    EnvironmentListener,
    SimulationEnvironment,
    generate_population,
)
from recovery_ledger.sim.generator import generate_cases

# `redteam/` is a first-party directory of this repository, alongside
# `experiments/`, and the Makefile already puts it on PYTHONPATH for
# `make redteam`. The live server is an application entry point, so it is
# allowed to know the repo's layout; the alternative — a second, parallel copy
# of the attack definitions inside the package — would let the interactive
# demo and the reported block rate drift apart, which is the one outcome that
# would make this feature dishonest.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_REDTEAM_DIR = _REPO_ROOT / "redteam"
if _REDTEAM_DIR.is_dir() and str(_REDTEAM_DIR) not in sys.path:
    sys.path.insert(0, str(_REDTEAM_DIR))

try:  # pragma: no cover - exercised by the server, not the unit tests
    from attacks import Attack, build_attacks  # type: ignore
except ImportError:  # pragma: no cover
    Attack = None  # type: ignore[assignment]

    def build_attacks():  # type: ignore[misc]
        return []


_ATTACK_CACHE: list[Any] | None = None


def attacks() -> list[Any]:
    global _ATTACK_CACHE
    if _ATTACK_CACHE is None:
        _ATTACK_CACHE = build_attacks()
    return _ATTACK_CACHE


def attack_catalogue() -> list[dict]:
    """What a client can fire, without the RuleContext internals."""
    return [
        {
            "name": a.name,
            "category": a.category,
            "intent": a.intent,
            "must_be_denied": a.must_be_denied,
        }
        for a in attacks()
    ]


def all_rule_names() -> list[str]:
    return [r.name for r in build_kernel().rules]


def _kernel_without(disabled: list[str]) -> KernelEngine:
    disabled_set = set(disabled or [])
    return KernelEngine(
        rules=[r for r in build_kernel().rules if r.name not in disabled_set]
    )


def fire(name: str, disabled_rules: list[str] | None = None) -> dict:
    """Run one named attack against the kernel and report the certificate.

    `disabled_rules` is the mutation lever. With it empty this is exactly what
    `make redteam` does. With a rule removed, the same attack is re-run against
    a deliberately weakened kernel, and `mutation` reports whether removing
    that rule is what let the attack through — which is the only way to know
    the rule was doing the work.
    """
    match = next((a for a in attacks() if a.name == name), None)
    if match is None:
        return {"error": f"no attack named {name!r}"}

    disabled = list(disabled_rules or [])
    cert = _kernel_without(disabled).issue_certificate(match.context)
    denied = [r for r in cert.rule_results if not r.passed]

    # The oracle is independent of the kernel: `must_be_denied` is asserted by
    # the attack definition, not derived from what the kernel happened to do.
    blocked = cert.decision.value == "DENY"
    correct = blocked == match.must_be_denied

    result = {
        "attack": {
            "name": match.name,
            "category": match.category,
            "intent": match.intent,
            "must_be_denied": match.must_be_denied,
        },
        "decision": cert.decision.value,
        "action_type": cert.action_type.value,
        "channel": cert.channel.value if cert.channel else None,
        "rules_evaluated": len(cert.rule_results),
        "disabled_rules": disabled,
        "correct": correct,
        "results": [
            {
                "rule": r.rule_name,
                "passed": r.passed,
                "detail": r.detail,
                "citation": (c.to_dict() if (c := citation_for(r.rule_name)) else None),
            }
            for r in cert.rule_results
        ],
        "denied_by": [
            {
                "rule": r.rule_name,
                "detail": r.detail,
                "citation": (c.to_dict() if (c := citation_for(r.rule_name)) else None),
            }
            for r in denied
        ],
    }

    if disabled:
        baseline = build_kernel().issue_certificate(match.context)
        was_blocked = baseline.decision.value == "DENY"
        result["mutation"] = {
            "baseline_decision": baseline.decision.value,
            "mutated_decision": cert.decision.value,
            # The finding that matters: with every rule present this attack is
            # refused, and with these rules removed it is not. That is the
            # rules doing work, stated as a fact about this run.
            "rule_was_load_bearing": was_blocked and not blocked,
            "note": (
                "The attack now passes. The removed rule was the only thing "
                "refusing it."
                if was_blocked and not blocked
                else "Still refused — another rule independently catches this. "
                "Defence in depth, not a single point of failure."
                if blocked
                else "This attack was not being refused even before the "
                "mutation; see `correct`."
            ),
        }
    return result


# ── counterfactuals ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class Lever:
    """One fact about the world that a viewer can change."""

    key: str
    label: str
    description: str
    # Which rule or mechanism this is expected to engage. Stated so a viewer
    # can check the prediction against what actually happens, rather than
    # being told afterwards what they just saw.
    expects: str
    # Some levers only mean anything on some cases: a pre-debit notice window
    # is meaningless on an invoice. The auto-picker honours this rather than
    # showing a lever that visibly does nothing and leaving it unexplained.
    requires_subscription: bool = False


LEVERS: list[Lever] = [
    Lever(
        key="night",
        label="It is 03:00, not midday",
        description="Move the agent's clock to 03:00 IST, leaving everything else identical.",
        expects="RBI.RECOVERY.HOURS should refuse contact; silent retries stay permitted.",
    ),
    Lever(
        key="opted_out",
        label="The customer opted out yesterday",
        description="Set the customer's opt-out flag and timestamp.",
        expects="TCCCPR.OPT_OUT.COOLING should refuse contact for 90 days.",
    ),
    Lever(
        key="promised",
        label="The customer promised to pay on the 12th",
        description="Register a promise-to-pay date the agent has already been given.",
        expects="POLICY.PROMISE_TO_PAY_WINDOW should refuse contact until that date plus grace.",
    ),
    Lever(
        key="fresh_debit",
        label="The pre-debit notice went out an hour ago",
        description="Move the case's detection time to one hour before now.",
        expects=(
            "EMANDATE2026.PRE_DEBIT_NOTICE should refuse a mandate debit inside "
            "the 24-hour window."
        ),
        requires_subscription=True,
    ),
    Lever(
        key="high_value",
        label="The amount is ₹90,000, not what it was",
        description="Raise the amount at risk above the agent's autonomy limit.",
        expects="The policy should hand off to a human rather than act (human_escalation_threshold).",
    ),
]


def lever_catalogue() -> list[dict]:
    return [
        {"key": l.key, "label": l.label, "description": l.description, "expects": l.expects}
        for l in LEVERS
    ]


def _apply_lever(case, lever_key: str, clock_now: datetime) -> tuple[Any, datetime, datetime | None]:
    """Returns (case, clock, promise_until) after applying one lever."""
    case = copy.deepcopy(case)
    now = clock_now
    promise = None

    if lever_key == "night":
        now = clock_now.replace(hour=3, minute=0)
    elif lever_key == "opted_out":
        case.customer.opted_out = True
        case.customer.opted_out_at = clock_now - timedelta(days=1)
    elif lever_key == "promised":
        promise = clock_now + timedelta(days=6)
    elif lever_key == "fresh_debit":
        case.detected_at = clock_now - timedelta(hours=1)
    elif lever_key == "high_value":
        case.amount_at_risk = 90_000.0
    return case, now, promise


def _trace(case, *, clock_now: datetime, promise: datetime | None, seed: int) -> dict:
    """Run one case through the real agent and return its ledger trace."""
    models = get_models()
    traits = generate_population([case], seed=seed)
    env = SimulationEnvironment(traits, seed=seed + 2)
    listener = EnvironmentListener(env)
    ledger = Ledger()

    agent = RecoveryAgent(
        detector=CaseDetector(),
        diagnoser=CaseDiagnoser(),
        policy=LookaheadEVDecisionPolicy(
            uplift_model=models.uplift, churn_model=models.churn
        ),
        kernel=build_kernel(),
        executor=SimulatedExecutor(),
        listener=listener,
        ledger=ledger,
        clock=lambda: clock_now,
    )
    if promise is not None:
        agent.promises[case.case_id] = promise

    outcome = agent.run_case(case)
    reason = outcome.stop_reason or outcome.pause_reason
    return {
        "status": outcome.status,
        "reason": reason.value if reason else None,
        "paid": case.case_id in listener.paid_cases,
        "entries": [
            {
                "seq": e.seq,
                "entry_type": e.entry_type,
                "payload": e.payload,
                "hash": e.hash,
            }
            for e in ledger._entries
        ],
        "denials": [
            {
                "rule": r["rule_name"],
                "detail": r.get("detail"),
                "citation": (c.to_dict() if (c := citation_for(r["rule_name"])) else None),
            }
            for e in ledger._entries
            if e.entry_type == "certificate" and e.payload.get("decision") == "DENY"
            for r in e.payload.get("rule_results", [])
            if not r.get("passed", True)
        ],
    }


# Actions that actually reach the customer. The kernel exempts RETRY and WAIT
# from the contact rules on purpose — a silent retry is not contact — so on a
# case the policy only ever retries, most levers correctly do nothing. That is
# the kernel working, but it makes for a confusing demo, so the case picker
# below finds cases where the agent does speak.
CONTACT_ACTIONS = {"ActionType.NUDGE", "ActionType.ESCALATE", "ActionType.NEGOTIATE",
                   "nudge", "escalate", "negotiate"}

# `generate_cases(n, seed)` is batch-size dependent: it draws its fields in one
# vectorised pass, so case 0 of a 1-case batch is NOT case 0 of a 40-case batch
# (same case_id, different amount). Indexing into differently sized batches
# would make the counterfactual silently compare two different cases and
# attribute the difference to the lever. Every function here indexes into a
# roster of exactly this size. Pinned by tests/test_live_range.py.
ROSTER_N = 40

_CONTACT_INDEX_CACHE: dict[tuple[int, int], list[int]] = {}


def _makes_contact(trace: dict) -> bool:
    for e in trace["entries"]:
        if e["entry_type"] == "action_result":
            if str(e["payload"].get("action_type")) in CONTACT_ACTIONS:
                return True
    return False


def roster(seed: int):
    """The one canonical case list for this seed. Always the same size, so an
    index means the same case everywhere."""
    return generate_cases(ROSTER_N, seed=seed, now=NOW)


def contact_case_indices(seed: int, scan: int = ROSTER_N) -> list[int]:
    """Indices of cases the agent actually contacts, rather than silently
    retrying. Cached because it costs one real run per case to find out."""
    key = (seed, ROSTER_N)
    if key in _CONTACT_INDEX_CACHE:
        return _CONTACT_INDEX_CACHE[key]
    cases = roster(seed)
    found = [
        i for i, case in enumerate(cases)
        if _makes_contact(_trace(copy.deepcopy(case), clock_now=NOW, promise=None, seed=seed))
    ]
    _CONTACT_INDEX_CACHE[key] = found
    return found


def counterfactual(seed: int, index: int | None, lever: str) -> dict:
    """The same case, run twice, with exactly one fact of the world changed.

    Both runs use the same agent, the same kernel, the same fitted models and
    the same simulator seed. Any difference in the two traces is attributable
    to the lever and nothing else — which is the whole point, and is the same
    discipline (common random numbers) the batch experiment uses to compare
    policies.
    """
    lever_def = next((l for l in LEVERS if l.key == lever), None)
    if lever_def is None:
        return {"error": f"no lever named {lever!r}"}

    auto_picked = False
    if index is None:
        cases_all = roster(seed)
        candidates = contact_case_indices(seed)
        if lever_def.requires_subscription:
            candidates = [
                i for i in range(len(cases_all))
                if type(cases_all[i]).__name__ == "FailedSubscriptionCase"
            ] or candidates
        if not candidates:
            return {"error": f"no case in the first {ROSTER_N} results in customer contact"}
        index = candidates[0]
        auto_picked = True

    cases = roster(seed)
    if not 0 <= index < len(cases):
        return {"error": f"case index {index} out of range 0..{len(cases) - 1}"}
    case = cases[index]

    baseline = _trace(copy.deepcopy(case), clock_now=NOW, promise=None, seed=seed)
    mutated_case, clock, promise = _apply_lever(case, lever, NOW)
    changed = _trace(mutated_case, clock_now=clock, promise=promise, seed=seed)

    contacts = _makes_contact(baseline)
    return {
        "case": {
            "index": index,
            "auto_picked": auto_picked,
            "case_id": case.case_id,
            "loss_type": type(case).__name__,
            "amount": float(case.amount_at_risk),
            "is_b2b": bool(case.customer.is_b2b),
            "language": case.customer.language_pref.value,
            "makes_contact": contacts,
        },
        "lever": {
            "key": lever_def.key,
            "label": lever_def.label,
            "description": lever_def.description,
            "expects": lever_def.expects,
        },
        "baseline": baseline,
        "changed": changed,
        "diverged": (
            baseline["reason"] != changed["reason"]
            or baseline["status"] != changed["status"]
            or len(baseline["entries"]) != len(changed["entries"])
        ),
        # Said plainly rather than left for the viewer to puzzle over: on a
        # case the agent never speaks on, the contact rules are exempt by
        # design and most levers will change nothing.
        "note": (
            None if contacts else
            "On this case the agent only ever retries silently. RETRY and WAIT "
            "are exempt from the contact rules — a background retry does not "
            "reach the customer — so the contact levers correctly change "
            "nothing here."
        ),
    }


def verify_entries(raw: list[dict]) -> dict:
    """Run possibly-tampered entries through the real chain verifier.

    Deliberately server-side and deliberately the production function: a
    tamper demo that re-implements hashing in the browser proves that the
    browser's copy works, which is not the claim being made.
    """
    try:
        return Ledger.from_entries(raw).verify_chain_detail()
    except (KeyError, TypeError, ValueError) as exc:
        return {
            "ok": False,
            "broken_at": None,
            "failure": "malformed",
            "detail": f"entries could not be read as a ledger: {exc}",
        }


def now_reference() -> str:
    return NOW.astimezone(timezone.utc).isoformat()
