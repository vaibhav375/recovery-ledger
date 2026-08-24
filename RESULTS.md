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
on Hillstrom (balanced 50/50 arms), materially off on Criteo (85/15
imbalance). Diagnosed as outcome-model calibration on the minority arm,
partially fixed by refitting per-arm, not fully closed. Documented in
`experiments/tier1_criteo/REPORT.md` rather than dropped from the table.

---

## B1 — measured money recovered across a batch

```
make eval        # 5,000 training + 2,000 evaluation cases
```

| | Treatment | Holdout (no contact) |
|---|---:|---:|
| Recovery rate | 37.13% | 15.47% |

**Incremental ₹ recovered per 1,000 at-risk cases: ₹310,910 (95% CI ₹150,240 – ₹471,072)**

The holdout recovers **15.47% of cases with no agent at all**. That is why
this project reports incremental rather than gross: a vendor quoting the
gross figure would be taking credit for every rupee in that column.

Supporting diagnostics from the same run: uplift correlation with true
(hidden) persuadability **0.349**; **817 contacts** sent; do-not-disturb
contact rate **16.8%**; 8 of 11 stopping reasons fired naturally; 34,173
ledger entries, hash chain verified; 673 cases published to the exception
list.

---

## Baselines — spec section 11.3, plus a falsification control

```
make baselines
```

Common random numbers across policies, paired bootstrap, same 2,000 cases.

| Policy | Incremental ₹/1000 | Contacts | ₹ per contact | % to do-not-disturbs |
|---|---:|---:|---:|---:|
| do_nothing | — (reference) | 0 | — | — |
| blast_everyone | 330,108 | 4,339 | 152.2 | 20.19% |
| rules_based_dunning | 330,108 | 4,339 | 152.2 | 20.19% |
| razorpay_current | 86,648 (**CI includes 0**) | 0 | — | — |
| random_targeting | 119,671 | 2,021 | 118.4 | 20.39% |
| ev_policy_no_churn | 340,988 | 2,257 | 302.2 | 20.12% |
| **ev_policy_greedy** | 301,018 | **1,339** | **449.6** | **13.59%** |
| ev_policy_lookahead | 300,677 | 1,318 | 456.3 | 13.81% |

**The result that matters: 2.85x more incremental recovery than random
targeting at comparable contact volume, with non-overlapping confidence
intervals.** Without this control the headline would be uninterpretable —
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
**retrained at every setting**.

| Claim | Holds at |
|---|---|
| **C1 — targeting beats matched-volume random targeting** | **25 / 25 settings** (margin 1.65x–4.24x) |
| C2 — targeting is more contact-efficient than mass-contact | 24 / 25 settings |

C1 never flips, including in the two settings constructed to break it (zero
annoyance decay, so persistence is never punished; zero amount↔liquidity
coupling, so the amount weighting carries no hidden signal).

**The single C2 flip is stated, not averaged.** At
`base_organic_resolution = 0.12`, mass-contact wins: when 12% of cases fix
themselves there is little incremental value left to target, learned τ̂
shrinks toward zero, and the selective policy correctly declines while brute
force scrapes up the remainder. "C2 holds except when organic recovery is
very high" is the truthful phrasing; "holds 96% of the time" would hide the
exact condition under which it fails.

**Best finding in the sweep, and it was not one I set out to test:** as the
amount↔liquidity coupling strengthens — high-value cases becoming
increasingly likely to be do-not-disturbs — the targeting advantage *widens*
from 1.75x to **4.24x** while mass-contact collapses from ₹1,015,545 to
₹197,499. **The harder the do-not-disturb problem, the more targeting is
worth.** Novelty claim N2 as a measured gradient rather than an assertion.

---

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
simulator, true do-not-disturbs opt out **1.93x** more often than others
when contacted. Two models must now both be wrong before a do-not-disturb
gets contacted.

Measured sweep of the parameter (from `λ_churn = 0`):

| λ_churn | Incremental ₹ | Contacts | Do-not-disturb % | ₹/contact |
|---:|---:|---:|---:|---:|
| 0 (term off) | 681,976 | 2,257 | 20.1% | 302 |
| 1.0 | 647,098 | 1,938 | 18.1% | 334 |
| 2.0 | 603,882 | 1,705 | 16.5% | 354 |
| **4.0 (default)** | 602,036 | 1,339 | **13.6%** | **450** |
| 8.0 | 517,442 | 899 | 10.8% | 576 |

**λ = 4.0 is the default because it strictly dominates λ = 2.0** — the same
total recovery using 21% fewer contacts and reaching meaningfully fewer
do-not-disturbs. Beyond it the trade turns real: λ = 8.0 buys another 2.8
points of do-not-disturb avoidance for 14% of incremental recovery.

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

- **7 of 11** reasons fire naturally in a real 2,000-case batch.
- **11 of 11** are proven reachable by
  `test_every_stopping_rule_is_reachable`, which fails the build if any rule
  becomes unreachable.

Both numbers are reported because they answer different questions. The four
that do not occur naturally need conditions a normal batch does not produce
(an engaged operator kill switch, a kernel denying every action, a case
where nothing is ever worthwhile, and promise-to-pay — which is now a
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
make redteam      # adversarial suite
```

All experiments are deterministic (fixed seeds; each has been run twice and
diffed byte-identical) and have been verified from a clean `git clone`.
