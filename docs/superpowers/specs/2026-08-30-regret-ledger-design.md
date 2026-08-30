# Design — the regret ledger: what refusing cost, and what it saved

**Date:** 2026-08-30
**Status:** approved, not yet implemented
**Extends:** N1 (incremental-first accounting) and N2 (negative-uplift
targeting). Deliberately **not** a new novelty claim — see Non-goals.

## Problem

The entire pitch of this system is that its value lies in *not* contacting
people. `make eval` reports ₹272,281 incremental per 1,000 cases, `make
baselines` reports 80% fewer contacts than mass-contact, and the dashboard
devotes a whole section to the three mechanisms that produce silence.

Nothing anywhere reports what that silence cost.

Every refusal is a bet that contacting would not have paid. Some of those bets
are wrong, and the simulator knows exactly which ones — `persuadability(traits)`
is the true per-case treatment effect, and it is already used to compute the
do-not-disturb diagnostics. The information to price the agent's own false
negatives has been sitting in the repo unqueried.

This matters more after `make calibration`. That experiment showed τ̂'s bottom
bin is 43.8% true do-not-disturbs and 56% ordinary customers priced as if they
were not — so the refusals driven by that model are *known* to contain errors,
and their cost is currently unmeasured and unpublished.

## What this is

A two-sided account of every case the agent declined to contact:

- **cost** — money forgone by refusing cases with τ_true > 0
- **saved** — harm avoided by refusing cases with τ_true < 0
- **net** — saved minus cost

Reporting only the cost would be self-flagellation with the same dishonesty as
reporting only gross recovery. Reporting only the saved would be marketing.

## Measurement

### Universe

The **treatment arm's declined cases only**. A case is declined when no contact
was ever executed, which includes cases where the policy proposed a nudge and
the compliance kernel denied it.

The holdout arm is excluded. It was never contacted *by design* — it is the
experimental control, not a refusal. Including it would be a category error
inflating the number by roughly half the batch, and there is a test for exactly
this (see Testing).

`resolved` cases leave the universe: they paid, so nothing was forgone.

### Headline estimator — expected forgone value

For each declined case, `amount_at_risk × τ_true`, accumulated separately by
the sign of τ_true. Deterministic, no resampling, no counterfactual re-run. It
is the same quantity B1 estimates — the incremental value of contact — totalled
over the cases the agent chose not to work.

Published caveat, in the same terms the rest of the repo uses: this is an
expectation under simulator truth, not a realised measurement.

### Paired check — realised counterfactual

`SimulationEnvironment` gives each case its own RNG stream seeded from
`(seed, case_id)`, independent of call order. It is already a common-random-
numbers design, so the counterfactual needs no special machinery.

For each declined case, construct **two** environment instances at the same
seed, step one with `WAIT` and the other with `NUDGE`, both at
`attempt_index=0`. Two instances rather than two calls on one instance: a
second call would advance that case's stream, and the point is that both arms
see the identical sequence. The difference is the realised incremental effect
with zero pairing variance.

The realised total should land inside the headline estimator's interval. If it
does not, one of the two is wrong, and that is reported rather than reconciled.

## Attribution

Five buckets, all derivable from ledger entries that already exist — the
`StopReason` written by `_stop()`, plus the kernel certificate's `DENY`.

| Bucket | Reasons | Meaning of regret here |
|---|---|---|
| **Mandatory** | kernel `DENY`, `opt_out`, `promise_to_pay_active`, `regulatory_ceiling`, `global_kill_switch` | The price of compliance. Not a judgement the agent made. |
| **Model judgement** | `negative_ev`, `do_not_disturb` | The agent chose. Correct when τ_true ≤ 0 (counts as *saved*); a **model error** when τ_true > 0 (counts as *cost*). |
| **Allocation** | `budget_exhausted` | No judgement about this case at all — it ran out of attempts. The most fixable cell. |
| **Case state** | `dispute_raised`, `hard_decline` | Ended for reasons unrelated to willingness to pay. |
| **Deferred** | `human_escalation_threshold` | A handoff, not a refusal. The money is not forgone; a human may work it. Reported separately and **excluded** from regret totals. |

## Pre-registered prediction

Fixed here, before the run, per the rule this repo applies to every other
experiment.

`make calibration` established that τ̂'s bottom bin is 43.8% true
do-not-disturbs against 17.3% of the population — meaning it is also 56%
customers with τ_true > 0 who are priced as if they were not. If that result is
true, the **model-judgement bucket must contain a non-trivial count of cases
with τ_true > 0**, and their forgone value must be greater than zero.

**If the model-error cell comes back at or near zero, the two experiments
contradict each other and one of them is wrong.** That outcome gets published
as a contradiction, not reconciled by adjusting either.

This is the point of the feature. It is not a dashboard of what the agent did;
it is a number capable of falsifying a result this repo has already published.

## Population and seeds

