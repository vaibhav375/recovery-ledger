# Tier 2 batch experiment — B1 headline result

**Every number below was produced by `experiments/tier2_simulation/run_batch.py`,
run on 2026-08-23.** Reproduce with `make eval` (or the command below) —
seeds are fixed throughout; re-running should give identical output
(verified: ran it twice, diffed, byte-identical).

```
uv run python experiments/tier2_simulation/run_batch.py --n-train 1000 --n-eval 1000
```

## What this measures, and what it does NOT claim

This is **policy dominance under stated assumptions, in simulation** — not
a real-world effect size. The simulator's response model
(`sim/environment.py`) is built from invented constants, loosely anchored
to published aggregate benchmarks (spec section 3.2) but never validated as
a causal model of real customer behaviour — only the *method* (uplift
learning + EV decisioning) was validated on real data, in Tier 1. Every
number in this report describes what happens *inside this simulation*,
under *this simulation's assumptions*. See `RAZORPAY_BUILDATHON_TRACK3_SPEC.md`
section 7 for why that distinction is load-bearing, not a hedge.

## Method

1. **Train** (n=1000): generate cases, randomly assign contact/no-contact
   50/50 (a mini RCT against the simulator, same logic Tier 1 validated on
   real data), observe outcomes, fit a T-learner (`policy/uplift/learners.py`
   — the same class Tier 1 validated) on the result.
2. **Eval** (n=1000, disjoint from training — different seed, no case
   overlap): split 50/50 into a **treatment arm** (full agent loop,
   `EVDecisionPolicy` driven by the fitted uplift model, all 11 compliance
   rules active) and a **randomised no-contact holdout arm**
   (`DoNothingPolicy` — always WAIT, same attempt budget). Both arms run
   through the identical `RecoveryAgent` machinery; the only difference is
   the policy.

## Result

| | Treatment (n=501) | Holdout (n=499) |
|---|---:|---:|
| Recovery rate | 39.12% | 13.43% |
| Gross ₹ recovered | 735,443 | 235,244 |
| Gross ₹ recovered per case | 1,468 | 471 |

**Incremental ₹ recovered per 1,000 at-risk cases: ₹996,519 (95% CI: ₹672,862 – ₹1,342,154)**

The confidence interval does not contain zero — under this simulation's
assumptions, the policy beats the no-contact baseline. Consistency check:
the holdout's 13.43% recovery rate is close to what pure organic
resolution predicts analytically (3 WAIT attempts at 5% each ≈
1-(0.95)³ ≈ 14.3%) — the holdout arm is behaving as a no-contact baseline
should, not doing anything hidden.

## Policy quality

- **657 contacts sent** across 501 treatment cases.
- **10 contacts (1.52%) went to predicted-negative-uplift cases** — the
  do-not-disturb segment (spec's N2). Target is ≈0; this isn't 0, but it's
  low. Not yet root-caused why those 10 slipped through — noted as an open
  item, not smoothed over.
- **100% certificate coverage**: every contact action in both arms went
  through the compliance kernel; nothing was executed without a
  certificate (structural property of the agent loop, not just observed
  behaviour this run).
- **Ledger**: 14,875 entries across both arms, hash chain verified valid.

## What this experiment does NOT yet include

- **Only one baseline comparison** (EV policy vs. do-nothing). Spec section
  11.3 requires 5: do-nothing, blast-everyone, Razorpay-current
  (single-retry-then-halt), rules-based dunning, and this policy. Only the
  first and last exist so far.
- **No sensitivity sweep.** The response model's specific constants haven't
  been varied to check whether the policy ranking (EV policy beats
  do-nothing) is stable across a range of plausible parameter choices —
  spec section 7.3 requires this before the simulation result can be
  called more than a single point estimate.
- **Cost accounting is incomplete.** Channel costs exist in the EV formula
  the policy uses internally, but this report doesn't yet total them
  against the incremental ₹ figure to produce "cost per incremental rupee
  recovered" (spec section 11.2).
- **First-contact CATE only.** The uplift model is trained on a single
  contact-vs-no-contact decision per case, not on the full multi-attempt,
  multi-channel action space the agent loop actually has available
  (RETRY's effect is a fixed calibrated constant, not learned;
  NEGOTIATE/ESCALATE_HUMAN aren't in the training data at all).
