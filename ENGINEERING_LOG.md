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

## 2026-08-23 (cont. 2) — Full compliance rule set (11 rules), COMPLIANCE.md

Extended `RuleContext` with structured consent/DLT/mandate state (mirroring
the certificate justification example in spec section 9.3's field names),
then implemented the rest of spec section 9.2's rule list: DLT registration,
header-class matching, consent validity, opt-out-option presence, and
number-series (`kernel/rules/tcccpr.py`); the e-mandate pre-debit notice
window (`kernel/rules/emandate_2026.py`); a DPDPA consent-record check
(`kernel/rules/dpdp.py`); and a tone-intensity escalation ceiling
(`kernel/rules/escalation.py`) that directly backs bar requirement B2
("compliant escalation... every rung is legally justified").

Wrote `COMPLIANCE.md`: every rule, its file, what it checks, and its source
citation. Two things flagged there rather than silently decided:

1. The 7-day explicit-consent-expiry rule's exact scope is genuinely
   ambiguous in the source material (does it apply to all explicit
   consent for service messages, or only consent reused from a different
   original purpose?). Encoded the strict/literal reading — a deny-by-
   default kernel should fail toward more restrictive when unsure, not
   less.
2. AFA requirements for mandate registration/modification/withdrawal are
   NOT encoded, because there's no `ActionType` in this project that
   represents those operations — the agent only acts against existing
   mandates. A rule against an action that can never be proposed would
   test nothing, so it's recorded as a gap instead of faked.
3. Purpose limitation and retention (DPDPA) aren't per-action rules at
   all — they're structural properties of what the system stores, and
   retention specifically is an honest open gap (no ledger purge policy
   exists yet).

Wired the full 11-rule kernel into `cli.py`'s default agent and re-ran
`make demo`: it now genuinely denies a real case rather than always
allowing — `case_000014` (a failed-subscription mandate retry) gets
`REGULATORY_CEILING` because its retry attempt landed 22.53 hours after its
pre-debit notice, 1.47 hours short of the 24-hour minimum. Checked this by
reading the actual certificate out of the written ledger, not by assuming
the rule fired for the reason intended:

```
DENIED BY: EMANDATE2026.PRE_DEBIT_NOTICE
  {'pre_debit_notice_sent_at': '2026-08-22 13:28:27+00:00',
   'hours_before_debit': 22.53, 'min_required_hours': 24}
```

19/20 demo cases still end in `negative_ev` (the stub policy exhausting its
fixed sequence) — expected, unchanged from before, since the policy itself
is still a stub.

57/57 tests passing (35 existing + 22 new rule tests), all added and green
before this was committed.

## 2026-08-23 (cont. 3) — LLM provider decision: local Ollama, qwen2.5:3b

Asked which LLM provider to build the persona simulation / listener /
drafting / negotiation components against. Answer: best available
open-source model, no subscription — meaning local inference, not a paid
API. This is a real constraint change from the original spec's assumption
of an API-based LLM and needed an actual decision, not a default guess.

Checked the hardware first rather than assume a model size: this machine is
a MacBook Air, Apple M1, **8GB RAM**. That's tight for anything above a 7B
model. Ollama was already installed with `qwen2.5:3b`, `qwen2.5:7b`,
`qwen3:4b`, and `llama3.2:3b` already pulled.

Ran the actual task (generate a Hinglish customer reply about paying after
salary on the 5th) on all three plausible candidates rather than pick by
spec-sheet size:

| Model | Time | Result |
|---|---|---|
| qwen2.5:3b | 8.7s | Correct Hinglish: "subscription pay fail ho gayi hai... salary aaye to pay karenge" |
| qwen2.5:7b | 30.3s | Mostly **English** despite the same instruction — worse fit, 3.5x slower |
| qwen3:4b | 110.8s | Best quality Hinglish, but a "thinking" model — even with `/no_think` it burned ~2 min per call. Unusable at batch scale (hundreds of simulated cases) |

**Decision: qwen2.5:3b as the default local model.** Counterintuitive
result worth keeping on record: the smaller model won on the one property
that actually mattered for this project (reliably switching into Hinglish
on instruction), and the "thinking" model that reasoned its way to the best
single answer is disqualified by its own latency the moment you need to run
it hundreds of times in a batch, which B1 explicitly requires.

Built `src/recovery_ledger/llm/client.py`: an `LLMClient` Protocol, a real
`OllamaClient` (HTTP against `localhost:11434`, confirmed working against
the actual running server, not just plausible-looking code), and a
`MockLLMClient` that isn't a temporary stand-in — it's what keeps `make
demo` working for anyone who clones this repo without Ollama installed.
`build_default_client()` checks Ollama's actual availability at call time
and falls back to the mock rather than crash. None of this is wired into
`cli.py`'s default demo agent yet (still the stub Listener) — that's next,
and it has to preserve the "runs from a clean clone with zero external
services" guarantee for the base demo path.

63/63 tests passing (6 new, including one real integration test against the
locally running Ollama server — not just a mock-only test suite pretending
to cover this).

## 2026-08-23 (cont. 4) — B1 achieved: real EV policy, real simulator, real ₹ number

The big gap flagged at the last status checkpoint: nothing in the repo
computed a ₹ recovery number yet, because policy and listener were both
stubs. Closed that today.

Built, in order:
- `sim/environment.py`: the response model ("recovery gym", spec 7.3).
  Hidden latent traits (liquidity, annoyance_threshold, dispute_propensity)
  drive a `persuadability(traits)` function that can go negative — the
  do-not-disturb segment (N2) falls out of the model rather than being
  hand-coded as a special case. Retry success rates loosely anchored to
  spec 3.2's published figures (17% generic, 35% subscription smart-retry,
  1% hard-decline). Every constant is stated as invented in the module
  docstring — anchoring an aggregate rate doesn't validate a causal
  response, which is the whole reason Tier 1 had to happen separately.
