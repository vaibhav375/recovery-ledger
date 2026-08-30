# Regret Ledger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Price every case the agent declined to contact — what refusing cost, what it saved, and which refusals were model errors.

**Architecture:** A pure attribution module under `src/recovery_ledger/policy/regret.py` (no simulator import, unit-testable in isolation), consumed by a new experiment `experiments/regret/run_regret.py` that deliberately re-evaluates `run_batch.py`'s population so the regret figure is quotable beside the ₹272,281 headline. `run_batch.py` is not modified. The seed test is refactored from a list into a declared registry so "deliberately shares a population" becomes checkable rather than expressed by omission.

**Tech Stack:** Python 3.12, numpy, pytest, existing `recovery_ledger` package. React/TypeScript + Vite for the dashboard task.

**Spec:** `docs/superpowers/specs/2026-08-30-regret-ledger-design.md`

## Global Constraints

- **Never fabricate a result.** Every number in a document must come from a committed artifact and be pinned by a test that fails when prose and artifact disagree.
- **A result is claimable only if it replicates.** Single-draw conclusions are claims about that draw.
- **A test that cannot fail is worse than no test.** Both "must-fail" tests in Task 1 are to be verified failing under mutation before the task is accepted.
- **Commits:** author `Vaibhav <handoovaibhav123@gmail.com>`, **no `Co-Authored-By` trailers, no third-party attribution.** Verify with `git log -1 --format='%(trailers:only)'` (must print nothing).
- **Do not modify** `experiments/tier2_simulation/run_batch.py` or `results.json`.
- Python: run everything with `PYTHONPATH=src .venv/bin/python3`.
- Contact actions are `ActionType.NUDGE` and `ActionType.NEGOTIATE` only. `RETRY` and `REROUTE` are payment-rail actions and are **not** customer contact (that distinction is novelty claim N6).

---

### Task 1: The regret attribution module

**Files:**
- Create: `src/recovery_ledger/policy/regret.py`
- Test: `tests/test_regret.py`

**Interfaces:**
- Consumes: `ActionType`, `StopReason` from `recovery_ledger.events.actions`; `LedgerEntry` shape (`.entry_type`, `.payload`) from `recovery_ledger.ledger.ledger`.
- Produces: `Bucket`, `DeclinedCase`, `RegretTotals`, `CONTACT_ACTIONS`, `was_contacted(entries)`, `classify(stop_reason, kernel_denied_contact)`, `regret_totals(declined)`, `totals_by_bucket(declined)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_regret.py`:

```python
"""Attribution and pricing of the cases the agent declined to contact.

Two of these tests exist to fail. A holdout-arm case entering the universe
would roughly double the reported regret, and a `negative_ev` refusal of a
customer with positive true uplift being filed as "saved" would turn a model
error into a success. Both are mutated in Task 1 Step 6 to prove they bite.
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=src .venv/bin/python3 -m pytest tests/test_regret.py -q`
Expected: collection error, `ModuleNotFoundError: No module named 'recovery_ledger.policy.regret'`

- [ ] **Step 3: Write the implementation**

Create `src/recovery_ledger/policy/regret.py`:

