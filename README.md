# Recovery Ledger

**Status: early build — Tier 1 validation in progress. Numbers below are placeholders until computed by code in this repo.**

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

## Status

- [x] Tier 1 validation (uplift learners + doubly-robust OPE reproduce known
      effects on real randomised data — Criteo / Hillstrom). Passed with one
      open finding (DR estimator bias under treatment-ratio imbalance, not
      fully closed). Full results and reproduction commands:
      [`experiments/tier1_criteo/REPORT.md`](experiments/tier1_criteo/REPORT.md).
- [ ] Event schemas + simulator ("the recovery gym")
- [ ] Compliance kernel (deterministic, no LLM, per-action certificates)
- [ ] Agent loop + policy (EV decisioning, budget constraints, 11 stopping rules)
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
make demo             # not yet implemented
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
