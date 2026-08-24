"""The provenance registry must not drift from the kernel.

A citation registry that silently falls behind the rules it describes is
worse than no registry: it invites a reader to trust a source for a rule that
no longer works that way, or leaves a refusal with no answer to "says who?".
These tests fail the build rather than let that happen.
"""

from __future__ import annotations

import pytest

from recovery_ledger.cli import build_default_agent
from recovery_ledger.kernel.provenance import REGISTRY, citation_for, registry_json
from recovery_ledger.ledger.ledger import Ledger


def _default_rule_names() -> list[str]:
    agent = build_default_agent(Ledger(), clock=lambda: None)
    return [rule.name for rule in agent.kernel.rules]


def test_every_registered_rule_has_a_citation():
    missing = [n for n in _default_rule_names() if citation_for(n) is None]
    assert not missing, f"rules with no provenance entry: {missing}"


def test_registry_has_no_entries_for_rules_that_do_not_exist():
    """The other direction: a stale citation for a deleted rule is a claim
    about a system that no longer exists."""
    live = set(_default_rule_names())
    orphans = sorted(set(REGISTRY) - live)
    assert not orphans, f"citations for rules not in the default kernel: {orphans}"


def test_policy_rules_are_not_dressed_up_as_law():
    """`POLICY.*` rules are this project's own limits. If one of them ever
    claims an instrument, the kernel is asserting a legal basis it does not
    have."""
    for name, c in REGISTRY.items():
        if name.startswith("POLICY."):
            assert c.kind == "policy", f"{name} is policy but declared {c.kind}"
            assert c.instrument is None, f"{name} claims instrument {c.instrument!r}"


def test_no_clause_number_without_a_primary_source():
    """The registry's core discipline: a section number may only appear where
    the requirement was read off the instrument itself, not off the spec's
    summary of it."""
    for name, c in REGISTRY.items():
        if c.clause is not None:
            assert c.confidence == "primary", (
                f"{name} pins clause {c.clause!r} but is only spec-sourced"
            )


def test_legal_citations_name_an_instrument_and_a_requirement():
    for name, c in REGISTRY.items():
        if c.kind != "policy":
            assert c.instrument, f"{name} has no instrument"
        assert c.requirement.strip(), f"{name} has no requirement text"
        assert c.encoded_as.strip(), f"{name} does not say what it checks"


def test_registry_json_is_serialisable_and_complete():
    js = registry_json()
    assert set(js) == set(REGISTRY)
    for name, d in js.items():
        assert d["requirement"] and d["encoded_as"], name
        assert d["confidence"] in ("primary", "spec"), name


@pytest.mark.parametrize("rule_name", ["RBI.RECOVERY.HOURS", "DPDPA.CONSENT_RECORD"])
def test_spot_check_known_citations(rule_name):
    c = citation_for(rule_name)
    assert c is not None and c.confidence == "primary"
    assert c.url
