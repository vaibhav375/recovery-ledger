"""Coverage for `experiments/regret/run_regret.py`'s own functions —
`treatment_arm()` and `declined_cases()` — which had no end-to-end test at
all before this file (see review findings 3 and 6).

`tests/test_regret.py` exercises the pure classification/pricing functions in
`src/recovery_ledger/policy/regret.py` against constructed `DeclinedCase`
objects. Nothing exercised the layer above it: reconstructing the treatment
arm from a ledger and traits, and turning ledger entries into `DeclinedCase`
rows in the first place. That gap mattered twice:

1. The holdout-arm guard used to be a single assert in `main()` on
   `len(treatment) / len(cases)`, computed independently of whatever
   collection was actually passed to `declined_cases()`. Swapping that
   argument for `cases` (both arms) left the ratio assert untouched and
   still green while silently doubling the priced universe.
   `test_declined_cases_rejects_cases_outside_the_treatment_arm` proves the
   guard now lives where the pricing actually happens.

2. `declined_cases()`'s kernel-denial path reads
   `e.payload.get("decision") == Decision.DENY.value` off a hand-shaped
   ledger entry. A renamed payload key here would silently stop matching,
   reclassify every compliance-blocked refusal as `model_judgement`, and
   inflate the model-error count the pre-registered prediction turns on —
   with no test anywhere positioned to notice.
   `test_declined_cases_end_to_end_against_a_small_constructed_ledger`
   builds a ledger by hand and checks every bucket path, including that one.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "experiments" / "regret"))
sys.path.insert(0, str(Path(__file__).parent.parent / "experiments" / "tier2_simulation"))

from run_batch import NOW  # noqa: E402
from run_regret import declined_cases, treatment_arm  # noqa: E402

from recovery_ledger.events.actions import ActionType, StopReason  # noqa: E402
from recovery_ledger.kernel.certificate import Decision  # noqa: E402
from recovery_ledger.ledger.ledger import Ledger  # noqa: E402
from recovery_ledger.policy.regret import Bucket  # noqa: E402
from recovery_ledger.sim.environment import generate_population  # noqa: E402
from recovery_ledger.sim.generator import generate_cases  # noqa: E402


def _population(n: int, seed: int):
    cases = generate_cases(n, seed=seed, now=NOW)
    traits = generate_population(cases, seed=seed)
    return cases, traits


def test_treatment_arm_is_a_proper_subset_of_the_population():
    cases, _ = _population(200, seed=555)
    treatment = treatment_arm(cases, seed=555)
    all_ids = {c.case_id for c in cases}
    treatment_ids = {c.case_id for c in treatment}
    assert treatment_ids < all_ids  # strict subset: a holdout arm exists
    assert 0.4 < len(treatment_ids) / len(all_ids) < 0.6


def test_declined_cases_rejects_cases_outside_the_treatment_arm():
    """Finding 3, mutation-proofed: pass the full population (as a stray
    edit of `declined_cases(ledger, treatment, traits, ...)` to
    `declined_cases(ledger, cases, traits, ...)` in `main()` would) instead
    of just the reconstructed treatment arm, and the function must refuse —
    not silently price the holdout arm too."""
    cases, traits = _population(200, seed=777)
    ledger = Ledger()
    with pytest.raises(AssertionError, match="reconstructed treatment arm"):
        declined_cases(ledger, cases, traits, cases=cases, seed=777)


def test_declined_cases_accepts_the_real_treatment_arm():
    cases, traits = _population(200, seed=778)
    treatment = treatment_arm(cases, seed=778)
    ledger = Ledger()  # no entries anywhere -> every case falls through to CASE_STATE
    declined, worked, resolved_excluded = declined_cases(
        ledger, treatment, traits, cases=cases, seed=778
    )
    assert worked == 0
    assert resolved_excluded == 0
    assert len(declined) == len(treatment)
    assert all(d.bucket is Bucket.CASE_STATE for d in declined)


def test_declined_cases_end_to_end_against_a_small_constructed_ledger():
    """Six treatment-arm cases, one ledger entry sequence each, covering
    every path `declined_cases()` can take: contacted, resolved, a kernel
    DENY overriding a later stop reason, a plain model-judgement refusal, an
    allocation refusal, and a human handoff."""
    cases, traits = _population(20, seed=999)
    treatment = treatment_arm(cases, seed=999)
    assert len(treatment) >= 6, "need at least 6 treatment-arm cases for this fixture"
    c0, c1, c2, c3, c4, c5 = (c.case_id for c in treatment[:6])

    ledger = Ledger()
    # c0: an executed nudge reached the customer -> "worked", never priced.
    ledger.append(c0, "action_result", {
        "executed": True, "action_type": ActionType.NUDGE.value,
    })
    # c1: the case resolved (they paid) -> excluded, nothing was forgone.
    ledger.append(c1, "stop", {"reason": StopReason.RESOLVED.value})
    # c2: the agent proposed a nudge, the kernel DENY'd it, and the case
    # later separately stopped on budget_exhausted. The kernel denial must
    # outrank that later stop reason: MANDATORY, not ALLOCATION. This is the
    # exact path a renamed "decision" payload key would silently break.
    ledger.append(c2, "certificate", {
        "decision": Decision.DENY.value, "action_type": ActionType.NUDGE.value,
    })
    ledger.append(c2, "stop", {"reason": StopReason.BUDGET_EXHAUSTED.value})
    # c3: the model itself refused on negative_ev, no kernel involvement.
    ledger.append(c3, "stop", {"reason": StopReason.NEGATIVE_EV.value})
    # c4: ran out of allocated attempts, no kernel denial anywhere.
    ledger.append(c4, "stop", {"reason": StopReason.BUDGET_EXHAUSTED.value})
    # c5: escalated to a human -> deferred, excluded from cost/saved.
    ledger.append(c5, "stop", {"reason": StopReason.HUMAN_ESCALATION_THRESHOLD.value})
    # every other treatment-arm case is left with no entries at all -> CASE_STATE.

    declined, worked, resolved_excluded = declined_cases(
        ledger, treatment, traits, cases=cases, seed=999
    )

    assert worked == 1
    assert resolved_excluded == 1
    by_id = {d.case_id: d for d in declined}
    assert by_id[c2].bucket is Bucket.MANDATORY, (
        "a kernel DENY certificate must outrank the later stop reason — if "
        "this is MODEL_JUDGEMENT or ALLOCATION instead, the payload key the "
        "kernel-denial check reads has silently stopped matching"
    )
    assert by_id[c3].bucket is Bucket.MODEL_JUDGEMENT
    assert by_id[c4].bucket is Bucket.ALLOCATION
    assert by_id[c5].bucket is Bucket.DEFERRED
    assert c0 not in by_id and c1 not in by_id
