# Engineering Log

Dated, unedited-after-the-fact record of what broke, what was tried, what actually
fixed it, and what was concluded. Dead ends are kept, not cleaned up — they are the
most useful entries for anyone re-running this work. This file feeds the buildathon
form's Q12 ("what broke, and how you got out") directly from source.

---

## 2026-08-23 — Project start

Read `RAZORPAY_BUILDATHON_TRACK3_SPEC.md` end to end. Verified the Track 03 brief
against the live buildathon page by pulling raw HTML directly (the page is
client-rendered; a plain fetch only returns the header) — confirmed the track
description, "the bar", stipend/duration/location, and the application form link
all match the spec verbatim. Deadline is 5 September 2026; the spec's 16-day plan
assumed a 20 August start, so the real remaining runway from today is 13 days, not
16. Recalibrated the phase-by-phase calendar accordingly.

Decisions locked in before writing any code:
- Repo: `recovery-ledger`, public on GitHub from commit 1.
- Stack: Python 3.11+, `uv`, `pytest`. `econml` for the uplift meta-learners
  (S/T/X-learner, causal forest via `CausalForestDML`, doubly-robust via
  `DRLearner`) and `scikit-uplift` for dataset fetching (Hillstrom, Criteo) and
  Qini/AUUC metrics — chosen over hand-rolling causal estimators or pulling in
  `causalml` (heavier native build requirements, more fragile in a 13-day budget).
- No LLM API key is configured yet. Every LLM-touching component (persona
  simulation, reply-intent listener, message drafting, negotiation dialogue) is
  being built behind a single interface (`src/recovery_ledger/llm/`) with a
  deterministic mock/cache backend first. Swapping in a real Anthropic client
  later should not require touching any calling code — this is the test of
  whether that boundary is actually clean.
- Deviating from the spec's literal day-by-day ordering in one place: the spec
  sequences the full agent loop (detect→diagnose→decide→gate→act→listen→stop) at
  Days 8–9, after the kernel and policy exist. Building a fully-stubbed
  end-to-end skeleton immediately after the Tier 1 gate instead, so `make demo`
  never has a stretch of days where the repo looks like a research notebook
  rather than a running agent (this is Rule 2 of the spec's own working
  agreements, taken literally).

Next: Tier 1 kill gate (§7.2) — Hillstrom first for iteration speed, then a
Criteo subsample. This is a hard stop: if the uplift learners and doubly-robust
estimator can't reproduce known treatment effects on real randomised data, the
project's central thesis is dead, and that has to surface today, not on day 10.

## 2026-08-23 — Tier 1 kill gate: PASSED (with one open finding)

Built `src/recovery_ledger/policy/ope/estimators.py` (IPS, SNIPS, DR — hand-
written, not from a library, since this is a headline methodological
component) and `src/recovery_ledger/policy/uplift/learners.py` (typed
wrappers around econml's S/T/X-learner and CausalForestDML). Validated the
OPE estimators first against a fully-controlled synthetic RCT with a known
oracle treatment effect (`tests/test_ope_estimators.py`) — all 6 tests passed
on the first run, including the property that DR's confidence interval is
narrower than IPS's at equal sample size.

Then ran the real Tier 1 validation. Full numbers and reproduction commands
are in `experiments/tier1_criteo/REPORT.md`; the headline: on both Hillstrom
and a 2% Criteo subsample, all four uplift learners score positive Qini/AUUC
(real heterogeneous signal, not noise), and IPS/SNIPS reproduce the datasets'
direct arm-mean treatment effect exactly. **Verdict: kill gate passed.**

Three real dead ends hit along the way, in order:

1. **`uv pip install -e .` produced a package that silently wasn't
   importable**, even after adding `__init__.py` files everywhere. Root
   cause: the editable install's `.pth` file (`_editable_impl_recovery_ledger.pth`,
   just a single line containing the absolute path to `src/`) was present,
   correctly formatted, and pointed at a real, readable directory — but
   Python's `site.addpackage()` was silently not processing it in this
   environment (confirmed by calling `site.addpackage()` directly: it
   returned `None` and added nothing to `sys.path`, with no exception raised
   anywhere in the call chain). Never root-caused *why* — spent real time on
   it (checked file encoding/BOM, `os.path.exists`, `io.open_code`, whether a
   virtualenv-seeder hook was interfering) and every individual piece of the
   mechanism checked out fine in isolation, yet the whole didn't work.
   Stopped debugging a Python stdlib internal and switched to something
   robust instead: pytest's built-in `pythonpath = ["src"]` ini option for
   tests, and `PYTHONPATH=src` for scripts. Don't revisit this unless it
   starts causing a different symptom — the workaround is not fragile.

2. **`sklift.datasets.fetch_criteo` returns `403 Forbidden`.** The package
   points at a Criteo-hosted S3 bucket (`criteo-bucket.s3.eu-central-1.amazonaws.com`)
   that's no longer publicly readable. Not a code bug — confirmed by hitting
   the URL directly. Fell back to the HuggingFace mirror
   (`criteo/criteo-uplift`) the spec itself lists as an alternative access
   path (§7.2). That mirror serves the dataset as 4 parquet shards.

3. **Those parquet shards are not row-shuffled.** Shard 0 is 100% one
   treatment arm (checked directly: `treatment.value_counts()` on shard 0
   returns only `1`, all 3.91M rows). This means naively sampling from a
   single shard, or even concatenating shards without checking, could produce
   a subsample with a badly wrong treatment ratio — the parquet conversion
   preserved the original file's row order, which is grouped by treatment,
   not randomised storage order. Fix: download and concatenate all 4 shards
   (340MB total, 14.0M rows) before taking any random subsample. Verified the
   fix by checking the pooled dataset's treatment ratio (0.850) and outcome
   rates (visit 4.699%, conversion 0.2917%) against the spec's cited
   published benchmarks (0.85, ≈4.7%, ≈0.29%) — matched.

One finding that surfaced honestly rather than being tuned away: the DR
estimator's implied ATE is further from the direct arm-mean ATE on Criteo
(gap 0.0027, after a fix) than on Hillstrom (gap 0.0012). Traced it to
Criteo's 85/15 treatment imbalance interacting badly with the outcome
model's calibration on the minority arm — refit DR's internals to use one
outcome model per treatment arm instead of one joint model with treatment as
a feature (the standard DR formulation, which the first draft had
simplified away), which shrank the gap from 0.0036 to 0.0027 but didn't
eliminate it. Left open rather than further tuned in place — see
`experiments/tier1_criteo/REPORT.md` for the full account and the candidate
next fix (better-calibrated outcome model, more cross-fitting folds).

Awaiting go-ahead before starting Tier 2 (domain simulator), per the
project's own non-negotiable rule that Tier 1 is a hard stop.