```python
"""What the agent's silences cost, and what they saved.

Every refusal to contact is a bet that contacting would not have paid. Some of
those bets are wrong. This module prices both sides of the account, because
reporting only the cost would be self-flagellation with the same dishonesty as
reporting only gross recovery, and reporting only the saving would be
marketing.

The module deliberately does not import the simulator. It attributes and prices
refusals given a true per-case uplift that someone else supplies, so it can be
tested against constructed cases where the answer is exact.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import Enum

from recovery_ledger.events.actions import ActionType, StopReason

# Actions that reach a customer. RETRY and REROUTE move money on the payment
# rails without messaging anyone, which is the entire content of claim N6.
CONTACT_ACTIONS = frozenset({ActionType.NUDGE.value, ActionType.NEGOTIATE.value})


class Bucket(str, Enum):
    """Why a case was never contacted."""

    MANDATORY = "mandatory"              # a rule forbade it
    MODEL_JUDGEMENT = "model_judgement"  # the agent chose
    ALLOCATION = "allocation"            # it ran out of attempts
    CASE_STATE = "case_state"            # it ended for unrelated reasons
    DEFERRED = "deferred"                # handed to a human; not a refusal


BUCKET_BY_STOP_REASON: dict[str, Bucket] = {
    StopReason.OPT_OUT.value: Bucket.MANDATORY,
    StopReason.PROMISE_TO_PAY_ACTIVE.value: Bucket.MANDATORY,
    StopReason.REGULATORY_CEILING.value: Bucket.MANDATORY,
    StopReason.GLOBAL_KILL_SWITCH.value: Bucket.MANDATORY,
    StopReason.NEGATIVE_EV.value: Bucket.MODEL_JUDGEMENT,
    StopReason.DO_NOT_DISTURB.value: Bucket.MODEL_JUDGEMENT,
    StopReason.BUDGET_EXHAUSTED.value: Bucket.ALLOCATION,
    StopReason.DISPUTE_RAISED.value: Bucket.CASE_STATE,
    StopReason.HARD_DECLINE.value: Bucket.CASE_STATE,
    StopReason.HUMAN_ESCALATION_THRESHOLD.value: Bucket.DEFERRED,
}


@dataclass(frozen=True)
class DeclinedCase:
    case_id: str
    amount_at_risk: float
    tau_true: float
    bucket: Bucket
    stop_reason: str

    @property
    def forgone(self) -> float:
        """Rupees refusing cost. Zero when contact would have done harm."""
        return self.amount_at_risk * self.tau_true if self.tau_true > 0 else 0.0

    @property
    def avoided(self) -> float:
        """Rupees refusing saved. Zero when contact would have helped."""
        return -self.amount_at_risk * self.tau_true if self.tau_true < 0 else 0.0

    @property
    def is_model_error(self) -> bool:
        """The agent judged this customer not worth contacting, and it was
        wrong. Only meaningful where the agent actually made the call."""
        return self.bucket is Bucket.MODEL_JUDGEMENT and self.tau_true > 0


@dataclass(frozen=True)
class RegretTotals:
    n: int
    cost: float
    saved: float
    net: float
    model_errors: int


def was_contacted(entries: Iterable) -> bool:
    """Did any customer-facing action actually execute for this case?

    Reads `action_result`, not `decision`: a nudge the policy proposed and the
    kernel denied falls back to WAIT and never reaches the customer, so
    counting decisions would record a contact that did not happen.
    """
    return any(
        e.entry_type == "action_result"
        and bool(e.payload.get("executed"))
        and e.payload.get("action_type") in CONTACT_ACTIONS
        for e in entries
    )


def classify(stop_reason: str | None, *, kernel_denied_contact: bool) -> Bucket:
    """Which bucket a refusal belongs to.

    A kernel denial outranks the stop reason. If the agent proposed contact and
    the compliance kernel refused it, the binding constraint was the rule, not
    the policy's judgement — whatever reason the case eventually terminated on.
    """
    if kernel_denied_contact:
        return Bucket.MANDATORY
    if stop_reason is None:
        return Bucket.CASE_STATE
    return BUCKET_BY_STOP_REASON.get(stop_reason, Bucket.CASE_STATE)


def _in_scope(declined: Iterable[DeclinedCase]) -> list[DeclinedCase]:
    return [d for d in declined if d.bucket is not Bucket.DEFERRED]


def regret_totals(declined: Sequence[DeclinedCase]) -> RegretTotals:
    rows = _in_scope(declined)
    cost = sum(d.forgone for d in rows)
    saved = sum(d.avoided for d in rows)
    return RegretTotals(
        n=len(rows), cost=cost, saved=saved, net=saved - cost,
        model_errors=sum(1 for d in rows if d.is_model_error),
    )


def totals_by_bucket(declined: Sequence[DeclinedCase]) -> dict[Bucket, RegretTotals]:
    grouped: dict[Bucket, list[DeclinedCase]] = {}
    for row in _in_scope(declined):
        grouped.setdefault(row.bucket, []).append(row)
    return {b: regret_totals(rows) for b, rows in grouped.items()}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=src .venv/bin/python3 -m pytest tests/test_regret.py -q`
Expected: PASS, 21 tests (the stop-reason mapping is parametrized over 10 reasons).

- [ ] **Step 5: Run the full suite for regressions**

Run: `PYTHONPATH=src .venv/bin/python3 -m pytest -q`
Expected: 433 passed (412 + 21).

- [ ] **Step 6: Mutate to prove the two must-fail tests bite**

Mutation A — make a model error read as a saving. In `is_model_error`, change `self.tau_true > 0` to `self.tau_true < 0`:

Run: `PYTHONPATH=src .venv/bin/python3 -m pytest tests/test_regret.py -q`
Expected: FAIL on `test_a_negative_ev_refusal_of_a_persuadable_customer_is_a_model_error`.
Then revert.

Mutation B — count a denied nudge as contact. In `was_contacted`, delete the `bool(e.payload.get("executed")) and` clause:

Run: `PYTHONPATH=src .venv/bin/python3 -m pytest tests/test_regret.py -q`
Expected: FAIL on `test_a_denied_nudge_is_not_contact`.
Then revert and re-run to confirm green.

- [ ] **Step 7: Commit**

