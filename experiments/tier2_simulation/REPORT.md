# Tier 2 batch experiment — B1 headline result

**Every number below was produced by `run_batch.py` / `run_baselines.py` in
this directory, run on 2026-08-24.** Two earlier headline figures have been
withdrawn — see "Revision history" below before citing anything here. Reproduce with `make eval`
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

## Revision history — read this before the numbers

This report has been revised twice, both times because a check turned up a
real defect rather than because the numbers were merely re-tuned. Both
withdrawn figures are recorded here rather than quietly replaced.

**2026-08-23, ₹996,519 — WITHDRAWN, was an artifact.** The first run
reported a suspiciously clean result: only 1.52% of contacts going to
predicted do-not-disturbs. Checked the next day rather than assumed:
`sim/environment.py`'s `generate_population()` drew every hidden trait
**fully independently of every observable case field**. Since the true
treatment effect (`persuadability()`) is a function only of those hidden
traits, it was **statistically independent of every feature the uplift
model was trained on, by construction** — nothing to learn, no matter how
good the learner. Confirmed by computing `corr(tau_hat, tau_true)` on
held-out data: **-0.02**. The 1.52% figure wasn't targeting skill; the true
population do-not-disturb rate was itself ~1.5%, so random targeting scored
about the same by coincidence. Fixed by giving traits a declared, measured
dependence on observable fields (correlation now rises monotonically with
training size: 0.15 → 0.24 → 0.42 at n=1000 → 2000 → 5000, the shape that
distinguishes real signal from an artifact). Now computed and regression-
tested on every run.

**2026-08-24, ₹220,074 — SUPERSEDED by two agent bugs, not by re-tuning.**
The first 5-baseline comparison showed the EV policy *losing to blindly
contacting everyone*. Rather than accept or tune that, it was instrumented —
after two wrong hypotheses (annoyance-cost miscalibration, ruled out by
sweeping `lambda_annoyance` to 0 and seeing recovery move only
30.60%→31.25%; and missing multi-attempt compounding, ruled out by building
a lookahead policy that changed almost nothing). Instrumenting the actual
action mix and stop reasons found two genuine defects:

1. **A single denied action killed the whole case.** `agent/loop.py` mapped
   any kernel `DENY` straight to `REGULATORY_CEILING` and terminated. Spec
   section 10, rule 10 is "the kernel denies *all remaining* actions". The
   EV policy prefers RETRY on mandate cases, ~half of which the 24-hour
   pre-debit-notice rule denies — so **240 of its cases were killed outright
   while `blast_everyone`, which never proposes RETRY, tripped that rule
   zero times.** An artificial penalty for using more of the action space.
   Now the loop falls back to WAIT (exempt from every contact rule) and only
   stops when that is denied too.
2. **The policy abandoned cases where waiting was free.** `EVDecisionPolicy`
   returned STOP whenever no action had positive EV — treating STOP and WAIT
   as equivalent. They are not: WAIT costs nothing, contacts nobody, and
   preserves organic self-resolution. Measured consequence: the EV policy
   recovered only **8.1% of overdue receivables against do-nothing's 13.9%**
   — actively worse than having no agent at all on that segment.

Both are fixed, both have regression tests, and together they closed
essentially the whole gap to the naive baselines (EV policy gross went
1,131,714 → 1,595,699 on the comparison batch).

**2026-08-24, ₹376,484 → ₹284,957 — a methodology change, not a bug fix.**
Two statistical defects were found while auditing the comparison design
itself:

1. **The simulator used one shared RNG stream.** A given case therefore saw
   different random draws under different policies, purely because the
   policy made a different number of calls before reaching it — pure noise
   with no informational content, in an experiment whose entire purpose is
   ranking policies. Now each case draws from its own stream seeded from
   (seed, case_id): a proper **common random numbers** design.
2. **The baseline comparison used an unpaired bootstrap on paired data.**
   Both arms are measured on the *same* cases in the same order, so case
   indices must be resampled once and applied to both arms. `run_batch.py`
   correctly keeps the unpaired version, since its treatment and holdout
   arms are disjoint splits of different cases.

