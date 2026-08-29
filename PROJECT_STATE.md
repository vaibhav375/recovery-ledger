# Recovery Ledger — project state

**Track 03 (AI Revenue Recovery), Razorpay AI Buildathon.**
Repo: https://github.com/vaibhav375/recovery-ledger (public)
Deadline: **5 September 2026**. Last updated: **30 August 2026** (6 days out).

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
| Tests | **396 passing** across 39 files | `make test` |

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
| N2 | Negative-uplift targeting (do-not-disturbs) | **Held.** DND opt-out ratio 1.29x [1.09, 1.51]; deployed policy contacts 11.53% DND vs mass-contact's 21.98%. |
| N3 | Deterministic India-regulatory compliance kernel | **Held.** 13 rules with provenance, per-action certificates, 100% block rate. |
| N4 | Contact as budget-constrained sequential decision | **Held, bounded.** The lookahead beats greedy by +₹6–7/case at λ=0 with a 5–8 attempt budget, replicated 3/3 draws. At the deployed λ=30 with a 3-attempt budget the two are indistinguishable (−₹0.12/case, sign flips). `LookaheadEVDecisionPolicy` is what ships; the honest statement is that it does not win *at these parameters*, and there is now a measured condition under which it does. |
| N5 | Two-tier validation | **Held.** Criteo + Hillstrom before simulator transfer. |
| N6 | Contact-free recovery | **Held.** Issuer-outage detection suppresses futile retries; no customer messaged. |

### Experiments (13, each with an artifact and a make target)
`tier1_criteo` · `tier2_simulation` · `sensitivity` · `fleet` · `negotiation` ·
`listener_eval` · `ope_deployment` · `fairness` · `pessimism` · `dnd_signal` ·
`horizon` · `uplift_ab` · `churn_lambda`

### Frontend
React + TypeScript + Vite, three.js 3D policy-space, inline SVG charts
generated from `data.json` (never embedded images, so charts cannot drift from
artifacts). `make dashboard` builds it; `make verify-page` asserts 9 sections
and 5 artifact-backed claims render on both the React and fallback paths.

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
2. **Uplift correlation is 0.347.** This is the weakest component. A bootstrap
   ensemble raises it to 0.445 (replicated 5/5) but did **not** improve
   recovered value (4 of 5 draws negative). Not shipped. The reason
   generalises: the policy thresholds `τ̂ × amount`, so calibration near the
   boundary matters, not global rank agreement.
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
- [ ] **Uplift calibration / decile chart.** The spec's evaluation protocol
      (§11) asks for it and it is the one required artifact absent. Plot
      predicted uplift decile against realised uplift on the holdout.
      *Expected validation:* monotone or near-monotone deciles; if not, that is
      itself the honest finding and belongs in RESULTS.md. Add a doc test
      pinning the decile figures.

### Tier B — strengthens the strongest claims
- [ ] **Test the DR cross-fitting hypothesis.** The mechanism is named but
      untested. Refit with stratified folds that guarantee minority-arm balance,
      or increase folds, and re-run `make dr-diagnosis`.
      *Expected validation:* either coverage rises to 3/3 (hypothesis confirmed,
      weak spot closed) or it does not (hypothesis refuted, still progress).
      Either outcome is publishable; do not tune until it passes.
- [ ] **Decide the ensemble on harm-reduction grounds.** Do-not-disturb rate
      fell in 5/5 draws (−1.76pp) at the cost of ~37 more contacts and
      unmeasured revenue. This is a judgement about what the system is *for*.
      *Expected validation:* if shipped, `tests/test_uplift_ab.py` requires the
      A/B to support it — so the justification must be written as a
      harm-reduction claim, not a revenue one.
- [ ] **Fleet change-point over time.** N6 currently detects an outage; showing
      detection latency against a known injected change-point would make it
      measurable rather than demonstrated.

### Tier C — scope worth having if time allows
- [ ] Global contact-budget allocator (knapsack across the fleet, not per-case).
- [ ] Model drift detection on the uplift model.
- [ ] Cost-sensitive channel choice (SMS vs WhatsApp vs voice by expected value).

### Housekeeping
- [ ] Commit `8d424b2` says "348 tests" when it was 331. Amending needs a
      force-push. **Owner's call** — a wrong number in a commit message is a
      small blemish; a rewritten public history may be a larger one.

---

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
make test          # 396 tests
make eval          # B1 headline
make baselines     # 8-policy comparison
make sensitivity   # 75/75 both criteria across 3 draws
make redteam       # 100% block rate, 0 leaks
make tier1-criteo  # IPS/SNIPS recover the arm-mean ATE
make dashboard     # rebuild page from artifacts
make verify-page   # 9 sections, 5 artifact-backed claims, both paths
make demo          # agent loop visible end to end
```

Then confirm the invariants that have actually broken before:

- [ ] `tests/test_results_doc_matches_artifacts.py` passes — no prose/artifact drift.
- [ ] `tests/test_experiment_seeds.py` passes — no two experiments share an evaluation population.
- [ ] `tests/test_css_class_collisions.py` passes — no silent layout collisions.
- [ ] `tests/test_frontend_build_preserves_data.py` passes — `data.json` survives a frontend build.
- [ ] `tests/test_deployed_policy_is_named_correctly.py` passes — no document names a policy the code does not run.
- [ ] `git status` clean; `git log origin/main..HEAD` empty.
- [ ] `git log --format='%an <%ae>' | sort -u` shows exactly one identity.
- [ ] Every figure in this file matches its artifact.

**Note on ordering:** `make dashboard` depends on `frontend-build` and must run
*after* it. Running `make frontend-build` alone used to delete
`dashboard/dist/data.json`; that is fixed (`emptyOutDir: false`) and tested, but
the dependency direction is still worth knowing.
