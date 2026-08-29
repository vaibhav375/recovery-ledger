# Does a better-correlated uplift model make better decisions?

`make uplift-ab` → `results_uplift_ab.json`

## Why this was run

The single T-learner correlates 0.347 with true persuadability. A 20-member
bootstrap ensemble of the same learner reaches 0.445, and that gain replicated
at +0.091, +0.096, +0.097 across three independent draws — the most reliable
model improvement available anywhere in this repo. Correlation with truth is
*the* headline diagnostic for a CATE model, so shipping the ensemble looked
like the obvious next move, and it was recommended as such.

Then two evaluation populations disagreed about whether it helped:

| population | single | ensemble | |
|---|---:|---:|---|
| batch eval (SEED+1000) | ₹272,281 | ₹291,588 | **+7.1%** |
| baselines eval (SEED+2000) | ₹317,168 | ₹290,581 | **−8.4%** |

Opposite signs, overlapping intervals. Quoting either alone would have produced
a confident claim in whichever direction the author preferred.

## Design

Both arms share the training cases, the randomised assignment, the churn model
(the flag does not touch it) and the evaluation populations. The single
difference is which uplift model the EV policy consults. Five evaluation draws
of 2,000 cases each.

The verdict rule was fixed before the run: an effect on recovered value is
claimable only if **every** draw agrees on its sign.

## Result

| draw | value Δ | τ̂ corr | do-not-disturb rate | contacts |
|---|---:|---|---|---:|
| 1 | −8,274 | 0.338 → 0.449 | 10.49% → 10.17% | +24 |
| 2 | −13,653 | 0.373 → 0.453 | 9.72% → 8.71% | +62 |
| 3 | −13,490 | 0.340 → 0.461 | 14.61% → 11.23% | +34 |
| 4 | **+10,506** | 0.360 → 0.453 | 11.97% → 8.49% | +37 |
| 5 | −15,998 | 0.351 → 0.443 | 8.63% → 8.01% | +27 |

| quantity | direction | replicated |
|---|---|---|
| τ̂ correlation | +0.099 | **5/5** |
| do-not-disturb contact rate | −1.76 pp | **5/5** |
| contacts sent | +37 | **5/5** |
| **recovered value** | mean −₹8,182 | **no — 4 negative, 1 positive** |

**The ensemble's effect on recovered value is undetermined.** Four draws of
five went the other way, which is suggestive, but the rule was fixed in advance
and the sign did not hold. Neither "the ensemble earns more" nor "the ensemble
earns less" is supportable.

## Why correlation and value came apart

This is the part worth keeping, because it is not a quirk of these five draws.

The policy does not rank cases by τ̂. It contacts when
`τ̂ × amount_at_risk` clears the cost of a message. That is a **threshold on a
product**, so what determines the decision is the calibration of τ̂ near the
boundary and the ordering of the cases sitting close to it — not global rank
agreement across the whole population.

Bagging raises correlation partly by shrinking extreme predictions toward the
mean. That is variance reduction, and it is exactly the operation most likely to
move borderline cases across a threshold in both directions at once. A model
can therefore be a better predictor and a worse decision rule, and the
correlation number cannot show it. The observed behaviour matches: the ensemble
contacted *more* cases in all five draws (+37 on average) while reaching *fewer*
do-not-disturbs, which is a shifted decision boundary, not a uniformly better
one.

## What ships, and on what grounds

The single T-learner. Not because the ensemble is worse — that is not
established either — but because there is no measured reason to change the
deployed policy, and the numbers the documents quote were produced by the
T-learner.

There is a defensible case for the ensemble on **harm reduction** rather than
revenue: do-not-disturb contact rate fell in 5/5 draws, by 1.76 percentage
points on average. That is a real, replicated effect on the metric this project
treats as a compliance concern rather than an optimisation target. It costs
about 37 additional contacts per 2,000 cases and an unmeasured amount of
revenue. That is a judgement call about what the system is for, not a
measurement, and it is left as one.

## The general lesson

A 29% relative improvement in CATE correlation produced no detectable
improvement in the objective. Correlation with ground-truth treatment effect is
a proxy, and this is a worked example of a proxy improving while the thing it
proxies for does not. Any future model change in this repo should be evaluated
on recovered value across several populations before it is described as an
improvement.
