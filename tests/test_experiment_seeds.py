"""Every experiment must evaluate on its own population.

Seeds are the only thing separating one experiment's evaluation set from
another's, and a collision does not fail — it produces two experiments quietly
measured on the same customers, which are then presented as independent
corroboration of each other.

That was live in this repo: `experiments/sensitivity/run_sweep.py` and
`experiments/tier2_simulation/run_baselines.py` both used `SEED + 2000`. They
avoided sharing a population only because they happen to be invoked with
different `--n-eval`, and `generate_cases` is batch-size dependent. Run the
sweep at `--n-eval 2000` and the sensitivity result would have been measured
on the baselines table's exact cases.

Correctness resting on an incidental argument value is not correctness.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Every experiment that draws its own evaluation population, and the source
# line that sets its offset from the shared SEED.
# One pattern for every file, matching any name that means "the seed this
# experiment evaluates on". Naming the exact variable per file made the test
# brittle to a refactor rather than to a collision: moving `eval_seed` in
# run_sweep.py to a module-level `BASE_EVAL_SEED` broke it, which is a false
# alarm about the thing it is supposed to guard.
EVAL_SEED_PATTERN = r"(?:BASE_EVAL_SEED|EVAL_SEED|eval_seed)\s*=\s*SEED \+ (\d+)"

EVAL_SEED_SOURCES = {
    # run_batch passes its eval seed inline rather than naming it.
    "tier2_simulation/run_batch.py": r"seed=SEED \+ (\d+)",
    "tier2_simulation/run_baselines.py": EVAL_SEED_PATTERN,
    "sensitivity/run_sweep.py": EVAL_SEED_PATTERN,
    "fleet/run_fleet.py": EVAL_SEED_PATTERN,
    "ope_deployment/run_ope_deployment.py": EVAL_SEED_PATTERN,
    "fairness/run_fairness.py": EVAL_SEED_PATTERN,
}


def _offsets() -> dict[str, int]:
    found: dict[str, int] = {}
    for rel, pattern in EVAL_SEED_SOURCES.items():
        path = ROOT / "experiments" / rel
        assert path.exists(), f"{rel} moved; update this test"
        m = re.search(pattern, path.read_text())
        assert m, f"could not find the eval-seed offset in {rel}"
        found[rel] = int(m.group(1))
    return found


def test_every_experiment_uses_a_distinct_evaluation_seed():
    offsets = _offsets()
    seen: dict[int, str] = {}
    collisions = []
    for rel, off in sorted(offsets.items()):
        if off in seen:
            collisions.append(f"{rel} and {seen[off]} both use SEED + {off}")
        seen[off] = rel
    assert not collisions, (
        "two experiments would evaluate on the same population:\n  "
        + "\n  ".join(collisions)
    )


def test_no_experiment_evaluates_on_its_own_training_seed():
    """Offset zero means the evaluation population is drawn from the seed the
    models were fitted on."""
    for rel, off in _offsets().items():
        assert off != 0, f"{rel} evaluates on the training seed"


def test_the_live_console_uses_the_same_separation():
    from recovery_ledger.live.session import DEFAULT_SEED, EVAL_SEED

    assert EVAL_SEED != DEFAULT_SEED


@pytest.mark.parametrize("n_a,n_b", [(1, 40), (1500, 2000), (2000, 4000)])
def test_generate_cases_really_is_batch_size_dependent(n_a, n_b):
    """The property that made the collision survivable, and that makes it
    dangerous to rely on. Pinned here as well as in the live-range tests,
    because this file is where someone will come looking after a collision."""
    from datetime import datetime, timezone

    from recovery_ledger.sim.generator import generate_cases

    now = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)
    a = generate_cases(n_a, seed=12345, now=now)[0]
    b = generate_cases(n_b, seed=12345, now=now)[0]
    assert a.case_id == b.case_id
    assert a.amount_at_risk != b.amount_at_risk, (
        "generate_cases has become batch-size independent — good, but the "
        "comments warning about it are now wrong and should be removed"
    )