The experiment deliberately evaluates on **`run_batch.py`'s population**
(`SEED + 1000`), because a regret figure is only quotable next to the headline
if it is measured on the same customers. `run_batch.py` itself is not modified
— submission week is the wrong time to edit the script the headline rests on,
and `results.json` is referenced by eight assertions in
`tests/test_results_doc_matches_artifacts.py`.

The artifact records `shares_population_with: "tier2_simulation/run_batch.py"`
so the sharing is a property of the file rather than a comment.

### Fixing exemption-by-omission in the seed test

`tests/test_experiment_seeds.py` enforces population distinctness by listing
files. `experiments/churn_lambda/run_lambda_sweep.py` deliberately shares the
baselines population, and it is accommodated by **not being in the list at
all** — which is indistinguishable from having been forgotten. The test cannot
tell an intentional sharer from an oversight, which is the same defect as the
λ_churn interval check: a guard that cannot fail in the direction that matters.

Replace the list with a registry of three declared kinds:

- `DISTINCT` — has its own evaluation population (the current 11 entries)
- `SHARES_WITH(other, reason)` — `churn_lambda/run_lambda_sweep.py` retro-registered
  against the baselines population, `regret/run_regret.py` added against
  `run_batch.py`
- `NO_EVAL_POPULATION(reason)` — `listener_eval/run_eval.py`,
  `negotiation/run_negotiation.py`, and both `tier1_criteo` scripts
  (`run_validation.py`, `run_dr_diagnosis.py`), which evaluate on real
  randomised datasets rather than a generated population

Then add a test that walks `experiments/` and fails on any `run_*.py` not
classified. There are 16 such files today: 11 `DISTINCT`, 1 `SHARES_WITH`, 4
`NO_EVAL_POPULATION`; `regret` makes 17. After this, adding an experiment without declaring its seed intent
breaks the build, and "deliberately shares" becomes a statement the test checks
rather than a silence it cannot read.

## Artifact

`experiments/regret/results_regret.json`, written by
`experiments/regret/run_regret.py`, target `make regret`, documented in
`experiments/regret/REPORT.md`.

Key ordering constraint: the `prediction` block is written **before** the
results block in the file, so it cannot be read as post-hoc.

```
{
  "n_eval", "eval_seed", "shares_population_with",
  "n_treatment_arm", "n_declined", "n_worked", "n_deferred",
  "prediction": { "rule", "model_error_cases_expected_above", "holds" },
  "totals": { "cost", "saved", "net" },
  "buckets": [ { "bucket", "n", "cost", "saved", "net", "model_errors" } ],
  "counterfactual_check": { "realised_cost", "realised_saved",
                            "inside_headline_interval" }
}
```

## Testing

Unit tests first, on constructed cases where the answer is exact — the method
used for `policy/uplift/calibration.py`. Two exist specifically to fail, and
both must be shown failing under mutation before the implementation is accepted:

1. **A holdout-arm case must never enter the universe.** This is the category
   error that would inflate the number by half the batch.
2. **A `negative_ev` refusal with τ_true > 0 must land in *model error*, not in
   *saved*.** Mutating the sign test has to break it.

Plus: doc tests pinning the totals and bucket rows in `RESULTS.md` the way the
decile table is pinned; the new seed-registry classification test; and a
determinism check (two runs, byte-identical artifact) matching the claim
`RESULTS.md` makes about every experiment.

## Where it surfaces

- **`RESULTS.md`** — a new section immediately after B1, because the pairing
  only reads if the two numbers are adjacent: recovered ₹272,281 per 1,000, and
  on the same cases the silences cost X, saved Y, net Z.
- **Dashboard** — inside the existing Silence section, not an eleventh section.
  Silence already argues that most of the agent's value is in not sending the
  message; this is the price tag on that argument and belongs under it.
- **`PROJECT_STATE.md`** — experiment count 14 → 15, the pre-registered
  prediction, and the seed-registry change against the §8 invariant list.

## Non-goals

- **No new novelty claim.** This extends N1 and N2. Inventing an N7 six days
  before the deadline would read as padding.
- **No change to the deployed policy.** This measures refusals; it does not
  alter which ones happen. Acting on the finding is separate work.
- **No modification of `run_batch.py`.**
- **No fix for whatever the allocation bucket reveals.** If `budget_exhausted`
  turns out to carry large forgone value, that argues for the global
  contact-budget allocator in PROJECT_STATE §6 Tier C — as a finding, not a
  scope increase.

## Risks

- **The pre-registered prediction may fail.** That is the design working, not
  the design breaking. It gets published as a contradiction between two
  experiments.
- **Six days to the deadline.** The definition of done in PROJECT_STATE §7 is
  already met except the video and form. If this cannot land finished and
  honestly reported, it should be dropped rather than shipped partial — an
  unbacked number would damage the one thing this repo is actually selling.
- **The counterfactual re-run doubles the runtime** of an already
  2,000-case experiment. If it proves slow, the headline estimator stands alone
  and the check runs at reduced n, reported as such.