- Extended `Listener` to receive the case and action, not just a bare
  case_id, and added `EnvironmentListener` adapting the response model to
  that interface — the unmodified agent loop now runs against simulated
  outcomes with zero changes to `agent/loop.py`'s structure.

**Caught a real bug before it could corrupt anything**, by thinking through
the holdout-policy design before writing it: audited whether kernel rules
treat `WAIT` the same as `RETRY` (both "not customer contact"), and found
only `timing.py` did. `budget.py`, `dpdp.py`, `escalation.py`,
`opt_out.py`, and `tcccpr.py`'s `_is_customer_contact` all exempted RETRY
but not WAIT — meaning a "do nothing" holdout policy issuing WAIT would
have been incorrectly gated by rules meant for outbound communications.
Fixed all five, added `tests/test_kernel_wait_exempt.py` with a
"worst-case context" regression test (every field set to whatever would
deny a real contact action) that confirms WAIT passes everything while the
identical context correctly still denies NUDGE — proving the test exercises
the exemption rather than a context that happens to pass regardless of
action type.

Then: `policy/features.py` (case → numeric vector, observable fields only —
deliberately excludes anything from `LatentTraits`, or the "learner" would
just read the answer key), `EVDecisionPolicy` and `DoNothingPolicy` in
`policy/decision.py` implementing the EV formula from spec 8.3 (simplified:
no explicit LTV/churn term — modelling per-customer LTV would need
assumptions with no basis to validate, so it's left out rather than
invented, and said so in the docstring).

Two test-writing mistakes surfaced real arithmetic I'd gotten wrong before
committing to it: expected a hard-decline case with zero uplift to STOP,
but RETRY is free and even a 1%-success free action has positive EV, so it
correctly chose RETRY instead — fixed the test, not the code, since the
code was right. Same pattern for an "annoyance eventually dominates"
test — the modest uplift I'd picked (0.1) was already smaller than the
fixed retry EV at attempt zero, so NUDGE was never going to win; raised it
to 0.3 so the test actually exercises what it claims to.

`experiments/tier2_simulation/run_batch.py`: trains a T-learner (the exact
class Tier 1 validated) on 1000 randomised-contact simulator cases, then
runs a disjoint 1000-case eval batch split 50/50 into a treatment arm
(`EVDecisionPolicy`) and a randomised no-contact holdout arm
(`DoNothingPolicy`), through the same `RecoveryAgent`/kernel/ledger
machinery. Ran it, checked the output made sense before trusting it: the
holdout arm's 13.43% recovery rate is close to the organic-resolution math
(1-0.95³≈14.3%) — the holdout is behaving like a no-contact baseline should,
not doing anything unaccounted for. Ran it twice, diffed — byte-identical.

**Result: ₹996,519 incremental per 1,000 cases (95% CI ₹672,862–₹1,342,154).**
CI excludes zero. Full result, method, and — importantly — what's NOT yet
included (4 of 5 baselines, sensitivity sweep, cost-per-incremental-rupee)
in `experiments/tier2_simulation/REPORT.md`. Claim scope stated explicitly
at the top of that report: policy dominance under stated assumptions, in
simulation, never a real-world effect size.

Wired `make eval` for real (was a stub that printed "not yet implemented").
`make demo` is untouched — still the stub policy, zero external
dependencies, fast — kept deliberately separate from `make eval` so the
base demo path never gets slower or more fragile as the real pipeline grows.

87/87 tests passing (13 new: environment model, WAIT-exemption regression,
decision policy, batch experiment consistency/determinism).

## 2026-08-24 — The B1 number from yesterday was wrong. Found it, fixed it, re-ran everything.

