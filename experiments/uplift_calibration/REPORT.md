# Uplift by decile — does the ranking the policy acts on exist in the data?

`make calibration` → `results_uplift_calibration.json`, `uplift_by_decile.png`

## Why this was run

The spec's evaluation protocol (§8.1, §11.2) asks for an uplift-by-decile
chart, and it was the one required artifact this repo did not have. It was also
the only remaining way to say anything about the CATE model that a deployment
could actually reproduce.

Every claim made about that model so far has run through one number:
correlation 0.347 with the simulator's hidden `persuadability` trait. That
number is not available in production — nothing outside a simulator knows the
trait — so it can validate the simulator's own bookkeeping and nothing else. A
decile chart needs only a randomised assignment, which a real deployment has by
construction if it keeps a holdout.

## Design

Fresh population of 4,000 cases per draw, disjoint from every other
experiment's (`SEED + 11000`, see `tests/test_experiment_seeds.py`). Contact is
assigned by coin flip, one nudge, payment observed. Cases are ranked by the
shipped single T-learner's predicted uplift and cut into ten equal bins, and
each bin's uplift is the contrast between its *own* contacted and not-contacted
rows. Three draws.

**The policy is deliberately not in the loop.** `LookaheadEVDecisionPolicy`
declines to contact the low deciles, so running it here would drive their
realised uplift to zero *because nobody was contacted* and produce a monotone
chart for a model that predicts nothing. This measures the model; `make eval`
measures the policy.

The rules were fixed before the run:

- **Ranking** holds only if the top decile beats the bottom in *every* draw.
- **Monotone** holds only if Spearman ≥ 0.9 in *every* draw; ≥ 0.7 is reported
  separately as the weaker "near-monotone".
- **Calibration** is reported, not judged. No threshold was set for the slope,
  because a threshold chosen after seeing the number cannot fail.

## Result

Mean over three draws of 4,000:

| decile | predicted τ̂ | realised uplift | true persuadability | true do-not-disturbs |
|---:|---:|---:|---:|---:|
| 1 | −0.0642 | +0.0179 | +0.0411 | 43.8% |
| 2 | +0.0098 | −0.0162 | +0.0365 | 40.2% |
| 3 | +0.0305 | +0.0223 | +0.0564 | 34.3% |
| 4 | +0.0469 | +0.0483 | +0.1036 | 16.2% |
| 5 | +0.0659 | +0.0888 | +0.1364 | 12.3% |
| 6 | +0.0863 | +0.1034 | +0.1664 | 6.6% |
| 7 | +0.1066 | +0.0896 | +0.1658 | 7.3% |
| 8 | +0.1289 | +0.1750 | +0.1831 | 4.4% |
| 9 | +0.1623 | +0.1730 | +0.1872 | 4.8% |
| 10 | +0.2850 | +0.2255 | +0.2061 | 2.8% |

| | draw 1 | draw 2 | draw 3 | verdict |
|---|---:|---:|---:|---|
| top − bottom decile | +0.2360 | +0.1546 | +0.2321 | **ranking holds, 3/3** |
| Spearman | +0.879 | +0.903 | +0.952 | **not monotone at 0.9** (near-monotone, 3/3) |
| calibration slope | 0.799 | 0.656 | 0.819 | mean **0.758** |
| Qini | +0.2613 | +0.2489 | +0.2642 | |
| τ̂ correlation with truth | 0.347 | 0.346 | 0.363 | consistent with the 0.347 in §2 |

## What it says

**The ranking is real.** The top decile realises +0.21 more payment probability
per contact than the bottom, in all three draws, with non-overlapping intervals
at both ends. The model is not sorting noise.

**It is not monotone, and it fails the pre-registered bar.** 0.879 in the first
draw is below the 0.9 that was set before the run. It is reported as failing
rather than as "essentially 0.9", and the near-monotone threshold is reported
as the separate, weaker claim it is. In the draw-averaged table the inversions sit at deciles 2, 7 and 9, and
which deciles invert moves between draws (draw 1 inverts at 4, 7, 9) — the
ordering is right in the large and unreliable step by step.

**The predictions are ~32% too spread out.** Slope 0.758: the model's
predictions range −0.064 to +0.285 while the truth ranges +0.041 to +0.206.
This is the mechanism `experiments/uplift_ab` suspected and could not show.
The policy contacts when `τ̂ × amount` clears the message cost — a threshold on
a product — so an over-spread τ̂ mis-places that threshold in both directions
even with the ranking intact. It also explains why a bootstrap ensemble raised
correlation to 0.445 without recovering more money: bagging shrinks extremes,
which moves cases across the threshold both ways.

**The bottom decile is where the do-not-disturbs are, but its realised uplift
is not negative.** 43.8% of it is truly negative-uplift, against 17.3% of the
population and 2.8% of the top decile — a 2.5x enrichment, which is the
targeting signal N2 needs. But the decile still averages +0.0411 true
persuadability and realises +0.0179, with an interval covering zero in all
three draws. The model predicts −0.0642 there.

So the honest statement about the shipped model's negative predictions is:
**they locate do-not-disturbs, they do not measure them.** A decile that is
44% do-not-disturb and 56% ordinary customers nets out slightly positive, and
τ̂ reports it as clearly negative. That is a calibration failure in exactly the
region N2 cares about most.

It does not retract N2. That claim rests on the deployed policy contacting
11.53% do-not-disturbs against mass-contact's 21.98% (`make baselines`) and on
an independent opt-out hazard of 1.29x [1.09, 1.51] (`make dnd-signal`) — a
second signal, from the churn model, which is the reason N2 was built not to
depend on τ̂ alone. This chart is evidence for why that design choice was
correct rather than cautious.

## What was not done

The slope is not corrected. A recalibration layer — isotonic regression on the
holdout, or a shrinkage factor on τ̂ — is the obvious next move and would
change the deployed policy's threshold behaviour, so it needs its own A/B under
the same replication rule as `experiments/uplift_ab`, not a patch. Applying it
here and re-quoting the headline would be tuning until it passes.
