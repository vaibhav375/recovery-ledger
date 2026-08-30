# Regret — what the agent's silences cost, and what they saved

**Every number below was produced by `run_regret.py` in this directory, on
the evaluation population `tier2_simulation/run_batch.py` measures its
₹272,281/1,000-cases headline on.** Reproduce with `make regret` — the seed
is fixed throughout; re-running gives identical output (verified: ran it
twice, diffed, byte-identical).

```
PYTHONPATH=src .venv/bin/python3 experiments/regret/run_regret.py --n-train 5000 --n-eval 2000
```

**The pre-registered prediction HOLDS.** 170 declined cases in the
model-judgement bucket had positive true uplift — a non-trivial count, as
predicted before the run.

## Why this was run

This system's central pitch is that most of its value is in *declining* to
contact people: 80% fewer messages than mass-contact, and a whole dashboard
section devoted to the three mechanisms that produce silence (mandatory
rules, the model's own judgement, and running out of allocated attempts).
Every one of those reports what the silence *saved*. Nothing in the repo
reported what it *cost* — every refusal is a bet that contacting would not
have paid, and some of those bets are wrong. The simulator has always known
which ones: `persuadability(traits)` is the true per-case treatment effect,
already queried for the do-not-disturb diagnostics elsewhere in this repo.
This experiment is that same query, asked of every declined case instead of
just the do-not-disturbs, and turned into rupees.

## Design

**Same customers as the B1 headline, by construction, not by coincidence.**
A regret figure is only quotable next to ₹272,281 if it prices refusals on
the exact population that number was measured on. `run_regret.py` imports
`run_eval`, `train_models`, `SEED` and `NOW` directly from
`tier2_simulation/run_batch.py` and calls them with the same seed
(`EVAL_SEED = SEED + 1000`), the same `n_train`/`n_eval` (5000/2000), and the
same shipped model (`ensemble=False`, the single T-learner) `make eval`
uses. `tests/test_experiment_seeds.py` records this as a declared
`"shares"` entry rather than leaving it to be discovered by a seed
collision.

**`run_batch.py` itself is untouched.** Submission week is the wrong time to
edit the script the B1 headline rests on, and its `results.json` is
referenced by eight doc-test assertions elsewhere in the repo. This
experiment only imports from it.

**The holdout arm must never enter the universe.** `run_eval` writes both
the treatment arm (run by the real policy) and the no-contact holdout arm
(the experimental control, never contacted *by design*) into the same
`Ledger`, so the ledger alone cannot say which cases the policy was ever
allowed to act on. `treatment_arm()` reconstructs `run_eval`'s own
`np.random.default_rng(seed + 1).integers(0, 2, size=n)` split to recover
just the treatment-arm cases, and `main()` asserts the reconstructed arm is
40-60% of the batch before using it — the guard against `run_eval`'s
assignment logic silently drifting out from under this reconstruction, which
would double-count holdout non-contacts as refusals and roughly double the
reported regret. It held: the treatment arm was 1,037 of 2,000 cases
(51.85%).

Each declined case is priced by its own `tau_true = persuadability(traits)`:
positive uplift priced as *forgone* (refusing cost money), negative uplift
priced as *avoided* (refusing was correct), by amount at risk. Cases handed
to a human (`human_escalation_threshold`) are excluded from cost/saved
entirely — a handoff is not a refusal, the money isn't forgone, it just
hasn't been decided yet.

## The pre-registered prediction

Fixed before this run, from `make calibration`'s result: the bottom
`tau_hat` decile is 43.8% true do-not-disturbs against roughly 17.3% of the
whole population — which means it is also **~56% customers with positive
true uplift**, priced by the model as though they were not. If that's true,
the model-judgement bucket here — cases the agent itself chose not to
contact, on `negative_ev` or `do_not_disturb` grounds — **must** contain a
non-trivial count of `tau_true > 0` refusals. Near zero would mean the two
experiments contradict each other, and that contradiction was to be
published as a finding, not quietly reconciled by adjusting either one.

**What the code actually checks, stated plainly.** The registered threshold
in `run_regret.py` is `MODEL_ERRORS_EXPECTED_ABOVE = 0` — the rule the code
enforces is `model_errors > 0`, which any non-zero count clears. That is
weaker than "a non-trivial count" above implies: the code has no way to
distinguish one model error from many. This is not being tightened now that
the result is in — raising a pre-registered threshold after seeing it pass
would be moving the goalposts, and exactly as much a violation of
pre-registration as loosening one to force a pass would be. Stated as
registered, not as it reads in prose: the rule is `> 0`, and the observed
count — 170 of 286 model-judgement refusals, 59% — clears that weak
threshold by a wide margin. The stronger "non-trivial count" framing above
is also satisfied by 170, but that framing is not what the committed code
checks.

## Result

2,000 eval cases, treatment arm 1,037. Of those: 234 were actually
contacted ("worked"), 6 were handed to a human and excluded, 243 resolved
without ever being contacted (they paid; nothing was forgone, so they are
excluded from cost/saved the same way the 6 deferred cases are), and 554
were declined and priced. That partition adds up:
234 + 6 + 243 + 554 = 1,037. The 243 resolved-without-contact cases are not
bookkeeping — they
are the selection mechanism the "Counterfactual check" section's one-sided
argument rests on: excluding them is what conditions the declined universe
on `paid_0 ~= 0`, which is exactly why that check cannot see a realised
saving (see below).

```
bucket                 n          cost         saved           net  errors
allocation           264        69,247         1,502       -67,746       0
model_judgement      286        63,822        92,177        28,355     170
case_state             4         1,278             0        -1,278       0
TOTAL                554       134,347        93,679       -40,669     170
```

Pre-registered prediction: model errors > 0
observed **170** → **HOLDS**

No `mandatory` bucket appears above zero: this is structural, not a sampling
accident. In this pipeline the compliance kernel issues `DENY` only on `retry`
actions—all 320 DENY certificates in `experiments/tier2_simulation/batch_ledger.json`
carry `action_type: "retry"`, with zero DENY on `nudge` or `negotiate`. Since only
`nudge` and `negotiate` count as customer contact (the distinction that is novelty
claim N6), a kernel denial can never turn a declined case into a *contact* refusal
here. The mandatory bucket is therefore unreachable via kernel denial in this pipeline,
and the other mandatory reasons (`opt_out`, `promise_to_pay_active`, `regulatory_ceiling`,
`global_kill_switch`) terminate cases before they reach the declined universe.

**Reading the table**: `allocation` (attempts exhausted) is the largest
single cost, and it is *not* the bucket the pre-registered prediction is
about — that prediction concerns `model_judgement` specifically, because
that is the bucket where the agent itself decided contact wasn't worth it.
Within `model_judgement`, net is *positive* (₹28,355): the ₹92,177 correctly
avoided in true do-not-disturbs outweighs the ₹63,822 forgone from the 170
cases the model judged wrong. That is consistent with — not a contradiction
of — the calibration finding: the bottom decile being 43.8% true
do-not-disturbs against 56% positive-uplift means the model is *right more
often by count of rupees saved* even while being wrong on a non-trivial
number of people. The prediction was only ever about the *count* of
`tau_true > 0` model-judgement refusals being non-trivial, and 170 is that.

## Counterfactual check

A second, independent estimate of the same 554 in-scope declined cases:
actually simulate each one under `WAIT` (what happened) and `NUDGE` (the
counterfactual), same per-case RNG stream (common random numbers), and sum
the difference.

```
Paired counterfactual over 560 declined cases...
  realised net -111,614 vs expected net -40,669
```

(560 is the full declined list including the 6 deferred cases, which the
print statement in the brief's code counts before the deferred filter; the
comparison itself — `check["n"] = 554` — matches `totals.n` exactly.)

**`realised_cost` disagrees with the model-based cost estimate by more than
resampling variance explains — a real finding on the one side of the ledger
this check can validate at all.** The spec named
`counterfactual_check.inside_headline_interval` before anyone knew this
check is one-sided by selection; implemented here on the half it actually
validates: a 95% bootstrap interval on the model-based cost total, built by
resampling the 554 in-scope declined cases' own `forgone` amounts with
replacement (2,000 replicates) — this captures how much the total cost
estimate would move across comparable draws of this same declined sample.
That interval is **[₹119,877, ₹148,032]**
(`cost_interval_low`/`cost_interval_high` in `results_regret.json`).
`realised_cost` — ₹111,614, from the paired WAIT/NUDGE simulation replay —
falls **outside** it, below the low end
(`realised_cost_inside_interval: false`). This is published as computed,
not suppressed or tuned: even on the side of the ledger this check is
capable of validating, the realised replay and the model-based estimate
disagree by more than the sampling variance of the cost total accounts
for. It is not evidence that `totals.cost` is fabricated — both numbers
come from the same committed, deterministic code, run twice and confirmed
byte-identical — but it means this section's earlier framing ("the
realised and expected costs agree closely") overstated the agreement, and
is corrected here rather than repeated.

`realised_saved` is exactly **`-0.0`** — not a small or noisy number, a
literal zero — against `totals.saved` of **₹93,679** baked into
`totals.net`. Across all 554 declined cases, the paired simulation replay
never once produced an instance where nudging looked worse than waiting.

That is not because the simulator or the common-random-numbers design makes
negative draws structurally impossible — sampled outside this declined
universe, over 6,000 fresh cases (`estimator_diagnostics()` in
`run_regret.py`, seed disjoint from both the training seed and the shared
evaluation batch above), 32 of 1,003 true do-not-disturbs (3.2%) showed a
genuine negative realised draw (paid under WAIT, not paid under NUDGE), and
the headline expectation estimator itself checks out closely on that
*unselected* 6,000-case population: mean `tau` and mean realised
`(paid_1 - paid_0)` agree at a ratio of **1.035**, so `amount x tau_true` is
on the same scale as the realised effect there. That population-level
calibration does not, on its own, explain the gap documented above between
`realised_cost` and its own bootstrap interval on *this* selected 554-case
sample — the two checks measure different things, and both are reported
rather than letting the friendlier one stand in for the other.

*(These three figures were previously computed out-of-band and quoted here
as 46 of 973 (4.7%), ratio 1.000, and 5.5% respectively — numbers nothing in
the repo regenerated. `estimator_diagnostics()` now computes all three on
every `make regret` run and writes them into `results_regret.json` under
`estimator_diagnostics`; the figures above are what that committed code
actually produces, not the prettier out-of-band ones, and
`tests/test_results_doc_matches_artifacts.py::test_regret_report_ratio_diagnostic_matches_the_artifact`
pins the ratio so this paragraph cannot drift from the artifact again.)*

**The actual cause is selection, not variance.** `declined_cases()` (by
design, not by accident — see "Design" above) excludes `resolved` cases:
they paid, so nothing was forgone. But that conditions the declined universe
on *not having paid under WAIT* — a refusal can only be observed to "save"
money when `paid_0 = 1` and `paid_1 = 0`, and every case where `paid_0 = 1`
was already routed to the resolved-skip before it could enter this universe.
Measured directly, on the same fresh unselected population: the WAIT-side
pay rate is 4.0% (16 of 400 sampled), and cases like those are exactly what
gets removed as `resolved` before the declined universe is built. Inside the
declined universe, `paid_0` is therefore ~0 by construction, so
`realised_saved` has no way to be anything but zero here regardless of how
many true do-not-disturbs are in it.

**Consequence: `realised_net` and `expected_net` are not the same estimand,
and the cost side is not cleanly validated either.** The paired
counterfactual can only speak to the *cost* side of the ledger at all — it
structurally cannot validate *saved* — and the bootstrap check above shows
it does not corroborate cleanly even there: `realised_cost` sits below its
own model-based interval, a real, published disagreement on the one side
this check can address. The 2.7x gap between `realised_net` (-₹111,614) and
`expected_net` (-₹40,669) remains an artifact of comparing a one-sided
quantity (cost only) against a two-sided one (cost minus saved) — that part
is not evidence `totals.net` is wrong — but it is no longer accurate to
call the cost-only comparison itself clean agreement. `results_regret.json`
records both facts directly on `counterfactual_check`: `"validates": "cost
side only"`, `"one_sided_because"` naming the selection mechanism above, and
now `cost_interval_low`/`cost_interval_high`/`realised_cost_inside_interval`
recording the bootstrap test and its outcome, so the caveat and the finding
both travel with the artifact and not only with this prose.

## What this does and does not license

**This licenses**: reporting the B1 headline (₹272,281 / 1,000 cases) beside
its own cost of declining, on the same customers, for the first time. It
licenses saying that of the 554 treatment-arm cases the agent declined to
contact, the model-based estimate is a net -₹40,669 (₹134,347 forgone against
₹93,679 avoided), and that within the bucket the agent itself controls
(`model_judgement`), 170 of 286 refusals were later shown to be customers
who would have responded positively to contact — a real, non-zero error
rate that the calibration experiment's decile analysis predicted must
exist. It licenses treating this as a genuine, structural cost of the
policy's caution, not noise. It also licenses reporting, plainly, that the
paired-simulation check on the cost side (₹111,614 realised) was tested
against a 95% bootstrap interval built from the same 554-case sample
(₹119,877–₹148,032) and landed outside it — a real disagreement, published
rather than tuned away, not a validation of `totals.cost`.

**This does not license**: quoting the ₹93,679 "saved" figure as
independently validated — the paired counterfactual could not observe a
single instance of it (`realised_saved = -0.0`) because the declined
universe's exclusion of `resolved` cases removes exactly the cases where a
saving could show up; that figure rests on the model-based estimate alone.
It also does not license quoting the ₹134,347 "cost" figure as
independently validated — the same paired counterfactual's realised cost
fell *outside* the 95% bootstrap interval built around that figure, which
is a documented disagreement, not a confirmation. Nor does it license
claiming the agent should therefore contact more people.
`model_judgement`'s net is still positive (₹28,355) — the model is
net-correct in this bucket even though it is wrong on a non-trivial count of
individuals, and `allocation` (attempts running out, not a modelling choice)
is the larger cost in absolute terms. It does not license treating
`realised_net` (-₹111,614) as a competing net estimate to weigh against
`expected_net` (-₹40,669) — they are not the same estimand, one is cost-only
and the other is cost-minus-saved, and the gap between them is that
selection artifact, not a disagreement between two valid measurements. And
it does not license any claim about real-world effect size: like every other
number in
this repo's Tier 2 experiments, this is priced entirely inside the
simulator's invented response model (`sim/environment.py`) — it says what
the policy's caution costs *under this simulation's assumptions*, not in
production.