Asked to work through known bugs and validate the pipeline before moving
on. The most important thing that came out of taking that seriously: the
₹996,519 headline number from 2026-08-23 was not a real result.

It looked fine on its own terms — deterministic, internally consistent
(holdout recovery rate matched the organic-resolution math independently),
CI excluded zero, and the previous day's report even flagged the
do-not-disturb-contact rate as a specific thing to check ("1.52%... not yet
root-caused"). Went back to actually check it rather than let a
plausible-looking number stand. Computed `corr(tau_hat, tau_true)` — the
fitted uplift model's prediction against the simulator's own hidden ground
truth — on held-out data: **-0.02**. Indistinguishable from noise.

Root cause: `sim/environment.py`'s `generate_population()` drew every
hidden trait (liquidity, annoyance_threshold, dispute_propensity)
independently of every observable case field. Since the true treatment
effect (`persuadability()`) is a pure function of those hidden traits, it
was therefore statistically independent of every feature the uplift model
had to learn from — by construction, not by bad luck. There was nothing to
learn no matter how good the learner was. The reported 1.52%
do-not-disturb-contact rate wasn't targeting skill; the true population
do-not-disturb rate was itself ~1.5%, so near-random targeting would have
shown almost the same number by coincidence. This is exactly the
"plausible simulator, unvalidated causal structure" trap spec section 7.1
describes for the domain simulator generally — turns out it's possible to
fall into a version of it by accident even after doing the two-tier
validation the spec prescribes, if the *transfer* step itself has a design
flaw.

Fixed `generate_population()` to derive traits with a declared dependence
on observable fields (B2B/amount → liquidity, B2B/loss-type → dispute
propensity, channel preference → annoyance threshold). First attempt used
shifts of 0.10-0.15 against traits with ~0.2 natural standard deviation —
checked again rather than assumed fixed: correlation was still weak and,
more tellingly, *not monotonic* in training set size (0.15 at n=1000, 0.16
at n=5000, dropping to 0.08 at n=20000) — the fingerprint of a signal too
marginal to reliably detect, not a "just needs more data" problem. Roughly
doubled the shift magnitudes. Correlation became monotonic and substantial:
0.15 → 0.24 → 0.42 as training size went 1000 → 2000 → 5000. That
monotonic-with-data shape is itself the evidence this is now a real,
learnable signal rather than an artifact — the kind of check that's more
convincing than any single number.

Added this correlation as a permanent, printed, and tested part of every
`make eval` run (`uplift_model_correlation_with_true_persuadability` in
`results.json`, with a regression test that fails if it drops back toward
zero) — this class of bug should never again require someone thinking to
manually check for it.

Also caught while fixing this: `Makefile`'s `eval` target hardcoded
`--n-train 1000 --n-eval 1000`, silently overriding the script's own
default even after the default was raised to 5000/2000 for a more reliable
fit. Would have kept running the weak-signal configuration indefinitely.
Fixed.

**Re-ran the full experiment. New, honest result: ₹220,074 incremental per
1,000 cases (95% CI ₹90,448–₹341,757).** Smaller than yesterday's
withdrawn figure, as expected — that figure was inflated by a policy
benefiting from RETRY/NUDGE's population-average effect while not
genuinely targeting on any real signal. This figure reflects real (if
imperfect — 0.41 correlation, not 1.0) learned heterogeneity. CI still
excludes zero. Do-not-disturb contact rate is honestly 16.26%, not 1.52% —
worse-looking, but real, and now the actual target for the next
improvement (try the X-learner or causal forest already implemented in
`policy/uplift/learners.py` but not yet swapped in). Verified deterministic
again (ran twice, diffed, byte-identical). Updated
`experiments/tier2_simulation/REPORT.md`, README, and this log with the
full account rather than quietly replacing the number.

90/90 tests passing (3 new: two trait-correlation regression tests in
`test_environment.py`, one uplift-correlation regression test in
`test_tier2_batch.py`).

While re-validating, also caught and precisely characterised a smaller,
separate issue: re-running Tier 1's Hillstrom validation produced identical
uplift-learner outputs (Qini, AUUC, predicted CATE — bit-for-bit) but a
tiny difference in the DR off-policy estimator's implied ATE (0.046255 vs
0.046222 at full precision). Ran it 3 more times to check the pattern
rather than shrug it off: all agreed to 4 decimal places (+0.0462), which
points at floating-point non-associativity in multi-threaded BLAS
operations inside `GradientBoostingClassifier` rather than an actual
unseeded random source — every explicit random draw in this codebase is
seeded, and a real seeding gap wouldn't produce results this stable across
repeats. Corrected `experiments/tier1_criteo/REPORT.md`'s reproducibility
claim to state this precisely rather than the blanket "reproduce it
exactly" it said before.
