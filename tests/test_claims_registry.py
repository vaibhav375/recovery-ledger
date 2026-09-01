"""Pre-registration as a mechanism instead of a habit.

This project fixes a rule before a run and reports the outcome whichever way it
falls. That discipline has been kept by hand, in eight different experiment
scripts, and the only thing stopping a future run from quietly reporting the
flattering half is somebody remembering. A habit nobody can check is a claim
about the author, not about the work.

The registry makes it checkable. Every pre-registered claim is declared once,
with the artifact field its verdict is read from, and three tests hold the line:

  - every registered claim resolves against a real artifact field, so the
    registry cannot drift into fiction;
  - every artifact carrying a pre-registered rule is registered, so a new
    experiment cannot slip a rule past the registry by not mentioning it;
  - a claim the evidence REFUTED or left UNRESOLVED may not be asserted as
    established in the published documents.

The last one is the point. It is the test that would have caught this project's
own worst near-miss - "strictly dominates" published from a run that no longer
reproduced - and it is the one that cannot be satisfied by good intentions.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from recovery_ledger.claims import REGISTRY, Status, load_claims

ROOT = Path(__file__).resolve().parents[1]


def test_every_registered_claim_resolves_against_its_artifact():
    unresolved = [c.id for c in load_claims(ROOT) if c.status is Status.MISSING]
    assert not unresolved, (
        "these claims name an artifact field that does not exist:\n  "
        + "\n  ".join(unresolved)
    )


def test_every_artifact_carrying_a_preregistered_rule_is_registered():
    """The coverage direction. A new experiment that fixes a rule before its
    run must declare it here, or the registry silently stops describing the
    project."""
    registered = {str(ROOT / c.artifact) for c in REGISTRY}
    carrying: list[str] = []
    for path in sorted(ROOT.glob("experiments/*/results*.json")):
        try:
            blob = json.loads(path.read_text())
        except Exception:
            continue
        if not isinstance(blob, dict):
            continue
        if re.search(r'"[a-z_]*rule"\s*:\s*"', json.dumps(blob)):
            carrying.append(str(path))
    missing = [p for p in carrying if p not in registered]
    assert not missing, (
        "these artifacts carry a pre-registered rule but no registry entry:\n  "
        + "\n  ".join(Path(m).relative_to(ROOT).as_posix() for m in missing)
    )


def _asserted(phrase: str, docs: str) -> bool:
    """Is the phrase used as an assertion, rather than quoted in a retraction?

    This repo publishes its own retractions, and the honest way to retract is
    to quote what was wrongly said: `an earlier version said it "strictly
    dominates", on the strength of a run this repo no longer reproduces`. A
    check that forbade the quoted form would push the project to delete its
    mistakes rather than record them, which is the opposite of the point. So a
    refuted claim may be QUOTED but not ASSERTED.

    Quotation is judged by the span the phrase sits in, not by delimiters
    hugging it exactly — `lambda_churn = 4.0 strictly dominates 2.0` is a code
    span containing the phrase and is just as much a quotation as
    "strictly dominates" is. Bold is deliberately NOT an exemption: emphasis is
    assertion, not quotation.
    """
    stripped = docs
    for pattern in (
        r"`[^`\n]*`",          # code spans
        r'"[^"\n]*"',          # straight double quotes
        r"'[^'\n]*'",          # straight single quotes
        r"\u201c[^\u201d\n]*\u201d",  # curly double quotes
    ):
        stripped = re.sub(pattern, " ", stripped)
    return phrase in stripped


def test_a_refuted_or_unresolved_claim_is_not_asserted_as_established():
    """The mechanism. A claim the evidence did not support must not appear in
    the documents dressed as one that did — though it may be quoted while
    being retracted."""
    docs = "\n".join(
        (ROOT / name).read_text()
        for name in ("RESULTS.md", "README.md", "PROJECT_STATE.md")
        if (ROOT / name).exists()
    )
    offenders = []
    for c in load_claims(ROOT):
        if c.status in (Status.HELD, Status.MISSING) or not c.forbidden_when_not_held:
            continue
        for phrase in c.forbidden_when_not_held:
            if _asserted(phrase, docs):
                offenders.append(f"{c.id} is {c.status.value} but the docs say {phrase!r}")
    assert not offenders, "\n  ".join(["claims asserted beyond their evidence:"] + offenders)


def test_the_registry_is_not_all_good_news():
    """A registry in which everything held would be evidence of selection, not
    of rigour. This project has published a refutation and an unresolved
    result; if that ever stops being true, look hard at why."""
    statuses = {c.status for c in load_claims(ROOT)}
    assert Status.HELD in statuses
    assert statuses & {Status.REFUTED, Status.UNRESOLVED}, (
        "every registered claim held — check whether an inconvenient one was "
        "quietly dropped from the registry"
    )


@pytest.mark.parametrize("claim", REGISTRY, ids=lambda c: c.id)
def test_each_claim_declares_where_its_verdict_comes_from(claim):
    assert claim.statement.strip()
    assert claim.artifact.strip()
    assert claim.verdict_path.strip()
    assert (ROOT / claim.artifact).exists(), f"{claim.artifact} does not exist"


@pytest.mark.parametrize("word", ["UNRESOLVED", "UNDETERMINED", "INCONCLUSIVE"])
def test_every_word_for_an_open_question_resolves_to_unresolved(word):
    """This repo says "the evidence did not settle it" three different ways
    across its experiments. Recognising only two of them was a silent bug: the
    recalibration result reads UNDETERMINED and the registry published it as
    REFUTED — a question left open reported as a question answered no."""
    from recovery_ledger.claims import Claim, Status

    c = Claim(id="probe", statement="s", artifact="a", verdict_path="v",
              held_values=("CLAIMABLE",))
    assert c.resolved(f"{word}: because reasons", missing=False).status is Status.UNRESOLVED


def test_a_genuinely_negative_verdict_still_reads_refuted():
    """The guard above must not turn every string into UNRESOLVED."""
    from recovery_ledger.claims import Claim, Status

    c = Claim(id="probe", statement="s", artifact="a", verdict_path="v",
              held_values=("CLAIMABLE",))
    assert c.resolved("REFUTED: it does not hold", missing=False).status is Status.REFUTED
