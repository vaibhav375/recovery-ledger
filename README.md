# Recovery Ledger

**Status: Tier 1 validation passed. B1 headline: ₹288,729 incremental recovery
per 1,000 cases (95% CI ₹133,924–₹432,362).** The decisive test: against a
control contacting a comparable number of cases *at random*, the agent
recovers **2.85x more incremental revenue with non-overlapping confidence
intervals** — so the targeting model, not merely contact volume, is doing the
work. It also edges blind mass-contact on recovery using 48% fewer contacts,
at 2x better cost per incremental rupee. Policy dominance under stated
assumptions, in simulation — not a real-world claim. **Four revisions to
these numbers** (three from real bugs, one from a methodology fix) are
documented in
[`experiments/tier2_simulation/REPORT.md`](experiments/tier2_simulation/REPORT.md)
rather than quietly replaced.

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
      **₹288,729 incremental per 1,000 cases (95% CI ₹133,924–₹432,362)**;
      holdout recovers 15.47% unaided, which is exactly why this reports
      incremental rather than gross.
- [x] **Baseline comparison + falsification test.** `make baselines`: the
      spec's 5 required policies, both EV variants, and a matched-volume
      random-targeting control, under common random numbers with a paired
      bootstrap. Headline: **2.85x incremental recovery vs random targeting
      at comparable contact volume** (non-overlapping CIs), and a tie with
      blind mass-contact at 48% fewer contacts.
- [x] **Do-not-disturb rate 20.2%** — level with untargeted policies, not
      better, and far from the ≈0 target. Honestly reported as the top open
      problem; the principled fix is the `λ_churn × P(churn) × LTV` term the
      spec includes and this omits for lack of a defensible LTV estimate.
- [x] **B3 — all 11 stopping rules, provably reachable.** `tests/test_all_stopping_rules.py`
      runs a crafted scenario suite and asserts **every one of the 11 reasons
      fires at least once** — B3 as an executable property, not a README claim.
      A real 2,000-case batch now fires **7 of 11 naturally** (the other four
      need operator action or an all-deny kernel). Promise-to-pay is a genuine
      **pause with scheduled resumption**, enforced as a compliance-kernel
      silence window; cases still paused at the horizon become the honest
      exception list.
- [x] **Red-team suite — 100% block rate, 0 violations.** `make redteam`:
      21 named attacks (timing evasion, consent forgery, opt-out violation,
      budget evasion, DLT/number-series evasion, mandate debit without
      notice, promise-window breach, tone escalation, and all of them at
      once), a **hostile policy driven end to end** (323 contacts attempted,
      0 executed without an ALLOW certificate), and **5,000 randomised
      fuzzed states** checked against oracles written from the regulations
      rather than from the rule code. Mutation-tested: sabotaging one rule
      produces 31 violations, so the 100% is a real gate, not a vacuous one.
- [x] **Sensitivity sweep — ranking stability (spec 7.3).** `make sensitivity`:
      5 simulator parameters x 5 values, uplift model retrained at every
      setting. **C1 (targeting beats matched-volume random) holds at 25/25
      settings**, margin 1.65x–4.24x, including the settings built to be
      hostile to it. C2 (contact efficiency vs mass-contact) holds at 24/25 —
      the single flip is reported, not averaged away. Best finding: the
      *harder* the do-not-disturb problem, the more targeting is worth.
- [ ] Real listener + LLM personas (LLM backend decided and built — see
      above — not yet wired into the loop's Listener)
- [ ] Negotiation + Section 43B(h) clock
- [ ] Fleet-level degradation detection

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
make sensitivity       # 5-parameter ranking-stability sweep — verified working
make redteam          # 21 named attacks + hostile policy + 5,000-state fuzz —
                       # verified working, 100% block rate, mutation-tested
```

This section only claims a command works once it has actually been run
successfully.

## What is NOT claimed

- No real-world causal effect size. The ₹288,729-per-1,000-cases figure above
  is a simulation result — policy dominance under stated assumptions, in
  simulation. Everything in `experiments/tier2_simulation/` runs against a
  simulator calibrated to published marginal benchmarks — that calibrates
  outcome rates, not causal response to intervention. See §7 of the spec, and
  the claim-scope section at the top of `experiments/tier2_simulation/REPORT.md`,
  for why that distinction matters.
- No category novelty — dunning agents, uplift modelling, and LLM dunning
  messaging all exist already. See §4 of the spec for what is and isn't claimed
  as novel here.
