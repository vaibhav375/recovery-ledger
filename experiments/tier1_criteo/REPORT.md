# Tier 1 validation report

**Every number below was produced by `run_validation.py` in this directory,
run on 2026-08-23.** Re-run with the commands shown to reproduce it exactly —
seeds are fixed (`SEED = 20260823`) throughout.

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
