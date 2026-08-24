"""The audit-trail browser must actually render the ledger it is given.

B4 asks for a *browsable* audit trail. These tests check the generator's
output is a complete, self-contained document carrying real data — not that
it looks nice, which is not a thing a test can assert.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "dashboard"))

from build_dashboard import build, case_card, group_by_case, rule_stats, summarise  # noqa: E402

from recovery_ledger.ledger.ledger import Ledger  # noqa: E402


def _ledger_entries(tmp_path: Path) -> Path:
    ledger = Ledger()
    ledger.append("case_a", "case_ingested", {"case_id": "case_a", "loss_type": "failed_payment",
                                              "amount_at_risk": 1234.0,
                                              "customer": {"language_pref": "hi", "channel_pref": "sms"}})
    ledger.append("case_a", "certificate", {"action_id": "x", "case_id": "case_a", "decision": "DENY",
                                            "action_type": "nudge", "channel": "sms",
                                            "rule_results": [{"rule_name": "R.ONE", "passed": False, "detail": {}},
                                                             {"rule_name": "R.TWO", "passed": True, "detail": {}}],
                                            "created_at": "2026-08-24T12:00:00"})
    ledger.append("case_a", "stop", {"reason": "budget_exhausted"})
    path = tmp_path / "led.json"
    ledger.write(path)
    return path


def test_generated_page_is_self_contained_and_carries_the_data(tmp_path):
    src = _ledger_entries(tmp_path)
    out = build(src, tmp_path / "index.html", max_cases=50)
    doc = out.read_text()

    assert doc.startswith("<!doctype html>")
    # No external resources: the page must work offline, from file://
    for external in ("http://", "https://", "<script src=", "<link "):
        assert external not in doc, f"page must be self-contained; found {external!r}"
    assert "case_a" in doc and "budget_exhausted" in doc


def test_summary_counts_denials_and_certificates(tmp_path):
    entries = json.loads(_ledger_entries(tmp_path).read_text())
    s = summarise(entries, group_by_case(entries))
    assert s["cases"] == 1
    assert s["certificates"] == 1
    assert s["denied"] == 1
    assert s["stop_reasons"] == {"budget_exhausted": 1}


def test_rule_stats_separate_passes_from_denials(tmp_path):
    entries = json.loads(_ledger_entries(tmp_path).read_text())
    stats = {r["rule"]: r for r in rule_stats(entries)}
    assert stats["R.ONE"]["failed"] == 1 and stats["R.ONE"]["passed"] == 0
    assert stats["R.TWO"]["passed"] == 1 and stats["R.TWO"]["failed"] == 0


def test_case_card_exposes_the_full_hash_chained_timeline(tmp_path):
    entries = json.loads(_ledger_entries(tmp_path).read_text())
    grouped = group_by_case(entries)
    card = case_card("case_a", grouped["case_a"])
    assert card["outcome"] == "budget_exhausted"
    assert card["denied"] == 1
    assert len(card["timeline"]) == 3
    # each step must carry its position in the hash chain, so the browser can
    # show provenance rather than just content
    assert all(step["hash"] and step["prev"] for step in card["timeline"])
