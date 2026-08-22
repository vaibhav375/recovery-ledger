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
