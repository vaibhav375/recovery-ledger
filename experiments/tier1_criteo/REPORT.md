# Tier 1 validation report

**Every number below was produced by `run_validation.py` in this directory,
run on 2026-08-23.** Re-run with the commands shown to reproduce it — seeds
are fixed (`SEED = 20260823`) throughout. Checked precisely rather than
assumed (2026-08-24, ran Hillstrom 3 more times): uplift learner outputs
(Qini, AUUC, predicted CATE) are exactly bit-reproducible; the DR
off-policy estimator's implied ATE is reproducible to 4 decimal places
(+0.0462 every time) but not bit-for-bit identical at full precision
(0.046255 vs 0.046222 across two runs) — most likely floating-point
non-associativity in multi-threaded BLAS operations inside
`GradientBoostingClassifier`, not an unseeded random draw (every explicit
random source in this codebase is seeded, and the variation is far too
small and too stable across repeats to be a real seeding gap). Doesn't
change any conclusion in this report.

## What this validates

Spec section 7.2: before any of this project's causal machinery touches the
domain simulator, it has to reproduce known treatment effects on genuinely
randomised public data. Two independent checks, run on two datasets:

1. **Do the uplift learners find real heterogeneous signal?** Four
   meta-learners (S/T/X-learner, causal forest) are scored by Qini
   coefficient and AUUC on a held-out test set. A positive score means the
   learner's ranking of "who benefits from contact" beats random ranking —
   the whole premise of targeting.
2. **Do the off-policy value estimators (IPS, SNIPS, DR) recover the true
   average treatment effect?** Because both datasets are genuinely
   randomised, the *direct* difference in arm means is itself an unbiased
   ground truth. IPS/SNIPS/DR never see that direct comparison — they
   reconstruct it purely from propensity-reweighted (and, for DR,
   outcome-model-corrected) individual outcomes. If they land near the
   direct number, the estimator implementation is correct.

## Hillstrom (Womens E-Mail vs No E-Mail, target = visit)

```
uv run python experiments/tier1_criteo/run_validation.py --dataset hillstrom --target-col visit
```

n = 42,693 · treated fraction = 0.501 · base rate = 12.88%

| Learner | Qini | AUUC | Fit time |
|---|---:|---:|---:|
| S-learner | +0.0414 | +0.0186 | 4.0s |
| T-learner | +0.0546 | +0.0248 | 3.6s |
| X-learner | +0.0492 | +0.0219 | 9.0s |
| Causal forest | +0.0386 | +0.0179 | 34.9s |

All four positive → all four learners find real heterogeneity, independently
of each other.

| Estimator | Implied ATE | Direct arm-mean ATE | Gap |
|---|---:|---:|---:|
| IPS | +0.0451 | +0.0451 | 0.0000 |
| SNIPS | +0.0451 | +0.0451 | 0.0000 |
| DR | +0.0463 | +0.0451 | 0.0012 |

IPS/SNIPS match to the shown precision (expected: with a genuinely balanced
50/50 randomisation, both estimators are algebraically close to the direct
arm-mean difference). DR is within 0.0012 — good.

## Criteo (real subsample, target = visit)

```
uv run python experiments/tier1_criteo/run_validation.py --dataset criteo --sample-frac 0.02 --target-col visit
```