```bash
git add src/recovery_ledger/policy/regret.py tests/test_regret.py
git commit -m "Price the refusals: attribution and two-sided regret totals

Every refusal to contact is a bet that contacting would not have paid, and
some of those bets are wrong. This prices both sides: cost where the true
uplift is positive, saved where it is negative.

A kernel denial outranks the stop reason. If the agent proposed contact and
the compliance kernel refused, the binding constraint was the rule and not the
policy's judgement, however the case later terminated.

Contact means NUDGE or NEGOTIATE. RETRY and REROUTE move money on the payment
rails without messaging anyone, which is the whole of N6, and counting them as
contact would erase that claim.

Two tests exist to fail and were mutated to prove it: a denied nudge counted as
contact, and a negative_ev refusal of a persuadable customer filed as saved
rather than as a model error."
```

---

### Task 2: Replace exemption-by-omission in the seed test

**Files:**
- Modify: `tests/test_experiment_seeds.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `SEED_REGISTRY: dict[str, tuple[str, str]]` where the value is `(kind, note)` and kind is one of `"distinct"`, `"shares"`, `"none"`. Task 3 adds `regret/run_regret.py` to it.

**Why:** `experiments/churn_lambda/run_lambda_sweep.py` deliberately shares the baselines population and is accommodated by not appearing in `EVAL_SEED_SOURCES` at all. The test cannot distinguish a deliberate sharer from a forgotten file. Same defect as the λ_churn interval check: a guard that cannot fail in the direction that matters.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_experiment_seeds.py`:

```python
# Every experiment entry point, and what it does about evaluation
# populations. Three declared kinds:
#   "distinct" — draws its own population; the offset must be unique
#   "shares"   — deliberately evaluates on another experiment's population
#   "none"     — evaluates on a real dataset, so there is no seed to collide
#
# Before this registry existed, a deliberate sharer was handled by being left
# out of the list, which is indistinguishable from having been forgotten.
SEED_REGISTRY: dict[str, tuple[str, str]] = {
    "tier2_simulation/run_batch.py": ("distinct", "the B1 headline population"),
    "tier2_simulation/run_baselines.py": ("distinct", ""),
    "sensitivity/run_sweep.py": ("distinct", ""),
    "fleet/run_fleet.py": ("distinct", ""),
    "ope_deployment/run_ope_deployment.py": ("distinct", ""),
    "fairness/run_fairness.py": ("distinct", ""),
    "pessimism/run_pessimism.py": ("distinct", ""),
    "dnd_signal/run_dnd_signal.py": ("distinct", ""),
    "horizon/run_horizon.py": ("distinct", ""),
    "uplift_ab/run_uplift_ab.py": ("distinct", ""),
    "uplift_calibration/run_calibration.py": ("distinct", ""),
    "churn_lambda/run_lambda_sweep.py": (
        "shares", "tier2_simulation/run_baselines.py — the curve is a "
                  "decomposition of the baselines table, so it must be "
                  "measured on the baselines cases"),
    "tier1_criteo/run_validation.py": ("none", "real RCT data (Criteo, Hillstrom)"),
    "tier1_criteo/run_dr_diagnosis.py": ("none", "real RCT data"),
    "listener_eval/run_eval.py": ("none", "a hand-authored gold set"),
    "negotiation/run_negotiation.py": ("none", "a scripted showpiece, no eval batch"),
}


def test_every_experiment_declares_what_population_it_evaluates_on():
    """The check that closes exemption-by-omission. A new experiment that
    does not declare its seed intent fails here, instead of silently being
    exempt from the collision test by not being listed."""
    found = {
        f"{path.parent.name}/{path.name}"
        for path in (ROOT / "experiments").glob("*/run_*.py")
    }
    undeclared = sorted(found - set(SEED_REGISTRY))
    stale = sorted(set(SEED_REGISTRY) - found)
    assert not undeclared, (
        "these experiments do not say whether they draw their own evaluation "
        "population, share another's, or use a real dataset:\n  "
        + "\n  ".join(undeclared)
    )
    assert not stale, "registry names files that no longer exist:\n  " + "\n  ".join(stale)


def test_declared_sharers_name_an_experiment_that_exists():
    for rel, (kind, note) in SEED_REGISTRY.items():
        if kind != "shares":
            continue
        target = note.split(" ")[0]
        assert (ROOT / "experiments" / target).exists(), (
            f"{rel} says it shares with {target!r}, which does not exist"
        )
```

- [ ] **Step 2: Prove the new guard bites**

The registry is written to match the tree, so these tests pass on arrival —
which proves nothing. Make them fail on purpose first.

Delete the `"fleet/run_fleet.py"` entry from `SEED_REGISTRY`, then run:
`PYTHONPATH=src .venv/bin/python3 -m pytest tests/test_experiment_seeds.py -q`
Expected: FAIL on `test_every_experiment_declares_what_population_it_evaluates_on`,
naming `fleet/run_fleet.py` as undeclared — which is precisely the state
`churn_lambda` was in before this task.

Restore the entry, then change `churn_lambda`'s note to name a directory that
does not exist and re-run.
Expected: FAIL on `test_declared_sharers_name_an_experiment_that_exists`.
Restore, re-run, confirm green.

- [ ] **Step 3: Point the existing collision test at the registry**

