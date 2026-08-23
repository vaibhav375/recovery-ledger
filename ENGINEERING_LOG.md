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

## 2026-08-23 (cont.) — Agent loop skeleton runs end to end

Go-ahead received. Built the thin, fully-real (not fake-stub) skeleton
flagged as a deliberate reordering back in the first log entry: event
schemas for all 4 loss types (`events/schemas.py`, pydantic, discriminated
union on `loss_type`), a hash-chained append-only ledger
(`ledger/ledger.py`), a deny-by-default compliance kernel
(`kernel/engine.py`) with 3 real rules (contact hours, opt-out cooling,
contact budget) and the mechanically-enforced no-LLM-import test
(`tests/test_kernel_no_llm_imports.py` — verified it actually catches a
violation, not just passes vacuously, by temporarily dropping an
`import anthropic` into `kernel/` and confirming the test fails, then
removing it), and the orchestrator (`agent/loop.py`) tying detector,
diagnoser, policy, kernel, executor, and listener together with a hard
step cap as a termination safety net.

`make demo` runs 20 synthetic cases across all 4 loss types through the full
loop and writes a verified-valid hash chain. Confirmed determinism isn't
just claimed: ran it twice and diffed the output — byte-identical.

One real bug caught by actually running it, not just writing it: the
synthetic case generator (`sim/generator.py`) used
`numpy.random.Generator.choice()` directly on a list of `str`-subclassed
`Enum` members (`Language`, `Channel`, `LossType`). NumPy silently coerces
enum members into a bogus fixed-width string dtype when building its
internal array — the values that came back out weren't valid enum members
at all (`np.str_('Language')` instead of `Language.EN`), which pydantic
correctly rejected. Fixed by sampling an index and indexing back into the
plain Python list instead of asking NumPy to touch the enums.

Also caught before it became a nasty repro-mismatch bug later: `cli.py`'s
first draft used wall-clock `datetime.now()` as the simulated world's
reference time, which would have made `make demo`'s case set different on
every run despite the fixed `--seed` — exactly the kind of thing spec's
"a judge re-running the repo must get my numbers" rule exists to catch.
Pinned to a fixed reference datetime; ledger entry timestamps (which record
when the run actually happened, correctly) are unaffected.

Everything in this loop except the ledger and the 3 kernel rules is still a
stub: the policy proposes a fixed 2-step sequence rather than real EV
decisioning, and the listener always returns `NO_REPLY` (no reply channel
wired). That's why every demo case currently ends in `negative_ev` — the
stub policy exhausting its fixed sequence, not a real decision. Expected,
not a bug; will change once the uplift/EV policy is transferred in.

35/35 tests passing (`make test`).
