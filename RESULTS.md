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
| Recovery rate | 36.84% | 15.47% |

**Incremental ₹ recovered per 1,000 at-risk cases: ₹288,729 (95% CI ₹133,924 – ₹432,362)**

The holdout recovers **15.47% of cases with no agent at all**. That is why
this project reports incremental rather than gross: a vendor quoting the
gross figure would be taking credit for every rupee in that column.

Supporting diagnostics from the same run: uplift model correlation with true
(hidden) persuadability **0.349**; 1,369 contacts sent; 34,081 ledger
entries, hash chain verified; 655 cases published to the exception list.

---

## Baselines — spec section 11.3, plus a falsification control

```
make baselines
```

Common random numbers across policies, paired bootstrap, same 2,000 cases.

| Policy | Incremental ₹/1000 (95% CI) | Contacts | ₹ per contact | % to do-not-disturbs |
|---|---:|---:|---:|---:|
| do_nothing | — (reference) | 0 | — | — |
| blast_everyone | 330,108 (249,085–421,457) | 4,339 | 152.2 | 20.19% |
| rules_based_dunning | 330,108 (249,085–421,457) | 4,339 | 152.2 | 20.19% |
| razorpay_current | 86,648 (**−16,693**–193,109) | 0 | — | — |
| random_targeting | 119,671 (75,027–165,618) | 2,021 | 118.4 | 20.39% |
| **ev_policy_greedy** | **340,988 (274,088–408,856)** | 2,257 | **302.2** | 20.12% |
| ev_policy_lookahead | 340,988 (274,088–408,856) | 2,251 | 303.0 | 20.08% |

**The result that matters: 2.85x more incremental recovery than random
targeting at comparable contact volume, with non-overlapping confidence
intervals.** Without this control the headline would be uninterpretable —
"fewer contacts, same money" could just be diminishing returns to volume and
would say nothing about the uplift model. This is what makes it a claim
about *targeting*.

**Against mass-contact the honest verdict is a tie on total recovery**
(overlapping CIs; the sign of the difference flips with the eval sample)
achieved with **48% fewer contacts** at 2x the per-contact efficiency.
Contact efficiency is the robust claim; a higher headline total is not.

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