Replace `EVAL_SEED_SOURCES` and `_offsets()` so the collision check reads only the `"distinct"` entries. `EVAL_SEED_PATTERN` is unchanged.

```python
def _offsets() -> dict[str, int]:
    found: dict[str, int] = {}
    for rel, (kind, _note) in SEED_REGISTRY.items():
        if kind != "distinct":
            continue
        path = ROOT / "experiments" / rel
        assert path.exists(), f"{rel} moved; update SEED_REGISTRY"
        pattern = (
            r"seed=SEED \+ (\d+)"
            if rel == "tier2_simulation/run_batch.py"
            else EVAL_SEED_PATTERN
        )
        m = re.search(pattern, path.read_text())
        assert m, f"could not find the eval-seed offset in {rel}"
        found[rel] = int(m.group(1))
    return found
```

Delete the now-unused `EVAL_SEED_SOURCES` dict.

- [ ] **Step 4: Run the file's tests**

Run: `PYTHONPATH=src .venv/bin/python3 -m pytest tests/test_experiment_seeds.py -q`
Expected: PASS, 8 tests (6 existing + 2 new).

- [ ] **Step 5: Run the full suite**

Run: `PYTHONPATH=src .venv/bin/python3 -m pytest -q`
Expected: 435 passed.

- [ ] **Step 6: Commit**

```bash
git add tests/test_experiment_seeds.py
git commit -m "A seed test that can tell a deliberate sharer from a forgotten one

The collision check enforced distinct evaluation populations by listing files.
churn_lambda deliberately evaluates on the baselines population, and it was
accommodated by not being in the list — which is exactly what a forgotten
experiment looks like. The test could not tell the two apart, so its silence
meant nothing.

The list becomes a registry where every entry point declares one of three
kinds: distinct, shares-with, or no-eval-population. A new test walks
experiments/ and fails on any run_*.py that declares nothing, so adding an
experiment without saying what it evaluates on now breaks the build.

churn_lambda is registered as sharing the baselines population, with the
reason, for the first time."
```

---

### Task 3: The regret experiment

**Files:**
- Create: `experiments/regret/run_regret.py`
- Create: `experiments/regret/REPORT.md`
- Modify: `Makefile` (add a `regret` target next to `calibration`)
- Modify: `tests/test_experiment_seeds.py` (register the new experiment)

**Interfaces:**
- Consumes: `Bucket`, `DeclinedCase`, `classify`, `was_contacted`, `regret_totals`, `totals_by_bucket` from Task 1; `SEED_REGISTRY` from Task 2.
- Produces: `experiments/regret/results_regret.json` with the key set given below; Task 4 pins figures from it and Task 5 renders it.

- [ ] **Step 1: Register the experiment's population intent**

In `tests/test_experiment_seeds.py`, add to `SEED_REGISTRY`:

```python
    "regret/run_regret.py": (
        "shares", "tier2_simulation/run_batch.py — a regret figure is only "
                  "quotable beside the headline if it is measured on the same "
                  "customers"),
```

- [ ] **Step 2: Write the experiment**

Create `experiments/regret/run_regret.py`:

