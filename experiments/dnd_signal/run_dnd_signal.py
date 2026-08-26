"""How much more do do-not-disturbs opt out when you contact them?

This number is load-bearing. Novelty claim N2 argues that churn risk is a
signal *independent* of predicted payment uplift, so that avoiding a
do-not-disturb no longer rests on one model being right. The evidence offered
for that was a single ratio: true do-not-disturbs opt out some multiple more
often than everyone else when contacted.

It was reported as **1.93x**, measured once at n = 5,000 — the training batch
size, which is where the measurement happened to be sitting. That is far too
small for the quantity. Opt-out on first contact is a ~1.4% event, so a
5,000-case draw yields roughly 20 events in the do-not-disturb arm, and the
ratio of two small counts is extremely unstable. Across five seeds at that
size it ranges 0.72x to 1.74x — a spread wider than the effect itself, and one
draw of it lands *below* 1.0, i.e. pointing the wrong way entirely.

This measures it at a sample size where it converges, over several seeds, with
a bootstrap interval, and reports the sample-size dependence so the original
figure's instability is visible rather than merely corrected.

The claim survives in direction and not in magnitude, which is the honest
outcome and the one reported.

Mechanically the effect is real and traceable in the simulator:

    persuadability  = 0.12 + 0.30*liquidity - 0.45*dispute + 0.20*(annoyance - 0.5)
    P(opt out)      = opt_out_per_contact * (1 + overcontacted) * (1.5 - annoyance)

Persuadability rises with the annoyance threshold and opt-out probability
falls with it, so customers with negative persuadability do carry a genuinely
elevated opt-out hazard. It is simply a smaller elevation than was claimed.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from recovery_ledger.events.actions import ActionType
from recovery_ledger.listener.listener import ReplyIntent
from recovery_ledger.sim.environment import (
    SimulationEnvironment,
    generate_population,
    persuadability,
)
from recovery_ledger.sim.generator import generate_cases

HERE = Path(__file__).parent
NOW = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)
SEED = 20260823
EVAL_SEED = SEED + 8000  # disjoint; see tests/test_experiment_seeds.py


def observe(n: int, seed: int, *, contact: bool) -> tuple[np.ndarray, np.ndarray]:
    """Opt-out indicator and do-not-disturb mask for one population."""
    cases = generate_cases(n, seed=seed, now=NOW)
    traits = generate_population(cases, seed=seed)
    dnd = np.array([persuadability(traits[c.case_id]) < 0 for c in cases])
    env = SimulationEnvironment(traits, seed=seed)
    action = ActionType.NUDGE if contact else ActionType.WAIT
    opted = np.array([
        float(env.step(c, action, 0).reply == ReplyIntent.OPT_OUT) for c in cases
    ])
    return opted, dnd


def _ratio(opted: np.ndarray, dnd: np.ndarray) -> float | None:
    base = opted[~dnd].mean()
    return float(opted[dnd].mean() / base) if base > 0 else None


def bootstrap_ci(opted, dnd, *, n_boot: int, seed: int) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(n_boot):
        i = rng.integers(0, len(opted), len(opted))
        r = _ratio(opted[i], dnd[i])
        if r is not None:
            draws.append(r)
    lo, hi = np.quantile(draws, [0.025, 0.975])
    return float(lo), float(hi)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sizes", type=int, nargs="+", default=[5000, 20000, 60000])
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--headline-n", type=int, default=60000)
    ap.add_argument("--n-boot", type=int, default=2000)
    args = ap.parse_args()

    print("Ratio of opt-out rates, do-not-disturbs vs everyone else, on first contact.\n")
    print(f"{'n':>8}  {'ratios across seeds':<44}{'spread':>8}")
    stability = []
    for n in args.sizes:
        rs = []
        for s in range(args.seeds):
            opted, dnd = observe(n, EVAL_SEED + s * 997, contact=True)
            r = _ratio(opted, dnd)
            if r is not None:
                rs.append(round(r, 3))
        spread = max(rs) - min(rs)
        stability.append({"n": n, "ratios": rs, "spread": round(spread, 3)})
        print(f"{n:>8}  {str([f'{r:.2f}' for r in rs]):<44}{spread:>8.2f}")

    opted, dnd = observe(args.headline_n, EVAL_SEED, contact=True)
    ratio = _ratio(opted, dnd)
    lo, hi = bootstrap_ci(opted, dnd, n_boot=args.n_boot, seed=SEED)

    # The paragraph that reported 1.93x also claimed opt-out is zero without
    # contact, which is what makes the effect cleanly attributable to contact.
    # Checked rather than assumed.
    not_contacted, _ = observe(args.headline_n, EVAL_SEED, contact=False)

    print(f"\nAt n = {args.headline_n:,}:")
    print(f"  do-not-disturbs   {opted[dnd].mean():.4f}   ({int(opted[dnd].sum())} opt-outs of {int(dnd.sum())})")
    print(f"  everyone else     {opted[~dnd].mean():.4f}   ({int(opted[~dnd].sum())} of {int((~dnd).sum())})")
    print(f"  ratio             {ratio:.2f}x   95% CI [{lo:.2f}, {hi:.2f}]")
    print(f"  opt-out with no contact: {not_contacted.mean():.4f}")
    print(f"\n  effect is real: {'yes' if lo > 1.0 else 'NO — the interval includes 1.0'}")
    print(f"  previously reported 1.93x is {'inside' if lo <= 1.93 <= hi else 'OUTSIDE'} this interval")

    out = {
        "headline_n": args.headline_n,
        "seed": EVAL_SEED,
        "ratio": round(ratio, 4),
        "ci_low": round(lo, 4),
        "ci_high": round(hi, 4),
        "opt_out_rate_do_not_disturbs": round(float(opted[dnd].mean()), 5),
        "opt_out_rate_others": round(float(opted[~dnd].mean()), 5),
        "opt_out_rate_without_contact": round(float(not_contacted.mean()), 5),
        "n_do_not_disturbs": int(dnd.sum()),
        "effect_excludes_one": bool(lo > 1.0),
        "previously_reported": 1.93,
        "previously_reported_inside_ci": bool(lo <= 1.93 <= hi),
        "stability_by_sample_size": stability,
    }
    (HERE / "results_dnd_signal.json").write_text(json.dumps(out, indent=2))
    print(f"\nWrote {HERE / 'results_dnd_signal.json'}")


if __name__ == "__main__":
    main()
