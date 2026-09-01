# Recovery Ledger — project state

**Track 03 (AI Revenue Recovery), Razorpay AI Buildathon.**
Repo: https://github.com/vaibhav375/recovery-ledger (public)
Deadline: **5 September 2026**. Last updated: **31 August 2026** (5 days out).

> ## How to use this file
>
> **This file must be updated whenever the repo changes.** It is the single
> place that says what is done, what is not, and what any number currently is.
> A stale state file is worse than no state file — this project has already
> been bitten three separate times by documents that drifted from the artifacts
> they described (the baselines table, the λ_churn curve, the DND ratio). Treat
> this document as one of those artifacts: if a run changes a figure here,
> change it here in the same commit.
>
> **All commits must be authored by the repo owner's GitHub identity**
> (`Vaibhav <handoovaibhav123@gmail.com>`). No co-author trailers, no
> third-party attribution. This is the submitted work of one person and the
> commit history is part of what is submitted. Verify with:
>
> ```
> git log --format='%an <%ae>' | sort -u        # must show exactly one identity
> git log -1 --format='%(trailers:only)'        # must be empty
> ```

---

## 1. What this project is

An agent that decides **whether to contact a customer at all**, and proves it
was allowed to. Three things distinguish it from a dunning bot:

1. It reports **incremental** rupees against a randomised no-contact holdout,
   not gross recovered revenue.
2. It models the **downside of contact** — customers whose payment probability
   *falls* when messaged — and declines to work them.
3. Every action passes a **deterministic compliance kernel** that emits a
   per-action certificate into a hash-chained ledger.

Two governing rules the build has held to throughout:

- **Never fabricate a result.** Every number in the docs is produced by
  re-runnable code and checked by a test that fails when prose and artifact
  disagree.
- **Never overclaim.** Claims are (a) method validity on real randomised data
  and (b) policy comparison under stated assumptions in simulation. Never a
  real-world effect size.

---

## 2. Current headline numbers

All from committed artifacts, all reproducible from the listed target.

| Figure | Value | Source |
|---|---|---|
| **B1 incremental recovery** | **₹272,281 per 1,000 cases** (95% CI ₹103,930–₹433,387) | `make eval` |
| vs random targeting at matched volume | **2.34x**, non-overlapping CIs | `make baselines` |
| vs blind mass-contact | indistinguishable on total, **80% fewer contacts**, 5.0x better cost per incremental rupee, 1.9x fewer do-not-disturbs | `make baselines` |
| Deployed policy (`LookaheadEVDecisionPolicy`) | ₹317,168/1,000, 883 contacts, 11.55% to do-not-disturbs | `make baselines` |
| Uplift model correlation with truth | 0.347 (single T-learner, the shipped model) | `make eval` |
| Uplift by decile — ranking | top decile beats bottom **3/3 draws** (+0.2360, +0.1546, +0.2321), Qini 0.258 | `make calibration` |
| Uplift by decile — monotonicity | Spearman 0.879, 0.903, 0.952 — **fails** the pre-registered 0.9, near-monotone 3/3 | `make calibration` |
| Uplift calibration slope | **0.758** (predictions ~a third too spread) | `make calibration` |
| **Tier 1b — real money** | **$424 per 1,000 customers** (95% CI $159–$678) on Hillstrom's randomised `spend` — the only money figure not from the simulator | `make tier1-revenue` |
| **Tier 1c — targeting, real data** | **+0.00652/user** (95% CI +0.00507–+0.00793), 8.94 SEs from zero, ~16% lift over random — B1's claim off the simulator | `make tier1-targeting` |
| Tier 1b — pooled, any email | **$597 per 1,000** (95% CI $378–$822) over 64,000 customers | `make tier1-revenue` |
| Tier 1b — targeting on real money | **not establishable here**: 0.441 SEs from zero, needs ~420,871 held-out customers against 32,000 available | `make tier1-revenue` |
| Tier 1 — Criteo | direct ATE +0.00938, IPS +0.00938, SNIPS +0.00938, DR +0.00671 | `make tier1-criteo` |
| Tier 1 — Hillstrom | direct +0.04511, IPS +0.04511, DR +0.04622 | `make tier1-hillstrom` |
| Sensitivity C1 (EV beats random) | **75/75** settings across 3 draws | `make sensitivity` |
| Sensitivity C2 (EV more contact-efficient than blast) | **75/75** across 3 draws | `make sensitivity` |
| Red team | **21 attacks, 20/20 must-deny blocked (100%)**, 0 leaks in 5,000 fuzz samples | `make redteam` |
| Hostile policy run | 323 contacts, **0 without an ALLOW certificate**, chain valid | `make redteam` |
| Listener accuracy | **95.24%** on a 42-item gold set (`qwen2.5:3b`) | `make listener-eval` |
| Stopping rules | **11 defined, 8 fired** in the headline batch | `make eval` |
| Compliance kernel | **13 rules**, all with provenance citations | `make redteam` |
| Ledger | 34,304 entries, chain valid | `make eval` |
| Claims registry | **6 held · 4 refuted · 2 unresolved**, generated from artifacts | `make claims` | `make claims` | `make claims` | `make claims` | `make claims` | `make claims` |
| Currency | ₹ is the simulator; $ is Hillstrom. Deliberately unreconciled — converting would mean inventing a rate for another team's data | — |
| Independent audit | **0 violations** over 5,712 certificates / 467 executed contacts, no agent involved | `make verify-ledger` |
| N6 detection latency | **50 attempts** median at a 78% collapse, monotone in severity, 0 false alarms in 30 controls | `make fleet-latency` |
| Regret — what the silences cost | 554 declined cases: cost ₹134,347, saved ₹93,679, **net ₹-40,669**; pre-registered prediction (170 model errors) HOLDS | `make regret` |
| Tests | **526 passing** across 45 files | `make test` |

