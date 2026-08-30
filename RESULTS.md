# Results

Every number here was produced by code in this repository and is
reproducible with the command shown beside it. Nothing is hand-entered,
illustrative, or carried over from a previous run.

**Read this first — what is and is not being claimed.** Two different kinds
of claim appear below, and conflating them would be the single easiest way
to mislead:

| | Claim | Evidence |
|---|---|---|
| **Method validity** | The causal machinery recovers known treatment effects | **Real randomised data** (Criteo, Hillstrom) |
| **Policy dominance** | This agent's policy beats named alternatives | **Simulation, under stated assumptions** |

**No real-world effect size is claimed anywhere.** The simulator's constants
are invented (see `src/recovery_ledger/sim/environment.py`); they are
loosely anchored to published aggregates, which constrains *outcome rates*
and not *causal response to intervention*. That distinction is the entire
reason Tier 1 exists, and why the sensitivity sweep reports ranking
stability rather than a point estimate.

---

## Tier 1 — method validity, on real randomised data

```
make tier1-hillstrom     # ~30s
make tier1-criteo        # downloads ~340MB on first run
```

The kill gate: before any of this touches a simulator, the uplift learners
and off-policy estimators must reproduce effects that are already known
from genuinely randomised experiments.

**Uplift learners — Qini coefficient (positive = better than random ranking):**

| Learner | Hillstrom | Criteo (2% subsample) |
|---|---:|---:|
| S-learner | +0.0414 | +0.0745 |
| T-learner | +0.0546 | +0.0663 |
| X-learner | +0.0492 | +0.0706 |
| Causal forest | +0.0386 | +0.0616 |

All eight positive — every learner finds real heterogeneity on both
datasets, independently of the others.

**Off-policy estimators vs. the datasets' own arm-mean ATE.** IPS/SNIPS/DR
never see the direct arm comparison; they reconstruct it from
propensity-reweighted individual outcomes. If they land on it, the
implementation is correct.

| Estimator | Hillstrom | Criteo |
|---|---:|---:|
| Direct arm-mean ATE (ground truth) | +0.0451 | +0.0094 |
| IPS | +0.0451 | +0.0094 |
| SNIPS | +0.0451 | +0.0094 |
| DR | +0.0462 | +0.0067 |

IPS and SNIPS match exactly on both. **DR is the honest weak spot** — close
on Hillstrom (balanced 50/50 arms), low on Criteo (85/15 imbalance).

That gap was previously described as "29% low", which overstated what one
number can support. `make dr-diagnosis` re-measures it on three *disjoint*
blocks of the Criteo pool, with a paired bootstrap on the treated-minus-control
contrast rather than two independently bootstrapped intervals:

| Block | Direct ATE | DR | DR 95% CI | Covers truth |
|---|---:|---:|---|:--:|
| 1 | +0.0096 | +0.0054 | [+0.0026, +0.0080] | no |
| 2 | +0.0074 | +0.0071 | [+0.0044, +0.0101] | yes |
| 3 | +0.0112 | +0.0075 | [+0.0045, +0.0104] | no |

DR reads low in all three blocks, but by 4%, 33% and 44% of the true effect —
so "29% low" was one draw's number, not a stable bias magnitude. Under the
pre-registered rule (bias requires *both* every interval missing truth *and* a
consistent sign) the verdict is **inconclusive, leaning bias**. IPS covers the
truth in 3/3.

What the diagnosis does rule out is the variance explanation: DR's paired
interval is 0.82x the width of IPS's, so it is not merely noisier. And with a
known constant propensity DR is unbiased for any outcome model, which points
at the cross-fitted q_hat on a 15% control arm carrying a 6.7x importance
weight. Not closed — but now characterised precisely enough to be actionable,
and IPS is the estimator to trust on this dataset. See
`experiments/tier1_criteo/REPORT.md`.

---

## B1 — measured money recovered across a batch

```
make eval        # 5,000 training + 2,000 evaluation cases
```

| | Treatment | Holdout (no contact) |
|---|---:|---:|
| Cases | 1,037 | 963 |
| Recovery rate | 33.46% | 15.47% |
| Gross ₹ recovered | ₹819,080 | ₹498,424 |

**Incremental ₹ recovered per 1,000 at-risk cases: ₹272,281 (95% CI ₹103,930 – ₹433,387)**

The holdout recovers **15.47% of cases with no agent at all**. That is why
this project reports incremental rather than gross: a vendor quoting the
gross figure would be taking credit for every rupee in that column.

Supporting diagnostics from the same run: uplift correlation with true
(hidden) persuadability **0.347**; **467 contacts** sent; do-not-disturb
contact rate **10.1%**; 8 of 11 stopping reasons fired naturally; 34,304
ledger entries, hash chain verified; 690 cases published to the exception
list.

Every figure in this section is read straight out of
`experiments/tier2_simulation/results.json`, and
`tests/test_results_doc_matches_artifacts.py` fails the build if this document
and that artifact ever disagree again — which they had, silently, for several
commits.

---

## Regret — what the silences cost, beside what contacting recovered

```
make regret       # the same 2,000-case population as make eval
```