Neither changes any conclusion; the headline point estimate moved because
the random draws changed, and the baseline CIs tightened because the paired
bootstrap no longer discards the correlation between arms.

## Method

1. **Train** (n=5000): generate cases, randomly assign contact/no-contact
   50/50 (a mini RCT against the simulator, same logic Tier 1 validated on
   real data), observe outcomes, fit a T-learner (`policy/uplift/learners.py`
   — the same class Tier 1 validated) on the result.
2. **Eval** (n=2000, disjoint from training — different seed, no case
   overlap): split ~50/50 into a **treatment arm** (full agent loop,
   `LookaheadEVDecisionPolicy` driven by the fitted uplift model, all 11
   compliance rules active) and a **randomised no-contact holdout arm**
   (`DoNothingPolicy` — always WAIT, same attempt budget).

## Result

| | Treatment (n=1037) | Holdout (n=963) |
|---|---:|---:|
| Recovery rate | 34.81% | 15.47% |
| Gross ₹ recovered | 801,323 | 469,727 |
| Gross ₹ recovered per case | 773 | 488 |

**Incremental ₹ recovered per 1,000 at-risk cases: ₹284,957 (95% CI: ₹128,725 – ₹451,483)**

CI excludes zero. The holdout arm recovers 15.47% of cases entirely on its
own — which is exactly why this project reports incremental rather than
gross. A vendor quoting the ₹801,323 gross figure would be taking credit for
the ₹469,727 that arrives with no agent at all.

## Does the targeting actually work? (the falsification test)

"Same recovery as mass-contact with far fewer contacts" is only evidence
about *targeting* if a policy contacting the same number of cases **at
random** does measurably worse. Otherwise the result would just be saying
something about diminishing returns to contact volume, and nothing about the
uplift model. So `RandomTargetingPolicy` was added as a matched-volume
control, and it happened to land at exactly the same contact count as the
greedy EV policy — 2,021 apiece, an unusually clean comparison:

| | Contacts | Incremental ₹/1000 (95% CI) | Incremental ₹ per contact |
|---|---:|---:|---:|
| random_targeting | 2,021 | 119,671 (75,027–165,618) | 118.4 |
| **ev_policy_greedy** | **2,021** | **340,000 (271,213–407,782)** | **336.5** |

**2.8x the incremental recovery from the identical number of contacts, with
non-overlapping confidence intervals.** That is the evidence that the uplift
model — not merely contact volume — is doing the work.

## 5-baseline comparison (spec section 11.3)

```
uv run python experiments/tier2_simulation/run_baselines.py --n-train 5000 --n-eval 2000
```

All 7 policies (the spec's 5, the matched-volume random control, and both EV
variants) run against the SAME 2,000-case eval batch, using **common random
numbers** (each case draws from its own RNG stream, so a case's luck doesn't
depend on what the policy did to other cases). Incremental ₹ is computed
against `do_nothing` on the same cases, with a **paired** bootstrap.

| Policy | Recovery rate | Incremental ₹/1000 (95% CI) | Contacts | Incremental ₹/contact | Cost per incremental ₹ | % to do-not-disturbs |
|---|---:|---:|---:|---:|---:|---:|
| do_nothing | 14.25% | — (reference) | 0 | n/a | n/a | n/a |
| blast_everyone | 36.40% | 330,108 (249,085–421,457) | 4,339 | 152.2 | 0.004081 | 20.19% |
| rules_based_dunning | 36.40% | 330,108 (249,085–421,457) | 4,339 | 152.2 | 0.004081 | 20.19% |
| razorpay_current | 16.35% | 86,648 (-16,693–193,109) | 0 | n/a | n/a | n/a |
| random_targeting | 23.55% | 119,671 (75,027–165,618) | 2,021 | 118.4 | 0.005232 | 20.39% |
| **ev_policy_greedy** | 36.45% | **340,000 (271,213–407,782)** | 2,021 | **336.5** | **0.001803** | 22.12% |
| ev_policy_lookahead | 36.30% | 336,529 (267,698–404,717) | 1,972 | 341.3 | 0.001777 | 22.57% |

