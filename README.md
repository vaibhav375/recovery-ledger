# Recovery Ledger

**Status: Tier 1 validation passed. B1 headline: ₹288,729 incremental recovery
per 1,000 cases (95% CI ₹133,924–₹432,362).** The decisive test: against a
control contacting a comparable number of cases *at random*, the agent
recovers **2.85x more incremental revenue with non-overlapping confidence
intervals** — so the targeting model, not merely contact volume, is doing the
work. Against blind mass-contact it is **statistically indistinguishable on
total recovery** (overlapping CIs — and the sign of the difference flips
with the sample, so "beats" would be an overclaim) while using **48% fewer
contacts** at 2x better cost per incremental rupee. The contact efficiency
is the robust claim; a higher headline total is not. Policy dominance under stated
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

| Document | What's in it |
|---|---|
| [`RESULTS.md`](RESULTS.md) | **Every measured number, with the command that reproduces it** |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Component contracts, data flow, and the reasoning behind each design decision |
| [`COMPLIANCE.md`](COMPLIANCE.md) | All 12 kernel rules, each cited to source, plus two ambiguities flagged rather than silently resolved |
| [`ENGINEERING_LOG.md`](ENGINEERING_LOG.md) | Dated build history — including the wrong turns, withdrawn numbers, and bugs found in my own work |
| [`RAZORPAY_BUILDATHON_TRACK3_SPEC.md`](RAZORPAY_BUILDATHON_TRACK3_SPEC.md) | The original spec this was built against |

## Where AI is used — and where it is deliberately not

This table is the answer to the "AI judgment" criterion ("the right tool in
the right place, **and where you chose not to use one**"). The bottom three
rows are the ones that matter.

| Use | LLM? | Why |
|---|---|---|
| Persona simulation / synthetic replies | ✅ | Language variety is exactly what LLMs are for |
| Inbound reply-intent classification | ✅ | Free text → structured intent |
| Message drafting (tone, language, Hinglish) | ✅ | Natural-language generation, template-constrained |
| Negotiation dialogue | ✅ | Bounded by a solver and the kernel |
| Root-cause narration | ✅ | Explanation, not decision |
| **Treatment-effect estimation** | ❌ | Needs calibrated probabilities and confidence intervals. An LLM cannot give you a Qini curve. Classical ML, validated on real RCT data first. |
| **Compliance decisions** | ❌ | **Must be deterministic and auditable.** Same input, same verdict, forever. "The model usually gets it right" is not a defence you can present to a regulator. |
| **Money-affecting final actions** | ❌ | Gated by the kernel and an explicit policy, never by generated text |

The constraint is enforced mechanically, not by discipline:
`tests/test_kernel_no_llm_imports.py` fails the build if anything under
`kernel/` imports an LLM client — and it has been mutation-tested to confirm
it actually catches a violation rather than passing vacuously.

## What is novel here — and what is not

**Not novel, said plainly.** Dunning and recovery agents as a category.
Uplift modelling as a technique. LLM-generated recovery messaging. Hinglish
voice bots. Butter Payments, Churnkey, Churn Buster, Recurly and Stripe
Revenue Recovery all exist and are good. The maturity of the category is
evidence the problem is real; it is not something to claim credit for.

**What is claimed, with honest build status:**

| | Claim | Status |
|---|---|---|
| **N1** | **Incremental-first accounting.** Recovery vendors overwhelmingly report *gross* recovered revenue. This reports incremental ₹ against a randomised no-contact holdout, with confidence intervals. The holdout here recovers 15.47% unaided — that is the number gross reporting quietly takes credit for. | ✅ Built, measured |
| **N2** | **Negative-uplift targeting ("do-not-disturbs").** Customers whose payment probability *falls* when contacted. Nobody in dunning models the downside of contact. | ⚠️ Modelled and measured, but the agent's do-not-disturb contact rate is 20.1% — level with untargeted policies, not better. Reported as the top open problem, not as a win. |
| **N3** | **A deterministic, machine-checkable India-regulatory compliance kernel** emitting a per-action certificate — TCCCPR/DLT, RBI recovery-agent norms, RBI e-mandate 2026, DPDPA. | ✅ Built: 12 rules, 100% red-team block rate, mutation-tested |
| **N4** | **Contact as a budget-constrained sequential decision problem**, not one-shot classification. | ⚠️ Partial: greedy EV under an explicit budget, plus a finite-horizon lookahead variant. Not a full constrained-MDP solver, and the spec explicitly permits the simplification — but it is a simplification, and the lookahead currently adds nothing measurable. |
| **N5** | **Two-tier validation** — causal machinery proven on real randomised public data *before* transfer to the simulator. Directly defeats "your synthetic number is circular". | ✅ Built (Criteo + Hillstrom) |
| **N6** | **Contact-free recovery** — detecting issuer degradation and suppressing retries into a dead issuer. | ❌ **Not built.** Listed here because it is in the design, not because it exists. |

Two of six are partial and one is not built at all. That is stated here
rather than left for a reader to discover.

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
      3.2's published benchmarks. Marginal calibration is loose rather than
      rigorous — flagged honestly in `experiments/tier2_simulation/REPORT.md`
      — but every invented constant is now injectable and swept (see the
      sensitivity sweep below).
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
- [x] **LLM reply-intent listener, validated (spec 8.5).** `make listener-eval`:
      **95.2% accuracy** on a hand-authored 42-example gold set (100% English,
      92% Hinglish, 92% Hindi), with promise-to-pay precision 0.88 / recall
      1.00 — the metric spec 11.2 asks for by name.
      **Opt-out is deliberately NOT left to the model.** Measured alone, the
      LLM recalled only 0.57 of opt-outs and every miss was Hindi/Hinglish;
      missing one is a TCCCPR violation, not a lost sale. A deterministic
      detector now runs first and overrides it, taking opt-out to
      **1.00 precision and 1.00 recall**. That is the same argument as the
      compliance kernel, applied one level down.
      The LLM-generated persona corpus scored only 42.9% — inspection showed
      the labels were wrong, not the classifier, so it is reported separately
      rather than used as ground truth.
- [ ] Negotiation + Section 43B(h) clock
- [ ] Fleet-level degradation detection

- [x] **B4 — browsable audit trail.** `make dashboard` renders the
      hash-chained ledger as a **self-contained HTML file** — no npm, no
      build step, no network; it opens by double-click. Browse cases, search
      and filter by outcome, open any case for its full decision trace with
      tabs for timeline / certificates / raw JSON, and see every kernel rule
      evaluated per action. UX architecture is modelled on
      [ThreeUI](https://github.com/MengTo/threeui) (app shell, browse grid,
      detail tabs, theming); its React/Vite/WebGL layer is deliberately not
      carried over — a build step would break the clean-clone property, and
      decorative 3D on a compliance tool would undercut the very thing this
      view exists to demonstrate. Verified in a real browser (Playwright):
      all views, search, drawer tabs and theme toggle work, zero JS errors.
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
make listener-eval     # reply-intent accuracy vs the gold set (needs Ollama)
make dashboard         # renders the audit trail to dashboard/index.html
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