Every section above reports what the policy's silence *saved*. Nothing in
this document, until now, reported what it *cost* — every refusal to contact
is a bet that contacting would not have paid, and some of those bets are
wrong. This experiment prices the 554 declined cases in the same
1,037-case treatment arm ₹272,281 was measured on, using the simulator's own
`persuadability(traits)` as the true per-case effect: positive true uplift
priced as forgone, negative true uplift priced as avoided.

Of the 1,037-case treatment arm: 234 were actually contacted ("worked"), 6
were handed to a human (excluded, not yet decided), 243 resolved without
ever being contacted (they paid; nothing was forgone, so they too are
excluded), and 554 were declined and priced below. That partition adds up:
234 + 6 + 243 + 554 = 1,037. The 243 resolved-without-contact cases are the
selection mechanism behind the counterfactual check's one-sidedness further
down: excluding them is what conditions the priced universe on `paid_0 ~= 0`.

| Bucket | n | Cost | Saved | Net | Model errors |
|---|---:|---:|---:|---:|---:|
| allocation | 264 | ₹69,247 | ₹1,502 | ₹-67,746 | 0 |
| model_judgement | 286 | ₹63,822 | ₹92,177 | ₹28,355 | 170 |
| case_state | 4 | ₹1,278 | ₹0 | ₹-1,278 | 0 |
| **Total** | **554** | **₹134,347** | **₹93,679** | **₹-40,669** | **170** |

**Beside the headline: recovered ₹272,281 per 1,000, and on the same cases
the silences cost ₹134,347, saved ₹93,679, net ₹-40,669.** Net is negative
— the silences cost more than they saved. That is unflattering and it is
published as it is.

**The allocation bucket is the largest single cost, and it was not
predicted.** `allocation` — cases that simply ran out of allocated contact
attempts, not a modelling choice — carries ₹69,247, more than
`model_judgement`'s ₹63,822. The pre-registered prediction below only ever
concerned `model_judgement`; `allocation` being the bigger cost is a finding
of its own, not a refutation of anything, and is worth stating rather than
folding quietly into the total.

**Pre-registered prediction, fixed before this run:** `make calibration`
reports the bottom `tau_hat` bin as 43.8% true do-not-disturbs against 17.3%
of the population, so it is also ~56% customers with positive true uplift.
The `model_judgement` bucket — cases the agent itself chose not to contact —
must therefore contain a non-trivial count of `tau_true > 0` refusals. Near
zero would refute one of the two experiments.

**170 model errors were observed → the prediction HOLDS.** The regret result
and `make calibration` corroborate rather than contradict each other. Within
`model_judgement`, net is still positive (₹28,355): the ₹92,177 correctly
avoided in true do-not-disturbs outweighs the ₹63,822 forgone from the 170
customers the model judged wrong — the model is right more often by rupees
saved even while wrong on a non-trivial count of people.

**The registered rule is weaker than "non-trivial count" implies, stated
plainly.** The threshold actually coded (`MODEL_ERRORS_EXPECTED_ABOVE = 0`
in `run_regret.py`) is `model_errors > 0` — any non-zero count passes. It is
not being raised now that the result is in: tightening a pre-registered
threshold after seeing it clear would be moving the goalposts, same as
loosening one to force a pass would be. As registered, the rule clears at
170 by a wide margin (170 of 286 model-judgement refusals, 59%); the
stronger "non-trivial count" framing above is also satisfied, but is not
what the code enforces.

**Caveat, load-bearing:** the headline estimator is an expectation under
simulator truth, not a realised measurement.

### Counterfactual check — validates the cost side only, and disagrees even there

A second, independent estimate replays each of the same 554 cases under
`WAIT` (what happened) and `NUDGE` (the counterfactual) with common random
numbers: realised cost ₹111,614 against the expected ₹134,347, realised net
₹-111,614 against expected net ₹-40,669.

**Tested, not assumed to agree: a 95% bootstrap interval on the model-based
cost total is [₹119,877, ₹148,032], and the realised cost (₹111,614) falls
outside it.** The interval resamples the 554 in-scope declined cases' own
`forgone` amounts with replacement (2,000 replicates), capturing how much
the total cost estimate would move across comparable draws of this same
sample. `results_regret.json` records the interval and the verdict directly:
`cost_interval_low`, `cost_interval_high`, `realised_cost_inside_interval:
false`. This is published as computed — even on the one side of the ledger
this check can validate at all, the realised replay and the model-based
estimate disagree by more than the sampling variance of the cost total
accounts for. It is not evidence `totals.cost` is fabricated (both figures
come from the same committed, deterministic code), but it is a real,
unresolved disagreement, not agreement to be waved past.

**`realised_saved` is exactly `-0.0`, not a small or noisy number.** This is
selection, not variance: `declined_cases()` excludes `resolved` cases (they
paid; nothing was forgone), which conditions the declined universe on *not*
having paid under `WAIT` — a saving can only be observed where `paid_0 = 1`
and `paid_1 = 0`, and every such case was already routed out as `resolved`
before it could enter this universe. **This check validates the cost side of
the ledger only — and, per the bootstrap result above, does not cleanly
corroborate it — so the ₹93,679 saved figure must not be quoted as
independently validated** — it rests on the model-based estimate alone; nor
should the ₹134,347 cost figure be quoted as independently validated, since
the realised replay landed outside its own interval.
`results_regret.json` records this directly on `counterfactual_check`:
`"validates": "cost side only"`. See `experiments/regret/REPORT.md` for the
full design and the estimator diagnostics that back this claim, including
that negative realised draws are not structurally impossible — they simply
do not occur inside this selected universe.

