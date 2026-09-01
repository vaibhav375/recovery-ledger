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
    "fleet/run_fleet_latency.py": ("distinct", ""),
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
    "regret/run_regret.py": (
        "shares", "tier2_simulation/run_batch.py — a regret figure is only "
                  "quotable beside the headline if it is measured on the same "
                  "customers"),
    "tier1_criteo/run_validation.py": ("none", "real RCT data (Criteo, Hillstrom)"),
    "tier1_targeting/run_targeting.py": ("none", "real RCT data (Criteo) — the policy claim off the simulator"),
    "tier1_revenue/run_revenue.py": ("none", "real RCT data (Hillstrom spend) — the one money figure in this repo not drawn from the simulator"),
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


def _offset_for(rel: str) -> int:
    """The eval-seed offset a single registry entry's file declares,
    regardless of its registered `kind` — used to compare a sharer's offset
    against its target's, not just to collision-check the "distinct" set."""
    path = ROOT / "experiments" / rel
    assert path.exists(), f"{rel} moved; update SEED_REGISTRY"
    pattern = (
        r"seed=SEED \+ (\d+)"
        if rel == "tier2_simulation/run_batch.py"
        else EVAL_SEED_PATTERN
    )
    m = re.search(pattern, path.read_text())
    assert m, f"could not find the eval-seed offset in {rel}"
    return int(m.group(1))


def test_declared_sharers_name_an_experiment_that_exists():
    for rel, (kind, note) in SEED_REGISTRY.items():
        if kind != "shares":
            continue
        target = note.split(" ")[0]
        assert (ROOT / "experiments" / target).exists(), (
            f"{rel} says it shares with {target!r}, which does not exist"
        )


def test_declared_sharers_name_a_registered_target_with_a_matching_offset():
    """A sharer only means what it claims if the thing it names is itself
    accountable in this registry, and if the two files actually evaluate on
    the same seed. Before this test, `run_regret.py`'s `EVAL_SEED = SEED +
    1000` matching `run_batch.py`'s own eval seed was unverified — a typo or
    a drifted refactor in either file would silently break the comparability
    the whole regret-ledger experiment rests on, with nothing here to catch
    it."""
    for rel, (kind, note) in SEED_REGISTRY.items():
        if kind != "shares":
            continue
        target = note.split(" ")[0]
        assert target in SEED_REGISTRY, (
            f"{rel} says it shares with {target!r}, which is not itself a "
            f"registered entry — a sharer must name something this file is "
            f"actually watching, not an experiment exempt by omission"
        )
        sharer_offset = _offset_for(rel)
        target_offset = _offset_for(target)
        assert sharer_offset == target_offset, (
            f"{rel} claims to share {target}'s population (SEED + "
            f"{target_offset}) but its own eval-seed offset is SEED + "
            f"{sharer_offset} — they are not measuring the same customers"
        )


def test_every_registry_entry_has_a_valid_kind():
    """Each registry entry's kind must be one of the three declared values.
    A typo'd kind silently drops that experiment from collision detection
    without any test failing — the same failure the task exists to close,
    just one level down."""
    valid_kinds = {"distinct", "shares", "none"}
    invalid = []
    for rel, (kind, _note) in SEED_REGISTRY.items():
        if kind not in valid_kinds:
            invalid.append(f"{rel}: {kind!r} (must be one of {sorted(valid_kinds)})")
    assert not invalid, (
        "these registry entries have invalid kind values:\n  "
        + "\n  ".join(invalid)
    )


def _offsets() -> dict[str, int]:
    return {
        rel: _offset_for(rel)
        for rel, (kind, _note) in SEED_REGISTRY.items()
        if kind == "distinct"
    }


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
