"""Fleet degradation detection latency — how fast N6's detector notices an
issuer going bad, and what false-alarm rate that speed is bought with (spec
section 8.4, novelty claim N6; PROJECT_STATE.md Tier B: "showing detection
latency against a known injected change-point would make it measurable
rather than demonstrated").

`make fleet` DEMONSTRATES the detector: it plants one outage and reports
`detection_correct: true`. That answers "does it fire", not "how fast", and
says nothing about how often it fires on nothing at all. This measures both,
against the exact detector shipped in `recovery_ledger/detector/fleet.py` —
`FleetDegradationDetector.detect()` is called unmodified, with its default
`recent_window`, `baseline_window`, `z_threshold` and `min_absolute_drop`.
Nothing about the detector changes here; only what it is fed does, and this
file must not be read as license to tune any of those constants to produce a
faster or cleaner-looking number.

METHOD. A synthetic issuer authorises at `pre_rate` (`HEALTHY_AUTH_RATE`,
0.90 — the same constant `sim/fleet_health.py` uses for a healthy issuer)
for `LEAD_IN_HOURS` of history — long enough that the detector's own 7-day
baseline window is already fully populated with healthy attempts before
anything is injected. At a known hour (the change-point), its authorisation
rate drops to one of several `POST_CHANGE_RATES` and stays there for the
rest of the run. Attempts continue to arrive at `ATTEMPTS_PER_HOUR` (25,
the same cadence `run_fleet.py` already uses — see its own comment on why
that number clears `MIN_RECENT_ATTEMPTS` comfortably), one hour's batch at a
time, and after each new hour the real, unmodified `detect()` is asked
whether this issuer is degraded. LATENCY is the number of post-change
attempts observed (hours elapsed x `ATTEMPTS_PER_HOUR`) at the first hour it
answers yes.

CONTROL draws never inject a change — the issuer stays healthy for the
whole window — and the identical polling procedure is run to see how often
the detector flags it anyway: a FALSE ALARM. `simulate_condition()` is the
single function both use; a control draw is just `post_rate == pre_rate`.

WHAT THE FALSE-ALARM FIGURE IS, AND IS NOT. It is a per-slice rate under
REPEATED testing: `detect()` is polled every hour for up to
`MAX_HOURS_CHECKED` hours, which is many independent looks at the same null
hypothesis, not the single pre/post check RESULTS.md's existing accuracy
table (0.968-1.000 precision over 60 independent outages) used. Repeated
polling is expected to inflate the true false-alarm probability relative to
a single check — that is not a flaw in this measurement, it is the actual
operating condition a fleet monitor runs under, and this reports that
number rather than the friendlier one-shot figure. It is also a single-slice
rate: production polls every issuer (and, per `detect()`'s default
dimensions, every method and region too), so the fleet-wide chance of at
least one false alarm somewhere is higher than the single-issuer number
reported here by roughly a union-bound factor of however many independent
slices are actually polled. Neither of those is corrected for here; both are
stated so the number is not read as more than it is.

THE CLAIM RULE (fixed before running; see `LATENCY_CLAIM_RULE` and
`latency_claim_verdict()` below, imported and exercised directly by
`tests/test_run_fleet_latency.py` with synthetic cases covering every
branch — not re-typed there):

    Latency is claimable only if it replicates: the median latency must be
    finite and the detector must fire in every draw at the largest effect
    size. If the detector misses the change-point in any draw at that
    size, report the miss rate rather than a latency. A latency figure is
    only meaningful alongside the false-alarm rate measured on no-change
    control runs, so both are reported together or neither is claimed.

Whatever this produces is published as-is. Effect sizes, seeds and draw
counts are fixed here, before running, and are not adjusted afterward to
produce a flattering number — if the detector is slow, or false-alarms
often under repeated polling, that is the finding, and it ships.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "tier2_simulation"))

from run_batch import SEED  # noqa: E402

from recovery_ledger.detector.fleet import (  # noqa: E402
    FleetDegradationDetector,
    PaymentAttempt,
)
from recovery_ledger.sim.fleet_health import HEALTHY_AUTH_RATE, OUTAGE_AUTH_RATE  # noqa: E402

HERE = Path(__file__).parent

LATENCY_CLAIM_RULE = (
    "Latency is claimable only if it replicates: the median latency must be "
    "finite and the detector must fire in every draw at the largest effect "
    "size. If the detector misses the change-point in any draw at that "
    "size, report the miss rate rather than a latency. A latency figure is "
    "only meaningful alongside the false-alarm rate measured on no-change "
    "control runs, so both are reported together or neither is claimed."
)

# Disjoint from every other experiment's evaluation-population offset; see
# tests/test_experiment_seeds.py's SEED_REGISTRY. 10000-13000 are already
# taken (uplift_ab, uplift_calibration, and run_regret's internal
# diagnostics/replication seeds) — this is the next free thousand.
EVAL_SEED = SEED + 14000

# A synthetic issuer, observed alone. `detect()`'s per-slice computation
# groups attempts by `getattr(a, dimension)` and compares each group only
# against itself — a slice's z-test and drop are unaffected by whether other
# issuers' attempts are present in `detector.attempts` at all. Simulating a
# single issuer therefore measures exactly the same per-slice statistic the
# five-issuer fleet in run_fleet.py would produce for this one issuer, at a
# fraction of the compute, and without needing four other issuers' health
# histories that don't change what this test is asking.
ISSUER = "LATENCY_TEST_ISSUER"
METHOD = "card"
REGION = "metro"

ATTEMPTS_PER_HOUR = 25
# > 7 days (the detector's own baseline_window), with an 8-hour margin so
# the baseline window is fully populated with pre-change attempts at the
# moment of the change-point, not straddling the start of history.
LEAD_IN_HOURS = 24 * 8
MAX_HOURS_CHECKED = 48
CHANGE_AT = datetime(2026, 1, 1, tzinfo=timezone.utc)

# Post-change success rates to sweep, smallest drop first. The last entry,
# OUTAGE_AUTH_RATE, is deliberately the exact magnitude run_fleet.py's own
# demonstrated outage uses — the "largest effect size" the claim rule above
# requires the detector to catch in every draw. The others are not tuned to
# make a curve look clean; they are round numbers spanning "just past the
# MIN_ABSOLUTE_DROP=0.15 gate" to "near-total outage".
POST_CHANGE_RATES = [0.70, 0.55, 0.40, OUTAGE_AUTH_RATE]

N_DRAWS_DEFAULT = 8
N_CONTROL_DRAWS_DEFAULT = 30


def simulate_condition(
    seed: int, post_rate: float, *, pre_rate: float = HEALTHY_AUTH_RATE,
    lead_in_hours: int = LEAD_IN_HOURS, max_hours: int = MAX_HOURS_CHECKED,
    attempts_per_hour: int = ATTEMPTS_PER_HOUR, change_at: datetime = CHANGE_AT,
) -> dict:
    """One independent draw. Builds `lead_in_hours` of history at `pre_rate`,
    then feeds the real `FleetDegradationDetector.detect()` one more hour of
    `post_rate` attempts at a time, stopping at the first hour it flags this
    issuer. `post_rate == pre_rate` is a no-change control run: any hour it
    fires there is a false alarm, not a detection.
    """
    rng = np.random.default_rng(seed)
    detector = FleetDegradationDetector()

    pre_attempts = []
    for h in range(lead_in_hours, 0, -1):
        at = change_at - timedelta(hours=h)
        for _ in range(attempts_per_hour):
            pre_attempts.append(PaymentAttempt(
                at=at, issuer=ISSUER, method=METHOD, region=REGION,
                succeeded=bool(rng.random() < pre_rate),
            ))
    detector.observe_many(pre_attempts)

    for hour_offset in range(1, max_hours + 1):
        at = change_at + timedelta(hours=hour_offset - 1)
        hour_attempts = [
            PaymentAttempt(
                at=at, issuer=ISSUER, method=METHOD, region=REGION,
                succeeded=bool(rng.random() < post_rate),
            )
            for _ in range(attempts_per_hour)
        ]
        detector.observe_many(hour_attempts)

        now = change_at + timedelta(hours=hour_offset)
        found = detector.detect(now, dimensions=("issuer",))
        if ISSUER in {d.slice_key for d in found}:
            return {
                "seed": seed, "detected": True,
                "latency_hours": hour_offset,
                "latency_attempts": hour_offset * attempts_per_hour,
            }

    return {"seed": seed, "detected": False, "latency_hours": None, "latency_attempts": None}


def sweep_effect_sizes(post_rates: list[float], *, n_draws: int, base_seed: int, **kwargs) -> list[dict]:
    """Run `n_draws` independent draws at each post-change rate. Each
    (effect size, draw) pair gets its own seed, offset far enough apart
    (x1000) that no draw count this experiment would plausibly use collides
    with the next effect size's block."""
    rows = []
    for i, post_rate in enumerate(post_rates):
        draws = [
            simulate_condition(base_seed + 1000 * i + d, post_rate, **kwargs)
            for d in range(n_draws)
        ]
        latencies = [d["latency_attempts"] for d in draws if d["detected"]]
        n_missed = sum(1 for d in draws if not d["detected"])
        rows.append({
            "post_rate": post_rate,
            "drop": round(HEALTHY_AUTH_RATE - post_rate, 4),
            "n_draws": n_draws,
            "n_detected": n_draws - n_missed,
            "n_missed": n_missed,
            "miss_rate": n_missed / n_draws,
            "median_latency_attempts": statistics.median(latencies) if latencies else None,
            "min_latency_attempts": min(latencies) if latencies else None,
            "max_latency_attempts": max(latencies) if latencies else None,
            "draws": draws,
        })
    return rows


