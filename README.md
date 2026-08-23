# Recovery Ledger

**Status: Tier 1 validation passed. B1 headline: ₹284,957 incremental recovery
per 1,000 cases (95% CI ₹128,725–₹451,483).** The decisive test: against a
control that contacts the *same 2,021 cases at random*, the agent recovers
**2.8x more incremental revenue with non-overlapping confidence intervals** —
so the targeting model, not merely contact volume, is doing the work. It also
matches blind mass-contact on recovery using 53% fewer contacts. Policy
dominance under stated assumptions, in simulation — not a real-world claim.
Three revisions to these numbers (two from real bugs, one from a methodology
fix) are documented in
[`experiments/tier2_simulation/REPORT.md`](experiments/tier2_simulation/REPORT.md)
rather than quietly replaced — including one result that is *not* flattering.

An autonomous revenue-recovery agent for Indian payments. It decides *whether, when,
how, and in what language* to intervene on at-risk revenue — failed payments,
abandoned checkouts, failed subscription mandates, overdue B2B receivables — and
reports **incremental** rupees recovered against a randomised no-contact holdout,
with every outbound action gated by a deterministic, machine-checkable compliance
kernel that emits a signed certificate per action.

Full design rationale, novelty claims, and the two-tier validation methodology are
in [`RAZORPAY_BUILDATHON_TRACK3_SPEC.md`](RAZORPAY_BUILDATHON_TRACK3_SPEC.md).
Build history and honest failures are in [`ENGINEERING_LOG.md`](ENGINEERING_LOG.md).

## Three framings that shape every decision in this repo

1. **The agent is the product. The measurement is the proof.** This must read as
   a running system, not a notebook.
2. **Report incremental, never gross.** Gross recovery numbers are misleading —
   a large share of failed payments recover on their own.
3. **The compliance kernel is deliberately not an LLM.** Headline design decision:
   an agent that is 99% compliant is 100% undeployable in a regulated business.

## LLM backend

Local, open-source, no subscription (explicit decision, not a default —
see `ENGINEERING_LOG.md`, 2026-08-23). Persona simulation, reply-intent
parsing, message drafting, and negotiation dialogue all go through the one
interface in [`src/recovery_ledger/llm/client.py`](src/recovery_ledger/llm/client.py):
a real `OllamaClient` (default model `qwen2.5:3b`, chosen after actually
timing it against `qwen2.5:7b` and `qwen3:4b` on real hardware — the 3B
model won on both speed and correctly switching into Hinglish on
instruction) and a `MockLLMClient` fallback. `kernel/` is mechanically
forbidden from importing this module at all.

To use the real backend: `brew install ollama && ollama pull qwen2.5:3b`.
Without it, anything that calls through this interface falls back to the
mock automatically — the base `make demo` never requires Ollama to be
running.

## Status

- [x] Tier 1 validation (uplift learners + doubly-robust OPE reproduce known
      effects on real randomised data — Criteo / Hillstrom). Passed with one
      open finding (DR estimator bias under treatment-ratio imbalance, not
      fully closed). Full results and reproduction commands:
      [`experiments/tier1_criteo/REPORT.md`](experiments/tier1_criteo/REPORT.md).
- [x] Event schemas (4 loss types, typed/validated) — real, not stub
- [x] Simulator ("the recovery gym") — hidden latent traits (liquidity,
      annoyance threshold, dispute propensity), a response model with
      negative responses (opt-out/dispute risk that rises with
      over-contacting), retry economics loosely anchored to spec section
      3.2's published benchmarks. Marginal calibration is loose, not
      rigorous, and there's no sensitivity sweep yet — both flagged
      honestly in `experiments/tier2_simulation/REPORT.md`.
- [x] Compliance kernel — deny-by-default engine, per-action certificates,
      hash-chained into the ledger, no-LLM-import test that fails the build
      (verified: mutation-tested, not just passing vacuously). 11 rules
      covering RBI recovery-agent norms, TRAI TCCCPR, the RBI e-mandate 2026
      framework, and DPDPA — see [`COMPLIANCE.md`](COMPLIANCE.md) for every
      rule, its source citation, and two ambiguities flagged rather than
      silently resolved. `make demo` shows the kernel genuinely denying a
      real case (a mandate retry attempted before its 24-hour pre-debit
      notice window elapsed), not just passing everything.
- [x] Agent loop — detect → diagnose → decide → gate → act → listen → stop.
      `make demo` (20 cases, stub fixed-sequence policy, for a fast,
      dependency-free look at the loop) is unchanged. `make eval` runs the
      real `LookaheadEVDecisionPolicy`, uplift-model-driven, over 5000+2000 cases.
- [x] **B1 — batch run, headline incremental ₹ + CI.** `make eval`:
      **₹284,957 incremental per 1,000 cases (95% CI ₹128,725–₹451,483)**;
      holdout recovers 15.47% unaided, which is exactly why this reports
      incremental rather than gross.
- [x] **Baseline comparison + falsification test.** `make baselines`: the
      spec's 5 required policies, both EV variants, and a matched-volume
      random-targeting control. Headline: **2.8x incremental recovery vs
      random targeting at the identical 2,021 contacts** (non-overlapping
      CIs), and a tie with blind mass-contact on recovery at 53% fewer
      contacts. Uses common random numbers and a paired bootstrap.
- [x] **One honest negative result**: the EV policy contacts *more* true
      do-not-disturbs (22.1%) than random targeting (20.4%). Root-caused,
      not excused — amount at risk and persuadability are correlated -0.45
      in this simulator, so `τ̂ × amount` is structurally pulled toward the
      cases most likely to be do-not-disturbs. Full analysis in the report.
- [ ] Real listener + LLM personas (LLM backend decided and built — see
      above — not yet wired into the loop's Listener)
- [ ] Negotiation + Section 43B(h) clock
- [ ] Fleet-level degradation detection
- [ ] Sensitivity sweep, red-team suite
- [ ] Dashboard / audit-trail browser
- [ ] Video + submission

## Running this repo

```
make setup           # create .venv, install deps — verified working
make test             # run the test suite — verified working
make tier1-hillstrom  # Tier 1 validation on Hillstrom — verified working
make tier1-criteo     # Tier 1 validation on a 2% Criteo subsample — verified
                       # working; downloads ~340MB from HuggingFace on first run
make demo             # runs 20 synthetic cases through the agent loop with the
                       # stub policy — verified working, deterministic
make eval             # trains the uplift model + runs the real 5000+2000-case
                       # batch experiment — verified working, deterministic
                       # (run twice, diffed byte-identical)
make baselines         # runs all 5 spec-required baselines + a matched-volume
                       # random-targeting control + both EV variants against the
                       # same eval batch — verified working, deterministic
make redteam          # not yet implemented
```

This section only claims a command works once it has actually been run
successfully. `make redteam` currently prints a clear "not yet implemented"
message and exits non-zero rather than silently doing nothing.

## What is NOT claimed

- No real-world causal effect size. The ₹284,957-per-1,000-cases figure above
  is a simulation result — policy dominance under stated assumptions, in
  simulation. Everything in `experiments/tier2_simulation/` runs against a
  simulator calibrated to published marginal benchmarks — that calibrates
  outcome rates, not causal response to intervention. See §7 of the spec, and
  the claim-scope section at the top of `experiments/tier2_simulation/REPORT.md`,
  for why that distinction matters.
- No category novelty — dunning agents, uplift modelling, and LLM dunning
  messaging all exist already. See §4 of the spec for what is and isn't claimed
  as novel here.
