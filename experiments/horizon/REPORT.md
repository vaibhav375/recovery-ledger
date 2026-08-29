# When does planning ahead actually pay?

**Question.** Novelty claim N4 says contact should be treated as a
budget-constrained *sequential* decision rather than one-shot classification.
The repo implements both a greedy EV policy and a finite-horizon lookahead that
solves the same problem by backward induction. The claim was marked "partial"
because in the headline batch the lookahead earned slightly *less* than greedy.

That is an honest report of a number and a useless answer to the question. A
zero difference is produced by a working solver in a regime where greedy is
already optimal, and equally by a solver that is broken, degenerate, or being
measured by something that cannot see what it does. Those have opposite
implications and the rupee total cannot distinguish them.

## What was actually wrong: the measurement, not the policy

The first version of this experiment swept 25 settings across 3 draws and
concluded the lookahead never wins. It was evaluating each policy with a single
`env.step` per case.

A lookahead policy's entire advantage is deferral — declining an attempt now
because a better moment is coming, or spending one now because it can see there
will be no later. A single-step harness charges it for every wait and credits it
for none. The sequential policy was guaranteed to look equal-or-worse no matter
how good it was, and the experiment returned a clean, confident, meaningless
negative across 75 policy comparisons.

`--mode rollout` plays the whole episode instead: each case runs until it pays,
opts out, or exhausts its attempt budget, with the environment carrying contact
count and accumulated annoyance across attempts. The single-step numbers are
kept in `results_horizon_single.json` as a record of what the wrong measurement
said.

Two facts show the rollout is the one with power. Under it a longer budget
recovers more money (₹221/case at 1 attempt, ₹862/case at 8 with λ=120), which
the single-step version could not represent at all; and the annoyance penalty λ
finally changes the outcome, where under single-step it had almost no effect.

## Controls

| Control | Result |
|---|---|
| Horizon 1 must agree on every case (no future to plan over → same algorithm) | **PASS**, agreement exactly 1.000 at all 5 λ values |
| The solver must differ from greedy somewhere, or it is not being exercised | differs in **20 of 25** settings |
| Disagreement should grow with the horizon | rises monotonically, 0 → 6 → 9 → 11 → 15 cases |

The first control is what rules out "the solver is broken". The second and third
rule out "the solver silently returns the greedy action".

## Result

Lookahead minus greedy, ₹/case, averaged over 3 independent evaluation
populations (n=2,000 each). A setting counts as a win only if **every** draw
agrees on the sign.

| max_attempts | λ=0 | λ=15 | λ=30 | λ=60 | λ=120 |
|---|---|---|---|---|---|
| 1 | +0 | +0 | +0 | +0 | +0 |
| 2 | +0 | +0 | +0 | +0 | +0 |
| 3 | +2 | +2 | −0 | −0 | −0 |
| 5 | **+6** | +4 | −1 | −0 | −0 |
| 8 | **+7** | +3 | −2 | −1 | −1 |

Bold = consistent across all three draws.

- **λ = 0, budget 5:** +₹6/case, per-draw [+12.3, +5.8, +0.9]
- **λ = 0, budget 8:** +₹7/case, per-draw [+11.0, +5.7, +2.9]
- **Deployed setting (budget 3, λ = 30):** −₹0.12/case, range [−1, +1], sign
  not consistent across draws — indistinguishable from zero.

## What this licenses saying

Planning ahead pays when the per-attempt annoyance penalty is small and the
attempt budget is long, and the effect is real enough to survive three
independent populations. It stops paying as soon as λ rises: at λ ≥ 30 the
penalty dominates the continuation value, every future attempt is worth less
than it costs, and the optimal plan collapses to the greedy one. Since the
calibrated deployment sits at λ = 30 with a 3-attempt budget, **greedy is within
noise of optimal there, and that is why the shipped policy is greedy.**

This is a narrower claim than "sequential decision-making beats classification",
and a more useful one: the sequential machinery is correct, it is measurably
doing something, and there is now a stated condition under which it earns its
complexity — which the deployment does not meet.

## What this does not license saying

The magnitude. Per-draw deltas at λ=0 range from +₹0.9 to +₹12.3, so "+₹6–7 per
case" is the mean of three noisy draws, not a precise effect size. Only the
sign replicated. Against totals of ₹411–862/case the advantage is roughly 1–2%,
which is small enough that it would not survive a change in the churn cost
constant without being re-measured.

Reproduce: `make horizon` (rollout, the default) — about 40 minutes.
Single-step comparison: `--mode single`.
