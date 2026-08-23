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
        return entry

    def verify_chain(self) -> bool:
        expected_prev = self.GENESIS_HASH
        for entry in self._entries:
            recomputed = hashlib.sha256(
                _canonical(
                    entry.seq, entry.case_id, entry.entry_type, entry.payload,
                    entry.timestamp, entry.prev_hash,
                ).encode()
            ).hexdigest()
            if entry.hash != recomputed or entry.prev_hash != expected_prev:
                return False
            expected_prev = entry.hash
        return True

    def entries_for_case(self, case_id: str) -> list[LedgerEntry]:
        return [e for e in self._entries if e.case_id == case_id]

    def __len__(self) -> int:
        return len(self._entries)

    def to_json(self) -> str:
        return json.dumps([e.to_dict() for e in self._entries], indent=2, default=str)

    def write(self, path: Path) -> None:
        path.write_text(self.to_json())
