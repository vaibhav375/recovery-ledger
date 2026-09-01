# Acting on a lower bound instead of a point estimate

`make pessimism` → `results_pessimism.json`

## Why this was run

τ̂ = 0.02 from a model that understands a segment and τ̂ = 0.02 from a model that
is guessing produce identical decisions. The policy has no way to express the
difference, so it spends the same budget on a confident estimate and a shrug.

A bootstrap ensemble of 20 learners gives a per-case standard error alongside
the estimate, and the policy can then act on `τ̂ − k·se` — a lower confidence
bound rather than a point. Larger `k` means more caution: contact only where the
model is both optimistic *and* sure.

## Design

5,000 training cases, 4,000 evaluation cases, swept over `k`, and repeated
across **3 independent evaluation draws** — because a best-`k` chosen on one
population is a claim about that population.

## What it found

The ensemble does correlate better with truth than the single T-learner:

| | draw 1 | draw 2 | draw 3 | mean |
|---|---:|---:|---:|---:|
| single T-learner | 0.3636 | 0.3714 | 0.3569 | **0.364** |
| 20-member ensemble | 0.4546 | 0.4672 | 0.454 | **0.4586** |

**But the best `k` is not stable across draws** — `best_k_per_draw` reads
[0.5, 0.5, 0.25], and `best_k_is_stable` is `False`. So the sweep is reported as a
*range* rather than a tuned value, because publishing the argmax of one draw as
"the optimal caution" is precisely the single-draw claim this project has
watched evaporate six times.

The wider finding is in `RESULTS.md`: caution keeps buying harm reduction long
after it stops buying money. Value per contact rises while net value moves only
a few rupees per case, so `k` is a policy choice about what the system is for,
not a parameter with a maximum to find.

## Relationship to the other uplift experiments

This is one of three attempts to improve the model and have the money follow.
`uplift_ab` shipped nothing because a better-correlated ensemble did not recover
more. `uplift_recalibration` shipped nothing because a correction that
demonstrably fixed the calibration slope did not either. Here a better-correlated
ensemble buys harm reduction rather than revenue.

All three point the same way: **improving a diagnostic is not improving the
decision.** The policy thresholds `τ̂ × amount`, so what matters is behaviour
near that boundary, not global fit.
