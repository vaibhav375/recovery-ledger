"""The live console must not quietly report a different model from the results.

The console displays `corr(tau_hat, tau_true)` next to decisions the model is
driving, which makes that number a claim. It was briefly wrong in two ways at
once: fitted on 3,000 cases instead of the 5,000 the published run uses, and
measured on the *training* cases rather than held out — a train-set
correlation flatters the model, so the console was not merely showing a
smaller number, it was showing a different and more generous quantity.

These tests pin the console to the published pipeline: same training size,
same disjoint evaluation seed, same figure.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from recovery_ledger.live.session import (
    DEFAULT_SEED,
    EVAL_N,
    EVAL_SEED,
    TRAIN_N,
    get_models,
    new_session,
    run_session,
)

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "experiments" / "tier2_simulation" / "results.json"
MAKEFILE = ROOT / "Makefile"


def _make_eval_args() -> dict[str, int]:
    """The --n-train / --n-eval `make eval` actually passes."""
    text = MAKEFILE.read_text()
    block = text[text.index("\neval:"):]
    block = block[: block.index("\n\n")]
    return {
        "n_train": int(re.search(r"--n-train\s+(\d+)", block).group(1)),
        "n_eval": int(re.search(r"--n-eval\s+(\d+)", block).group(1)),
    }


def test_console_trains_on_the_same_size_as_the_published_run():
    args = _make_eval_args()
    assert TRAIN_N == args["n_train"], (
        f"the console fits on {TRAIN_N} cases but `make eval` publishes results "
        f"from {args['n_train']} — the console would be demonstrating a "
        f"different model from the one RESULTS.md describes"
    )
    assert EVAL_N == args["n_eval"]


def test_evaluation_seed_is_disjoint_from_the_training_seed():
    """Cases the agent is shown working must not come from the distribution it
    was fitted on."""
    assert EVAL_SEED != DEFAULT_SEED


@pytest.mark.skipif(not RESULTS.exists(), reason="run `make eval` first")
def test_reported_correlation_equals_the_published_figure():
    published = json.loads(RESULTS.read_text())[
        "uplift_model_correlation_with_true_persuadability"
    ]
    live = get_models().uplift_correlation
    assert live == pytest.approx(published, abs=1e-9), (
        f"the console reports corr = {live:.4f} but results.json publishes "
        f"{published:.4f}. One of them is describing a model the other is not."
    )


def test_correlation_is_measured_held_out_not_on_the_training_cases():
    """A train-set correlation is optimistically biased. If this ever starts
    measuring on the fitted data it will read noticeably higher, and the number
    on screen will be flattering the model that is making the decisions."""
    import numpy as np

    from recovery_ledger.live.session import NOW
    from recovery_ledger.policy.features import cases_to_feature_matrix
    from recovery_ledger.sim.environment import generate_population, persuadability
    from recovery_ledger.sim.generator import generate_cases

    models = get_models()
    train_cases = generate_cases(TRAIN_N, seed=DEFAULT_SEED, now=NOW)
    train_traits = generate_population(train_cases, seed=DEFAULT_SEED)
    X = cases_to_feature_matrix(train_cases)
    in_sample = float(np.corrcoef(
        models.uplift.predict_cate(X),
        np.array([persuadability(train_traits[c.case_id]) for c in train_cases]),
    )[0, 1])

    assert models.uplift_correlation != pytest.approx(in_sample, abs=1e-9), (
        "the reported correlation matches the in-sample one exactly, which "
        "means it is being measured on the training cases"
    )


# ── the run itself ───────────────────────────────────────────────────────

def test_a_run_terminates_and_its_chain_verifies():
    session = new_session(seed=EVAL_SEED, n_cases=8)
    run_session(session)
    assert session.error is None
    assert session.summary is not None
    assert session.summary["chain"]["ok"] is True
    assert session.summary["cases"] == 8
    assert sum(session.summary["stop_reasons"].values()) >= 1


def test_pacing_does_not_contaminate_the_reported_agent_time():
    """The throttle exists so a human can read the loop. If it leaked into
    `agent_ms` the console would be reporting the agent as ~10x slower than it
    is, in a place viewers read as a performance claim."""
    paced = new_session(seed=EVAL_SEED, n_cases=4, pace_ms=25)
    run_session(paced)
    assert paced.summary["paced_ms"] > 0
    assert paced.summary["wall_ms"] > paced.summary["agent_ms"]
    # Agent time should be small and roughly independent of the throttle.
    assert paced.summary["agent_ms"] < paced.summary["paced_ms"]


def test_the_kill_switch_stops_a_run_and_says_so_in_the_ledger():
    """Stopping rule 11, through the live path: engaging the switch must
    terminate the remaining cases *and* leave that reason in the trail."""
    session = new_session(seed=EVAL_SEED, n_cases=25)
    session.kill.engage()
    run_session(session)
    assert session.summary["killed"] is True
    assert session.summary["stop_reasons"].get("global_kill_switch", 0) > 0
    reasons = [
        e.payload.get("reason")
        for e in session.ledger._entries
        if e.entry_type == "stop"
    ]
    assert "global_kill_switch" in reasons
    assert session.summary["chain"]["ok"] is True


def test_the_roster_reports_the_model_estimate_the_policy_will_act_on():
    session = new_session(seed=EVAL_SEED, n_cases=5)
    run_session(session)
    started = next(e for e in session._events if e["type"] == "run_started")
    assert len(started["roster"]) == 5
    assert all("tau_hat" in c for c in started["roster"])
    assert started["uplift_correlation"] == pytest.approx(
        get_models().uplift_correlation, abs=1e-3
    )


def test_the_kill_switch_stops_the_run_without_sleeping_through_the_rest_of_the_fleet():
    """Engaging the kill switch must stop the run promptly.

    The throttle exists so a human can read the loop and reach the kill switch.
    It is applied per *ledger entry*, and a case stopped by the kill switch
    still writes two entries — `case_ingested` and `stop` — so before this was
    fixed, killing a paced run cost `2 x remaining_cases x pace_ms` in pure
    `time.sleep()` after the operator had already pressed stop. Measured on a
    120-case run at 150 ms: the kill landed at 3.0 s and the run took a further
    37.3 s, of which 36.0 s was sleeping.

    The audit record is deliberately kept — every case still gets its
    kill-switch stop entry, because B4's claim is that the ledger accounts for
    every case the agent saw. What is dropped is the pacing, whose only purpose
    (letting a human intervene) is already served once they have intervened.
    """
    import threading
    import time

    from recovery_ledger.live.session import new_session, run_session

    session = new_session(seed=7, n_cases=40, pace_ms=150)

    def engage() -> None:
        time.sleep(0.4)
        session.kill.engage()

    threading.Thread(target=engage, daemon=True).start()
    started = time.perf_counter()
    run_session(session)
    elapsed = time.perf_counter() - started

    killed = [
        e for e in session.ledger._entries
        if e.entry_type == "stop" and e.payload.get("reason") == "global_kill_switch"
    ]
    assert killed, "the kill switch never fired; the test proves nothing"

    # Unpaced, the post-kill work is a few milliseconds. Paced per entry it was
    # 2 x 40 x 150 ms = 12 s. Anything near that means the fix regressed.
    assert elapsed < 5.0, (
        f"run took {elapsed:.1f}s after a kill at 0.4s — the throttle is still "
        f"sleeping through {len(killed)} killed cases"
    )

    # The audit record must survive the speed-up.
    assert session.summary["killed"] is True
    assert session.ledger.verify_chain()
