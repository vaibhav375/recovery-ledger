"""Sensitivity sweep (spec section 7.3).

"Sweep the response-function parameters across a defensible range and show
the policy ranking is stable. Stability of ranking under assumption sweeps
is the honest claim, not a point estimate."

That sentence is the whole reason this file exists. Every constant in
`sim/environment.py` is invented. A single incremental-rupee figure computed
at one arbitrary setting of those constants is worth very little; what can
honestly be claimed is that the *ordering* of policies survives across the
range of settings a reasonable person might have chosen instead.

Two claims are tested at every setting:

- **C1 — targeting beats random at comparable volume.** The EV policy
  recovers more incremental revenue than `random_targeting`. This is the
  claim that says the uplift model is doing real work, so it is the one
  that most needs to survive.
- **C2 — targeting is more contact-efficient than blind mass-contact.** The
  EV policy earns more incremental rupees per contact than
  `blast_everyone`.

Where a claim flips, the sweep says so rather than reporting an average.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "tier2_simulation"))

from run_baselines import run_one_policy  # noqa: E402
from run_batch import NOW, SEED  # noqa: E402

from recovery_ledger.events.actions import ActionType  # noqa: E402
from recovery_ledger.policy.decision import (  # noqa: E402
    BlastEveryonePolicy,
    DoNothingPolicy,
    EVDecisionPolicy,
    RandomTargetingPolicy,
)
from recovery_ledger.policy.features import cases_to_feature_matrix  # noqa: E402
from recovery_ledger.policy.uplift.learners import TLearnerModel  # noqa: E402
from recovery_ledger.sim.environment import (  # noqa: E402
    DEFAULT_PARAMS,
    ResponseParams,
    SimulationEnvironment,
    generate_population,
)
from recovery_ledger.sim.generator import generate_cases  # noqa: E402

HERE = Path(__file__).parent

# Defensible ranges. Each is a span a reasonable person could have picked
# instead of the default, not an arbitrary +/- on the chosen value.
SWEEPS: dict[str, tuple[str, list[float]]] = {
    "base_organic_resolution": (
        "How often a case resolves with no intervention. Sets the holdout's "
        "recovery and therefore how much room any agent has to add value.",
        [0.02, 0.035, 0.05, 0.08, 0.12],
    ),
    "annoyance_decay_per_excess_contact": (
        "How fast repeated contact erodes willingness to pay. Load-bearing: "
        "near-independence of contacts is what made blind persistence "
        "competitive in the baseline comparison.",
        [0.0, 0.025, 0.05, 0.10, 0.20],
    ),
    "retry_success_generic": (
        "Automated retry success rate; spec 3.2 cites 15-20% for the "
        "industry, so the range spans well outside that.",
        [0.05, 0.11, 0.17, 0.25, 0.35],
    ),
    "amount_liquidity_coupling": (
        "Strength of the amount <-> liquidity relationship that drives the "
        "do-not-disturb tension. Zero means amount says nothing about "
        "persuadability.",
        [0.0, 0.125, 0.25, 0.40, 0.55],
    ),
    "opt_out_per_contact": (
        "Per-contact opt-out hazard. Higher values punish over-contacting "
        "harder and should favour selective policies.",
        [0.005, 0.01, 0.015, 0.03, 0.06],
    ),
}


# SEED + 6000, not + 2000: run_baselines.py already uses + 2000, and these two
# experiments only avoided evaluating on an identical population because they
# happen to pass different --n-eval (generate_cases is batch-size dependent).
# Correctness resting on an incidental argument value is the same fragility
# that has bitten this repo twice. Offsets are now pairwise distinct by
# construction, pinned by tests/test_experiment_seeds.py.
BASE_EVAL_SEED = SEED + 6000


def evaluate_setting(params: ResponseParams, *, n_train: int, n_eval: int,
                     eval_seed: int = BASE_EVAL_SEED) -> dict:
    """Train on this simulator, then compare policies on a disjoint batch.

    The uplift model is retrained for every setting. Reusing a model fitted
    against different physics would measure staleness, not sensitivity.
    """
    train_cases = generate_cases(n_train, seed=SEED, now=NOW)
    train_traits = generate_population(train_cases, seed=SEED, params=params)
    env = SimulationEnvironment(train_traits, seed=SEED, params=params)
    rng = np.random.default_rng(SEED)
    treatment = rng.integers(0, 2, size=n_train)
    outcomes = np.array([
        float(env.step(c, ActionType.NUDGE if treatment[i] == 1 else ActionType.WAIT, 0).paid)
        for i, c in enumerate(train_cases)
    ])
    model = TLearnerModel(random_state=SEED)
    model.fit(cases_to_feature_matrix(train_cases), treatment, outcomes)

    # SEED + 6000, not + 2000: run_baselines.py already uses + 2000, and these
    # two experiments only avoided evaluating on an identical population
    # because they happen to pass different --n-eval (generate_cases is
    # batch-size dependent). Correctness resting on an incidental argument
    # value is the same fragility that has bitten this repo twice. The offsets
    # are now pairwise distinct by construction, pinned by
    # tests/test_experiment_seeds.py.
    cases = generate_cases(n_eval, seed=eval_seed, now=NOW)
    traits = generate_population(cases, seed=eval_seed, params=params)

    policies = {
        "do_nothing": DoNothingPolicy(),
        "blast_everyone": BlastEveryonePolicy(),
        "random_targeting": RandomTargetingPolicy(contact_rate=0.45, seed=7),
        "ev_policy": EVDecisionPolicy(uplift_model=model),
    }
    runs = {
        name: run_one_policy(name, pol, cases, traits, seed=eval_seed + 1, params=params)
        for name, pol in policies.items()
    }

    baseline = runs["do_nothing"]["gross_recovered"]
    out = {}
    for name, r in runs.items():
        incremental = r["gross_recovered"] - baseline
        out[name] = {
            "incremental": incremental,
            "contacts": r["contacts_sent"],
            "incremental_per_contact": incremental / r["contacts_sent"] if r["contacts_sent"] else None,
            "dnd_rate": r["pct_contacts_to_do_not_disturbs"],
        }

    ev, rand, blast = out["ev_policy"], out["random_targeting"], out["blast_everyone"]
    return {
        "policies": out,
        # C1: does targeting beat random?
        "c1_ev_beats_random": ev["incremental"] > rand["incremental"],
        "c1_margin_ratio": (ev["incremental"] / rand["incremental"]) if rand["incremental"] > 0 else None,
        # C2: is targeting more contact-efficient than mass-contact?
        "c2_ev_more_efficient_than_blast": (
            (ev["incremental_per_contact"] or 0) > (blast["incremental_per_contact"] or 0)
        ),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n-train", type=int, default=3000)
    ap.add_argument("--n-eval", type=int, default=1500)
    ap.add_argument(
        "--eval-draws", type=int, default=3,
        help="independent evaluation populations to repeat the whole sweep over",
    )
    args = ap.parse_args()

    # One draw is not a robustness result. Moving this experiment's evaluation
    # seed off a collision with run_baselines.py changed C2 from 24/25 to
    # 25/25 — same code, same settings, different customers. A claim that
    # flips on the evaluation draw is a claim about that draw, so the sweep is
    # now repeated over several and the spread is what gets reported.
    draws = [BASE_EVAL_SEED + 100 * d for d in range(args.eval_draws)]
    per_draw: list[dict] = []

    for draw_i, eval_seed in enumerate(draws):
        print(f"\n########## evaluation draw {draw_i + 1}/{len(draws)} "
              f"(eval_seed={eval_seed}) ##########")
        results, c1_h, c1_t, c2_h, c2_t, flips = _one_draw(
            eval_seed, args.n_train, args.n_eval
        )
        per_draw.append({
            "eval_seed": eval_seed,
            "c1_held": c1_h, "c1_of": c1_t,
            "c2_held": c2_h, "c2_of": c2_t,
            "c2_flip_settings": flips,
            "sweeps": results,
        })
        print(f"  draw {draw_i + 1}: C1 {c1_h}/{c1_t}, C2 {c2_h}/{c2_t}"
              + (f", C2 flipped at {flips}" if flips else ""))

    _report(per_draw, args)


def _one_draw(eval_seed: int, n_train: int, n_eval: int):
    results: dict[str, list[dict]] = {}
    c1_total = c1_held = 0
    c2_total = c2_held = 0
    c2_flips: list[str] = []

    for param, (rationale, values) in SWEEPS.items():
        print(f"\n=== {param} ===\n  {rationale}")
        rows = []
        for v in values:
            setting = replace(DEFAULT_PARAMS, **{param: v})
            r = evaluate_setting(setting, n_train=n_train, n_eval=n_eval,
                                 eval_seed=eval_seed)
            ev, rand, blast = (r["policies"][k] for k in ("ev_policy", "random_targeting", "blast_everyone"))
            c1_total += 1
            c2_total += 1
            c1_held += bool(r["c1_ev_beats_random"])
            c2_held += bool(r["c2_ev_more_efficient_than_blast"])
            if not r["c2_ev_more_efficient_than_blast"]:
                c2_flips.append(f"{param}={v}")
            ratio = r["c1_margin_ratio"]
            print(
                f"  {param}={v:<6} ev={ev['incremental']:>10,.0f}  random={rand['incremental']:>10,.0f}  "
                f"blast={blast['incremental']:>10,.0f}  "
                f"C1={'OK ' if r['c1_ev_beats_random'] else 'FLIP'}"
                f"{f' ({ratio:.2f}x)' if ratio else ''}  "
                f"C2={'OK' if r['c2_ev_more_efficient_than_blast'] else 'FLIP'}"
            )
            rows.append({"value": v, **r})
        results[param] = rows

    return results, c1_held, c1_total, c2_held, c2_total, c2_flips


def _report(per_draw: list[dict], args) -> None:
    c1_held = sum(d["c1_held"] for d in per_draw)
    c1_total = sum(d["c1_of"] for d in per_draw)
    c2_held = sum(d["c2_held"] for d in per_draw)
    c2_total = sum(d["c2_of"] for d in per_draw)
    all_flips = sorted({f for d in per_draw for f in d["c2_flip_settings"]})
    # A setting that flips in every draw is a real boundary of the claim. One
    # that flips in some but not others is sampling noise, and reporting
    # either the best or the worst draw alone would misrepresent it.
    consistent = sorted(
        f for f in all_flips
        if all(f in d["c2_flip_settings"] for d in per_draw)
    )

    summary = {
        "eval_draws": len(per_draw),
        "c1_ev_beats_random": {
            "held": c1_held, "of": c1_total, "rate": c1_held / c1_total,
            "per_draw": [f"{d['c1_held']}/{d['c1_of']}" for d in per_draw],
        },
        "c2_ev_more_contact_efficient_than_blast": {
            "held": c2_held, "of": c2_total, "rate": c2_held / c2_total,
            "per_draw": [f"{d['c2_held']}/{d['c2_of']}" for d in per_draw],
            "settings_that_ever_flip": all_flips,
            "settings_that_flip_in_every_draw": consistent,
        },
    }

    print("\n=== RANKING STABILITY ACROSS EVALUATION DRAWS ===")
    print(f"  C1 (EV beats random targeting):   {c1_held}/{c1_total}  "
          f"per draw {summary['c1_ev_beats_random']['per_draw']}")
    print(f"  C2 (EV more contact-efficient):   {c2_held}/{c2_total}  "
          f"per draw {summary['c2_ev_more_contact_efficient_than_blast']['per_draw']}")
    if all_flips:
        print(f"  C2 flips somewhere: {all_flips}")
        print(f"  C2 flips in EVERY draw: {consistent or 'none — every flip is draw-dependent'}")

    (HERE / "results_sensitivity.json").write_text(
        json.dumps({"summary": summary, "draws": per_draw,
                    "n_train": args.n_train, "n_eval": args.n_eval}, indent=2, default=str))
    _plot(per_draw[0]["sweeps"])
    print(f"\nWrote {HERE / 'results_sensitivity.json'}")


def _plot(results: dict[str, list[dict]]) -> None:
    n = len(results)
    fig, axes = plt.subplots(1, n, figsize=(4.2 * n, 4.2), sharey=False)
    if n == 1:
        axes = [axes]
    for ax, (param, rows) in zip(axes, results.items()):
        xs = [r["value"] for r in rows]
        for policy, colour in [("ev_policy", "#2f855a"), ("blast_everyone", "#2b6cb0"),
                               ("random_targeting", "#a0aec0")]:
            ax.plot(xs, [r["policies"][policy]["incremental"] for r in rows],
                    marker="o", label=policy, color=colour)
        ax.set_title(param, fontsize=9)
        ax.set_xlabel("parameter value")
        ax.set_ylabel("incremental ₹ vs do-nothing")
        ax.legend(fontsize=7)
    fig.suptitle("Sensitivity sweep — is the policy ranking stable? (simulation)", fontsize=11)
    fig.tight_layout()
    fig.savefig(HERE / "sensitivity_sweep.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()
