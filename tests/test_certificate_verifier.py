"""An outsider's check on the audit trail, with no agent in the room.

B4's claim is a hash-chained trail with a certificate behind every action. The
dashboard makes that *browsable*; browsing is not auditing. This verifies it:
given only a ledger file, re-derive each certificate's ALLOW/DENY from the rule
results recorded inside it, and confirm nothing executed without one.

What it deliberately cannot do is re-run the rules against the original
`RuleContext` — the context is not stored in the ledger, only the rule
outcomes are. So this checks that a certificate is internally consistent,
complete and honoured, not that the rules were computed correctly in the first
place. That limit is the finding, and it is stated rather than papered over.

Several of these tests exist to fail: a decision that contradicts its own rule
results, an action executed under a DENY, and a certificate missing a rule must
each be caught, because a verifier that passes everything is theatre.
"""

from __future__ import annotations

import pytest

from recovery_ledger.kernel.verifier import verify_ledger


def _cert(case_id, decision, action_type, rules, *, seq=0):
    return {
        "seq": seq, "case_id": case_id, "entry_type": "certificate",
        "payload": {
            "action_id": f"act_{seq}", "case_id": case_id,
            "decision": decision, "action_type": action_type, "channel": None,
            "rule_results": [
                {"rule_name": n, "passed": p, "detail": {}} for n, p in rules
            ],
        },
    }


def _result(case_id, action_type, executed, *, seq=1):
    return {
        "seq": seq, "case_id": case_id, "entry_type": "action_result",
        "payload": {"executed": executed, "action_type": action_type, "channel": None},
    }


ALL_PASS = [("RULE.A", True), ("RULE.B", True)]
ONE_FAIL = [("RULE.A", True), ("RULE.B", False)]


def test_a_clean_trail_verifies():
    report = verify_ledger([
        _cert("c1", "ALLOW", "nudge", ALL_PASS, seq=0),
        _result("c1", "nudge", True, seq=1),
    ])
    assert report.ok
    assert report.certificates == 1
    assert not report.violations


def test_an_allow_whose_own_rules_failed_is_caught():
    """THE FAILURE DIRECTION. The certificate says ALLOW while carrying a
    failed rule — the decision does not follow from its own evidence."""
    report = verify_ledger([_cert("c1", "ALLOW", "nudge", ONE_FAIL, seq=0)])
    assert not report.ok
    assert any("does not follow" in v.detail for v in report.violations)


def test_a_deny_with_every_rule_passing_is_caught():
    report = verify_ledger([_cert("c1", "DENY", "nudge", ALL_PASS, seq=0)])
    assert not report.ok
    assert any("does not follow" in v.detail for v in report.violations)


def test_a_contact_executed_under_a_deny_is_caught():
    report = verify_ledger([
        _cert("c1", "DENY", "nudge", ONE_FAIL, seq=0),
        _result("c1", "nudge", True, seq=1),
    ])
    assert not report.ok
    assert any("without an allowing certificate" in v.detail for v in report.violations)


def test_a_contact_executed_with_no_certificate_at_all_is_caught():
    report = verify_ledger([_result("c1", "nudge", True, seq=0)])
    assert not report.ok
    assert any("without an allowing certificate" in v.detail for v in report.violations)


def test_a_certificate_missing_a_rule_the_others_evaluated_is_caught():
    """A rule that silently stops being evaluated is how a kernel quietly
    loses a regulation."""
    report = verify_ledger([
        _cert("c1", "ALLOW", "nudge", ALL_PASS, seq=0),
        _cert("c2", "ALLOW", "nudge", [("RULE.A", True)], seq=1),
    ])
    assert not report.ok
    assert any("RULE.B" in v.detail for v in report.violations)


def test_an_unexecuted_action_needs_no_certificate():
    """A denied action that never ran is the kernel working, not a violation."""
    report = verify_ledger([
        _cert("c1", "DENY", "nudge", ONE_FAIL, seq=0),
        _result("c1", "nudge", False, seq=1),
    ])
    assert report.ok


def test_non_contact_actions_do_not_require_an_allowing_certificate():
    """RETRY and REROUTE move money on the rails without messaging anyone —
    that distinction is novelty claim N6 and the verifier must not erase it."""
    report = verify_ledger([_result("c1", "retry", True, seq=0)])
    assert report.ok


def test_the_real_committed_ledger_verifies():
    """The artifact the project actually ships."""
    import json
    from pathlib import Path

    raw = json.loads((Path(__file__).resolve().parents[1]
                      / "experiments" / "tier2_simulation" / "batch_ledger.json").read_text())
    entries = raw["entries"] if isinstance(raw, dict) else raw
    report = verify_ledger(entries)
    assert report.ok, f"the shipped ledger does not verify: {report.violations[:3]}"
    assert report.certificates > 0


def test_a_tampered_ledger_is_caught_by_the_chain():
    """The other half of the guarantee: internal consistency means nothing if
    the file can be edited after the fact. Flip one recorded decision and the
    hash chain must refuse it."""
    import json
    from pathlib import Path

    from recovery_ledger.kernel.verifier import verify_ledger
    from recovery_ledger.ledger.ledger import Ledger

    raw = json.loads((Path(__file__).resolve().parents[1]
                      / "experiments" / "tier2_simulation" / "batch_ledger.json").read_text())
    entries = raw["entries"] if isinstance(raw, dict) else raw

    tampered = [dict(e) for e in entries]
    for e in tampered:
        if e["entry_type"] == "certificate" and e["payload"].get("decision") == "DENY":
            e["payload"] = {**e["payload"], "decision": "ALLOW"}
            break

    assert Ledger.from_entries(tampered).verify_chain() is False
    # and the decision no longer follows from its own rule results either
    report = verify_ledger(tampered, chain_valid=False)
    assert not report.ok