def run_false_alarm_controls(*, n_draws: int, base_seed: int, pre_rate: float = HEALTHY_AUTH_RATE, **kwargs) -> dict:
    """No change is ever injected — `post_rate == pre_rate` throughout. Any
    draw where `simulate_condition` still reports `detected: True` fired on
    pure noise: a false alarm, under the same hourly-polling procedure the
    effect-size sweep above uses, so the two numbers are bought under
    identical conditions."""
    draws = [
        simulate_condition(base_seed + d, pre_rate, pre_rate=pre_rate, **kwargs)
        for d in range(n_draws)
    ]
    n_false_alarms = sum(1 for d in draws if d["detected"])
    return {
        "n_draws": n_draws,
        "n_false_alarms": n_false_alarms,
        "false_alarm_rate": n_false_alarms / n_draws,
        "draws": draws,
    }


def latency_claim_verdict(
    *, all_detected_at_largest_effect: bool, n_missed_at_largest_effect: int,
    n_draws_at_largest_effect: int, median_latency_at_largest_effect: float | None,
    false_alarm_rate: float | None,
) -> tuple[bool, str]:
    """Apply LATENCY_CLAIM_RULE (see the module docstring). Four branches,
    checked in this order — a miss at the largest effect size is reported
    before anything else is even considered, because the rule's own wording
    ("report the miss rate rather than a latency") makes that the dominant
    failure mode, not one candidate among equals:

    1. the detector missed the change-point in at least one draw at the
       largest effect size swept -> NOT CLAIMABLE, report the miss rate.
    2. no false-alarm rate was measured at all -> NOT CLAIMABLE; a latency
       is only meaningful alongside one.
    3. the median latency at the largest effect size is not a finite number
       (e.g. no draw detected, despite (1) passing — a defensive branch,
       not one this experiment's own sweep should ever reach) -> NOT
       CLAIMABLE.
    4. otherwise -> CLAIMABLE.
    """
    if not all_detected_at_largest_effect:
        return False, (
            f"NOT CLAIMABLE: the detector missed the change-point in "
            f"{n_missed_at_largest_effect} of {n_draws_at_largest_effect} "
            f"draws at the largest effect size swept. Per LATENCY_CLAIM_RULE, "
            f"a miss at the largest effect size means latency is not "
            f"claimable here — the miss rate is reported instead."
        )
    if false_alarm_rate is None:
        return False, (
            "NOT CLAIMABLE: no false-alarm rate was measured on no-change "
            "control runs. Per LATENCY_CLAIM_RULE, a latency figure is only "
            "meaningful alongside a false-alarm rate — neither is claimed "
            "without the other."
        )
    if median_latency_at_largest_effect is None or not math.isfinite(median_latency_at_largest_effect):
        return False, (
            "NOT CLAIMABLE: the median latency at the largest effect size is "
            "not a finite number."
        )
    return True, (
        f"CLAIMABLE: the detector fired in all {n_draws_at_largest_effect} "
        f"draws at the largest effect size swept (median latency "
        f"{median_latency_at_largest_effect:.0f} attempts), reported "
        f"alongside a false-alarm rate of {false_alarm_rate * 100:.1f}% "
        f"measured on no-change control runs under the same polling "
        f"procedure."
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--draws", type=int, default=N_DRAWS_DEFAULT,
                     help="independent draws per effect size (>= 5)")
    ap.add_argument("--control-draws", type=int, default=N_CONTROL_DRAWS_DEFAULT,
                     help="independent no-change control draws")
    ap.add_argument("--max-hours", type=int, default=MAX_HOURS_CHECKED)
    ap.add_argument("--attempts-per-hour", type=int, default=ATTEMPTS_PER_HOUR)
    ap.add_argument("--lead-in-hours", type=int, default=LEAD_IN_HOURS)
    args = ap.parse_args()

    assert args.draws >= 5, "the replication rule this project uses everywhere else needs at least 5 draws"

    kwargs = dict(
        max_hours=args.max_hours, attempts_per_hour=args.attempts_per_hour,
        lead_in_hours=args.lead_in_hours,
    )

    print(f"Sweeping {len(POST_CHANGE_RATES)} effect sizes x {args.draws} draws "
          f"(healthy rate {HEALTHY_AUTH_RATE:.2f}, {args.attempts_per_hour} "
          f"attempts/hour, polled hourly for up to {args.max_hours}h)...")
    effect_sizes = sweep_effect_sizes(
        POST_CHANGE_RATES, n_draws=args.draws, base_seed=EVAL_SEED, **kwargs
    )

    print(f"\n{'post rate':>10}{'drop':>7}{'detected':>10}{'miss rate':>11}"
          f"{'median lat.':>13}{'min':>7}{'max':>7}")
    for r in effect_sizes:
        med = f"{r['median_latency_attempts']:.0f}" if r["median_latency_attempts"] is not None else "n/a"
        mn = str(r["min_latency_attempts"]) if r["min_latency_attempts"] is not None else "n/a"
        mx = str(r["max_latency_attempts"]) if r["max_latency_attempts"] is not None else "n/a"
        print(f"{r['post_rate']:>10.2f}{r['drop']:>7.2f}{r['n_detected']:>6d}/{r['n_draws']:<3d}"
              f"{r['miss_rate']:>10.1%} {med:>12} {mn:>6} {mx:>6}")

    print(f"\nRunning {args.control_draws} no-change false-alarm control draws...")
    false_alarm = run_false_alarm_controls(
        n_draws=args.control_draws, base_seed=EVAL_SEED + 500, **kwargs
    )
    print(f"  false alarms: {false_alarm['n_false_alarms']} of {false_alarm['n_draws']} "
          f"({false_alarm['false_alarm_rate']:.1%})")

    largest_effect = min(effect_sizes, key=lambda r: r["post_rate"])
    claimable, verdict = latency_claim_verdict(
        all_detected_at_largest_effect=largest_effect["n_missed"] == 0,
        n_missed_at_largest_effect=largest_effect["n_missed"],
        n_draws_at_largest_effect=largest_effect["n_draws"],
        median_latency_at_largest_effect=largest_effect["median_latency_attempts"],
        false_alarm_rate=false_alarm["false_alarm_rate"],
    )
    print(f"\nrule: {LATENCY_CLAIM_RULE}")
    print(f"\nverdict: {verdict}")

    out = {
        "healthy_auth_rate": HEALTHY_AUTH_RATE,
        "outage_auth_rate": OUTAGE_AUTH_RATE,
        "attempts_per_hour": args.attempts_per_hour,
        "lead_in_hours": args.lead_in_hours,
        "max_hours_checked": args.max_hours,
        "n_draws": args.draws,
        "n_control_draws": args.control_draws,
        "effect_sizes": effect_sizes,
        "false_alarm": false_alarm,
        "largest_effect_post_rate": largest_effect["post_rate"],
        "claim_rule": LATENCY_CLAIM_RULE,
        "claimable": claimable,
        "verdict": verdict,
    }
    (HERE / "results_fleet_latency.json").write_text(json.dumps(out, indent=2))
    print(f"\nWrote {HERE / 'results_fleet_latency.json'}")


if __name__ == "__main__":
    main()
