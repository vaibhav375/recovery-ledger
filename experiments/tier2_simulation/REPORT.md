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
| Recovery rate | 33.75% | 15.37% |
| Gross ₹ recovered | 880,178 | 454,814 |
| Gross ₹ recovered per case | 849 | 472 |

**Incremental ₹ recovered per 1,000 at-risk cases: ₹376,484 (95% CI: ₹203,979 – ₹554,243)**

CI excludes zero. Note the holdout arm recovers 15.37% of cases entirely on
its own — that is precisely why this project reports incremental rather
than gross. A vendor quoting the ₹880,178 gross figure would be taking
credit for the ₹454,814 that would have arrived with no agent at all.

## Policy quality

- **uplift_model_correlation_with_true_persuadability: 0.42.** Real, but
  far from perfect — a genuinely hard prediction problem with a T-learner on
  5,000 noisy Bernoulli outcomes, the same signal-to-noise challenge Tier 1
  flagged for Criteo's 0.29% conversion rate.
- **905 contacts sent, 167 (18.45%) to true-negative-uplift cases.** Not
  close to spec's ≈0 target, and slightly *worse* than the 16.26% recorded
  before the loop fixes — a direct, expected consequence of those fixes:
  cases that were previously killed outright by a single kernel denial now
  stay alive and get contacted, so more do-not-disturbs get reached. Real
  tradeoff, reported rather than buried.
- **100% certificate coverage**, structurally guaranteed by the loop design.
- **Ledger**: 33,301 entries, hash chain verified valid.

## 5-baseline comparison (spec section 11.3)

```
uv run python experiments/tier2_simulation/run_baselines.py --n-train 5000 --n-eval 2000
```

All 6 policies (the spec's 5, plus both EV variants) run against the SAME
2,000-case eval batch. Incremental ₹ here is computed against `do_nothing`'s
outcome on that same batch — a different design from the headline number
above (which uses a genuine random holdout split), answering "how does each
policy rank against named alternatives on identical cases".

| Policy | Recovery rate | Incremental ₹/1000 (95% CI) | Contacts | Channel cost | Cost per incremental ₹ | % to do-not-disturbs |
|---|---:|---:|---:|---:|---:|---:|
| do_nothing | 13.85% | — (reference) | 0 | 0 | n/a | n/a |
| blast_everyone | 35.90% | 355,209 (233,271–473,252) | 4,393 | 1,347 | 0.003792 | 20.49% |
| rules_based_dunning | 35.90% | 355,209 (233,271–473,252) | 4,393 | 1,347 | 0.003792 | 20.49% |
| razorpay_current | 16.55% | 130,228 (6,823–256,378) | 0 | 0 | n/a | n/a |
| ev_policy_greedy | 34.15% | 348,644 (230,016–480,680) | 1,794 | 545 | 0.001562 | 16.83% |
| **ev_policy_lookahead** | 34.25% | **353,755 (236,316–483,965)** | **1,733** | **527** | **0.001490** | 17.54% |

Chart: `experiments/tier2_simulation/baselines_comparison.png`.

### What this actually shows

**The EV policy matches blind contact on recovery while using 61% fewer
contacts.** ₹353,755 vs ₹355,209 incremental — a 0.4% difference with
heavily overlapping confidence intervals, i.e. statistically
indistinguishable — from 1,733 contacts instead of 4,393. Cost per
incremental rupee is **2.5x better** (0.001490 vs 0.003792), and it reaches
fewer do-not-disturbs (17.54% vs 20.49%).

That efficiency, not a higher headline ₹, is the honest claim. In this
simulation the ceiling on recovery is set mostly by how many times you are
willing to contact someone; the value of targeting is getting the same
result for far less contact volume, spend, and customer annoyance — all of
which carry real costs (churn, complaints, TCCCPR complaint-threshold
exposure) that this batch's short-horizon ₹ accounting does not price in.

**`blast_everyone` and `rules_based_dunning` remain byte-identical.** Both
reduce to "NUDGE every attempt, up to 3, regardless of signal", and
`sim/environment.py` doesn't differentiate pay probability by channel — so
two policies differing only in default channel are the same policy to the
simulator. They differ only in `approx_channel_cost`. A real simulator
limitation, documented rather than hidden.

**The lookahead reformulation is a marginal win, not the fix.** It edges
greedy EV on both recovery (₹353,755 vs ₹348,644) and contact efficiency
(1,733 vs 1,794 contacts). Worth keeping, but it was built on a hypothesis
that turned out to be wrong: before the two agent bugs were found, adding
lookahead changed almost nothing (1,128,226 vs 1,131,714 gross). The real
gains came from the bug fixes, not the cleverer algorithm — recorded here
because the opposite conclusion would have been easy and flattering to draw.

## What this experiment still does NOT include

- **No sensitivity sweep** over the response model's parameters — spec
  section 7.3 requires this before any result here can be called more than
  a single point estimate. Especially warranted now: the baseline
  comparison's shape turned out to depend heavily on the response model's
  near-independence between successive contacts, which is an assumption,
  not a finding.
- **Do-not-disturb contact rate is 17.54%, nowhere near the ≈0 target.**
  The policy reduces it relative to blind contact but does not come close
  to eliminating it, and it got slightly worse after the loop fixes (more
  cases survive to be contacted).
- **Only the T-learner is used in the reported runs.** S/X-learner were
  measured (correlations 0.42 / 0.37 vs T's 0.40 — comparable) and the
  causal forest is **not usable on this feature set**: it emits CATE
  estimates outside the mathematically possible [-1, 1] range for a
  probability difference (mean -1.23, std 4.43, only 29% of predictions in
  range). Removing feature collinearity improved that materially (to 60% in
  range) but did not fix it; root cause not yet identified, so it is
  excluded rather than reported. Documented as a known defect.
- **`cost_per_incremental_rupee` counts channel costs only** — not
  annoyance, churn, or complaint-handling cost.
- **First-contact CATE only** — RETRY's effect is a fixed calibrated
  constant, not learned; NEGOTIATE/ESCALATE_HUMAN aren't in training data.
- **The lookahead policy's `p_resolve` is approximated** as
  `base_resolution_prob + tau_hat`, because the uplift model estimates an
  incremental effect and not an absolute payment probability. That
  approximation is the weakest link in the policy and is why
  `base_resolution_prob` is an explicit parameter rather than a buried
  constant.
