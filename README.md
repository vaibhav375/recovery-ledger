# Recovery Ledger

**Status: early build. Tier 1 validation passed; agent loop skeleton and compliance
kernel run end to end. The core money-measurement pipeline (simulator response
model, EV policy, real listener) has not started yet — see Status below.**

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
- [ ] Simulator ("the recovery gym") — thin skeleton only so far: deterministic
      case generation across all 4 loss types. Latent traits, a response
      model, marginal calibration, and the sensitivity sweep are not built yet.
- [x] Compliance kernel — deny-by-default engine, per-action certificates,
      hash-chained into the ledger, no-LLM-import test that fails the build
      (verified: mutation-tested, not just passing vacuously). 11 rules
      covering RBI recovery-agent norms, TRAI TCCCPR, the RBI e-mandate 2026
      framework, and DPDPA — see [`COMPLIANCE.md`](COMPLIANCE.md) for every
      rule, its source citation, and two ambiguities flagged rather than
      silently resolved. `make demo` shows the kernel genuinely denying a
      real case (a mandate retry attempted before its 24-hour pre-debit
      notice window elapsed), not just passing everything.
- [x] Agent loop skeleton — detect → diagnose → decide → gate → act → listen →
      stop runs end to end (`make demo`) for all 4 loss types, every step
      ledgered, chain verified. Policy and listener are still stubs (fixed
      action sequence; no real reply channel) — the real uplift-driven EV
      policy lands after Tier 2 simulator work.
- [ ] Listener + LLM personas
- [ ] Negotiation + Section 43B(h) clock
- [ ] Fleet-level degradation detection
- [ ] Evaluation: 5 baselines, sensitivity sweep, red-team suite
- [ ] Dashboard / audit-trail browser
- [ ] Video + submission

## Running this repo

```
make setup           # create .venv, install deps — verified working
make test             # run the test suite — verified working
make tier1-hillstrom  # Tier 1 validation on Hillstrom — verified working
make tier1-criteo     # Tier 1 validation on a 2% Criteo subsample — verified
                       # working; downloads ~340MB from HuggingFace on first run
make demo             # runs 20 synthetic cases through the full agent loop —
                       # verified working, deterministic (run twice, diffed)
make eval             # not yet implemented
make redteam          # not yet implemented
```

This section only claims a command works once it has actually been run
successfully. `make demo`/`eval`/`redteam` currently print a clear "not yet
implemented" message and exit non-zero rather than silently doing nothing.

## What is NOT claimed

- No real-world causal effect size. Everything in `experiments/tier2_simulation/`
  is a simulation calibrated to published marginal benchmarks — that calibrates
  outcome rates, not causal response to intervention. See §7 of the spec for why
  that distinction matters.
- No category novelty — dunning agents, uplift modelling, and LLM dunning
  messaging all exist already. See §4 of the spec for what is and isn't claimed
  as novel here.