Chart: `experiments/tier2_simulation/baselines_comparison.png`.

### What this shows

- **Against blind mass-contact**: the EV policy matches or slightly exceeds
  it on recovery (340,000 vs 330,108, overlapping CIs — treat as a tie) using
  **53% fewer contacts**, at 2.3x better cost per incremental rupee.
- **Against matched-volume random targeting**: 2.8x the incremental recovery
  from the same 2,021 contacts, CIs non-overlapping. The targeting is real.
- **`razorpay_current`'s CI includes zero** — a single automated retry then
  halting is not reliably better than doing nothing at all, in this
  simulation. That is precisely the gap spec section 3.3 describes.

### The result that is NOT flattering

**The EV policy contacts a higher share of true do-not-disturbs than either
random targeting or mass-contact** (22.1% vs 20.4% and 20.2%). Since
avoiding do-not-disturbs (N2) is a headline novelty claim, this deserves to
be stated plainly rather than buried.

Investigated rather than excused. In this simulator, amount at risk and true
persuadability are **negatively correlated (-0.45)** by construction: larger
amounts imply lower liquidity, which lowers persuadability. Measured
consequence — the high-amount half of the population is **28.2%
do-not-disturbs against the low-amount half's 6.0%**. The EV criterion is
`τ̂ × amount`, so it is structurally drawn toward high-amount cases, which
are exactly the ones most likely to be true do-not-disturbs. Where the
model's τ̂ is wrong (correlation with truth is ~0.35–0.42, not 1.0), the
amount term dominates and pulls it into contacting them.

This is a genuine tension in the EV formulation, not a coding defect: the
policy is optimising expected rupees, and expected rupees and
do-not-disturb-avoidance genuinely conflict in this population. Fixing it
properly means pricing the true cost of contacting a do-not-disturb (churn,
complaints, TCCCPR complaint-threshold exposure) into the objective rather
than treating annoyance as a flat per-attempt penalty — which is the
`λ_churn × P(churn) × LTV` term the spec's full formula has and this
implementation deliberately omits for lack of any defensible LTV estimate.
Named as the top candidate for the next round of work rather than patched
over.

## What this experiment still does NOT include

- **No sensitivity sweep** over the response model's parameters — spec
  section 7.3 requires this before any result here can be called more than
  a single point estimate. Especially warranted given how much the
  do-not-disturb finding above depends on one modelling choice (the
  amount↔liquidity coupling).
- **Do-not-disturb contact rate is 22.1%, worse than random targeting's
  20.4%** — see "The result that is NOT flattering" above. The single most
  important open problem in this project.
- **The `λ_churn × P(churn) × LTV` term is omitted** from the EV formula,
  for lack of any defensible LTV estimate. That omission is the direct cause
  of the do-not-disturb problem.
- **Only the T-learner is used in reported runs.** S/X-learner were measured
  and are comparable (correlations 0.42 / 0.37 vs T's 0.40). The causal
  forest is **not usable on this feature set**: it emits CATE estimates
  outside the mathematically possible [-1, 1] range for a probability
  difference (mean -1.23, std 4.43, 29% in range). Removing feature
  collinearity improved it materially (to 60% in range) but did not fix it;
  root cause unidentified, so it is excluded and documented rather than
  reported.
- **`cost_per_incremental_rupee` counts channel costs only** — not annoyance,
  churn, or complaint-handling cost.
- **First-contact CATE only** — RETRY's effect is a fixed calibrated
  constant, not learned; NEGOTIATE/ESCALATE_HUMAN aren't in training data.
- **The lookahead policy's `p_resolve` is approximated** as
  `base_resolution_prob + τ̂`, because the uplift model estimates an
  incremental effect, not an absolute payment probability. That
  approximation is the policy's weakest link, which is why
  `base_resolution_prob` is an explicit parameter rather than a buried
  constant.