```python
"""What the agent's silences cost, and what they saved.

This system's pitch is that its value is in NOT contacting people: 80% fewer
messages than mass-contact, a whole dashboard section about the three
mechanisms that produce silence. Nothing reported what that silence cost.

Every refusal is a bet that contacting would not have paid, and the simulator
knows which bets were wrong — `persuadability(traits)` is the true per-case
effect, already used for the do-not-disturb diagnostics. The information to
price the agent's own false negatives has been in the repo, unqueried.

POPULATION. This deliberately evaluates on run_batch.py's cases (SEED + 1000).
A regret figure is only quotable beside the B1 headline if it is measured on
the same customers. run_batch.py itself is untouched: submission week is the
wrong time to edit the script the headline rests on, and its results.json is
referenced by eight doc-test assertions.

THE PRE-REGISTERED PREDICTION, fixed before the run. `make calibration` showed
tau_hat's bottom bin is 43.8% true do-not-disturbs against 17.3% of the
population — so it is also 56% customers with positive true uplift, priced as
if they were not. If that result is true, the model-judgement bucket MUST
contain a non-trivial count of cases with tau_true > 0. If that cell comes back
at or near zero, the two experiments contradict each other and one of them is
wrong. That gets published as a contradiction, not reconciled.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "tier2_simulation"))

from run_batch import NOW, SEED, run_eval, train_models  # noqa: E402

from recovery_ledger.events.actions import ActionType  # noqa: E402
from recovery_ledger.policy.regret import (  # noqa: E402
    Bucket,
    DeclinedCase,
    classify,
    regret_totals,
    totals_by_bucket,
    was_contacted,
)
from recovery_ledger.sim.environment import (  # noqa: E402
    SimulationEnvironment,
    generate_population,
    persuadability,
)
from recovery_ledger.sim.generator import generate_cases  # noqa: E402

# Deliberately run_batch.py's evaluation population; see the module docstring
# and tests/test_experiment_seeds.py.
EVAL_SEED = SEED + 1000

MODEL_ERROR_PREDICTION = (
    "make calibration reports the bottom tau_hat bin as 43.8% true "
    "do-not-disturbs, so it is also ~56% customers with positive true uplift. "
    "The model-judgement bucket must therefore contain a non-trivial count of "
    "tau_true > 0 refusals. Near zero refutes one of the two experiments."
)
MODEL_ERRORS_EXPECTED_ABOVE = 0


def treatment_arm(cases, *, seed: int):
    """The cases run_eval assigned to the treatment arm.

    run_eval writes BOTH arms into the same Ledger, so the ledger alone cannot
    say which cases the policy was ever allowed to work. It splits with
    `np.random.default_rng(seed + 1).integers(0, 2, size=n)`, so the identical
    call reproduces the assignment exactly. If run_eval's split ever changes,
    this must change with it — the assertion in main() is what catches that.
    """
    rng = np.random.default_rng(seed + 1)
    is_treatment = rng.integers(0, 2, size=len(cases)).astype(bool)
    return [c for c, t in zip(cases, is_treatment) if t]


def declined_cases(ledger, treatment, traits) -> tuple[list[DeclinedCase], int]:
    """Every treatment-arm case that never received a message.

    The holdout arm is deliberately absent: it was left alone by design, as the
    experimental control, not by a refusal. Including it would roughly double
    the reported regret, which is why `treatment` is passed in rather than the
    full batch and why the caller asserts the arm size.
    """
    declined: list[DeclinedCase] = []
    worked = 0
    for case in treatment:
        case_id = case.case_id
        entries = ledger.entries_for_case(case_id)
        if was_contacted(entries):
            worked += 1
            continue
        stops = [e for e in entries if e.entry_type == "stop"]
        reason = stops[-1].payload.get("reason") if stops else None
        if reason == "resolved":
            continue  # they paid; nothing was forgone
        kernel_denied = any(
            e.entry_type == "certificate"
            and e.payload.get("decision") == "deny"
            and e.payload.get("action_type") in {ActionType.NUDGE.value, ActionType.NEGOTIATE.value}
            for e in entries
        )
        declined.append(DeclinedCase(
            case_id=case_id,
            amount_at_risk=float(case.amount_at_risk),
            tau_true=float(persuadability(traits[case_id])),
            bucket=classify(reason, kernel_denied_contact=kernel_denied),
            stop_reason=reason or "unknown",
        ))
    return declined, worked


def realised_incremental(case, traits, *, seed: int) -> float:
    """The paired counterfactual for one declined case.

    SimulationEnvironment gives each case its own RNG stream seeded from
    (seed, case_id), independent of call order, so it is already a common
    random numbers design. Two instances at the same seed rather than two calls
    on one: a second call would advance that case's stream, and the point is
    that both arms see the identical sequence.
    """
    env_wait = SimulationEnvironment(traits, seed=seed)
    env_nudge = SimulationEnvironment(traits, seed=seed)
    paid_0 = float(env_wait.step(case, ActionType.WAIT, 0).paid)
    paid_1 = float(env_nudge.step(case, ActionType.NUDGE, 0).paid)
    return float(case.amount_at_risk) * (paid_1 - paid_0)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n-train", type=int, default=5000)
    ap.add_argument("--n-eval", type=int, default=2000)
    ap.add_argument("--counterfactual", action="store_true", default=True)
    ap.add_argument("--no-counterfactual", dest="counterfactual", action="store_false")
    args = ap.parse_args()

    print(f"Training on {args.n_train} randomised-contact cases...")
    uplift, churn = train_models(args.n_train, seed=SEED, ensemble=False)

    print(f"Re-running run_batch's evaluation population (seed {EVAL_SEED})...")
    _results, ledger = run_eval(args.n_eval, uplift, seed=EVAL_SEED, churn_model=churn)

    cases = generate_cases(args.n_eval, seed=EVAL_SEED, now=NOW)
    traits = generate_population(cases, seed=EVAL_SEED)
    treatment = treatment_arm(cases, seed=EVAL_SEED)

    # The holdout arm must never enter the universe. If run_eval's assignment
    # drifts away from the reconstruction above, this is where it surfaces.
    assert 0.4 < len(treatment) / len(cases) < 0.6, (
        f"treatment arm is {len(treatment)}/{len(cases)}; run_eval's 50/50 "
        f"assignment no longer matches treatment_arm()"
    )
    declined, worked = declined_cases(ledger, treatment, traits)

    totals = regret_totals(declined)
    by_bucket = totals_by_bucket(declined)
    n_deferred = sum(1 for d in declined if d.bucket is Bucket.DEFERRED)

    print(f"\n{'bucket':<18}{'n':>6}{'cost':>14}{'saved':>14}{'net':>14}{'errors':>8}")
    for bucket, t in sorted(by_bucket.items(), key=lambda kv: -kv[1].cost):
        print(f"{bucket.value:<18}{t.n:>6}{t.cost:>14,.0f}{t.saved:>14,.0f}"
              f"{t.net:>14,.0f}{t.model_errors:>8}")
    print(f"{'TOTAL':<18}{totals.n:>6}{totals.cost:>14,.0f}{totals.saved:>14,.0f}"
          f"{totals.net:>14,.0f}{totals.model_errors:>8}")

    holds = totals.model_errors > MODEL_ERRORS_EXPECTED_ABOVE
    print(f"\nPre-registered prediction: model errors > {MODEL_ERRORS_EXPECTED_ABOVE}")
    print(f"  observed {totals.model_errors} -> {'HOLDS' if holds else 'REFUTED'}")
    if not holds:
        print("  REFUTED. This contradicts make calibration. Publish the "
              "contradiction; do not reconcile it.")

    check = None
    if args.counterfactual:
        print(f"\nPaired counterfactual over {len(declined)} declined cases...")
        by_id = {c.case_id: c for c in treatment}
        realised = np.array([
            realised_incremental(by_id[d.case_id], traits, seed=EVAL_SEED + 2)
            for d in declined if d.bucket is not Bucket.DEFERRED
        ])
        check = {
            "n": int(realised.size),
            "realised_cost": float(realised[realised > 0].sum()),
            "realised_saved": float(-realised[realised < 0].sum()),
            "realised_net": float(-realised.sum()),
            "expected_net": totals.net,
        }
        print(f"  realised net {check['realised_net']:,.0f} vs "
              f"expected net {totals.net:,.0f}")

    out = {
        "n_eval": args.n_eval,
        "eval_seed": EVAL_SEED,
        "shares_population_with": "tier2_simulation/run_batch.py",
        "n_declined": totals.n,
        "n_worked": worked,
        "n_deferred": n_deferred,
        # Written above the results so it cannot be read as post-hoc.
        "prediction": {
            "rule": MODEL_ERROR_PREDICTION,
            "model_errors_expected_above": MODEL_ERRORS_EXPECTED_ABOVE,
            "model_errors_observed": totals.model_errors,
            "holds": bool(holds),
        },
        "totals": {
            "cost": round(totals.cost, 2),
            "saved": round(totals.saved, 2),
            "net": round(totals.net, 2),
            "model_errors": totals.model_errors,
        },
        "buckets": [
            {
                "bucket": b.value, "n": t.n,
                "cost": round(t.cost, 2), "saved": round(t.saved, 2),
                "net": round(t.net, 2), "model_errors": t.model_errors,
            }
            for b, t in sorted(by_bucket.items(), key=lambda kv: -kv[1].cost)
        ],
        "counterfactual_check": check,
    }
    (HERE / "results_regret.json").write_text(json.dumps(out, indent=2))
    print(f"\nWrote {HERE / 'results_regret.json'}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Add the make target**

In `Makefile`, immediately after the `calibration` target:

```makefile
regret:
	PYTHONPATH=src .venv/bin/python3 experiments/regret/run_regret.py \
		--n-train 5000 --n-eval 2000
