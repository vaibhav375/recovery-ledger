"""The red-team suite must pass in CI, not only when run by hand.

Spec section 9.5 sets the target at a 100% block rate with zero violations.
These tests fail the build if the compliance kernel ever regresses — which
is the only way that target means anything.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "redteam"))

from run_redteam import (  # noqa: E402
    run_fuzz,
    run_hostile_policy_end_to_end,
    run_named_attacks,
)


def test_every_named_attack_is_blocked():
    result = run_named_attacks()
    assert result["block_rate"] == 1.0, (
        f"block rate {result['block_rate']:.1%}; leaked attacks: {result['leaks']}"
    )


def test_no_legitimate_action_is_wrongly_blocked():
    """A kernel that denies everything would score 100% on the attacks above
    and be useless. At least one legitimate action must still get through."""
    result = run_named_attacks()
    assert not result["false_positives"], (
        f"legitimate actions wrongly blocked: {result['false_positives']}"
    )


def test_hostile_policy_never_gets_an_uncertified_contact_executed():
    """Deny-by-default as a system property: even a policy that always
    proposes maximum-pressure contact cannot get one executed without an
    ALLOW certificate behind it."""
    result = run_hostile_policy_end_to_end(n_cases=150)
    assert result["contacts_executed_without_allow_certificate"] == 0
    assert result["ledger_chain_valid"] is True


def test_fuzzed_states_never_leak():
    """Random states checked against oracles written from the regulations
    rather than from the rule implementations."""
    result = run_fuzz(n=2000)
    assert result["leaks"] == 0, f"fuzz found leaks: {result['examples']}"
