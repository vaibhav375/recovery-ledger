"""Audit a Recovery Ledger trail with no agent in the room.

B4's claim is a hash-chained trail carrying a certificate behind every action.
The dashboard makes that browsable, and browsing is not auditing: it shows you
what the system says about itself, in the system's own words, rendered by the
system's own code. This is the check a third party can run instead — point it
at a ledger file and it re-derives each certificate's verdict from the rule
results recorded inside it, then confirms nothing reached a customer without
one.

Four things are checked, and each is a way the trail could be lying:

1. **The chain is intact.** Entries commit to the one before them, so a
   retrospective edit breaks the hash.
2. **Every decision follows from its own evidence.** A certificate carries the
   per-rule outcomes it was issued on. ALLOW must mean every rule passed, DENY
   must mean at least one did not. A certificate that says ALLOW while holding
   a failed rule is not a compliance record, it is a rubber stamp.
3. **Every certificate evaluated the whole rule set.** A rule that quietly
   stops being evaluated is how a kernel loses a regulation without anybody
   noticing, and it looks identical to a rule that always passes.
4. **Nothing that reached a customer lacks an allowing certificate.** Contact
   means NUDGE or NEGOTIATE; RETRY and REROUTE move money on the payment rails
   without messaging anyone, which is the whole of claim N6, so they are not
   held to the contact requirement.

WHAT THIS CANNOT DO, stated plainly because it bounds the guarantee. The
ledger records each rule's *outcome*, not the `RuleContext` it was evaluated
against. So this verifies that a certificate is internally consistent,
complete, and honoured — not that the rules computed the right answer from the
world's actual state. Re-deriving that would need the context recorded
alongside the outcome, and it is not. An auditor gets "the kernel's reasoning
is self-consistent and was obeyed", which is worth having and is less than
"the kernel was right".
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

CONTACT_ACTIONS = frozenset({"nudge", "negotiate"})
ALLOW = "ALLOW"
DENY = "DENY"


@dataclass(frozen=True)
class Violation:
    kind: str
    case_id: str
    detail: str


@dataclass
class VerificationReport:
    entries: int = 0
    certificates: int = 0
    executed_contacts: int = 0
    rules_expected: list[str] = field(default_factory=list)
    chain_valid: bool | None = None
    violations: list[Violation] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations and self.chain_valid is not False

    def render(self) -> str:
        lines = [
            f"entries            {self.entries:,}",
            f"certificates       {self.certificates:,}",
            f"executed contacts  {self.executed_contacts:,}",
            f"rules per cert     {len(self.rules_expected)}",
            f"chain              {'valid' if self.chain_valid else 'NOT CHECKED' if self.chain_valid is None else 'BROKEN'}",
        ]
        if self.violations:
            lines.append(f"\n{len(self.violations)} violation(s):")
            for v in self.violations[:20]:
                lines.append(f"  [{v.kind}] {v.case_id}: {v.detail}")
            if len(self.violations) > 20:
                lines.append(f"  ... and {len(self.violations) - 20} more")
        else:
            lines.append("\nno violations")
        return "\n".join(lines)


def _payload(entry: Any) -> dict:
    return entry.get("payload", {}) if isinstance(entry, dict) else {}


def _kind(entry: Any) -> str:
    return entry.get("entry_type", "") if isinstance(entry, dict) else ""


def verify_ledger(
    entries: Sequence[Any], *, chain_valid: bool | None = None
) -> VerificationReport:
    """Audit a sequence of ledger entries. Pure — no agent, no kernel, no
    simulator. `chain_valid` is threaded through from whoever loaded the file,
    because hashing is the Ledger's own business."""
    report = VerificationReport(entries=len(entries), chain_valid=chain_valid)

    certs = [e for e in entries if _kind(e) == "certificate"]
    report.certificates = len(certs)

    # The rule set every certificate should carry: the widest set any single
    # certificate evaluated. Taking the union rather than a hardcoded list
    # keeps the verifier independent of the kernel's current registry.
    expected: list[str] = []
    for c in certs:
        for r in _payload(c).get("rule_results", []):
            name = r.get("rule_name")
            if name and name not in expected:
                expected.append(name)
    report.rules_expected = expected

    for c in certs:
        p = _payload(c)
        case_id = p.get("case_id", "?")
        results = p.get("rule_results", [])
        names = {r.get("rule_name") for r in results}
        failed = [r.get("rule_name") for r in results if not r.get("passed")]
        decision = p.get("decision")

        # (2) the decision must follow from the evidence it carries
        should = DENY if failed else ALLOW
        if decision != should:
            report.violations.append(Violation(
                "decision", case_id,
                f"certificate {p.get('action_id')} records {decision} but its own rule "
                f"results say {should} — the decision does not follow from its evidence"
                + (f" (failed: {', '.join(str(f) for f in failed)})" if failed else ""),
            ))

        # (3) no rule may silently drop out
        missing = [n for n in expected if n not in names]
        if missing:
            report.violations.append(Violation(
                "coverage", case_id,
                f"certificate {p.get('action_id')} did not evaluate "
                f"{', '.join(missing)} — a rule that stops being evaluated looks "
                f"exactly like a rule that always passes",
            ))

    # (4) nothing reached a customer without an allowing certificate.
    #
    # One certificate per execution, consumed in order. A case is routinely
    # contacted several times, so it is not enough that SOME allow exists for
    # the pair — each execution must have its own, issued before it. Keeping
    # only the latest allow per (case, action) makes a correctly certified
    # third contact retrospectively certify the first, which is precisely the
    # hole an auditor is looking for.
    allowed: dict[tuple[str, str], list[int]] = {}
    for i, e in enumerate(entries):
        if _kind(e) != "certificate":
            continue
        p = _payload(e)
        if p.get("decision") == ALLOW:
            key = (p.get("case_id", "?"), p.get("action_type", ""))
            allowed.setdefault(key, []).append(i)

    for i, e in enumerate(entries):
        if _kind(e) != "action_result":
            continue
        p = _payload(e)
        action = p.get("action_type", "")
        if not p.get("executed") or action not in CONTACT_ACTIONS:
            continue
        report.executed_contacts += 1
        case_id = e.get("case_id") or p.get("case_id", "?")
        pool = allowed.get((case_id, action), [])
        match = next((j for j in pool if j < i), None)
        if match is None:
            report.violations.append(Violation(
                "uncertified", case_id,
                f"a {action} was executed without an allowing certificate before it",
            ))
        else:
            pool.remove(match)

    return report


def verify_file(path: str | Path) -> VerificationReport:
    """Load a ledger file and audit it, verifying the hash chain too."""
    raw = json.loads(Path(path).read_text())
    entries = raw["entries"] if isinstance(raw, dict) and "entries" in raw else raw

    chain: bool | None = None
    try:  # the chain is the Ledger's own arithmetic; reuse it when importable
        from recovery_ledger.ledger.ledger import Ledger

        chain = Ledger.from_entries(entries).verify_chain()
    except Exception:
        chain = None

    return verify_ledger(entries, chain_valid=chain)


def main(argv: Iterable[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("ledger", help="path to a ledger JSON file")
    args = ap.parse_args(list(argv) if argv is not None else None)

    report = verify_file(args.ledger)
    print(report.render())
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