Data note: `sklift.datasets.fetch_criteo`'s S3 source returned `403
Forbidden` on 2026-08-23 (the bucket Criteo published this dataset from is no
longer publicly reachable through that package). Switched to the dataset's
HuggingFace parquet mirror (`criteo/criteo-uplift`), downloaded and cached
locally under `data/`. That mirror's 4 parquet shards are **not row-shuffled
relative to the original file** — shard 0 alone is 100% one treatment arm.
`load_criteo()` concatenates all 4 shards before sampling, which is required
for the resulting sample to be a valid random subsample. See
`ENGINEERING_LOG.md` (2026-08-23) for the full account.

Full pooled dataset (13,979,592 rows) matches the spec's cited published
benchmarks before any subsampling: treated fraction 0.8500 (spec: 0.85),
visit rate 4.699% (spec: ≈4.7%), conversion rate 0.2917% (spec: ≈0.29%).

2% random subsample used below: n = 279,592 · treated fraction = 0.850 ·
base rate = 4.69%.

| Learner | Qini | AUUC | Fit time |
|---|---:|---:|---:|
| S-learner | +0.0745 | +0.0292 | 25.2s |
| T-learner | +0.0663 | +0.0261 | 22.2s |
| X-learner | +0.0706 | +0.0278 | 46.8s |
| Causal forest | +0.0616 | +0.0243 | 345.5s |

Again all four positive, and larger in magnitude than on Hillstrom.

| Estimator | Implied ATE | Direct arm-mean ATE | Gap |
|---|---:|---:|---:|
| IPS | +0.0094 | +0.0094 | 0.0000 |
| SNIPS | +0.0094 | +0.0094 | 0.0000 |
| DR | +0.0067 | +0.0094 | 0.0027 |

## The one real finding worth flagging (not a blocker)

DR's gap from the direct ATE is larger on Criteo (0.0027) than on Hillstrom
(0.0012). The mechanism: Criteo's treatment ratio is 85/15, not 50/50.
`doubly_robust_value`'s outcome-regression correction term needs a model of
E[Y|X,T] for both arms; the first implementation fit **one joint model** with
treatment concatenated as a feature, which under-weights a minority-class
indicator among 12 other features — worse the more imbalanced the arms are.
Refitting with **one model per treatment arm** (the standard DR formulation)
narrowed the gap from 0.0036 to 0.0027 but did not close it fully. The
remaining gap is plausibly the outcome model itself (`GradientBoostingClassifier`,
80 trees, 5-fold cross-fit) being under-calibrated on the 15%-share control
arm at this sample size — a candidate fix (more trees, more folds, or a
better-calibrated base learner) that hasn't been tried yet. Logged here
instead of quietly tuned away, per the project's own rule against fabricated
or laundered numbers.

## Verdict

**Kill gate: PASSED, with one open finding.** Both uplift learners and
off-policy estimators reproduce known treatment effects on two independent,
genuinely randomised real datasets. IPS/SNIPS are exact-to-shown-precision on
both. DR is directionally correct and close on both, with a diagnosed,
partially-fixed, not-fully-closed bias under high treatment-ratio imbalance
that should be revisited before DR estimates are used for anything more than
a cross-check against IPS/SNIPS in Tier 2.

---

## Addendum: is DR biased on Criteo, or just imprecise?

`make dr-diagnosis` → `results_dr_diagnosis.json`

This report previously recorded DR recovering +0.0067 against a direct arm-mean
ATE of +0.0094 and called it "29% low". That phrase describes a single point
estimate, and a point estimate below truth is consistent with two different
facts — a systematic bias worth fixing, or one draw from a wide sampling
distribution. Nothing in the repo could tell them apart, so a documented weak
spot sat unactionable.

Two things were wrong with the evidence, both fixed here.

**The intervals were not paired.** The artifact reports separate bootstrap
intervals for the always-treat and never-treat values. Differencing those by eye
double-counts the noise they share: the two values are computed on the same
rows, from the same cross-fitted `q_hat`, with overlapping correction terms.
The diagnosis resamples rows once and differences within each draw, giving the
contrast its own interval — 0.0057 wide against the 0.0075 you get by adding
the marginals.

**The draws were not independent.** The first version of the diagnosis drew
three train/test splits of the *same* pooled sample. Two 30% test sets from one
pool share about a third of their rows, so agreement between them is partly an
artifact of shared data. The pool is now partitioned into three non-overlapping
blocks of ~93,000 rows, asserted disjoint at runtime. That the direct ATE itself
varies across blocks (+0.0096, +0.0074, +0.0112) is the visible sign that these
are genuinely different samples.

### Result

| Block | n | Direct ATE | DR | DR 95% CI (paired) | Covers | Gap |
|---|---:|---:|---:|---|:--:|---:|
| 1 | 93,198 | +0.00957 | +0.00538 | [+0.00261, +0.00799] | no | −43.8% |
| 2 | 93,197 | +0.00744 | +0.00712 | [+0.00443, +0.01014] | yes | −4.2% |
| 3 | 93,197 | +0.01118 | +0.00751 | [+0.00451, +0.01041] | no | −32.8% |

IPS covers the truth in 3/3 blocks. DR covers it in 1/3.

**Verdict: inconclusive, leaning bias** — under a rule fixed before the run,
which requires *both* that every interval miss the truth *and* that the sign be
consistent. The sign is consistent (low in all three). The intervals are not:
block 2 lands within 4% of truth. So the direction replicates and the magnitude
does not, which is precisely why "29% low" should never have been stated as a
property of the estimator. It was a property of one subsample.

### What this rules out

The variance explanation, which was the obvious first hypothesis: with 85%
treated, the control arm holds 15% of the rows at a 6.7x importance weight
against the treated arm's 1.2x, so a wide never-treat interval is expected. But
DR's paired contrast interval is **0.82x the width of IPS's** — DR is the more
precise of the two here, not the noisier one. Imprecision cannot explain a gap
this consistent in sign.

That leaves the outcome model. Note what it does *not* leave: with a known
constant propensity, the DR correction term is unbiased for any `q_hat`
whatsoever, so a merely miscalibrated outcome model should not move DR's
expectation at all. A residual bias under a known propensity points at the
cross-fitting — most plausibly that `q_hat` for the minority arm is fit on
folds where that arm is scarce, making its errors correlated with the fold
assignment rather than independent of it. That is a specific, testable
mechanism, and it is not tested here.

### Practical consequence

Use IPS on this dataset. It is unbiased under the known design propensity,
covers the truth in every block, and its only cost — a wider interval — is the
honest one. DR's extra precision is not free if it is buying that precision
with a systematic offset.

---

## Fold-count sweep: does the named mechanism respond to cross-fitting at all?

`make dr-foldsweep` → `results_dr_foldsweep.json` (sample_frac 0.02, n_boot 500,
same 3 disjoint blocks as above; 26m45.57s wall clock — see Runtime below)

PROJECT_STATE.md's Tier B backlog named the mechanism above — a cross-fitted
`q_hat` starved on Criteo's 15% control arm — but proposed "refit with
stratified folds that guarantee minority-arm balance, or increase folds" as
the untested fix. Half of that was already shipped when it was written:
`dr_contributions` already stratifies its k-fold split on the *joint* of
treatment and outcome (`strata = treatment * 2 + outcome`), and `q_hat` is
already fit as one model per arm, not a joint model with treatment as a
feature. So "refit with stratified folds" was not an outstanding step. What
was never tested is narrower: does the residual gap actually respond to the
cross-fitting fold count at all? If the mechanism is a fold-local minority
arm starved of training rows, more folds should shrink it — each fold then
holds out a smaller slice, leaving more of the scarce control arm available
to train `q_hat` on.

**The rule, fixed before running (quoted verbatim from
`results_dr_foldsweep.json`'s `rule` field, the same string
`FOLD_SWEEP_RULE` in `run_dr_diagnosis.py` enforces and prints, so the prose
here and the string the code actually carries cannot drift apart unnoticed):**

> The cross-fitting hypothesis predicts the gap shrinks as folds increase -- more folds means more training data per fold and a better-conditioned minority arm. It is CONFIRMED if coverage rises to 3/3 at higher fold counts. It is REFUTED if coverage and the mean gap are essentially flat across 2 -> 20 folds, which would mean the residual gap has some other cause and the named mechanism is not it. Anything else is UNRESOLVED.

### Result

| n_folds | coverage | mean gap | mean \|gap\| |
|---:|---:|---:|---:|
| 2 | 1/3 | -0.00282 | 0.00282 |
| 5 | 1/3 | -0.00272 | 0.00272 |
| 10 | 1/3 | -0.00281 | 0.00281 |
| 20 | 1/3 | -0.00278 | 0.00278 |

**Verdict: REFUTED.** Coverage sits at exactly 1/3 at every fold count from 2
to 20 — a 10x increase in fold count does not move it even once. The mean
gap magnitude wanders between 0.00272 and 0.00282, a spread of 4% around its
own mean, with no monotone trend in either direction as folds increase — not
the shrinking-toward-zero the cross-fitting hypothesis predicts. Per-draw,
the same block (seed 20260823) misses the direct ATE by roughly the same
margin (−0.0042 to −0.0045) at every fold count, and the block that already
covered truth (seed 20261323) keeps covering it at every fold count too. The
fold count is not moving anything.

This closes the mechanism PROJECT_STATE.md's Tier B item named. The gap is
real (see the bias-vs-noise diagnosis above), but it is not caused by
cross-fitting starving the minority arm on fold-local training data — if it
were, refitting with more folds would have shown at least some movement in
either coverage or the gap, and it shows none. The residual bias's actual
cause remains open; ruled out are (1) sampling noise (the bias-vs-noise
diagnosis above), and now (2) the cross-fitting fold count. What has not
been tested: the outcome model class itself (`GradientBoostingClassifier`,
80 trees, uncalibrated) on the minority arm's absolute row count — the fold
count changes what fraction of the control arm each fold model trains on
within one block, but the block's total control-arm row count (∼15% of
~93,000) doesn't move with it, and that total may be the actual constraint.

### Runtime

The sweep fits the cross-fitted outcome model 2 arms × 2 policies × n_folds
times per block, for n_folds ∈ {2, 5, 10, 20} across 3 blocks — 444 model
fits versus 60 for the single `make dr-diagnosis` run. Measured wall time:
26m45.57s (1,457.74s user + 67.59s system CPU, 95% CPU). Direct ATE and IPS
are computed once per block and
reused across the sweep since neither depends on n_folds — only the model
fits inside `dr_contributions` do.

No fold count, sample fraction, seed, or bootstrap setting was tuned after
seeing a result. The rule above was fixed before the sweep ran, on the same
committed disjoint blocks the bias-vs-noise diagnosis already used.