---

## 3. What is implemented

### Pipeline
Detector → Diagnoser → Policy (EV / lookahead) → **Compliance kernel** →
Executor → Listener → Ledger. `make demo` runs it end to end with the agent
loop visible.

### The four required blocks
- **B1** — incremental ₹ + CI against a randomised holdout. Done.
- **B2** — escalation ladder, every rung compliance-justified. Done.
- **B3** — all **11 stopping rules** implemented, unit-tested, all reachable.
- **B4** — hash-chained audit trail, browsable, 100% certificate coverage.

### Novelty claims (spec §4)
| # | Claim | Status |
|---|---|---|
| N1 | Incremental-first accounting | **Held.** ₹272,281 with CI vs randomised holdout. |
| N2 | Negative-uplift targeting (do-not-disturbs) | **Held, and now qualified.** DND opt-out ratio 1.29x [1.09, 1.51]; deployed policy contacts 11.53% DND vs mass-contact's 21.98%. The decile chart shows τ̂'s bottom decile is 43.8% true do-not-disturbs against 17.3% of the population, but does *not* realise negative uplift — it locates them without measuring them. The claim survives because it runs through the churn model as a second signal, not through τ̂ alone. |
| N3 | Deterministic India-regulatory compliance kernel | **Held.** 13 rules with provenance, per-action certificates, 100% block rate. |
| N4 | Contact as budget-constrained sequential decision | **Held, bounded.** The lookahead beats greedy by +₹6–7/case at λ=0 with a 5–8 attempt budget, replicated 3/3 draws. At the deployed λ=30 with a 3-attempt budget the two are indistinguishable (−₹0.12/case, sign flips). `LookaheadEVDecisionPolicy` is what ships; the honest statement is that it does not win *at these parameters*, and there is now a measured condition under which it does. |
| N5 | Two-tier validation | **Held.** Criteo + Hillstrom before simulator transfer. |
| N6 | Contact-free recovery | **Held.** Issuer-outage detection suppresses futile retries; no customer messaged. |

### Experiments (15, each with an artifact and a make target)
`tier1_criteo` · `tier2_simulation` · `sensitivity` · `fleet` · `negotiation` ·
`listener_eval` · `ope_deployment` · `fairness` · `pessimism` · `dnd_signal` ·
`horizon` · `uplift_ab` · `churn_lambda` · `uplift_calibration` ·
`regret` · `dr_foldsweep` · `fleet_latency` · `regret`

### Frontend
React + TypeScript + Vite, three.js 3D policy-space, inline SVG charts
generated from `data.json` (never embedded images, so charts cannot drift from
artifacts). `make dashboard` builds it; `make verify-page` asserts 12 sections
and 9 artifact-backed claims render with WebGL both on and off.

The calibration section is the newest and the only one that argues against the
system it documents: a two-panel chart — the ranking above, the residual at its
own zoom below — plus the three pre-registered rules printed with their
outcomes, one of which reads FAILED.

Drawing the residual caught a wrong sentence before it shipped. The first draft
of the section's copy said the predictions "cross the measurements once and are
wrong on both sides of the crossing", which is the tidy story an over-spread
model is supposed to tell. The residual panel showed five sign changes: the
error is concentrated at the two ends (-0.082 on the bottom bin, +0.059 on the
top) and is small and unsigned across the middle. The chart was rendered from
the artifact, so it disagreed with the prose immediately. RESULTS.md and the
commit never carried the claim — the picture caught it first.