```

- [ ] **Step 4: Run it**

Run: `make regret`
Expected: a bucket table, the pre-registered verdict, the counterfactual line, and `results_regret.json` written.

**If the prediction is REFUTED, stop and report it. Do not adjust either experiment to agree.** That outcome is a finding and needs a human decision about how to publish it.

- [ ] **Step 5: Confirm determinism**

Run:
```bash
cp experiments/regret/results_regret.json /tmp/regret1.json
make regret >/dev/null
diff /tmp/regret1.json experiments/regret/results_regret.json && echo "byte-identical"
```
Expected: `byte-identical`. `RESULTS.md` claims every experiment is deterministic; this must hold.

- [ ] **Step 6: Run the full suite**

Run: `PYTHONPATH=src .venv/bin/python3 -m pytest -q`
Expected: 435 passed.

- [ ] **Step 7: Write the report**

Create `experiments/regret/REPORT.md` covering, in this order: why it was run; the design (population sharing and why `run_batch.py` was not modified); the pre-registered prediction stated before the result; the bucket table with the real numbers from Step 4; the counterfactual check; and what the finding does and does not license. If the prediction was refuted, say so in the first paragraph.

- [ ] **Step 8: Commit**

```bash
git add experiments/regret/ Makefile tests/test_experiment_seeds.py
git commit -m "make regret: price the silences on the headline's own cases"
```

---

### Task 4: Publish the figures and pin them

**Files:**
- Modify: `RESULTS.md` (new section directly after the B1 section)
- Modify: `tests/test_results_doc_matches_artifacts.py`
- Modify: `PROJECT_STATE.md`

**Interfaces:**
- Consumes: `experiments/regret/results_regret.json` from Task 3.
- Produces: nothing later tasks depend on.

- [ ] **Step 1: Write the RESULTS.md section**

Insert immediately after the B1 section so the pairing reads: recovered ₹272,281 per 1,000, and on the same cases the silences cost X, saved Y, net Z. Render every figure exactly as the doc test below will assert it. State the pre-registered prediction and its verdict. Include the caveat verbatim: the headline estimator is an expectation under simulator truth, not a realised measurement.

- [ ] **Step 2: Write the doc test**

Append to `tests/test_results_doc_matches_artifacts.py`:

```python
REGRET = ROOT / "experiments" / "regret" / "results_regret.json"


