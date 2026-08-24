"""The audit trail's central claim is that you cannot quietly edit it.

`verify_chain()` returning False is easy to write and easy to write *wrongly*
— a function that always returns False passes a naive test. These tests pin
both directions: an untouched chain verifies, and each distinct way of
tampering is caught, at the right entry, with the right diagnosis.
"""

from __future__ import annotations

import copy

import pytest

from recovery_ledger.ledger.ledger import Ledger


def _chain(n: int = 6) -> Ledger:
    led = Ledger()
    for i in range(n):
        led.append(f"case_{i // 2:03d}", "decision", {"step": i, "action": "nudge"})
    return led


def _raw(led: Ledger) -> list[dict]:
    return copy.deepcopy([e.to_dict() for e in led._entries])


def test_untouched_chain_verifies():
    result = _chain().verify_chain_detail()
    assert result["ok"] is True
    assert result["broken_at"] is None
    assert result["checked"] == 6


def test_empty_chain_verifies():
    assert Ledger().verify_chain_detail()["ok"] is True


def test_editing_a_payload_is_caught_at_that_entry():
    raw = _raw(_chain())
    raw[3]["payload"]["action"] = "escalate"
    result = Ledger.from_entries(raw).verify_chain_detail()
    assert result["ok"] is False
    assert result["broken_at"] == 3
    assert result["failure"] == "content_altered"


def test_editing_a_payload_and_refreshing_its_hash_still_breaks_the_next_link():
    """The interesting attack: a tamperer who knows to recompute the hash of
    the entry they edited. The *next* entry still commits to the old hash, so
    the chain catches it one step later."""
    raw = _raw(_chain())
    raw[2]["payload"]["action"] = "escalate"
    # Recompute entry 2's own hash the way the ledger would, from the two
    # genuine entries before it.
    fixed = Ledger.from_entries(raw[:2])
    fixed.append(raw[2]["case_id"], raw[2]["entry_type"], raw[2]["payload"])
    raw[2]["hash"] = fixed._entries[2].hash
    raw[2]["timestamp"] = fixed._entries[2].timestamp

    result = Ledger.from_entries(raw).verify_chain_detail()
    assert result["ok"] is False
    assert result["broken_at"] == 3
    assert result["failure"] == "chain_relinked"


def test_deleting_an_entry_is_caught_as_a_relink():
    raw = _raw(_chain())
    del raw[2]
    for i, d in enumerate(raw):
        d["seq"] = i  # a tamperer would renumber to hide the gap
    result = Ledger.from_entries(raw).verify_chain_detail()
    assert result["ok"] is False
    # Renumbering changes the hashed content, so it is caught immediately.
    assert result["broken_at"] == 2
    assert result["failure"] in ("content_altered", "chain_relinked")


def test_reordering_two_entries_is_caught():
    raw = _raw(_chain())
    raw[2], raw[3] = raw[3], raw[2]
    result = Ledger.from_entries(raw).verify_chain_detail()
    assert result["ok"] is False
    # `broken_at` is the offending entry's own `seq`, not its position in the
    # list — after a swap those differ, and the entry's claimed identity is
    # the more useful thing to report to whoever has to go and look at it.
    assert result["broken_at"] == 3
    assert result["failure"] == "chain_relinked"


def test_verify_chain_bool_still_agrees_with_the_detailed_form():
    led = _chain()
    assert led.verify_chain() is True
    raw = _raw(led)
    raw[1]["payload"]["step"] = 99
    tampered = Ledger.from_entries(raw)
    assert tampered.verify_chain() is False
    assert tampered.verify_chain_detail()["ok"] is False


# ── observers ────────────────────────────────────────────────────────────

def test_observers_see_every_entry_in_order():
    led = Ledger()
    seen: list[int] = []
    led.subscribe(lambda e: seen.append(e.seq))
    for i in range(4):
        led.append("case_000", "step", {"i": i})
    assert seen == [0, 1, 2, 3]


def test_unsubscribe_stops_delivery():
    led = Ledger()
    seen: list[int] = []
    stop = led.subscribe(lambda e: seen.append(e.seq))
    led.append("c", "step", {})
    stop()
    led.append("c", "step", {})
    assert seen == [0]


def test_a_broken_observer_cannot_break_the_ledger():
    """A live UI subscriber must never be able to take down a run or corrupt
    the trail it is watching."""
    led = Ledger()
    led.subscribe(lambda e: (_ for _ in ()).throw(RuntimeError("boom")))
    seen: list[int] = []
    led.subscribe(lambda e: seen.append(e.seq))
    led.append("c", "step", {"a": 1})
    led.append("c", "step", {"a": 2})
    assert seen == [0, 1]
    assert led.verify_chain() is True


@pytest.mark.parametrize("field_name", ["case_id", "entry_type", "timestamp"])
def test_editing_any_hashed_field_is_caught(field_name):
    raw = _raw(_chain())
    raw[4][field_name] = "tampered"
    result = Ledger.from_entries(raw).verify_chain_detail()
    assert result["ok"] is False
    assert result["broken_at"] == 4
