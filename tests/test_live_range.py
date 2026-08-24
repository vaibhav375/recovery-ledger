"""The live console must show the same system the results come from.

The risk this file exists to close is not a crash — it is a demo that quietly
diverges from the measured pipeline: a weaker kernel, a different case, a
lever that appears to work because it changed the subject. Each test below
pins one of those.

These run the real models, so they are slower than the rest of the suite;
they are worth it, because a dishonest demo is the one failure this project
cannot afford.
"""

from __future__ import annotations

import pytest

from recovery_ledger.live import range as rng
from recovery_ledger.live.session import build_kernel
from recovery_ledger.sim.generator import generate_cases


# ── the roster ───────────────────────────────────────────────────────────

def test_case_generation_is_batch_size_dependent():
    """The trap this module has to route around, pinned so nobody 'simplifies'
    the roster back into a variable-sized call.

    `generate_cases` draws its fields in one vectorised pass, so case 0 of a
    1-case batch and case 0 of a 40-case batch share an id but are different
    cases. Indexing into differently sized batches would make a counterfactual
    compare two unrelated cases and blame the lever for the difference.
    """
    from recovery_ledger.live.session import NOW

    one = generate_cases(1, seed=20260823, now=NOW)[0]
    many = generate_cases(40, seed=20260823, now=NOW)[0]
    assert one.case_id == many.case_id
    assert one.amount_at_risk != many.amount_at_risk


def test_roster_is_stable_for_a_seed():
    a = rng.roster(20260823)
    b = rng.roster(20260823)
    assert len(a) == len(b) == rng.ROSTER_N
    assert [c.case_id for c in a] == [c.case_id for c in b]
    assert [c.amount_at_risk for c in a] == [c.amount_at_risk for c in b]


# ── the kernel range ─────────────────────────────────────────────────────

def test_catalogue_is_the_real_redteam_suite():
    cat = rng.attack_catalogue()
    assert len(cat) >= 20, "the red-team suite did not load"
    assert all({"name", "category", "intent", "must_be_denied"} <= set(a) for a in cat)


def test_every_attack_that_must_be_denied_is_denied():
    """The same claim `make redteam` makes, asserted through the live path so
    the interactive console cannot report a better number than the suite."""
    failures = []
    for a in rng.attack_catalogue():
        result = rng.fire(a["name"])
        if not result["correct"]:
            failures.append((a["name"], result["decision"], a["must_be_denied"]))
    assert not failures, f"kernel range disagreed with the oracle: {failures}"


def test_fire_reports_which_rule_refused_and_cites_it():
    r = rng.fire("contact_outside_hours_02")
    assert r["decision"] == "DENY"
    rules = [d["rule"] for d in r["denied_by"]]
    assert "RBI.RECOVERY.HOURS" in rules
    citation = next(d["citation"] for d in r["denied_by"] if d["rule"] == "RBI.RECOVERY.HOURS")
    assert citation and citation["instrument"]


def test_range_uses_the_full_kernel_by_default():
    r = rng.fire("contact_outside_hours_02")
    assert r["rules_evaluated"] == len(build_kernel().rules)
    assert r["disabled_rules"] == []


def test_unknown_attack_is_an_error_not_a_pass():
    assert "error" in rng.fire("no_such_attack")


# ── mutation: the suite must be able to fail ─────────────────────────────

def test_disabling_the_responsible_rule_lets_the_attack_through():
    """The whole point of the mutation lever. If this ever passes with the
    rule removed, the 100% block rate was measuring nothing."""
    r = rng.fire("contact_outside_hours_02", disabled_rules=["RBI.RECOVERY.HOURS"])
    assert r["decision"] == "ALLOW"
    assert r["mutation"]["rule_was_load_bearing"] is True
    assert r["mutation"]["baseline_decision"] == "DENY"


def test_disabling_an_unrelated_rule_does_not_let_the_attack_through():
    """Defence in depth, stated as a fact: removing a rule that was not the
    one refusing must leave the refusal standing."""
    r = rng.fire("contact_outside_hours_02", disabled_rules=["POLICY.CONTACT_BUDGET"])
    assert r["decision"] == "DENY"
    assert r["mutation"]["rule_was_load_bearing"] is False


def test_disabling_every_rule_denies_by_default():
    """Deny-by-default: an empty kernel must refuse everything, not permit
    everything. A kernel that fails open is worse than no kernel."""
    r = rng.fire("contact_outside_hours_02", disabled_rules=rng.all_rule_names())
    assert r["decision"] == "DENY"
    assert r["rules_evaluated"] == 0


# ── counterfactuals ──────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "lever,expected_rule",
    [
        ("night", "RBI.RECOVERY.HOURS"),
        ("opted_out", "TCCCPR.OPT_OUT.COOLING"),
        ("promised", "POLICY.PROMISE_TO_PAY_WINDOW"),
        ("fresh_debit", "EMANDATE2026.PRE_DEBIT_NOTICE"),
    ],
)
def test_each_lever_engages_the_rule_it_advertises(lever, expected_rule):
    """A lever that changes the outcome for some *other* reason would be a lie
    told with real data. Each one must engage the rule it names."""
    r = rng.counterfactual(seed=20260823, index=None, lever=lever)
    assert "error" not in r
    assert r["diverged"] is True, f"{lever} changed nothing"
    assert expected_rule in {d["rule"] for d in r["changed"]["denials"]}


def test_high_value_lever_escalates_to_a_human():
    r = rng.counterfactual(seed=20260823, index=None, lever="high_value")
    assert r["changed"]["reason"] == "human_escalation_threshold"


def test_baseline_and_changed_share_everything_but_the_lever():
    """Common random numbers: same case, same seed, same models. Two runs of
    the *same* baseline must be identical, or nothing attributed to a lever
    means anything."""
    a = rng.counterfactual(seed=20260823, index=0, lever="night")
    b = rng.counterfactual(seed=20260823, index=0, lever="opted_out")
    assert a["case"]["case_id"] == b["case"]["case_id"]
    assert a["baseline"]["reason"] == b["baseline"]["reason"]
    assert len(a["baseline"]["entries"]) == len(b["baseline"]["entries"])


def test_unknown_lever_is_an_error():
    assert "error" in rng.counterfactual(seed=1, index=0, lever="nope")


def test_out_of_range_index_is_an_error():
    assert "error" in rng.counterfactual(seed=20260823, index=9999, lever="night")


# ── tamper check through the live path ───────────────────────────────────

def test_verify_entries_accepts_a_clean_chain_and_rejects_an_edited_one():
    from recovery_ledger.ledger.ledger import Ledger

    led = Ledger()
    for i in range(4):
        led.append("case_000", "decision", {"i": i})
    raw = [e.to_dict() for e in led._entries]
    assert rng.verify_entries(raw)["ok"] is True

    raw[2]["payload"]["i"] = 99
    bad = rng.verify_entries(raw)
    assert bad["ok"] is False
    assert bad["broken_at"] == 2


def test_verify_entries_survives_malformed_input():
    result = rng.verify_entries([{"nonsense": True}])
    assert result["ok"] is False
    assert result["failure"] == "malformed"
