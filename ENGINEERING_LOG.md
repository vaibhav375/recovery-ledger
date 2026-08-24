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

## 2026-08-24 (cont.) — 5-baseline comparison: an uncomfortable, honest result

Next planned step after the bug fix: spec section 11.3's required 5-way
baseline comparison (do-nothing, blast-everyone, Razorpay-current,
rules-based dunning, this project's EV policy). Added
`BlastEveryonePolicy`, `RazorpayCurrentPolicy`, `RulesBasedDunningPolicy` to
`policy/decision.py` and `experiments/tier2_simulation/run_baselines.py`,
running all 5 against the same 2000-case eval batch.

Two findings surfaced by actually running it, not by assuming the ranking
would come out favourably:

1. `blast_everyone` and `rules_based_dunning` produce byte-identical
   outcomes. Traced immediately: `sim/environment.py`'s response model
   doesn't differentiate pay probability by channel at all, so two
   "different" always-contact policies that differ only in default channel
   choice are the same policy from the simulator's point of view. Not
   fixed today (documented instead) — real simulator gap worth revisiting.

2. **The EV policy currently recovers LESS gross/incremental ₹ than blind
   contact, and its incremental CI includes zero** (₹91,696 vs
   blast-everyone's ₹355,209 per 1,000 cases). This is not the result a
   "smarter" policy is supposed to produce. Investigated rather than
   filed away: swept `lambda_annoyance` from 30 down to 0 — recovery moved
   only 30.60%→31.25%, nowhere near closing the 4.65-point gap to
   blast-everyone's 35.90%, ruling out annoyance-cost miscalibration as
   the main driver. Best working explanation: `sim/environment.py` treats
   each NUDGE as close to an independent Bernoulli trial (probability
   barely decays until real overcontact), so persistence compounds — three
   independent tries beat one greedy estimate. The EV policy makes a
   single-attempt, single-estimate decision each round and can give up
   early on a case whose noisy `tau_hat` (0.41-correlated, not 1.0) looks
   weak that specific round, forfeiting compounding value a policy with no
   judgement at all captures automatically. Spec section 8.3 explicitly
   permits the greedy simplification; this is a concrete, evidenced case
   of the cost of taking it, not a hypothetical one.

Also checked what the EV policy IS doing better, instead of only reporting
the bad news: its do-not-disturb contact rate (14.76%) is genuinely lower
than blind targeting's (20.49%) — measured on the real, correlation-tested
signal, not noise. Reported both halves plainly in
`experiments/tier2_simulation/REPORT.md`: not yet unambiguously better than
naive persistence on raw ₹ this batch, measurably better at avoiding
customers who shouldn't be contacted at all. Concrete next steps identified
and left for later, not attempted today under time pressure: proper
multi-attempt value modelling (lookahead/DP correction to the greedy EV,
not a single-shot estimate per round) and trying the X-learner or causal
forest already implemented but not yet swapped in.

94/94 tests passing (4 new: one per new baseline policy, one integration
test running all 5 against the same batch).

## 2026-08-24 (cont. 2) — Chasing the EV policy's underperformance: two wrong hypotheses, then two real bugs

Started on the prioritised follow-up list, item 1: the EV policy losing to
naive mass-contact. This entry is the most useful one in this log so far,
because most of it is wrong turns.

**Wrong hypothesis 1 — a better learner would fix it.** Compared all four
uplift learners on correlation with true persuadability. Result: s=0.42,
t=0.40, x=0.37 — all comparable, none a fix. Also found `causal_forest`
emitting CATE estimates with mean **-1.21 and std 4.84**, which are
*impossible* for a treatment effect on a probability (must be in [-1,1]);
only 29% of its predictions were even in range. Caught only because I
printed the distribution rather than just the correlation.

Two feature defects surfaced while investigating that: `amount_at_risk` was
~4000x the scale of every other (0/1) feature, and the full one-hot
encoding made the design matrix rank-deficient (rank 11 of 16 — three
constant-zero columns, plus each one-hot group summing to 1 creating
dependencies *between* groups). Fixed both: log1p the amount, drop the
first level of each categorical (which is what Tier 1's
`pd.get_dummies(drop_first=True)` was already doing — the domain pipeline
had quietly diverged from the validated one). Honest outcome: **this did
not fix causal_forest** (in-range went 29%→60%, still broken). I had
written a comment claiming the scaling fixed it before verifying; deleted
that claim rather than leave a false statement in the code. Causal forest
is now documented as a known defect and excluded, not silently dropped.

**Wrong hypothesis 2 — missing multi-attempt compounding.** Built
`LookaheadEVDecisionPolicy`: a finite-horizon DP over the remaining attempt
budget, so an action's value includes the option to keep working the case
if it doesn't resolve now. Measured: gross 1,128,226 vs greedy's 1,131,714.
**Essentially no change.** Two hypotheses, two misses.

**Then stopped guessing and instrumented.** Logged the actual action mix,
stop reasons, and per-loss-type recovery for both policies. That found it
immediately, and it was nothing I'd guessed:

1. `greedy_ev` had **240 `regulatory_ceiling` stops; `blast_everyone` had
   zero.** The loop mapped any single kernel DENY straight to case
   termination. The EV policy prefers RETRY on mandate cases, ~half of
   which the 24h pre-debit-notice rule denies — so it was being killed for
   using more of the action space, while a policy that only ever nudges
   never tripped that rule at all. Spec section 10 rule 10 says stop when
   the kernel denies *all remaining* actions; the loop was implementing
   "denied the first action we happened to propose". A spec-compliance bug
   masquerading as a policy-quality problem.
2. Per-loss-type recovery showed `greedy_ev` at **8.1% on overdue
   receivables vs do-nothing's 13.9%** — the agent was doing actively worse
   than not existing on that segment. Cause: `if best_ev <= 0: STOP`
   conflated STOP with WAIT. WAIT is free, contacts nobody, and preserves
   organic self-resolution; STOP throws the case away. The policy was
   abandoning cases rather than costlessly waiting.

Fixed both (loop falls back to WAIT and only stops when that is also
denied; policies return WAIT instead of STOP when nothing has positive EV).
Together these closed essentially the whole gap: EV policy gross went
1,131,714 → 1,595,699 against blast_everyone's 1,598,606.

**Where that leaves the claim.** The agent is now statistically
indistinguishable from blind mass-contact on recovery (₹353,755 vs
₹355,209, overlapping CIs) using **1,733 contacts instead of 4,393** — 2.5x
better cost per incremental rupee, fewer do-not-disturbs reached. So the
defensible claim is *efficiency*, not a bigger headline number, and the
report says exactly that rather than implying the agent "wins".

Headline B1 re-run with the lookahead policy: **₹376,484 per 1,000 cases
(95% CI ₹203,979–₹554,243)**, up from ₹220,074. Both experiments verified
deterministic again (run twice, diffed, byte-identical).

One honest regression to note: do-not-disturb contact rate went *up*
slightly (16.26% → 18.45%) — a direct consequence of the loop fix, since
cases that were previously killed by a single denial now survive and get
contacted. Real tradeoff, recorded rather than buried.

100/100 tests passing (5 new lookahead-policy tests, including one that
verifies do-not-disturb protection survives the reformulation; 3 existing
tests updated because the WAIT-instead-of-STOP behaviour is deliberately
different — the opt-out test was rewritten to assert the actual safety
property, "an opted-out customer is never contacted", rather than the
incidental stop-reason it previously checked).

## 2026-08-24 (cont. 3) — Auditing my own comparison design: two statistical bugs, and the test that could have falsified the whole claim

Asked to check for bugs and whether the results were actually the best
achievable. The most valuable thing to come out of it was a test I had not
run, that could have invalidated the previous day's headline claim.

**Two statistical defects in the comparison design itself:**

1. **The simulator used one shared RNG stream.** A given case saw different
   random draws under different policies, purely because the policy made a
   different number of calls before reaching it. In an experiment whose sole
   purpose is *ranking policies against each other*, that is pure noise with
   no informational content. Replaced with per-case streams seeded from
   (seed, case_id) — a proper common-random-numbers design, so any measured
   difference between policies on a case is caused by decisions rather than
   RNG bookkeeping.
2. **The baseline comparison used an unpaired bootstrap on paired data.**
   Both arms are measured on the *same* cases in the same order; resampling
   them independently discards the correlation between arms and mis-sizes
   every interval. Added `_paired_bootstrap_ci` with a test that fails if
   the paired version isn't actually tighter than the unpaired one on
   correlated arms. `run_batch.py` deliberately keeps the unpaired version —
   correct there, because its treatment and holdout arms are disjoint splits
   of *different* cases.

**The test I should have run a day earlier.** Yesterday's claim was "equal
recovery to mass-contact with 61% fewer contacts". That is only evidence
about *targeting* if a policy contacting the same number of cases AT RANDOM
does worse. If random targeting at matched volume did just as well, the
result would have been about diminishing returns to contact volume and
would have said nothing whatsoever about the uplift model — and I would have
been implicitly claiming credit for the model regardless. Built
`RandomTargetingPolicy` as that control. It happened to land at exactly the
same contact count as the greedy EV policy, 2,021 apiece:

- random_targeting: 119,671 incremental/1000 (CI 75,027–165,618), 118.4 ₹/contact
- ev_policy_greedy: 340,000 incremental/1000 (CI 271,213–407,782), 336.5 ₹/contact

**2.8x, non-overlapping CIs, identical contact volume.** The claim survived,
but it was not safe to assume it would — and it is now falsifiable on every
run rather than asserted.

**One genuinely unflattering finding, kept prominent rather than buried.**
The EV policy contacts a *higher* share of true do-not-disturbs (22.1%) than
either random targeting (20.4%) or mass-contact (20.2%). Since avoiding
do-not-disturbs is one of the project's headline novelty claims (N2), this
is the opposite of what it should show. Root-caused with data rather than
explained away: in this simulator amount at risk and true persuadability
correlate **-0.45** (larger amounts imply lower liquidity implies lower
persuadability), so the high-amount half of the population is **28.2%
do-not-disturbs vs the low-amount half's 6.0%**. The EV criterion is
`τ̂ × amount`, so it is structurally drawn toward exactly the cases most
likely to be do-not-disturbs, and where τ̂ is wrong (correlation ~0.35–0.42,
not 1.0) the amount term dominates.

That is a real tension in the objective function, not a coding error: the
policy optimises expected rupees, and in this population expected rupees and
do-not-disturb-avoidance genuinely conflict. The principled fix is the
`λ_churn × P(churn) × LTV` term the spec's full formula includes and this
implementation omits for lack of a defensible LTV estimate. Logged as the
top candidate for the next round rather than patched over with a fudge
factor.

Headline moved ₹376,484 → ₹284,957 purely because the CRN change altered the
random draws; CI still excludes zero. Baseline CIs tightened as expected
from the paired bootstrap. Everything re-verified deterministic.

Also worth recording as a near miss: while investigating the learner choice
I wrote a code comment claiming the feature-scaling fix had resolved the
causal forest's impossible CATE values — *before* verifying it. It had not
(29% → 60% in valid range, still broken). Deleted the claim rather than
leave a false statement in the codebase. The lesson is the same one this
whole day keeps teaching: write the claim after the measurement, not before.

102/102 tests passing (2 new: random-targeting determinism/rate, and a
paired-vs-unpaired bootstrap width test).

## 2026-08-24 (cont. 4) — Auditing the code I had just written, and finding the real formula bug

Asked, fairly, what about bugs in the work I had *just* done — I had audited
the experimental methodology but the code implementing those fixes was hours
old and barely scrutinised. Three things came out of it.

**A false alarm I raised on myself, and correctly retracted.** Wrote a check
for whether the new per-case RNG had collapsed (distinct cases sharing a
stream). It reported "distinct cases have distinct streams: False", which
looked alarming. Rather than immediately "fixing" it, checked the raw
per-case draws directly: they were plainly distinct (0.676… vs 0.532… vs
0.392…). **My test was the artifact, not the code** — it ran 200 nudges at
one case, by which point annoyance saturation drives pay probability to zero
for every case, so both sequences trivially became all-False. Worth
recording: the instinct to "fix" on a red signal without confirming the
signal is itself sound would have made the code worse.

**A latent fragility, checked and found harmless.** The categorical outcome
sampler in `step()` walks a cumulative-probability ladder; if the four
outcome probabilities ever summed above 1.0, later categories (promise-to-pay)
would be truncated and `no_reply` would become impossible. `opt_out_prob`
grows linearly in overcontact and is unbounded in principle. Swept the
reachable parameter space: max total mass is **0.6875**, safe — but only
because the loop's hard step cap keeps overcontact small. Documented rather
than "fixed", since there is no actual defect to fix.

**A genuine, consequential bug in the EV objective itself.** NUDGE was valued
at `τ̂ × amount`, where τ̂ is an **incremental** effect (CATE). RETRY was
valued at `p_retry × amount`, where `p_retry` is an **absolute** probability.
Both fed the same `max()`. That is apples-to-oranges, and the spec's formula
is explicitly `Δp_pay(action) × ₹amount` — a delta for *every* action. The
bug overvalued RETRY by `0.05 × amount` on every case (~40% overstatement of
its relative worth at the mean case size). A hard-decline retry — 1% success
against a 5% organic rate, therefore worth precisely nothing — was being
valued at `0.01 × amount`. Fixed with
`_retry_incremental_prob() = max(p_retry − base, 0)`.

**The best part: this fix substantially resolved the "unflattering finding" I
had written up hours earlier.** I had reported, prominently, that the EV
policy contacted *more* true do-not-disturbs (22.1%) than random targeting
(20.4%) — and had root-caused it to a structural tension between `τ̂ × amount`
and do-not-disturb avoidance. After the formula fix that rate fell to
**20.19%**, level with mass-contact and better than random. So the finding
was, in significant part, a *symptom of the bug* rather than the inherent
property I had confidently attributed it to. The structural pressure is real
(amount and persuadability correlate -0.45 here) but far smaller than it
looked. Corrected the report rather than leaving the more dramatic earlier
narrative standing.

Also verified, because it looked too neat to trust: random_targeting and
ev_policy_greedy had landed on *exactly* 2,021 contacts each. Checked whether
that was an aliasing bug by recomputing both selections independently —
Jaccard 0.435, selections genuinely different, totals coincidentally equal.
Real coincidence, not a defect.

Net effect on results: headline ₹284,957 → ₹258,796 (CI ₹101,137–₹426,996,
still excludes zero). Baseline comparison improved: EV policy now edges
blind mass-contact (340,988 vs 330,108 incremental/1000) using 48% fewer
contacts, and beats matched-volume random targeting 2.85x with
non-overlapping CIs. Greedy and lookahead converged to identical recovery
once the formula was right — so the lookahead reformulation, which an
earlier entry credited as a marginal win, is now doing essentially nothing.
Said so in the report rather than letting the earlier credit stand.

104/104 tests passing (2 new regression tests pinning the incremental-vs-
absolute distinction, plus two stale test comments corrected because they
described the old, buggy arithmetic).

## 2026-08-24 (cont. 5) — B3: all 11 stopping rules, and two defects the design surfaced

Implemented the approved B3 design. Two defects were found while designing
it, before any code was written, which is the useful part.

**Defect 1 — `BUDGET_EXHAUSTED` was mis-attributed as `NEGATIVE_EV`.** The
loop mapped *every* policy `STOP` to `NEGATIVE_EV`, including the one
returned on reaching `max_attempts`. So the last full run's 1,335
`negative_ev` stops were mostly budget exhaustion wearing the wrong label,
and `budget_exhausted` read 0 — not because it never happened, but because
it was never recorded. Fixed by having `ActionDecision` carry its own
`stop_reason` so the loop attributes rather than guesses.

**Defect 2 — promise-to-pay was terminal.** Spec rule 6 is "pause until the
promised date + grace, then re-evaluate". Treating it as an ending
abandoned 115 cases at exactly the moment the customer signalled intent to
pay.

**A design collision worth recording.** My first implementation had
do-not-disturb and hard-decline terminate the case the moment they were
detected. That is intuitive and it is wrong — it re-creates the earlier bug
where abandoning a case forfeits the free organic resolution it would
otherwise get (the one that had the EV policy recovering 8.1% of overdue
receivables against do-nothing's 13.9%). The test suite caught it
immediately. Restructured so these are *classifications of why the agent
never acted*, applied when the budget is spent, rather than licences to
abandon early: the agent still waits out the window costlessly, contacts
nobody, and records an accurate terminal reason.

**The B3 test caught a second gap in my own design.** With that restructure,
`NEGATIVE_EV` became genuinely unreachable — everything routed to
do-not-disturb, hard-decline, or budget-exhausted. The
"every rule must fire" test failed and named the missing rule. Fixed by
distinguishing "never worth acting at all" (rule 4) from "acted until the
budget ran out" (rule 3), which is sound because expected value is
monotonically non-increasing in attempts, so not-worthwhile-at-attempt-0
implies never-worthwhile. That test paid for itself within an hour of being
written.

**Results.** A real 2,000-case batch now fires **7 of 11** reasons naturally
(do_not_disturb 92, resolved 382, budget_exhausted 507, dispute 34, opt_out
19, human_escalation 2, hard_decline 1). The remaining four need conditions
a normal batch doesn't produce — an engaged kill switch, a kernel that
denies literally everything, a case where nothing is ever worthwhile, and
promise-to-pay which is now a *pause* and resolves later rather than
terminating. All 11 are proven reachable by
`tests/test_all_stopping_rules.py::test_every_stopping_rule_is_reachable`,
which is the honest way to claim B3: 7 occur naturally, 11 are demonstrably
reachable, and the distinction is stated rather than blurred.

Headline moved ₹258,796 → **₹288,729** (CI ₹133,924–₹432,362) — the promise
resumption recovers cases that were previously abandoned. Baselines
unchanged in shape; EV policy still ~2.85x matched-volume random targeting.
655 cases land in the honest exception list.

121/121 tests passing (17 new: 11 per-rule, the all-rules-reachable test,
and 5 for the resumption queue). All experiments re-verified deterministic.

## 2026-08-24 (cont. 6) — Red-team suite: 100% block rate, and proving that number means something

Built the adversarial harness (spec section 9.5). The interesting part was
deciding what an honest version of this even is.

**What the spec asks for vs. what is actually possible.** Section 9.5 says
"an adversarial LLM attempts to induce non-compliant sends (jailbreak the
drafter...)". But the compliance kernel is deliberately *not* an LLM — it is
a deterministic predicate over structured state. There is no prompt to
jailbreak and no persuasion to resist. Building a fake "adversarial LLM
attacks the kernel" demo would be theatre, and a panel would see through it
immediately. Said so explicitly in `redteam/attacks.py` rather than quietly
producing something that looks impressive and means nothing.

The real attack surface is: crafted state that slips past a rule; a contact
executed without a valid certificate; and a policy that has been compromised
or badly tuned. So the suite has three layers:

1. **21 named attacks**, each with an oracle stated *from the regulation*
   rather than from the rule implementation — checking the kernel against a
   restatement of its own code would prove nothing.
2. **A hostile policy end to end** — replaced the decision policy with one
   that always proposes maximum-pressure voice contact, ran 300 real cases
   through the full loop, and asserted no contact was ever *executed*
   without an ALLOW certificate behind it. 323 contacts attempted, 0
   uncertified. This tests deny-by-default as a system property rather than
   the kernel in isolation.
3. **5,000 randomised fuzzed states** against independent oracles. Handwritten
   cases only find the leaks you already thought of.

**Result: 100% block rate, 0 violations, across all three layers.**

**And then I checked whether that number can fail at all.** A suite that
cannot fail is worthless, so I mutation-tested it the same way as the
no-LLM-import gate: deliberately sabotaged the contact-hours rule to always
pass, re-ran, and got **31 violations** — 3 named attacks leaking and 28
fuzz leaks — then restored the rule and confirmed a clean 0 and an empty git
diff. So the 100% is a real gate.

Worth noting what that mutation test revealed about the layers: the three
named contact-hours attacks caught the sabotage, but the fuzz layer caught
**28** distinct leaking states. The randomised layer is doing substantially
more work than the handwritten one, which is the argument for having it.

One guard added deliberately: `test_no_legitimate_action_is_wrongly_blocked`.
A kernel that simply denied everything would score a perfect 100% on the
attack suite and be completely useless. That test asserts at least one
legitimate action (a silent retry outside contact hours, which is not
customer contact) still gets through, so the block rate can't be gamed by
over-blocking.

125/125 tests passing. `make redteam` wired.

## 2026-08-24 (cont. 7) — Sensitivity sweep: the ranking holds, and one flip worth reporting

Built the sweep spec section 7.3 asks for: "sweep the response-function
parameters across a defensible range and show the policy ranking is stable.
Stability of ranking under assumption sweeps is the honest claim, not a
point estimate."

First a refactor: every invented constant in `sim/environment.py` moved into
an injectable `ResponseParams` dataclass, defaults reproducing the previous
module globals exactly (verified — all 125 tests passed unchanged
immediately after). You cannot sweep a constant you cannot inject.

Chose five parameters, each with a range a reasonable person could have
picked instead of the default rather than an arbitrary +/- around it. The
uplift model is **retrained at every setting** — reusing a model fitted
against different physics would measure staleness, not sensitivity, and
getting that wrong would have quietly invalidated the whole exercise.

Two claims tested at all 25 settings:

- **C1 — the EV policy beats matched-volume random targeting: 25/25.**
  Margin ranges 1.65x to 4.24x. This is the claim that matters most, since
  it is the one asserting the model does real work rather than the result
  being an artifact of contact volume. It survives the two settings
  specifically constructed to break it: zero annoyance decay (brute-force
  persistence never punished) and zero amount-liquidity coupling (the EV
  policy's amount weighting carries no hidden information about
  persuadability). Both pinned as tests.
- **C2 — the EV policy is more contact-efficient than blind mass-contact:
  24/25.**

**The single flip, stated rather than averaged away.** At
`base_organic_resolution = 0.12`, mass-contact wins on contact efficiency
(blast ₹236,770 incremental vs the EV policy's ₹82,576). Mechanism: when
12% of cases fix themselves, there is little incremental value left to
target, learned tau shrinks toward zero, the selective policy correctly
declines to act, and brute force still scrapes up what remains. The honest
statement is "C2 holds except when organic recovery is very high", not "C2
holds 96% of the time" — the flip is systematic and explainable, not noise,
and averaging it into a percentage would hide exactly the condition under
which the claim fails.

**The best result in the sweep was not one I set out to test.** As
`amount_liquidity_coupling` strengthens — high-value cases becoming
increasingly likely to be do-not-disturbs — the EV policy's advantage over
random targeting *widens* from 1.75x to 4.24x, while blind mass-contact
collapses from ₹1,015,545 to ₹197,499. So the harder the do-not-disturb
problem gets, the more targeting is worth. That is novelty claim N2 showing
up as a measured gradient rather than an assertion, and it is a much better
argument for the thesis than any single point estimate.

Worth noting the contrast with an earlier entry: the do-not-disturb tension
was first written up as an embarrassing finding, then partly dissolved by a
bug fix, and has now turned into the sweep's strongest supporting evidence.
Same phenomenon, three different readings, each honest at the time.

128/128 tests passing. `make sensitivity` wired.

## 2026-08-24 (cont. 8) — Caught myself overclaiming, then closed the documentation gaps

Asked to check for bugs or dropped results before starting anything new.
The health check itself was clean — 128 tests, `make eval` reproducing
₹288,729, red-team at 100%/0 violations, demo working. But cross-reading
two experiments against each other turned up something worse than a bug: a
claim I had been making that the data does not support.

**The overclaim.** The sensitivity sweep at default parameters showed
`blast=603,976` ahead of `ev=507,119`, while `make baselines` showed the EV
policy ahead (340,988 vs 330,108). Those should agree, so I chased it.
Turned out not to be a bug at all: the ranking simply **flips with the eval
sample**. At n_eval=1500 mass-contact leads 603,976 to 536,990; at
n_eval=2000 the EV policy leads 681,976 to 660,216. Same parameters, same
code, opposite ordering.

The confidence intervals had already been saying this — 340,988
(274,088–408,856) against 330,108 (249,085–421,457) overlap heavily — and I
had written "the agent edges blind mass-contact" anyway, reading a point
estimate as a result. Corrected in README and REPORT.md, with the flip
evidence recorded so the correction is checkable rather than just asserted.

The robust claims survive and are unchanged: 2.85x against matched-volume
random targeting with non-overlapping CIs, 48% fewer contacts, 2x
per-contact efficiency, and C1 holding at 25/25 sweep settings. The
not-robust claim was only ever the least interesting one — a bigger headline
total. Worth noting the pattern though: the overclaim crept in precisely
where I *wanted* a clean "we beat them" line.

**Then the documentation gaps.** Audited what spec section 12 requires
against what exists: `ARCHITECTURE.md` and `RESULTS.md` were both missing
outright, the section 8.5 LLM/no-LLM table was absent from the README
despite the spec saying to include it verbatim because it *is* the answer to
the "AI judgment" criterion, and the novelty claims were nowhere in the
README despite being a Definition-of-Done item.

Wrote all four. Two things I did deliberately rather than by default:

- **`RESULTS.md` numbers were extracted programmatically** from the results
  JSON rather than retyped, because hand-copying figures across documents is
  exactly how a repo ends up with a number nobody can reproduce.
- **The novelty table carries honest build status.** N1, N3, N5 are built
  and measured. N2 is modelled and measured but the agent's do-not-disturb
  rate (20.1%) is merely *level* with untargeted policies, so it is marked
  as the top open problem rather than a win. N4 is partial — greedy EV plus
  a lookahead that currently adds nothing measurable, not a constrained-MDP
  solver. **N6 is not built at all** and is marked ❌. Two of six partial and
  one absent, said in the README rather than left for a reader to find.

128/128 tests still passing.

## 2026-08-24 (cont. 9) — Dashboard: B4's "browsable", and a deliberate divergence from the suggested template

Asked to use MengTo/threeui as inspiration or template for the dashboard.
Read the repo before deciding how: it is a React + Vite + Three.js/WebGL
component library, npm-installable, whose components are decorative 3D
pieces (`AtTheHorizon` and similar).

**What I took, and what I deliberately did not.** The genuinely valuable
thing in ThreeUI for this project is its *application architecture*: sidebar
shell, searchable browse grid, and detail pages with source tabs. That last
pattern maps almost exactly onto an audit trail — browse cases, open one,
inspect it through tabs. Adopted wholesale.

Did not adopt the React/Vite/npm build or the WebGL layer, for two reasons
worth stating rather than silently skipping:

1. This repo is pure Python and has a carefully maintained property — clone
   it, run one command, everything works, no external services. Requiring
   `npm install` to view an audit trail would break that, and would put a
   build step between a judge and the thing they are trying to evaluate.
2. Decorative 3D on a *regulated-payments compliance tool* would actively
   undercut the property this view exists to demonstrate. "Would you trust
   it" is an explicit judging criterion; WebGL shaders behind a table of
   TCCCPR rule evaluations would read as unserious.

So: ThreeUI's UX architecture and visual language, implemented as a single
self-contained HTML file generated by Python from the ledger. Opens by
double-click, works offline, 636 KB.

**Verified rather than assumed.** Rendered it in a real headless browser via
Playwright and exercised every interaction — nav between the three views,
search filtering (20 → 9 cards on "overdue"), opening the case drawer, all
three detail tabs, closing it, and the theme toggle. **Zero JS errors.** A
hand-written HTML generator is exactly the kind of thing that silently
produces a blank page, so this was worth checking properly rather than
eyeballing the file size.

Pointed it at the real batch ledger rather than the demo one: the demo runs
the stub policy, so it shows 20 identical `budget_exhausted` cases and a
single denial. The batch ledger shows 7 distinct stop reasons and **349 real
denials across 5,703 certificates** — and the compliance view makes visible
at a glance that every one of those denials comes from
`EMANDATE2026.PRE_DEBIT_NOTICE`, which is precisely the finding that took
instrumentation to uncover during the earlier bug hunt. The dashboard now
surfaces it immediately.

Tests deliberately do not use Playwright — that would put a 95 MB browser
download in CI. They assert the generator's output instead: that the page is
genuinely self-contained (no `http://`, no `<script src=`, no `<link>`),
that summary counts separate denials from passes, and that every timeline
step carries its hash-chain position so the browser can show provenance
rather than just content. Playwright stays as a manual verification tool.

132/132 tests passing.

## 2026-08-24 (cont. 10) — LLM listener: the labelled set was the problem, and opt-out should never have been the model's job

Wired the LLM into reply-intent classification, which spec section 8.5
permits *on condition* it is "validated against a labelled set, report
accuracy". Getting that validation honest took three passes.

**Pass 1 — the self-labelling idea, and why it failed.** The neat design is
to have the simulator pick a ground-truth intent, have a persona LLM write
text expressing it, then have the listener classify it back. Labels come
free by construction. Generated 91 replies across 6 intents x 3 languages
(batched, ~18 calls, 198s, cached to disk so the eval is reproducible
without Ollama).

Measured **42.9%**. Then read the disagreements instead of reporting the
number, and the corpus was the problem, not the classifier. Asked to write
as a customer who had already paid, qwen2.5:3b produced "Waste of time with
all these chase msgs" (not a payment claim at all) and "Aur message mat
bhijo mujhse" — which literally means *stop messaging me*, i.e. the opt-out
intent, filed under `paid`. Hindi output was frequently incoherent; Hindi
scored 27.3% against English's 62.5%.

A labelled set whose labels are wrong cannot validate anything, and
publishing 42.9% would have attributed corpus noise to the listener.

Worth recording that few-shot anchoring materially improved generation
before I gave up on it as ground truth — without style examples the model
wrote "Sab kochi? Bhai aapke yaar pay day ho jayega"; with them, "Abhi paise
nahi hoga, 15th January ka salary aayega tab karunga". Also tested
qwen2.5:7b for generation on the theory that a bigger model is worth it when
the work is one-time and cached — it was not clearly better and 3x slower,
so 3b stayed.

**Pass 2 — a hand-authored gold set.** 42 examples, 7 per intent, balanced
across English/Hindi/Hinglish, each written so only one reading is
reasonable. Result: **88.1%**, versus 42.9% on the generated corpus. Most of
the original "error" was indeed label noise.

**Pass 3 — the finding that mattered.** On clean labels, opt-out recall was
**0.57**. The model missed 3 of 7, and every miss was Hindi or Hinglish —
"कृपया मुझसे दोबारा संपर्क न करें" ("please do not contact me again") came
back as `wrong_person`.

Every other intent being wrong costs money. Opt-out being wrong costs
compliance: continuing to contact someone who asked you to stop is a TCCCPR
violation, and it silently skips the 90-day cooling obligation. That is
exactly the class of decision this project already argues should not rest on
a language model — the compliance-kernel argument, one level down. So
opt-out got a deterministic detector that runs before the LLM and overrides
it, with patterns grouped by language so a compliance reviewer can actually
read them, and a deliberately asymmetric bias (a false positive costs
revenue; a false negative is a breach).

That took the combined system to **92.9%**, opt-out recall to 1.00 — and
immediately produced a false positive of my own making: "maine to
subscription band kar diya tha, phir charge kyun hua" ("I had cancelled it,
so why was I charged") is a *dispute*, caught by my `band kar` pattern.
"band karo" is the imperative "stop it"; "band kar diya" is past tense "I
cancelled it". Tightened the pattern to the imperative form only.

**Final: 95.2% overall** (100% English, 92% Hinglish, 92% Hindi), opt-out
1.00 precision and 1.00 recall, promise-to-pay 0.88/1.00 — the metric spec
11.2 names explicitly. Both the gold and generated results are published; the
generated one is labelled as unreliable ground truth rather than quietly
dropped, because the gap between 42.9% and 95.2% is itself the evidence for
why hand-authored labels were necessary.

Tests mock the LLM, so none of this needs Ollama in CI. They pin the
properties that matter: unparseable model output becomes NO_REPLY rather
than an action, an unreachable model degrades to NO_REPLY rather than a
guess, silent actions never produce a reply, and a deliberately wrong model
answer is still overridden to OPT_OUT.

145/145 tests passing.

## 2026-08-24 (cont. 11) — The churn term: fixing the do-not-disturb problem I had been flagging for days

The top open problem, flagged repeatedly and never fixed: the agent's
do-not-disturb contact rate sat at 20.1%, level with random targeting's
20.4%. Novelty claim N2 says this project models the downside of contact;
the measurement said it did so no better than not trying.

**The excuse I had been giving myself was wrong.** The spec's EV formula has
a `λ_churn × P(churn) × LTV` term. I omitted it and documented the reason as
"no defensible LTV estimate". That reasoning conflated two separable things.
`P(churn | contact)` is not an assumption at all — it is **learnable from
exactly the same randomised data the uplift model already trains on**. An
opt-out is an observed outcome; the contact assignment is randomised; the
causal effect of contact on churn is identified by precisely the machinery
Tier 1 already validated. Only the LTV multiplier is an assumption, and one
named parameter is a completely different thing from a silently absent term.

Checked the signal was real before building anything:

- opt-out rate when contacted: 1.33%; when not contacted: **0.0%** — contact
  is the entire cause, so the effect is cleanly identified
- true do-not-disturbs opt out **1.93x** more often than others when
  contacted

That 1.93x is the whole argument. Churn risk is an **independent** signal
from `τ̂_pay`. Avoiding do-not-disturbs previously required one model
(correlation ~0.35-0.42 with truth) to be right; now it requires two to both
be wrong. Defence in depth, using a model that costs nothing extra to fit.

Swept `λ_churn` rather than picking a value by feel:

| λ_churn | incremental | contacts | dnd% | ₹/contact |
|---|---|---|---|---|
| 0 | 681,976 | 2257 | 20.1% | 302 |
| 2.0 | 603,882 | 1705 | 16.5% | 354 |
| 4.0 | 602,036 | 1339 | 13.6% | 450 |
| 8.0 | 517,442 | 899 | 10.8% | 576 |

Set the default to 4.0 because it **strictly dominates 2.0** — same total
recovery (602,036 vs 603,882, within noise) using 21% fewer contacts and
reaching meaningfully fewer do-not-disturbs. That is not a judgement call,
it is a dominated option being discarded.

**Kept `ev_policy_no_churn` in the baseline comparison on purpose**, so the
term's effect is visible rather than asserted: 12% less incremental
recovery, 41% fewer contacts, 49% better rupees-per-contact, a third fewer
do-not-disturbs reached.

**One thing I was careful not to claim.** The headline batch moved
₹288,729 → ₹310,910, which looks like the churn term also *increased*
recovery. It did not — the CI is ₹150,240-₹471,072 and the two figures sit
well inside each other's intervals. That is exactly the overclaim I made
days ago with mass-contact and had to withdraw. The defensible statement is
"same recovery, 40% fewer contacts, materially fewer do-not-disturbs", and
that is what the docs say.

A test premise of mine was also wrong and worth recording: I first wrote the
suppression test against a subscription case, where RETRY (incremental 0.30
x amount) already beats a modest nudge regardless of churn — so the
"without churn" arm was never NUDGE and the test could not demonstrate
anything. Switched to a checkout-abandonment case, which has no retry
available. The code was right; the test was measuring the wrong thing.

151/151 tests passing. All experiments re-verified deterministic.
