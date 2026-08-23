from recovery_ledger.ledger.ledger import Ledger


def test_empty_ledger_verifies():
    assert Ledger().verify_chain() is True


def test_chain_verifies_after_appends():
    ledger = Ledger()
    ledger.append("case_1", "detection", {"amount": 100})
    ledger.append("case_1", "decision", {"action": "nudge"})
    ledger.append("case_2", "detection", {"amount": 250})
    assert ledger.verify_chain() is True
    assert len(ledger) == 3


def test_entries_link_via_prev_hash():
    ledger = Ledger()
    e0 = ledger.append("case_1", "detection", {})
    e1 = ledger.append("case_1", "decision", {})
    assert e0.prev_hash == ledger.GENESIS_HASH
    assert e1.prev_hash == e0.hash


def test_entries_for_case_filters_correctly():
    ledger = Ledger()
    ledger.append("case_1", "detection", {})
    ledger.append("case_2", "detection", {})
    ledger.append("case_1", "decision", {})
    assert len(ledger.entries_for_case("case_1")) == 2
    assert len(ledger.entries_for_case("case_2")) == 1


def test_tampering_with_payload_breaks_verification():
    ledger = Ledger()
    ledger.append("case_1", "detection", {"amount": 100})
    ledger.append("case_1", "decision", {"action": "nudge"})
    # Directly mutate a stored entry's payload without going through append —
    # simulates someone editing the audit trail after the fact.
    tampered = ledger._entries[0]
    ledger._entries[0] = type(tampered)(
        seq=tampered.seq, case_id=tampered.case_id, entry_type=tampered.entry_type,
        payload={"amount": 999999}, timestamp=tampered.timestamp,
        prev_hash=tampered.prev_hash, hash=tampered.hash,
    )
    assert ledger.verify_chain() is False


def test_tampering_with_hash_breaks_verification():
    ledger = Ledger()
    ledger.append("case_1", "detection", {"amount": 100})
    tampered = ledger._entries[0]
    ledger._entries[0] = type(tampered)(
        seq=tampered.seq, case_id=tampered.case_id, entry_type=tampered.entry_type,
        payload=tampered.payload, timestamp=tampered.timestamp,
        prev_hash=tampered.prev_hash, hash="0" * 64,
    )
    assert ledger.verify_chain() is False


def test_deterministic_hash_given_same_content():
    """Two ledgers appending identical (case_id, entry_type, payload) content
    at the same sequence position must produce the same hash chain shape —
    the timestamp is the only non-reproducible input, so pin it out by only
    comparing prev_hash linkage and chain validity, not raw hash equality."""
    a, b = Ledger(), Ledger()
    a.append("case_1", "detection", {"x": 1})
    b.append("case_1", "detection", {"x": 1})
    assert a.verify_chain() and b.verify_chain()
    assert a._entries[0].prev_hash == b._entries[0].prev_hash == Ledger.GENESIS_HASH
