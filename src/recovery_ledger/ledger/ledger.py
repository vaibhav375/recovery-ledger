"""Append-only, hash-chained audit trail (spec section 5.7 / B4).

Every entry commits to the full content of every entry before it: tampering
with or deleting an entry anywhere in the chain changes that entry's hash,
which breaks every hash after it. `verify_chain()` re-derives every hash from
its stored content and checks it against both the stored hash and the next
entry's `prev_hash` link — this is what "100% certificate coverage" and "an
audit trail, browsable" (spec Definition of Done) are checked against.

This module has no ML, no LLM, no network calls — it's pure bookkeeping and
is deliberately kept that way.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class LedgerEntry:
    seq: int
    case_id: str
    entry_type: str
    payload: dict
    timestamp: str
    prev_hash: str
    hash: str

    def to_dict(self) -> dict:
        return {
            "seq": self.seq,
            "case_id": self.case_id,
            "entry_type": self.entry_type,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "prev_hash": self.prev_hash,
            "hash": self.hash,
        }


def _canonical(seq: int, case_id: str, entry_type: str, payload: dict, timestamp: str, prev_hash: str) -> str:
    """Deterministic JSON serialisation used for hashing. Key order is fixed
    via sort_keys so the same logical content always hashes the same way."""
    return json.dumps(
        {
            "seq": seq,
            "case_id": case_id,
            "entry_type": entry_type,
            "payload": payload,
            "timestamp": timestamp,
            "prev_hash": prev_hash,
        },
        sort_keys=True,
        default=str,
    )


@dataclass
class Ledger:
    GENESIS_HASH: str = field(default="0" * 64, init=False)
    _entries: list[LedgerEntry] = field(default_factory=list)
    # Observers are notified as entries land. This exists so the live console
    # can watch a real run in progress without the agent loop knowing anything
    # about a UI: the loop writes to the ledger exactly as it always did, and
    # the ledger is the only thing that fans out.
    _observers: list[Callable[[LedgerEntry], None]] = field(
        default_factory=list, repr=False, compare=False
    )

    def subscribe(self, observer: Callable[[LedgerEntry], None]) -> Callable[[], None]:
        """Register an observer; returns a function that unregisters it."""
        self._observers.append(observer)

        def unsubscribe() -> None:
            try:
                self._observers.remove(observer)
            except ValueError:
                pass

        return unsubscribe

    def append(self, case_id: str, entry_type: str, payload: dict) -> LedgerEntry:
        prev_hash = self._entries[-1].hash if self._entries else self.GENESIS_HASH
        seq = len(self._entries)
        timestamp = datetime.now(timezone.utc).isoformat()
        canonical = _canonical(seq, case_id, entry_type, payload, timestamp, prev_hash)
        entry_hash = hashlib.sha256(canonical.encode()).hexdigest()
        entry = LedgerEntry(
            seq=seq,
            case_id=case_id,
            entry_type=entry_type,
            payload=payload,
            timestamp=timestamp,
            prev_hash=prev_hash,
            hash=entry_hash,
        )
        self._entries.append(entry)
        for observer in tuple(self._observers):
            # An observer must never be able to corrupt the audit trail. A
            # broken subscriber is the subscriber's problem.
            try:
                observer(entry)
            except Exception:  # noqa: BLE001
                pass
        return entry

    def verify_chain(self) -> bool:
        return self.verify_chain_detail()["ok"]

    def verify_chain_detail(self) -> dict:
        """Verify, and say *where* and *how* it failed.

        `verify_chain()` answering only True/False is fine for a test and
        useless for an auditor: "the trail is broken" does not tell you which
        entry was altered, or whether someone edited a payload, re-pointed a
        link, or deleted an entry outright. Those leave different signatures
        and this returns them.

        `broken_at` is the offending entry's own `seq` field, which is what an
        auditor has to go and look up. After a reorder that is not the same as
        its position in the list, deliberately: the entry's claimed identity is
        the useful one.
        """
        expected_prev = self.GENESIS_HASH
        for entry in self._entries:
            recomputed = hashlib.sha256(
                _canonical(
                    entry.seq, entry.case_id, entry.entry_type, entry.payload,
                    entry.timestamp, entry.prev_hash,
                ).encode()
            ).hexdigest()
            if entry.hash != recomputed:
                return {
                    "ok": False,
                    "checked": len(self._entries),
                    "broken_at": entry.seq,
                    "failure": "content_altered",
                    "detail": (
                        f"entry #{entry.seq} ({entry.entry_type}) hashes to "
                        f"{recomputed[:12]} but stores {entry.hash[:12]} — its "
                        f"content was changed after it was written"
                    ),
                    "expected_hash": recomputed,
                    "stored_hash": entry.hash,
                }
            if entry.prev_hash != expected_prev:
                return {
                    "ok": False,
                    "checked": len(self._entries),
                    "broken_at": entry.seq,
                    "failure": "chain_relinked",
                    "detail": (
                        f"entry #{entry.seq} ({entry.entry_type}) points back to "
                        f"{entry.prev_hash[:12]} but the entry before it hashes "
                        f"to {expected_prev[:12]} — an entry was removed, "
                        f"reordered, or spliced in"
                    ),
                    "expected_hash": expected_prev,
                    "stored_hash": entry.prev_hash,
                }
            expected_prev = entry.hash
        return {
            "ok": True,
            "checked": len(self._entries),
            "broken_at": None,
            "failure": None,
            "detail": f"all {len(self._entries)} entries verify against their own content and the link before them",
        }

    @classmethod
    def from_entries(cls, raw: list[dict]) -> "Ledger":
        """Rebuild a ledger from serialised entries *without re-hashing them*.

        Used by the tamper check: the point is to feed possibly-altered
        entries to the real `verify_chain_detail` and watch it catch them, so
        the stored hashes must be preserved exactly as given.
        """
        ledger = cls()
        for d in raw:
            ledger._entries.append(
                LedgerEntry(
                    seq=int(d["seq"]),
                    case_id=str(d["case_id"]),
                    entry_type=str(d["entry_type"]),
                    payload=d.get("payload") or {},
                    timestamp=str(d["timestamp"]),
                    prev_hash=str(d["prev_hash"]),
                    hash=str(d["hash"]),
                )
            )
        return ledger

    def entries_for_case(self, case_id: str) -> list[LedgerEntry]:
        return [e for e in self._entries if e.case_id == case_id]

    def __len__(self) -> int:
        return len(self._entries)

    def to_json(self) -> str:
        return json.dumps([e.to_dict() for e in self._entries], indent=2, default=str)

    def write(self, path: Path) -> None:
        path.write_text(self.to_json())