def test_regret_totals_match_the_artifact(results_md):
    t = _load(REGRET)["totals"]
    for key in ("cost", "saved", "net"):
        assert f"₹{t[key]:,.0f}" in results_md, (
            f"RESULTS.md does not state the regret {key} of ₹{t[key]:,.0f}"
        )


def test_regret_bucket_rows_match_the_artifact(results_md):
    for row in _load(REGRET)["buckets"]:
        rendered = f"| {row['bucket']} | {row['n']} | ₹{row['cost']:,.0f} | ₹{row['saved']:,.0f} |"
        assert rendered in results_md, f"bucket row missing or stale: {rendered!r}"


def test_the_regret_prediction_verdict_is_reported_as_it_came_out(results_md):
    """The prediction can refute make calibration. If it does, RESULTS.md has
    to say so — this test fails when the document claims the friendlier
    outcome."""
    p = _load(REGRET)["prediction"]
    assert f"{p['model_errors_observed']} model errors" in results_md
    verdict = "holds" if p["holds"] else "refuted"
    assert verdict in results_md.lower()


def test_regret_was_measured_on_the_headline_population():
    assert _load(REGRET)["shares_population_with"] == "tier2_simulation/run_batch.py"
```

- [ ] **Step 3: Run the doc tests**

Run: `PYTHONPATH=src .venv/bin/python3 -m pytest tests/test_results_doc_matches_artifacts.py -q`
Expected: PASS.

- [ ] **Step 4: Prove the doc tests can fail**

Change one digit of the net figure in `RESULTS.md`, re-run Step 3, expect FAIL on `test_regret_totals_match_the_artifact`, then revert and re-run to green.

- [ ] **Step 5: Update PROJECT_STATE.md**

Experiment count 14 → 15 and add `regret` to the list; add the headline regret figures to the §2 table with `make regret` as the source; add `make regret` to the §8 validation order; note the seed-registry change against the §8 invariant list; update the test count to the number Step 6 reports.

- [ ] **Step 6: Run the full suite**

Run: `PYTHONPATH=src .venv/bin/python3 -m pytest -q`
Expected: 439 passed.

- [ ] **Step 7: Commit**

```bash
git add RESULTS.md PROJECT_STATE.md tests/test_results_doc_matches_artifacts.py
git commit -m "Publish what refusing cost, beside what contacting recovered"
```

---

### Task 5: Surface it in the dashboard

**Files:**
- Modify: `dashboard/build_dashboard.py` (in `build_data()` only — the `build()` fallback dict does not get it)
- Modify: `frontend/src/types.ts`
- Create: `frontend/src/components/RegretLedger.tsx`
- Modify: `frontend/src/sections/Silence.tsx`
- Modify: `frontend/src/app.css`
- Modify: `dashboard/verify_page.py`

**Interfaces:**
- Consumes: `data.regret` — the Task 3 artifact, served through `data.json`.
- Produces: a `.rl-regret` element that `verify_page.py` requires.

- [ ] **Step 1: Serve the artifact**

In `dashboard/build_dashboard.py`, inside `build_data()` only, after the `calibration` entry:

```python
        # What the silences cost. Served from the artifact rather than
        # retyped, like every other figure on the page.
        "regret": load_optional(ROOT / "experiments" / "regret" / "results_regret.json"),
```

In `frontend/src/types.ts`, add `regret: any | null;` to the `Dashboard` type.

- [ ] **Step 2: Build the component**

Create `frontend/src/components/RegretLedger.tsx`. One row per bucket, cost
extending left of a centre line and saved extending right, so the sign of each
bucket is a direction rather than a number to parse. `var(--accent)` for saved,
`var(--fg-dim)` for cost, and `var(--rl-deny)` reserved for the model-error
count — the one cell that indicts the model.

```tsx
/** What the agent's silences cost, and what they saved.
 *
 * Two-sided per bucket because the sign is the content: a refusal of a
 * persuadable customer and a refusal of a do-not-disturb are opposite events,
 * and a single-signed bar chart would add them together.
 */
