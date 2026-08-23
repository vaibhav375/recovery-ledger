# Tier 2 batch experiment — B1 headline result

**Every number below was produced by `experiments/tier2_simulation/run_batch.py`,
run on 2026-08-24 (superseding the 2026-08-23 run — see "A bug in the first
version" below, this is not a minor revision).** Reproduce with `make eval`
(or the command below) — seeds are fixed throughout; re-running gives
identical output (verified: ran it twice, diffed, byte-identical).

```
uv run python experiments/tier2_simulation/run_batch.py --n-train 5000 --n-eval 2000
```

## What this measures, and what it does NOT claim

This is **policy dominance under stated assumptions, in simulation** — not
a real-world effect size. The simulator's response model
(`sim/environment.py`) is built from invented constants, loosely anchored
to published aggregate benchmarks (spec section 3.2) but never validated as
a causal model of real customer behaviour — only the *method* (uplift
learning + EV decisioning) was validated on real data, in Tier 1. Every
number in this report describes what happens *inside this simulation*,
under *this simulation's assumptions*.

## A bug in the first version of this experiment (2026-08-23) — read this before the numbers

The first run of this experiment reported ₹996,519 incremental per 1,000
cases with a suspiciously clean-looking result: only 1.52% of contacts went
to predicted do-not-disturbs. That number was **not evidence of good
targeting**. It was checked, not assumed, the next day: `sim/environment.py`'s
`generate_population()` originally drew every hidden trait (liquidity,
annoyance_threshold, dispute_propensity) **fully independently of every
observable case field**. Since the true treatment effect
(`persuadability()`) is a function only of those hidden traits, it was
therefore **statistically independent of every feature the uplift model was
trained on, by construction** — there was nothing for the model to learn,
no matter how good the learner was.

Confirmed by computing `corr(tau_hat, tau_true)` on held-out data:
**-0.02** — indistinguishable from zero. The reported 1.52%
do-not-disturb-contact rate wasn't the policy avoiding do-not-disturbs; the
true population do-not-disturb rate was itself only 1.5%, so an
essentially-random targeting policy would have shown almost the same number
by coincidence.

**Fix**: `generate_population()` now derives each trait with a declared,
non-trivial dependence on observable fields (e.g. B2B customers and
lower-amount cases skew more liquid; B2B and overdue-receivable cases skew
more dispute-prone; WhatsApp-preferring customers tolerate more contact than
SMS-only ones). The first attempt at this fix used shifts of 0.10-0.15
against traits with ~0.2 natural standard deviation — still too weak:
`corr(tau_hat, tau_true)` was noisy and non-monotonic across training sizes
(0.15 at n=1000, 0.16 at n=5000, dropping to 0.08 at n=20000 — the signature
of a signal too marginal to reliably detect, not a data-size problem).
Roughly doubled the shift magnitudes; correlation became monotonic and
substantial: 0.15 → 0.24 → 0.42 as training size went 1000 → 2000 → 5000.
That monotonic-with-data pattern is itself the evidence the signal is now
real, not an artifact.

**This correlation is now computed and reported on every run**
(`uplift_model_correlation_with_true_persuadability` in `results.json`) and
has a regression test (`tests/test_uplift_model_correlates_with_true_persuadability`)
that fails the build if it ever drops back toward zero.

## Method (unchanged from 2026-08-23)

1. **Train** (n=5000): generate cases, randomly assign contact/no-contact
   50/50 (a mini RCT against the simulator, same logic Tier 1 validated on
   real data), observe outcomes, fit a T-learner (`policy/uplift/learners.py`
   — the same class Tier 1 validated) on the result.
2. **Eval** (n=2000, disjoint from training — different seed, no case
   overlap): split ~50/50 into a **treatment arm** (full agent loop,
   `EVDecisionPolicy` driven by the fitted uplift model, all 11 compliance
   rules active) and a **randomised no-contact holdout arm**
   (`DoNothingPolicy` — always WAIT, same attempt budget).

## Result

| | Treatment (n=1037) | Holdout (n=963) |
|---|---:|---:|
| Recovery rate | 32.59% | 14.54% |
| Gross ₹ recovered | 643,747 | 385,878 |
| Gross ₹ recovered per case | 621 | 401 |

**Incremental ₹ recovered per 1,000 at-risk cases: ₹220,074 (95% CI: ₹90,448 – ₹341,757)**

Smaller than the withdrawn 2026-08-23 figure (₹996,519) — expected and
correct. That figure was inflated by a policy that was, in effect, not
targeting on real signal at all while still benefiting from RETRY and
NUDGE's *average* effect across the whole population. This figure reflects
a policy genuinely using (imperfect, 0.41-correlated) learned heterogeneity.
The CI still excludes zero: under this simulation's assumptions, the policy
still beats the no-contact baseline.

## Policy quality — the more honest picture

- **uplift_model_correlation_with_true_persuadability: 0.41.** Real, but
  far from perfect — this is a genuinely hard prediction problem with a
  T-learner on 5000 noisy Bernoulli outcomes, the same kind of
  signal-to-noise challenge Tier 1 flagged for Criteo's 0.29% conversion
  rate.
- **947 contacts sent, 154 (16.26%) to predicted-negative-uplift cases.**
  Not close to spec's ≈0 target. This is the honest number the 2026-08-23
  run's 1.52% was masking. Room for real improvement here: try the X-learner
  or causal forest (already implemented in `policy/uplift/learners.py`,
  not yet swapped in), more training data, or a stricter EV threshold
  before proposing NUDGE.
- **100% certificate coverage**, structurally guaranteed by the loop design,
  confirmed again this run.
- **Ledger**: 28,851 entries, hash chain verified valid.

## What this experiment still does NOT include

- **Only one baseline comparison** (EV policy vs. do-nothing). Spec section
  11.3 requires 5.
- **No sensitivity sweep** over the response model's parameters.
- **Cost accounting is incomplete** — no "cost per incremental rupee
  recovered" yet.
- **First-contact CATE only** — RETRY's effect is a fixed calibrated
  constant, not learned; NEGOTIATE/ESCALATE_HUMAN aren't in training data.
- **Only the T-learner is used.** Given the do-not-disturb leakage above,
  trying the X-learner or causal forest next is a concrete, motivated next
  step, not just "more thorough coverage for its own sake."
