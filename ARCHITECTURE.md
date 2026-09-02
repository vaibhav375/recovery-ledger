# Architecture

## The loop

```
                    ┌──────────────────────────────────────┐
                    │  EVENT SOURCES  (events/schemas.py)  │
                    │  4 loss types, one discriminated     │
                    │  union — payment · checkout ·        │
                    │  subscription/mandate · receivable   │
                    └──────────────────┬───────────────────┘
                                       │  RecoveryCase
                    ┌──────────────────▼───────────────────┐
                    │  1. DETECTOR      detector/          │
                    │     is this case still at risk?      │
                    └──────────────────┬───────────────────┘
                    ┌──────────────────▼───────────────────┐
                    │  2. DIAGNOSER     diagnoser/         │
                    │     failure taxonomy, root cause     │
                    └──────────────────┬───────────────────┘
                                       │  Diagnosis
                    ┌──────────────────▼───────────────────┐
                    │  3. POLICY        policy/            │
                    │     uplift τ̂ → EV → action           │
                    │     uplift/  ope/  decision.py       │
                    └──────────────────┬───────────────────┘
                                       │  ActionDecision
        ╔══════════════════════════════▼═══════════════════╗
        ║  4. COMPLIANCE KERNEL     kernel/                ║
        ║     DETERMINISTIC · NO LLM · DENY BY DEFAULT     ║
        ║     13 rules → signed Certificate                ║
        ║     no certificate ⇒ no action, structurally     ║
        ╚══════════════════════════════┬═══════════════════╝
                                       │  Certificate (ALLOW)
                    ┌──────────────────▼───────────────────┐
                    │  5. EXECUTOR      executor/          │
                    │     simulated channel adapters       │
                    └──────────────────┬───────────────────┘
                    ┌──────────────────▼───────────────────┐
                    │  6. LISTENER      listener/          │
                    │     reply → structured intent        │
                    └──────────────────┬───────────────────┘
                                       │  ReplyIntent
                    ┌──────────────────▼───────────────────┐
                    │  7. LEDGER        ledger/            │
                    │     append-only, hash-chained        │
                    └──────────────────────────────────────┘

   agent/loop.py   orchestrates 1→7 for a single case
   agent/runner.py drives a batch, owns the clock, resumes paused cases
```

## Component contracts

Each unit below can be understood, replaced, and tested without reading the
internals of the others.

| Component | Input | Output | Depends on |
|---|---|---|---|
| `detector` | `RecoveryCase`, resolved flag | `bool` at-risk | — |
| `diagnoser` | `RecoveryCase` | `Diagnosis` | — |
| `policy` | `RecoveryCase`, `Diagnosis`, attempt index | `ActionDecision` | fitted uplift model |
| `kernel` | `RuleContext` | `Certificate` (ALLOW/DENY + per-rule results) | **nothing** — deliberately |
| `executor` | `Certificate` | `ActionResult` | — |
| `listener` | case, action, attempt | `ReplyIntent` | LLM (optional) |
| `ledger` | entry type + payload | hash-chained entry | — |
| `agent/loop` | `RecoveryCase` | `CaseOutcome` | all of the above |
| `agent/runner` | `list[RecoveryCase]` | `BatchResult` | `agent/loop` |

## The decisions that shape this design

### The compliance kernel is not an LLM, and that is enforced mechanically

`tests/test_kernel_no_llm_imports.py` fails the build if anything under
`kernel/` imports an LLM client. It has been mutation-tested — a temporary
`import anthropic` was confirmed to break it — so it is a real gate rather
than a vacuous pass.

The kernel depends on *nothing* in the table above. It is a pure predicate
over structured state: same input, same verdict, forever, auditable after
the fact. An agent that is 99% compliant is 100% undeployable in a regulated
business, and "the model usually gets it right" is not a defence anyone can
present to a regulator.

### Deny-by-default is structural, not a convention

`KernelEngine` returns DENY unless *every* registered rule passes, and zero
registered rules denies everything rather than allowing everything. The
executor only accepts a `Certificate`, so there is no code path that
executes an action without one. The red-team suite verifies this
end-to-end with a deliberately hostile policy: 323 maximum-pressure contacts
attempted, 0 executed without an ALLOW.

### A case can pause, not only terminate

`run_case` returns `CaseOutcome` — either terminated with a `StopReason`, or
paused with a `resume_at`. This exists because a promise to pay is a
*suspension*, not an ending (spec section 10, rule 6); treating it as
terminal abandoned cases at exactly the moment the customer signalled intent
to pay.

`agent/runner.py` therefore owns the clock: it runs the batch, collects
paused cases, advances simulated time to the earliest resumption, and
re-runs those due. Cases still paused at the horizon become the honest
exception list. The attempt budget carries across resumptions, so a customer
cannot be worked indefinitely by promising repeatedly.

### The policy says *why* it stopped

`ActionDecision.stop_reason` exists because the loop used to map every
policy STOP to `NEGATIVE_EV`, including the one meaning "budget exhausted".
That conflation hid budget exhaustion entirely from the audit trail.
Attribution belongs to whoever has the information.

### Simulator constants are injectable

Every invented constant lives in `ResponseParams`. Spec section 7.3 requires
showing the policy *ranking* is stable when those constants are swept — and
you cannot sweep a constant you cannot inject.

### Common random numbers

Each case draws from its own RNG stream seeded from `(seed, case_id)`, not a
shared stream consumed in call order. Otherwise the same case sees different
luck under different policies purely because a policy made a different
number of prior calls — pure noise in an experiment whose only purpose is
ranking policies against each other.

## Where the LLM is, and is not

The LLM boundary is a single `Protocol` in `llm/client.py`. Everything that
uses natural language goes through it; nothing else does. `kernel/` is
forbidden from importing it at all. See the table in `README.md` for the
per-use-case reasoning.

## Test strategy

128 tests. The ones that matter most are the ones that can *fail loudly*:

- `test_kernel_no_llm_imports` — mutation-tested
- `test_every_stopping_rule_is_reachable` — fails if any of the 11 stopping
  rules becomes unreachable; it caught a real gap within an hour of being
  written
- `test_uplift_model_correlates_with_true_persuadability` — fails if the
  model stops learning real signal, which is exactly the failure that
  silently invalidated an early headline number
- `tests/test_redteam.py` — 100% block rate enforced in CI, plus a guard
  that a legitimate action is not wrongly blocked (so the rate cannot be
  gamed by over-blocking)
- `test_no_legitimate_action_is_wrongly_blocked`, `test_paired_bootstrap_is_tighter_than_unpaired`

Determinism is verified by running each experiment twice and diffing.
