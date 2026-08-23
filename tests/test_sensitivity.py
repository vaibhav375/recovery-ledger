"""The sensitivity sweep's core claim must hold in CI, not just when run
by hand: the policy ranking has to survive the simulator's constants being
set differently (spec section 7.3)."""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "experiments" / "sensitivity"))
sys.path.insert(0, str(Path(__file__).parent.parent / "experiments" / "tier2_simulation"))

from run_sweep import evaluate_setting  # noqa: E402

from recovery_ledger.sim.environment import DEFAULT_PARAMS  # noqa: E402


def test_targeting_beats_random_at_default_parameters():
    r = evaluate_setting(DEFAULT_PARAMS, n_train=1500, n_eval=800)
    assert r["c1_ev_beats_random"], "the uplift model must beat random targeting"


def test_targeting_still_beats_random_when_contacts_are_independent():
    """The most hostile setting for a selective policy: no annoyance decay at
    all, so brute-force persistence is never punished."""
    params = replace(DEFAULT_PARAMS, annoyance_decay_per_excess_contact=0.0)
    r = evaluate_setting(params, n_train=1500, n_eval=800)
    assert r["c1_ev_beats_random"]


def test_targeting_still_beats_random_when_amount_says_nothing_about_persuadability():
    """Removes the amount<->liquidity coupling entirely, so the EV policy's
    amount weighting carries no hidden information about who is persuadable."""
    params = replace(DEFAULT_PARAMS, amount_liquidity_coupling=0.0)
    r = evaluate_setting(params, n_train=1500, n_eval=800)
    assert r["c1_ev_beats_random"]