---

## 4. The plan, and what it turned into

The original plan was: build the pipeline, validate on real randomised data,
measure against baselines, publish. That is done. The work since has been of a
different kind, and it is the part worth understanding.

**Every experiment now takes `--eval-draws`, and a result is only claimable if
its sign replicates across independent populations.** This rule was not
designed up front. It was forced by watching single-draw conclusions evaporate
five separate times:

| Claim | Single draw said | Replication said |
|---|---|---|
| Sensitivity C2 | 24/25 | 75/75 |
| OPE coverage | clean pass | 69% |
| DND ratio | 1.93x | 1.29x [1.09, 1.51] |
| Lookahead advantage | +₹61/case | sign flipped to −₹2 |
| Ensemble uplift model | +7.1% | undetermined (4 neg, 1 pos) |

The generalisable finding: **a single-draw conclusion is a claim about that
draw.** Every headline figure in §2 has survived this rule.

A third, found in the final pre-submission sweep: **an artifact that nobody
re-runs goes stale silently.** `results_fleet.json` was committed reporting 351
futile retries avoided; the experiment is deterministic and reproduces 340. The
code had changed behaviour and the artifact was never regenerated, so README
and RESULTS.md both quoted a figure that no longer existed. It was the one
headline number with no doc test pinning it — every other figure had one, and
this was the one that drifted. Now pinned.

A second lesson, newer: **a test that cannot fail is worse than no test.** The
λ_churn dominance check was first written against confidence-interval overlap,
which cannot fail in the direction that matters, and would have published a 9%
revenue loss as "strictly dominates" *with an artifact behind it* — the
appearance of rigour aimed at the wrong question.

---

## 5. Known limitations — stated, not hidden

These are published in `RESULTS.md` and should stay published. Underclaiming
buys credibility; the spec says so explicitly.

