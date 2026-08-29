"""The documents must name the policy the code actually runs.

This is not hypothetical. `experiments/horizon/REPORT.md` concluded that at the
calibrated parameters "greedy is within noise of optimal there, and that is why
the shipped policy is greedy". The measurement behind it was sound. The sentence
was false: `LookaheadEVDecisionPolicy` is what `run_batch.py` instantiates, what
the live console runs, and what the baselines table labels deployed.

That failure mode is invisible to every other test in this repo. The doc-vs-
artifact tests compare numbers to numbers, and the numbers were all correct —
what drifted was a claim about which component the numbers came from. A reader
who trusted it would have been told the system works in a way it does not.

So this pins the wiring to the prose: whatever class the batch runner and the
live session construct is the one the documents may call deployed.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUN_BATCH = ROOT / "experiments" / "tier2_simulation" / "run_batch.py"
LIVE_SESSION = ROOT / "src" / "recovery_ledger" / "live" / "session.py"
BASELINES = ROOT / "experiments" / "tier2_simulation" / "results_baselines.json"

POLICIES = ("LookaheadEVDecisionPolicy", "EVDecisionPolicy")


def _constructed(path: Path) -> str:
    """The policy class handed to the agent in this file."""
    source = path.read_text()
    m = re.search(r"policy=(\w+)\(", source)
    assert m, f"no policy= construction found in {path.name}"
    assert m.group(1) in POLICIES, f"unexpected policy {m.group(1)} in {path.name}"
    return m.group(1)


def test_batch_runner_and_live_console_run_the_same_policy():
    """If these ever diverge, 'the deployed policy' stops having one referent
    and every claim using the phrase becomes ambiguous."""
    batch, live = _constructed(RUN_BATCH), _constructed(LIVE_SESSION)
    assert batch == live, (
        f"run_batch runs {batch} but the live console runs {live}; the docs "
        "cannot correctly call either one 'deployed'"
    )


def test_no_document_claims_a_policy_ships_that_does_not():
    deployed = _constructed(RUN_BATCH)
    other = "EVDecisionPolicy" if deployed == "LookaheadEVDecisionPolicy" else "LookaheadEVDecisionPolicy"
    label = "greedy" if other == "EVDecisionPolicy" else "lookahead"

    forbidden = [
        f"the shipped policy is {label}",
        f"so {label} ships",
        f"we ship {label}",
        f"that is why the shipped policy is {label}",
    ]
    for doc in ("RESULTS.md", "README.md", "PROJECT_STATE.md",
                "experiments/horizon/REPORT.md"):
        path = ROOT / doc
        if not path.exists():
            continue
        text = path.read_text().lower()
        for phrase in forbidden:
            assert phrase not in text, (
                f"{doc} says '{phrase}' but {deployed} is what actually runs"
            )


def test_the_baselines_row_called_deployed_is_the_one_that_runs():
    """The doc tests read `ev_policy_lookahead` as the deployed row. That
    mapping is an assumption, and this is where it is checked."""
    if not BASELINES.exists():
        pytest.skip("baselines artifact not generated")
    deployed = _constructed(RUN_BATCH)
    expected_row = ("ev_policy_lookahead" if deployed == "LookaheadEVDecisionPolicy"
                    else "ev_policy_greedy")
    policies = {p["policy"] for p in json.loads(BASELINES.read_text())["policies"]}
    assert expected_row in policies, (
        f"{deployed} ships but the baselines table has no {expected_row} row"
    )
    doc_test = (ROOT / "tests" / "test_results_doc_matches_artifacts.py").read_text()
    assert f'pol["{expected_row}"]' in doc_test, (
        f"the headline doc test does not treat {expected_row} as deployed, "
        f"but {deployed} is what runs"
    )
