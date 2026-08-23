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

**2026-08-24, ₹284,957 → ₹258,796 — a genuine formula bug in the EV
objective.** Auditing the newly-written code (rather than only the
methodology) turned up an apples-to-oranges comparison inside the EV
calculation itself. NUDGE was valued at `τ̂ × amount`, where τ̂ is an
**incremental** effect (CATE = P(pay|contact) − P(pay|no contact)). RETRY was
valued at `p_retry × amount`, where `p_retry` is an **absolute** probability.
Both went into the same `max()`. The spec's formula is explicitly
`Δp_pay(action) × ₹amount` (section 8.3) — a *delta* for every action.

The effect was to overvalue RETRY by `base_resolution_prob × amount` (0.05 ×
amount) on every case — roughly a 40% overstatement of retry's relative worth
at the mean case size — systematically pushing the policy toward retrying
when it should have been nudging or waiting. A hard-decline retry, which
succeeds 1% of the time against a 5% organic rate and is therefore *worth
nothing*, was being valued at `0.01 × amount`.

Fixed by introducing `_retry_incremental_prob()` = `max(p_retry − base, 0)`.

**This also substantially resolved the do-not-disturb problem reported
earlier the same day.** The EV policy's do-not-disturb contact rate fell from
**22.1% to 20.2%** — no longer worse than random targeting (20.4%) or
mass-contact (20.2%). That earlier "unflattering finding" was, in significant
part, a symptom of this bug rather than an inherent tension in the objective:
overvaluing RETRY distorted the whole action mix. The structural pressure
described there is real and still present, but it is much smaller than it
looked.

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
| Recovery rate | 34.43% | 15.47% |
| Gross ₹ recovered | 771,443 | 469,727 |
| Gross ₹ recovered per case | 744 | 488 |

**Incremental ₹ recovered per 1,000 at-risk cases: ₹258,796 (95% CI: ₹101,137 – ₹426,996)**

CI excludes zero. The holdout arm recovers 15.47% of cases entirely on its
own — exactly why this project reports incremental rather than gross. A
vendor quoting the ₹771,443 gross figure would be taking credit for the
₹469,727 that arrives with no agent at all.

## Does the targeting actually work? (the falsification test)

"Same recovery as mass-contact with far fewer contacts" is only evidence
about *targeting* if a policy contacting a similar number of cases **at
random** does measurably worse. Otherwise the result says something about
diminishing returns to contact volume and nothing about the uplift model.
`RandomTargetingPolicy` is that control:

| | Contacts | Incremental ₹/1000 (95% CI) | Incremental ₹ per contact |
|---|---:|---:|---:|
| random_targeting | 2,021 | 119,671 (75,027–165,618) | 118.4 |
| **ev_policy_greedy** | 2,259 | **340,988 (274,088–408,856)** | **301.9** |

**2.85x the incremental recovery at a comparable contact volume, with
non-overlapping confidence intervals**, and 2.5x more incremental rupees
earned per contact spent. That is the evidence that the uplift model — not
merely contact volume — is doing the work.

## 5-baseline comparison (spec section 11.3)

```
uv run python experiments/tier2_simulation/run_baselines.py --n-train 5000 --n-eval 2000
```

All 7 policies (the spec's 5, the matched-volume random control, and both EV
variants) run against the SAME 2,000-case eval batch under **common random
numbers**, with incremental ₹ computed against `do_nothing` on the same cases
using a **paired** bootstrap.

| Policy | Recovery rate | Incremental ₹/1000 (95% CI) | Contacts | Incremental ₹/contact | Cost per incremental ₹ | % to do-not-disturbs |
|---|---:|---:|---:|---:|---:|---:|
| do_nothing | 14.25% | — (reference) | 0 | n/a | n/a | n/a |
| blast_everyone | 36.40% | 330,108 (249,085–421,457) | 4,339 | 152.2 | 0.004081 | 20.19% |
| rules_based_dunning | 36.40% | 330,108 (249,085–421,457) | 4,339 | 152.2 | 0.004081 | 20.19% |
| razorpay_current | 16.35% | 86,648 (-16,693–193,109) | 0 | n/a | n/a | n/a |
| random_targeting | 23.55% | 119,671 (75,027–165,618) | 2,021 | 118.4 | 0.005232 | 20.39% |
| **ev_policy_greedy** | 36.45% | **340,988 (274,088–408,856)** | 2,259 | 301.9 | **0.002012** | 20.19% |
| ev_policy_lookahead | 36.45% | 340,988 (274,088–408,856) | 2,253 | 302.7 | 0.002007 | 20.15% |

Chart: `experiments/tier2_simulation/baselines_comparison.png`.

### What this shows

- **Against blind mass-contact**: the EV policy edges it on recovery
  (340,988 vs 330,108 — overlapping CIs, so treat as a tie) using **48%
  fewer contacts**, at 2x the incremental rupees per contact and 2x better
  cost per incremental rupee.
- **Against matched-volume random targeting**: 2.85x the incremental
  recovery, CIs non-overlapping. The targeting is real.
- **`razorpay_current`'s CI includes zero** — a single automated retry then
  halting is not reliably better than doing nothing at all in this
  simulation. That is precisely the unowned gap spec section 3.3 describes.
- **Greedy and lookahead now perform identically** on recovery (differing by
  6 contacts out of ~2,255). Once the EV formula was corrected, the lookahead
  reformulation stopped mattering — worth stating, since an earlier version
  of this report credited it with more than it deserves.

### On do-not-disturbs — a correction to an earlier finding

An earlier version of this report flagged, prominently, that the EV policy
contacted *more* true do-not-disturbs (22.1%) than random targeting (20.4%).
After fixing the incremental-vs-absolute bug above, that rate fell to
**20.19%** — level with mass-contact and slightly better than random. The
earlier finding was largely a **symptom of the bug**, not an inherent
property of the objective.

What remains true, and still falls short of novelty claim N2's aspiration:
the policy is only *comparable* to untargeted policies at avoiding
do-not-disturbs, not meaningfully better, and nowhere near the ≈0 target.
The structural pressure is real — amount at risk and true persuadability
correlate **-0.45** in this simulator (the high-amount half of the
population is **28.2% do-not-disturbs against the low-amount half's 6.0%**),
so a `τ̂ × amount` objective is inherently drawn toward the cases most likely
to be do-not-disturbs. Properly countering it needs the
`λ_churn × P(churn) × LTV` term the spec's full formula includes and this
implementation omits for lack of any defensible LTV estimate. That remains
the top open problem.

## What this experiment still does NOT include

- **No sensitivity sweep** over the response model's parameters — spec
  section 7.3 requires this before any result here can be called more than
  a single point estimate. Especially warranted given how much the
  do-not-disturb finding above depends on one modelling choice (the
  amount↔liquidity coupling).
- **Do-not-disturb contact rate is 20.2%** — level with untargeted policies,
  not meaningfully better, and nowhere near the ≈0 target novelty claim N2
  aspires to. The single most important open problem in this project.
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