Every figure in this section is read straight out of
`experiments/regret/results_regret.json`, pinned by
`tests/test_results_doc_matches_artifacts.py`.

---

## Baselines — spec section 11.3, plus a falsification control

```
make baselines
```

Common random numbers across policies, paired bootstrap, same 2,000 cases.

| Policy | Incremental ₹/1000 | Contacts | ₹ per contact | % to do-not-disturbs |
|---|---:|---:|---:|---:|
| do_nothing | — (reference) | 0 | — | — |
| blast_everyone | 354,371 | 4,340 | 163.3 | 21.98% |
| rules_based_dunning | 354,371 | 4,340 | 163.3 | 21.98% |
| razorpay_current | 66,905 (**CI includes 0**) | 0 | — | — |
| random_targeting | 135,730 | 2,014 | 134.8 | 22.84% |
| ev_policy_no_churn | 372,590 | 2,051 | 363.3 | 22.48% |
| **ev_policy_greedy** | 317,168 | **885** | **716.8** | **11.53%** |
| ev_policy_lookahead | 317,168 | 883 | 718.4 | 11.55% |

**The result that matters: 2.34x more incremental recovery than random
targeting at comparable contact volume, with non-overlapping confidence
intervals.** (The deployed policy is `ev_policy_greedy`; an earlier version of
this line quoted `ev_policy_no_churn`'s multiple instead.) Without this control the headline would be uninterpretable —
"fewer contacts, same money" could just be diminishing returns to volume and
would say nothing about the uplift model. This is what makes it a claim
about *targeting*.

**Against mass-contact the honest verdict is a tie on total recovery**
(overlapping CIs; the sign of the difference flips with the eval sample)
achieved with far fewer contacts at 2-3x the per-contact efficiency.
Contact efficiency is the robust claim; a higher headline total is not.

**`ev_policy_no_churn` is in the table on purpose.** It is the same policy
with the `λ_churn` term switched off, so the effect of that term is visible
rather than asserted: it trades **12% of incremental recovery** for **41%
fewer contacts**, **49% better rupees-per-contact**, and a **third fewer
do-not-disturbs reached** (20.1% → 13.6%). That is a stated policy choice,
not a free win — see below.

**`razorpay_current`'s CI includes zero.** A single automated retry followed
by halting is not reliably better than doing nothing in this simulation —
which is precisely the unowned gap described in spec section 3.3.

---

## Ranking stability — sensitivity sweep

```
make sensitivity
```

Five invented simulator constants, five values each, uplift model
**retrained at every setting** — and the whole sweep repeated over
**3 independent evaluation populations**, because one draw is not a
robustness result.

| Claim | Holds at | Per draw |
|---|---|---|
| **C1 — targeting beats matched-volume random targeting** | **75 / 75** (median margin 2.16x, 10th–90th pct 1.80x–2.69x) | 25/25, 25/25, 25/25 |
| **C2 — targeting is more contact-efficient than mass-contact** | **75 / 75** | 25/25, 25/25, 25/25 |

**The margin is quoted as a median, not a range.** The largest single ratio in
the sweep is 82x, and it is not a finding: at `base_organic_resolution = 0.12`
random targeting's incremental recovery swings from ₹-10,734 to
₹88,486 across draws, so in one of them the ratio is a division by a
near-zero denominator and in another the denominator is negative and the ratio
is undefined. C1 still holds at that setting in every draw — targeting beats
random even when random loses money — but the *ratio* there carries no
information and quoting it as a headline would be quoting an artifact.

C1 never flips, including in the two settings constructed to break it (zero
annoyance decay, so persistence is never punished; zero amount↔liquidity
coupling, so the amount weighting carries no hidden signal).

### Why this is measured across draws, and what that changed

An earlier version of this experiment ran one evaluation population and
reported **C2 at 24/25**, with a paragraph explaining the single flip: at
`base_organic_resolution = 0.12`, mass-contact appeared to win.

That evaluation seed collided with `run_baselines.py`'s. Moving it — the two
experiments had only avoided sharing a population because they happen to be
invoked with different `--n-eval` — changed C2 to 25/25. Same code, same
settings, different customers.

Neither number is reportable on its own. So the sweep now runs 3 draws, and
the flip does not reproduce in any of them.

**It was not a marginal call — the metric is unstable there.** Incremental
rupees *per contact* at `base_organic_resolution = 0.12`:

| evaluation draw | targeting | mass-contact |
|---|---:|---:|
| original (the flip) | ₹60 | ₹78 |
| draw 1 | ₹294 | ₹40 |
| draw 2 | ₹163 | ₹31 |
| draw 3 | ₹158 | ₹-12 |

Targeting's figure spans ₹60–₹294 and mass-contact's spans ₹-12–₹78
across draws. When 12% of cases resolve themselves there is little
incremental value left to divide by a contact count, and the ratio becomes a
quotient of two small noisy numbers. **A single-draw verdict at that setting
is uninformative in either direction** — which is the honest replacement for
the previous paragraph, not an upgrade from 24/25 to 25/25.

**Best finding in the sweep, and not one I set out to test:** as the
amount↔liquidity coupling strengthens — high-value cases becoming
increasingly likely to be do-not-disturbs — the targeting advantage *widens*
from 2.21x to **3.74x** while mass-contact collapses from
₹981,220 to ₹265,496. **The harder the do-not-disturb problem, the
more targeting is worth.** Novelty claim N2 as a measured gradient rather
than an assertion.

---

## Uplift by decile — is the ranking real?

```
make calibration
```

The τ̂ model has been reported through one number all project: correlation
**0.347** with the simulator's hidden `persuadability` trait. No deployment can
compute that — nothing outside a simulator knows the trait — so it validates
the simulator's bookkeeping and nothing else. The spec asks for the version a
deployment *can* compute (§8.1, §11.2), and it was the last required artifact
missing here.

4,000 fresh cases per draw, contact assigned by coin flip, ranked by τ̂ and cut
into ten bins. Each bin's uplift is the contrast between its **own** contacted
and not-contacted rows — a bin scored against the population's control mean
comes out monotone for a model that predicts nothing. The deployed policy is
deliberately absent: it declines to contact the low deciles, which would drive
their realised uplift to zero because nobody was contacted. This measures the
model; `make eval` measures the policy.

| decile | predicted τ̂ | realised uplift | true persuadability | true do-not-disturbs |
|---:|---:|---:|---:|---:|
| 1 | -0.0642 | +0.0179 | +0.0411 | 43.8% |
| 2 | +0.0098 | -0.0162 | +0.0365 | 40.2% |
| 3 | +0.0305 | +0.0223 | +0.0564 | 34.3% |
| 4 | +0.0469 | +0.0483 | +0.1036 | 16.2% |
| 5 | +0.0659 | +0.0888 | +0.1364 | 12.3% |
| 6 | +0.0863 | +0.1034 | +0.1664 | 6.6% |
| 7 | +0.1066 | +0.0896 | +0.1658 | 7.3% |
| 8 | +0.1289 | +0.1750 | +0.1831 | 4.4% |
| 9 | +0.1623 | +0.1730 | +0.1872 | 4.8% |
| 10 | +0.2850 | +0.2255 | +0.2061 | 2.8% |

Three rules were fixed before the run. Two of the three answers are not the
flattering one.

**The ranking is real.** Top decile minus bottom is +0.2360, +0.1546, +0.2321 across
the three draws — positive in every one, with non-overlapping intervals at the
two ends. Qini 0.258. The model is not sorting noise.

**It is not monotone, and it misses the bar that was set for it.** Spearman
0.879, 0.903, 0.952, against a pre-registered 0.9. It clears the weaker
near-monotone threshold of 0.7 in all three draws, and that is
reported as the weaker claim it is rather than rounded up to the stronger one.
Which deciles invert moves between draws; the ordering is right in the large
and unreliable step by step.

**The predictions are about a third too spread out.** Calibration slope
0.799, 0.656, 0.819, mean **0.758** — τ̂ ranges -0.064 to +0.285 where the truth
ranges +0.041 to +0.206. This is the mechanism `experiments/uplift_ab`
suspected and could not show. The policy contacts when `τ̂ × amount` clears the
message cost, a threshold on a product, so an over-spread τ̂ mis-places that
threshold in both directions even with the ranking intact — and it explains why
a bootstrap ensemble that raised correlation to 0.445 recovered no more money.
Bagging shrinks extremes, which moves cases across the threshold both ways.

**The bottom decile locates do-not-disturbs; it does not measure them.**
43.8% of that decile is truly negative-uplift, against 17.3% of the
population and 2.8% of the top decile — a 2.5x enrichment, and that
enrichment is the targeting signal N2 needs. But the decile still averages
+0.0411 true persuadability and realises +0.0179, with an interval covering
zero in every draw, while τ̂ calls it -0.0642. A bin that is 44%
do-not-disturb and 56% ordinary customer nets out slightly positive, and the
model reports it as clearly negative.

That is a calibration failure in precisely the region N2 cares about most, and
it is the strongest argument in this repo for why N2 was built not to rest on
τ̂ alone. The deployed policy's do-not-disturb avoidance (11.5% against
mass-contact's 22.0%) runs through the churn model as a second, independently
identified signal. Had that design leaned on τ̂'s negative predictions being
right, this chart would have found it out.

The slope is **not corrected**. Isotonic recalibration or a shrinkage factor on
τ̂ is the obvious next move, it would change the policy's threshold behaviour,
and it therefore needs its own A/B under the same replication rule as
`experiments/uplift_ab` — not a patch applied here and quoted into the
headline. See `experiments/uplift_calibration/REPORT.md`.

## Do-not-disturbs — novelty claim N2

The agent's do-not-disturb contact rate was, for most of this project's
life, **level with untargeted policies** — 20.1% against random targeting's
20.4%. Avoiding them rested entirely on `τ̂_pay` being correct, and `τ̂_pay`
correlates only ~0.35–0.42 with truth.

The fix is the `λ_churn × P(churn) × LTV` term the spec's EV formula
specifies (section 8.3) and this project originally omitted, on the stated
grounds of having no defensible LTV estimate. That reasoning conflated two
separable things: **P(churn | contact) is learnable from exactly the same
randomised data the uplift model already trains on.** An opt-out is an
observed outcome and the assignment is randomised, so the causal effect of
contact on churn is identified the same way the effect on payment is. Only
the LTV multiplier is an assumption — and one named parameter is very
different from a silently missing term.

It works because it is an **independent** signal: measured on this
simulator, true do-not-disturbs opt out **1.29x** (95% CI 1.09–1.51) more often than others
when contacted. Two models must now both be wrong before a do-not-disturb
gets contacted.

Measured sweep of the parameter (from `λ_churn = 0`):

| λ_churn | Incremental ₹/1000 | Contacts | Do-not-disturb % | ₹/contact |
|---:|---:|---:|---:|---:|
| 0.0 (term off) | 372,590 | 2,051 | 22.5% | 363 |
| 1.0 | 363,648 | 1,533 | 17.3% | 474 |
| 2.0 | 349,048 | 1,219 | 13.8% | 573 |
| **4.0 (default)** | 317,168 | 885 | **11.5**% | **717** |
| 8.0 | 268,071 | 535 | 8.2% | 1,002 |

**λ = 4.0 does not dominate λ = 2.0 — it trades.** An earlier version of this
section said it "strictly dominates", on the strength of a run this repo no
longer reproduces. Re-measured (`make lambda-sweep`), moving from 2.0 to 4.0
costs ₹31,880 per 1,000 cases (9.1% of incremental recovery) and buys
27% fewer contacts and 2.3 points less do-not-disturb exposure. The
two intervals overlap, so the revenue difference is not resolved at this sample
size — but unresolved is not the same as absent, and the script records both
tests separately so the weaker one cannot be quoted as the stronger.

The curve is monotone in both directions across the whole grid: every increase
in λ buys less contact and less do-not-disturb exposure for less money. There
is no free point on it.

**This is a policy choice, not an optimum.** A merchant who prices customer
goodwill differently should set it differently, which is exactly why the
whole curve is published rather than a single number.

## Contact-free recovery — novelty claim N6

```
make fleet
```

Every other lever here decides whether to *contact* someone. This one
recovers revenue by noticing the payment rail is broken and declining to
retry into it. **No customer is messaged to produce this value.**

A two-proportion z-test compares each slice's recent success rate against
its own baseline, so a structurally weak issuer is not flagged merely for
being weak — only for getting *worse*. Attribution then names the dimension
that explains it, because an issuer outage also drags down the aggregate for
every method and region it serves, and an operator needs the root cause
rather than all three.

The detector never sees which issuer is actually out. It has only the
observed attempt stream.

| | blind | fleet-aware |
|---|---:|---:|
| Retries into the degraded issuer | 351 | **0** |
| Gross ₹ recovered | 1,348,020 | 1,389,285 |
| ₹ recovered on outage-hit cases | 20,349 | **61,613** |
| Contacts | 852 | 933 |

**+₹41,264 recovered, all of it on the outage-hit cases**, by stopping 351
futile retries. The cost is 81 extra contacts — the agent switches strategy
on cases where retrying became worthless, which is the honest caveat: the
*detection* is contact-free, and it reallocates effort rather than
eliminating it.

### The detector's own accuracy, and a floor that was set wrong

Measured against ground truth over 60 independent outages, sweeping how much
of the attempt stream the detector gets to see:

| Recent attempts observed | 24 | 60 | 150 | 360 | 900 |
|---|---:|---:|---:|---:|---:|
| Precision | 0.968 | **1.000** | 1.000 | 1.000 | 1.000 |
| Recall | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |

The first version of this detector had a minimum-observations floor of 20
and produced false positives. Adding a minimum effect-size gate barely
helped, which was the clue: the false alarms were not small dips but
genuinely large *apparent* drops from small-sample noise. The floor was
simply too low. At 60+ observations precision is perfect and stays perfect.

The floor is now 60, which makes the detector **decline to judge a thinly
observed slice rather than judge it badly**. That is the correct direction:
a false positive suppresses retries into a *working* issuer and destroys
recovery outright, while a missed detection merely forgoes an optimisation.

## Off-policy evaluation in the deployment loop

```
make ope        # 5,000 training + 4,000 evaluation cases, 20 logging draws per setting
```

Tier 1 proved the estimators recover a known answer on real randomised data.
That establishes the method. It does not establish the thing an operator wants:
**before shipping a new targeting rule, can you value it from logs you already
have, without testing it on customers?**

The deployed EV policy runs with ε-greedy exploration and logs the propensity
score. Six candidate policies — none of them deployed — are then valued from
those logs alone, and every estimate is checked against the truth the simulator
can be asked for. Repeated over 20 independent logging draws, because
coverage from a single log is a coin flip.

**Framing, stated up front:** this is the single targeting decision (contact or
not, once per case), evaluated as a contextual bandit. It is *not*
full-sequence OPE of the multi-step agent loop — importance weights compound
along a trajectory, and that needs sequential estimators this project has not
validated.

### Without exploration, logs can only describe themselves

| ε | policies identified | usable overlap |
|---:|---:|---:|
| 0.00 | 1 / 6 | 1 / 6 |
| 0.05 | 6 / 6 | 4 / 6 |
| 0.10 | 6 / 6 | 6 / 6 |
| 0.20 | 6 / 6 | 6 / 6 |
| 0.40 | 6 / 6 | 6 / 6 |

At ε = 0 one of the two actions has probability zero on every case, so for any
policy that disagrees anywhere the estimand is **not identified** — no quantity
of data recovers it. The single identified policy is the deployed one, which is
not evaluation.

This is why the check is not effective sample size. At ε = 0 the agreeing rows
are numerous and evenly weighted, so **ESS looks healthy while the estimate
answers a different question**: the value of the target policy restricted to the
sub-population the logger agreed with. An early version of `overlap_report`
judged on ESS alone and called those logs usable.

### The estimator is sound. The money is the problem.

Nominal coverage is 95%. Over 20 logging draws × 6 policies:

| ε | coverage, payment rate | coverage, net ₹ | picks the best policy, payment rate | picks the best policy, net ₹ |
|---:|---:|---:|---:|---:|
| 0.05 | 92% | 69% | 18 / 20 | 5 / 20 |
| 0.10 | 100% | 69% | 20 / 20 | 7 / 20 |
| 0.20 | 98% | 77% | 20 / 20 | 13 / 20 |
| 0.40 | 95% | 87% | 20 / 20 | 13 / 20 |

On the **bounded** outcome the estimators do what they claim: at ε = 0.10 every
interval covers the truth and the logs identify the truly best policy in
20 / 20 runs.

On **net rupees** they do not. Coverage runs 69%–87% against a nominal 95%, and at
ε = 0.10 the logs pick the best policy 7 / 20 times.

The cause is the tail, not the method. One opt-out on a large subscription costs
`λ_churn × 6 × invoice`; a single case can move the mean by more than the gap
between two policies. Mean absolute error falls monotonically as exploration
rises (₹231 → ₹147 → ₹120 → ₹92), which is variance shrinking rather than bias being corrected.

**The honest operating rule: choose policies on the bounded outcome, and treat
the rupee figure as an estimate with no coverage guarantee.** That is narrower
than "we can evaluate policies offline", and it is what the measurements
support.

### What exploration costs

At ε = 0.10 the exploring policy earned **₹206 per case against the deployed
policy's ₹227** — about **₹20 per case** to buy the ability to
value any future policy from the same logs.

A real price, stated as one. It is also the price every recovery system pays
either way: a system that never explores is not saving it, it is paying it later
as the cost of A/B testing each change on live customers — without an audit
trail and without a confidence interval.

### The single-seed run would have misled us

The first version ran one logging draw per ε. At ε = 0.10 it reported every
interval covering the truth and the ranking agreeing: a clean pass. Replication
shows that was luck — the real coverage there is 69% and the ranking agrees
35% of the time. Nothing about the code changed between those two
conclusions; only the number of times it was run.

Full detail: `experiments/ope_deployment/REPORT.md`.

## Disparity audit of the policy

```
make fairness     # 4,000 cases, 2,000 permutations, 16 hypotheses
```

The compliance kernel checks whether an **action** is permitted. Nothing else
here checks whether the **policy** distributes its attention fairly. An agent
can refuse every illegal action and still systematically decline to work one
group's cases.

Raw contact-rate gaps prove nothing — the policy contacts on expected value,
uplift times amount, so a group with larger invoices *should* be contacted
more. Every test conditions on predicted uplift crossed with amount, the two
quantities the objective is entitled to use. Because this is a simulator, one
further check is available that no production audit can run: within the same
cells, does the *true* benefit differ? If treatment differs and true benefit
does not, the model invented the difference.

| segment | contact gap, excess over null | p | true-benefit gap | p | verdict |
|---|---:|---:|---:|---:|---|
| language | +0.017 | 0.080 | ₹+30 | 0.046 | no significant gap |
| b2b | +0.056 | 0.001 | ₹+87 | 0.001 | explained |
| amount quartile | +0.146 | 0.001 | ₹+209 | 0.001 | explained |
| loss type | +0.476 | 0.001 | ₹+172 | 0.004 | explained |

**No unexplained disparity in any segment.** The language result is the one
that mattered most going in and it is clean: contact rates run
21–28% across English, Hindi, Hinglish and regional speakers, and
the gap does not survive conditioning.

The detector is not merely incapable of firing:
`tests/test_fairness_audit.py` plants a 25-point within-cell disparity and
requires it to be caught, and plants one fully explained by the conditioning
and requires it not to be.

### The finding the treatment-rate tests cannot see

Correlation between predicted and true uplift, by group:

| group | correlation | contact rate |
|---|---:|---:|
| **B2B** | **0.11** | 0.311 |
| B2C | 0.36 | 0.241 |
| **Amount Q1 (smallest)** | **0.09** | 0.302 |
| Amount Q3 | 0.33 | 0.132 |
| every language | 0.31 – 0.35 | 0.21 – 0.28 |

Language is even. The other two are not, and the pattern is uncomfortable:
**the policy acts most confidently on the segments the model understands
least.** B2B gets the highest contact rate (31.1% against 24.1%) and has the
worst model correlation (0.11 against 0.36). The smallest invoices have a
correlation of 0.09 — effectively no signal — and are contacted more than
the quartiles the model reads best.

That is not disparate treatment. It is **epistemic** inequality, and an audit
that only checks contact rates passes it without comment.

### Two targeting failures, surfaced in passing

Descriptive, not significance-tested:

- **Amount Q2 and Q3 are the wrong way round.** Q3 is worth ₹353 per case —
  the highest in the book — and gets the lowest contact rate (13.2%). Q2 is
  worth ₹239 and gets the highest (34.8%).
- **Overdue receivables have negative true value** (₹-69 per case: contact
  destroys more through opt-outs than it recovers) and are still contacted
  20.2% of the time.

### What "contact" had to be corrected to mean

The first version measured only customer contact and reported failed
subscriptions at 0.9% — apparently the most neglected group in the book.
They are not: the policy works **100%** of them, by silent retry, because a
subscription can be re-charged without messaging anyone. Measuring contact
alone read correct channel choice as neglect. Both rates are now reported —
the same distinction the kernel already makes when it exempts RETRY from the
contact-hours rule.

Two further methodology errors, both caught and both documented in
`experiments/fairness/REPORT.md`: a gap statistic that could not report zero,
and a multiple-comparison correction applied to the test where it made crying
wolf *easier* rather than harder.

## Acting on a lower bound instead of a point estimate

```
make pessimism    # 5,000 training + 4,000 evaluation cases, 3 draws, 20-model ensemble
```

The disparity audit found the policy doing two things badly. Overdue
receivables are worth **−₹69 per contact** — contact destroys more through
opt-outs than it recovers — and the policy contacts 20.2% of them anyway. The
smallest invoices get the model's *highest* predicted uplift and its worst
correlation with truth (0.09).

Both are the same failure. `τ̂ = 0.02` from a model that understands a segment
and `τ̂ = 0.02` from a model that is guessing produce identical decisions,
because a point estimate cannot tell them apart.

`BootstrapEnsembleModel` fits the same learner on 20 bootstrap resamples and
reports a per-case standard error; the policy acts on **τ̂ − k·se**. k = 0 is
exactly the deployed policy, so the sweep's origin is what ships rather than a
separate branch.

### The ensemble improves the estimate before any caution is applied

Correlation with true persuadability, both models scored on the **same**
evaluation populations:

| model | mean | per draw |
|---|---:|---|
| single T-learner (deployed) | 0.364 | 0.364, 0.371, 0.357 |
| **20-model bootstrap ensemble** | **0.459** | 0.455, 0.467, 0.454 |

A consistent **+0.095** in every draw, from averaging alone. The matched
comparison matters: quoting the ensemble against the 0.347 published elsewhere
would be comparing across different evaluation populations, which is not a
comparison.

### What caution buys, and what it costs

Mean over 3 draws:

| k | contacts | net ₹/case | ₹/contact | harmful contacts | % harmful |
|---:|---:|---:|---:|---:|---:|
| 0.00 | 1,047 | ₹183 | ₹699 | 79 | 7.5% |
| 0.25 | 878 | ₹186 | ₹849 | 53 | 6.1% |
| 0.50 | 713 | ₹192 | ₹1,075 | 34 | 4.8% |
| 1.00 | 432 | ₹172 | ₹1,592 | 15 | 3.5% |
| 1.50 | 233 | ₹167 | ₹2,874 | 8 | 3.6% |
| 2.00 | 99 | ₹162 | ₹6,524 | 4 | 3.7% |

"Harmful" means the case's *true* expected value of contact is negative — a
quantity only a simulator can supply, and the cleanest statement of what a
point estimate was costing.

**The net-value gain is small and not stable. The harm reduction is large and
consistent.** Best k lands at [0.5, 0.5, 0.25] across the three draws, improving net value
by ₹4–₹14 per case — so it is reported as a **range, k ≈ 0.25–0.5, not
a tuned value**. At k = 0.5 the agent sends **32% fewer messages**, cuts
harmful contacts **79 → 34**, and lifts value per contact from
**₹699 to ₹1,075**.

Past k = 0.5 the curve turns: k = 1.0 sends 432 messages and earns
₹172/case, *below* k = 0. Caution keeps buying harm reduction long
after it stops buying money, which is a real trade to state rather than a
number to tune.

**A single draw would have reported this as a clean +7.4% win.** It is not;
the third draw improves by ₹4/case, a fifth of the first two. That is the
third time in this project a single-draw conclusion has failed replication.

Full detail: `experiments/pessimism/REPORT.md`.

## Reply-intent listener — spec section 8.5

```
make listener-eval    # needs a local Ollama running qwen2.5:3b
```

Free-text customer replies, in English, Hindi and Hinglish, classified into
the structured intent the agent loop acts on.

| | Gold set (hand-authored) | LLM-generated personas |
|---|---:|---:|
| Examples | 42 | 91 |
| Accuracy | **95.2%** | 44.0% |
| English | 100% | 62.5% |
| Hinglish | 92% | 42.3% |
| Hindi | 92% | 27.3% |

`promise_to_pay` — the metric spec 11.2 asks for by name — reaches precision
**0.88** / recall **1.00** on the gold set.

**Both columns are reported, and the second one is bad.** The generated corpus
scores 44.0%, and inspection showed why: an LLM asked to write a customer
reply *for a given intent* writes a reply that is ambiguous between intents,
so a large part of that number is the corpus being wrong rather than the
classifier. It is kept here because deleting the unflattering half of an
evaluation is how evaluations stop meaning anything — and because the gap
between 95.2% and 44.0% is the honest measure of how much this result depends
on the test set being real.

**Opt-out is deliberately not left to the model.** Measured alone, the LLM
recalled only 0.57 of opt-outs and every miss was Hindi or Hinglish. Missing
one is a TCCCPR violation, not a lost sale, so a deterministic detector runs
first and overrides the classifier — taking opt-out to precision
**1.00** and recall **1.00**. Same argument as the compliance kernel,
applied one level down: the thing that must not be wrong does not get to be
probabilistic.

## Negotiation and Section 43B(h)

```
make negotiate
```

For B2B receivables the agent negotiates rather than merely chases. The
division of labour is the design:

| | Decides |
|---|---|
| **Section 43B(h) clock** | what leverage exists |
| **NPV solver** | what may be conceded, and whether to bother |
| **Compliance kernel** | whether that concession is permitted at all |
| **LLM** | the sentence — using only supplied figures |

**The India-specific lever.** Under Section 43B(h) (Finance Act 2023), a
buyer who does not pay an MSME supplier within the MSMED Act's 45-day window
cannot claim that expense as a deduction *in the year it was incurred*.
Precision matters here: the deduction is **deferred to the year of actual
payment, not forfeited**. The loose version — "you lose the deduction" — is
wrong, and a CFO would know it instantly.

That inverts the negotiation. A normal dunning agent asks a buyer to do
something that costs them money. This one points at something in the
buyer's *own* interest.

The solver's most interesting behaviour follows directly:

> **No discount offered:** 13 days remain in the counterparty's 45-day MSME
> window, so settling early is already in their interest under Section
> 43B(h). **Leverage, not margin.**

Breakeven discounts are computed, not guessed — `d = 1 − (1+r)^(−days/365)`,
so at 18% cost of capital a 90-day delay justifies at most 4.00%, and the
merchant's envelope then clips it further.

**The envelope is enforced by the kernel, not by the solver.** On the happy
path the rule never fires, because the solver already respects the bounds —
which is exactly why it belongs in the kernel. Conceding margin is a
money-affecting action, and this project's position is that such actions are
permitted by a deterministic gate rather than by the good behaviour of
whatever proposed them. On the ₹900,000 scenario the kernel returns **DENY**
and no message is drafted at all.

### Where the LLM was measured and then removed

Negotiation drafting defaults to a **deterministic template**, and that is a
finding rather than caution. With numeric grounding passing, qwen2.5:3b
still produced drafts that were legally wrong:

- *"Settling now will allow you to **claim** a deferral cost of Rs 10,200"* —
  inverted; settling *avoids* it
- *"the MSME payment window closed **45 days** ago"* — it had closed 35 days
  ago; the model conflated the window's length with elapsed time. **Both
  figures were legitimately supplied, so the grounding check could not catch
  it**
- *"the associated **penalty** under Section 43B(h)"* — there is no penalty

Numeric grounding checks numbers, not meaning. A fluent, confident, wrong
statement about a counterparty's tax position is worse than a plain correct
one, and would destroy the credibility the whole 43B(h) argument rests on.
So the template is the default and the LLM is opt-in for contexts where a
human reviews the wording — the same judgement as the compliance kernel,
reached the same way: by measuring where a model is trustworthy rather than
assuming it either way.

## Compliance — B2 and B4

```
make redteam
```

| | Result |
|---|---|
| Named adversarial attacks blocked | **20 / 20 (100%)** |
| Hostile policy: contacts executed without an ALLOW certificate | **0** (of 323 attempted) |
| Randomised fuzz leaks (5,000 states) | **0** |
| Certificate coverage | 100%, structural |
| Ledger hash chain | valid on every run |

**Mutation-tested, because a suite that cannot fail proves nothing.**
Sabotaging one rule (contact hours → always pass) produces **31 violations**
— 3 named attacks and 28 fuzz leaks — and restoring it returns a clean 0.
The fuzz layer catches ~9x more leaking states than the handwritten attacks,
which is the argument for having it.

The suite also asserts **no legitimate action is wrongly blocked** — a kernel
that denied everything would score a perfect 100% and be useless.

---

## B3 — stopping rules

```
pytest tests/test_all_stopping_rules.py
```

- **8 of 11** reasons fire naturally in a real 2,000-case batch.
- **11 of 11** are proven reachable by
  `test_every_stopping_rule_is_reachable`, which fails the build if any rule
  becomes unreachable.

Both numbers are reported because they answer different questions. The three
that do not occur naturally need conditions a normal batch does not produce
(`global_kill_switch`, an engaged operator halt; `regulatory_ceiling`, a
kernel denying every available action; and `promise_to_pay_active` — which is now a
*pause* that resolves later rather than a termination).

---

## Honest exception list

655 cases in the last batch did not recover. They are enumerated with
reasons by `exception_report()` in `src/recovery_ledger/agent/runner.py` —
cases still paused awaiting a promised payment at the horizon, and cases
that terminated without the money arriving. Published rather than hidden,
per spec section 11.2.

---

## Reproducing everything

```
make setup        # create venv, install
make test         # 128 tests
make demo         # agent loop, 20 cases, no external services needed
make eval         # B1 headline
make baselines    # policy comparison
make sensitivity  # ranking stability
make calibration  # uplift by decile
make redteam      # adversarial suite
```

All experiments are deterministic (fixed seeds; each has been run twice and
diffed byte-identical) and have been verified from a clean `git clone`.