export default function RegretLedger({ regret }: { regret: any }) {
  if (!regret?.buckets?.length) return null;
  const t = regret.totals;
  const widest = Math.max(...regret.buckets.flatMap((b: any) => [b.cost, b.saved]), 1);
  const pct = (v: number) => `${(v / widest) * 50}%`;
  const inr = (v: number) => `₹${Math.round(v).toLocaleString("en-IN")}`;

  return (
    <div className="rl-regret">
      <h3>What the silences cost.</h3>
      <p>
        Every refusal is a bet that contacting would not have paid. On the same
        cases the headline was measured on, those bets cost <b>{inr(t.cost)}</b>,
        saved <b>{inr(t.saved)}</b>, and netted <b>{inr(t.net)}</b>.{" "}
        <span className="rl-regret-err">{t.model_errors} model errors</span> —
        refusals of customers who would have paid.
      </p>
      <ul className="rl-regret-rows">
        {regret.buckets.map((b: any) => (
          <li key={b.bucket}>
            <span className="rl-regret-name">{b.bucket.replace(/_/g, " ")}</span>
            <span className="rl-regret-bar">
              <span className="rl-regret-cost" style={{ width: pct(b.cost) }} />
              <span className="rl-regret-saved" style={{ width: pct(b.saved) }} />
            </span>
            <span className="rl-regret-net">{inr(b.net)}</span>
          </li>
        ))}
      </ul>
      <p className="rl-regret-foot">
        An expectation under simulator truth, not a realised measurement. Cost
        left of centre, saved right of it.
      </p>
    </div>
  );
}
```

The bar element is a flex row with `justify-content: center` and the cost span
in `flex-direction: row-reverse` order, so both halves grow outward from the
middle. Add to `frontend/src/app.css`:

```css
/* ── regret: two-sided, because the sign is the content ─────────────── */
.rl-regret { margin: clamp(36px, 5vw, 60px) 0 0; }
.rl-regret h3 { margin: 0 0 10px; font-size: 15px; font-weight: 600; }
.rl-regret > p { margin: 0 0 22px; font-size: 13.5px; font-weight: 300;
  line-height: 1.65; color: var(--fg-dim); max-width: 62ch; }
.rl-regret b { color: var(--foreground); font-weight: 600; }
.rl-regret-err { color: var(--rl-deny); }
.rl-regret-rows { list-style: none; margin: 0; padding: 0; }
.rl-regret-rows li {
  display: grid; grid-template-columns: 150px 1fr 110px;
  gap: 16px; align-items: center; padding: 9px 0;
  border-top: 1px solid var(--line-soft);
}
.rl-regret-name { font-size: 12.5px; color: var(--fg-dim); text-transform: capitalize; }
.rl-regret-bar { display: flex; justify-content: center; height: 10px; }
.rl-regret-cost { background: var(--fg-dim); height: 100%; }
.rl-regret-saved { background: var(--accent); height: 100%; }
.rl-regret-net {
  font-family: var(--mono); font-size: 12px; text-align: right;
  font-variant-numeric: tabular-nums; color: var(--fg-dim);
}
@media (max-width: 720px) {
  .rl-regret-rows li { grid-template-columns: 1fr 90px; }
  .rl-regret-bar { grid-column: 1 / -1; }
}
```

- [ ] **Step 3: Place it in Silence**

In `frontend/src/sections/Silence.tsx`, render `<RegretLedger regret={regret} />` after the existing three-item grid and before the quadrant, guarded by `regret &&`. Pass `regret` down from `App.tsx` as `data.regret`. Silence already argues that the agent's value is in not sending the message; this is the price tag on that argument and belongs under it rather than in a new section.

- [ ] **Step 4: Require it on the page**

In `dashboard/verify_page.py`, add to `required_sections`:

```python
    ".rl-regret": "regret ledger",
```

and to `expected`:

```python
    f"₹{inr(d['regret']['totals']['net'])}": "regret: net",
```

- [ ] **Step 5: Build and verify**

Run:
```bash
make dashboard
.venv/bin/python3 dashboard/serve.py &
make verify-page
```
Expected: `OK — 11 sections and 7 artifact-backed claims render on both paths`

- [ ] **Step 6: Check mobile and reduced motion**

Screenshot `.rl-regret` at 390px wide and confirm no label renders below ~9px and nothing clips at the left edge. Load with `reduced_motion="reduce"` and confirm every mark paints at full opacity.

- [ ] **Step 7: Run the full suite**

Run: `PYTHONPATH=src .venv/bin/python3 -m pytest -q`
Expected: 439 passed.

- [ ] **Step 8: Commit**

```bash
git add dashboard/ frontend/
git commit -m "Put the price of the silences under the section that argues for them"
```

---

## Verification when the plan is complete

```bash
PYTHONPATH=src .venv/bin/python3 -m pytest -q   # all green
make regret && make eval && make calibration    # artifacts regenerate
make dashboard && make verify-page              # 11 sections, 7 claims
git log --format='%an <%ae>' | sort -u          # exactly one identity
git log origin/main..HEAD --format='%(trailers:only)'   # prints nothing
```