1. **DR on Criteo reads low.** On three disjoint blocks: −4%, −33%, −44% of the
   true effect. Direction replicates, magnitude does not. Verdict *inconclusive,
   leaning bias* under a pre-registered rule. Ruled out variance (DR's interval
   is 0.82× IPS's). Mechanism named — cross-fitting on a 15% minority arm — and
   **not tested**. Use IPS on this dataset.
2. **Uplift correlation is 0.347, and the predictions are ~a third too spread
   out.** This is the weakest component. A bootstrap ensemble raises the
   correlation to 0.445 (replicated 5/5) but did **not** improve recovered
   value (4 of 5 draws negative). Not shipped. `make calibration` now shows the
   mechanism rather than asserting it: the decile chart's calibration slope is
   0.758, so τ̂ spans -0.064 to +0.285 where the truth spans +0.041 to
   +0.206. The policy thresholds `τ̂ × amount`, so an over-spread τ̂ mis-places
   that threshold in both directions even with the ranking intact — global rank
   agreement was never the objective. The deciles are near-monotone but fail a
   pre-registered Spearman bar of 0.9 (0.879, 0.903, 0.952). **Not corrected**:
   isotonic recalibration would change the deployed threshold and needs its own
   replicated A/B, not a patch.
3. **λ_churn = 4.0 is a judgement call, not an optimum.** It costs 9.1% of
   incremental recovery to buy 27% fewer contacts and 2.3 points less
   do-not-disturb exposure. The curve is monotone; no setting is free.
4. **OPE net-rupee coverage is 69–87% against a nominal 95%.** Identification
   holds; precision does not. Published as such.
5. **All policy comparison is in simulation.** Tier 1 validates the causal
   machinery on real randomised data; the rupee figures are simulator figures
   under stated assumptions.

---

## 6. Next steps for a complete pipeline

Ordered by what most improves the submission. Nothing here is required for the
definition of done — that is §7.

### Tier A — the remaining spec gap
- [x] **Uplift calibration / decile chart.** Done — `make calibration`,
      `experiments/uplift_calibration/`. The expected validation was
      "monotone or near-monotone deciles, and if not, that is the finding":
      **near-monotone, not monotone.** Spearman 0.879, 0.903, 0.952 against a bar of
      0.9 fixed before the run; the ranking itself holds 3/3 draws. Two
      findings came out of it that the correlation number could not have
      produced: the calibration slope is 0.758, which is the mechanism
      `uplift_ab` suspected and could not show; and τ̂'s bottom decile locates
      do-not-disturbs (43.8% vs 17.3% of the population) without realising
      negative uplift. Both published in RESULTS.md, both pinned by doc tests.
      *Left open deliberately:* the slope is not corrected. Isotonic
      recalibration or shrinkage on τ̂ would move the policy's threshold and so
      needs its own A/B under the replication rule — see Tier B.

### Tier B — strengthens the strongest claims
- [x] **Test the DR cross-fitting hypothesis — REFUTED.** This item was
      written believing stratified folds were an outstanding fix; they were
      not — `dr_contributions` already stratifies its k-fold split on the
      *joint* of treatment and outcome and already fits one outcome model
      per arm, not a joint model with treatment as a feature (that was fixed
      earlier; see the docstring on `doubly_robust_value`). What was actually
      untested was narrower: does the residual gap respond to the
      cross-fitting fold count at all. `make dr-foldsweep` swept n_folds over
      {2, 5, 10, 20} on the same three disjoint blocks
      `make dr-diagnosis` uses, under a rule fixed before running (coverage
      rising to 3/3 confirms; coverage and mean gap essentially flat across
      the range refutes). Result: coverage flat at 1/3 at every fold count —
      coarse evidence with only 3 blocks, since coverage is an integer out of
      3 and cannot by itself distinguish no-effect from not-enough-power. The
      continuous mean gap carries the real weight: flat within 4%
      (0.00272–0.00282) across the whole 2→20 range, exactly where a real
      minority-arm-starvation effect should have shown at least partial
      movement. It didn't. **REFUTED** — the hypothesis predicted a shrink
      that appeared at no fold count; cross-fitting is not established as the
      cause. Not claimed: that the mechanism is closed with more certainty
      than a 3-block, 4-point sweep buys — the residual bias's actual cause
      remains open, and the bias itself is unchanged, still "inconclusive,
      leaning bias." See `experiments/tier1_criteo/REPORT.md` and
      `RESULTS.md`.
- [x] **Claims registry.** Done — `make claims`, `CLAIMS.md`, `claims.json`,
      `src/recovery_ledger/claims.py`. Pre-registration stops being a habit
      and becomes a mechanism: a refuted claim cannot be asserted in the
      documents, an artifact carrying a rule cannot go unregistered, and the
      suite fails if every claim ever comes back held.
- [x] **Recalibrate τ̂ and A/B it.** Done — `make recalibration`. **UNDETERMINED**
      and not shipped: draws disagree on sign (-13,736, +39,602, +18,635).
      The correction demonstrably works as arithmetic — the held-out slope moves
      **0.6674 → 0.9508** — and recovered value still does not follow. Third
      measurement of the same lesson: improving a diagnostic (correlation in
      `uplift_ab`, calibration slope here) is not improving the decision.
- [ ] **Decide the ensemble on harm-reduction grounds.** Do-not-disturb rate
      fell in 5/5 draws (−1.76pp) at the cost of ~37 more contacts and
      unmeasured revenue. This is a judgement about what the system is *for*.
      *Expected validation:* if shipped, `tests/test_uplift_ab.py` requires the
      A/B to support it — so the justification must be written as a
      harm-reduction claim, not a revenue one.
- [x] **Fleet change-point over time.** Done — `make fleet-latency`,
      `experiments/fleet/REPORT.md`. The detector fired in **8/8 draws at every
      severity swept**, with latency monotone in severity (median 125 attempts
      for a 20% drop, 50 for a 78% collapse) and **0 false alarms in
      30 control draws**. N6's speed is now measured rather than
      demonstrated. The monotonicity is a check on the detector, not just a
      description: a two-proportion test should clear its threshold on less
      evidence as divergence grows, and it does.

### Tier C — scope worth having if time allows
- [x] **Independent certificate verifier.** Done — `make verify-ledger`,
      `src/recovery_ledger/kernel/verifier.py`. Re-derives every certificate's
      verdict from the rule outcomes recorded inside it and confirms one
      allowing certificate per executed contact, from the ledger file alone.
      Bounded honestly: the context is not recorded, so it proves the kernel's
      reasoning self-consistent and obeyed, not correct.
- [ ] Global contact-budget allocator (knapsack across the fleet, not per-case).
- [ ] Model drift detection on the uplift model.
- [ ] Cost-sensitive channel choice (SMS vs WhatsApp vs voice by expected value).

### Housekeeping
- [x] **`Co-Authored-By` trailers stripped.** Done 1 September 2026. All 79
      commits were rewritten with `git filter-branch --msg-filter`, verified
      tree-identical before and after (`de42db8d…` both sides, zero files
      differing), and force-pushed. `git log --format='%(trailers:only)' |
      grep -c Co-Authored-By` now returns **0**, and the whole history carries
      exactly one identity. The commit-message prose that *discusses* the
      trailer problem was deliberately preserved — the filter was anchored to
      `^Co-Authored-By:`, so the project's record of its own issue survives.
      Attribution to the `vaibhav375` account needs no further git work:
      `handoovaibhav123@gmail.com` is the author on every commit, so GitHub
      attributes them once that address is verified on the account.
- [x] **The "348 tests" commit.** Resolved by the rewrite above — that commit
      no longer exists on `main`. It survives only in the local backup refs,
      which are disposable.

## 7. Definition of done (spec §17)

| Requirement | Status |
|---|---|
| `make demo` runs end to end from a clean clone | ✅ |
| Batch run over ≥ hundreds of cases → incremental ₹ + CI (B1) | ✅ 2,000 cases |
| Escalation ladder, every rung compliance-justified (B2) | ✅ |
| All 11 stopping rules implemented and unit-tested (B3) | ✅ 11 defined, all reachable |
| Hash-chained audit trail, browsable, 100% certificate coverage (B4) | ✅ |
| Tier 1 reproduces known effects on real randomised data | ✅ Criteo + Hillstrom |
| All 5 baselines compared; sensitivity shows stable ranking | ✅ 8 policies, 75/75 both criteria |
| Red team: 100% block rate, 0 violations | ✅ 20/20, 0 leaks in 5,000 |
| Test enforcing no LLM imports under `kernel/` | ✅ |
| Honest exception list published | ✅ `RESULTS.md` |
| README states novelty claims **and what is not novel** | ✅ |
| `ENGINEERING_LOG.md` populated with real failures | ✅ |
| Repo public | ✅ |
| **5-min video recorded, live demo, unlisted** | ❌ **owner's own work** |
| **All 12 form fields ready** | ❌ **owner's own work** |

**The two open items are deliberately not automated.** The video script, the
form answers, and in particular Q12 ("what broke") must be the owner's own
words. Q12 has abundant material: five evaporated single-draw results, a stale
artifact caught by a policy that consults no model, a test that could not fail,
and a frontend build that deleted the page's data with no error anywhere.

---

## 8. Validation expected before submission

Run in this order. Every one must pass.

```bash
make test          # 526 tests
make eval          # B1 headline
make baselines     # 8-policy comparison
make sensitivity   # 75/75 both criteria across 3 draws
make tier1-revenue # real-money effect on a randomised experiment
make tier1-targeting # B1's targeting claim on real randomised data
make recalibration # does fixing the slope pay? (undetermined, not shipped)
make calibration   # uplift by decile: ranking 3/3, near-monotone, slope 0.758
make fleet-latency  # detection latency + false-alarm rate for N6
make regret        # what the silences cost, beside what contacting recovered
make redteam       # 100% block rate, 0 leaks
make claims        # pre-registration registry: 4 held, 3 refuted, 1 unresolved
make verify-ledger # third-party audit: 0 violations, chain valid
make tier1-criteo  # IPS/SNIPS recover the arm-mean ATE
make dashboard     # rebuild page from artifacts
make verify-page   # 12 sections, 9 artifact-backed claims, both paths
make demo          # agent loop visible end to end
```

Then confirm the invariants that have actually broken before:

- [x] `tests/test_results_doc_matches_artifacts.py` passes — no prose/artifact drift.
- [x] `tests/test_experiment_seeds.py` passes — no two experiments share an evaluation population,
      except a declared `"shares"` entry in `SEED_REGISTRY` (`regret/run_regret.py`
      deliberately shares `tier2_simulation/run_batch.py`'s population, and
      `churn_lambda/run_lambda_sweep.py` shares `run_baselines.py`'s — both by
      design, not by omission).
- [x] `tests/test_css_class_collisions.py` passes — no silent layout collisions.
- [x] `tests/test_frontend_build_preserves_data.py` passes — `data.json` survives a frontend build.
- [x] `tests/test_deployed_policy_is_named_correctly.py` passes — no document names a policy the code does not run.
- [ ] `git status` clean; `git log origin/main..HEAD` empty.
- [x] `git log --format='%an <%ae>' | sort -u` shows exactly one identity.
- [x] Every figure in this file matches its artifact — verified 1 September
      2026 against results.json, results_uplift_calibration.json,
      results_dnd_signal.json, results_fleet_latency.json and claims.json.

**Note on ordering:** `make dashboard` depends on `frontend-build` and must run
*after* it. Running `make frontend-build` alone used to delete
`dashboard/dist/data.json`; that is fixed (`emptyOutDir: false`) and tested, but
the dependency direction is still worth knowing.
